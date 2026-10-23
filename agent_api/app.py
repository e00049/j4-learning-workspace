import asyncio
import logging
import os
import random
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

log = logging.getLogger("agent-api")

PROJECT         = os.environ["GCP_PROJECT"]
LOCATION        = os.environ.get("GCP_LOCATION", "us-east4")
MODEL           = os.environ.get("MODEL", "gemini-2.5-flash")
MCP_URL         = os.environ.get("MCP_URL", "http://wallettracker-mcp:8080/mcp")
MAX_ROUNDS      = int(os.environ.get("MAX_ROUNDS", "5"))
THINKING_BUDGET = os.environ.get("THINKING_BUDGET")          # unset = model default
MAX_INFLIGHT    = int(os.environ.get("MAX_INFLIGHT", "8"))     # per pod; extra requests get 503
RETRY_ATTEMPTS  = int(os.environ.get("RETRY_ATTEMPTS", "4"))   # Gemini calls on 429/503
SYS = ("You are WalletTracker. Use the tools for every number. "
       "If the tools can't answer, say so.")

# ---- Metrics (low-cardinality labels only) ----
REQS     = Counter("agent_requests_total", "Requests to /ask", ["status"])
REQ_SEC  = Histogram("agent_request_seconds", "End-to-end /ask latency",
                     buckets=(0.5, 1, 2, 3, 5, 8, 13, 20, 30, 60))
LLM_SEC  = Histogram("agent_llm_seconds", "Gemini call latency", ["model"],
                     buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13, 20))
TOKENS   = Counter("agent_llm_tokens_total", "Gemini tokens", ["model", "type"])
TOOLS    = Counter("agent_tool_calls_total", "MCP tool calls", ["tool"])
ROUNDS   = Histogram("agent_rounds", "Model rounds per question", buckets=(1, 2, 3, 4, 5, 6))
INFLIGHT = Gauge("agent_inflight_requests", "In-flight /ask requests in this pod")
SHED     = Counter("agent_shed_total", "Requests rejected because the pod was full")
UPSTREAM = Counter("agent_upstream_errors_total", "Gemini API errors", ["code"])
RETRIES  = Counter("agent_llm_retries_total", "Gemini retries after 429/503")

client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
app = FastAPI(title="WalletTracker agent API")
SLOTS = asyncio.Semaphore(MAX_INFLIGHT)


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def record_usage(resp):
    u = resp.usage_metadata
    if not u:
        return
    for kind, val in (("input", u.prompt_token_count),
                      ("output", u.candidates_token_count),
                      ("thinking", u.thoughts_token_count)):
        if val:
            TOKENS.labels(model=MODEL, type=kind).inc(val)


async def generate(contents, cfg):
    """Call Gemini; retry 429/503 with exponential backoff + jitter."""
    delay = 1.0
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        t0 = time.perf_counter()
        try:
            resp = await client.aio.models.generate_content(model=MODEL, contents=contents, config=cfg)
            LLM_SEC.labels(model=MODEL).observe(time.perf_counter() - t0)
            record_usage(resp)
            return resp
        except genai_errors.APIError as e:
            UPSTREAM.labels(code=str(e.code)).inc()
            if e.code not in (429, 503) or attempt == RETRY_ATTEMPTS:
                raise
            RETRIES.inc()
            await asyncio.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, 8.0)


def to_http_error(exc):
    """Unwrap ExceptionGroups (from the MCP client's TaskGroup) and map to a clear status."""
    cause = exc
    while isinstance(cause, BaseExceptionGroup) and cause.exceptions:
        cause = cause.exceptions[0]
    log.warning("ask failed: %s: %s", type(cause).__name__, str(cause)[:200])
    if isinstance(cause, genai_errors.APIError):
        if cause.code == 429:
            return HTTPException(429, detail="model capacity busy, retry later",
                                 headers={"Retry-After": "5"})
        return HTTPException(502, detail=f"model error {cause.code}")
    if isinstance(cause, (httpx.HTTPError, ConnectionError, TimeoutError)):
        return HTTPException(502, detail=f"tool server error: {type(cause).__name__}")
    return HTTPException(500, detail=f"internal error: {type(cause).__name__}")


@app.middleware("http")
async def measure(request: Request, call_next):
    if request.url.path != "/ask":
        return await call_next(request)
    start, status = time.perf_counter(), 500
    try:
        if SLOTS.locked():
            SHED.inc()
            status = 503
            return JSONResponse({"error": "busy, retry shortly"}, status_code=503,
                                headers={"Retry-After": "2"})
        async with SLOTS:
            INFLIGHT.inc()
            try:
                response = await call_next(request)
            finally:
                INFLIGHT.dec()
        status = response.status_code
        return response
    finally:
        REQS.labels(status=str(status)).inc()
        REQ_SEC.observe(time.perf_counter() - start)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ask")
async def ask(body: Ask):
    used, rounds = [], 0
    try:
        async with streamablehttp_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                                   parameters_json_schema=t.inputSchema)
                         for t in tools]
                cfg = types.GenerateContentConfig(
                    system_instruction=SYS,
                    tools=[types.Tool(function_declarations=decls)],
                    temperature=0,
                    thinking_config=(types.ThinkingConfig(thinking_budget=int(THINKING_BUDGET))
                                     if THINKING_BUDGET else None))
                contents = [types.Content(role="user", parts=[types.Part(text=body.question)])]
                for _ in range(MAX_ROUNDS):
                    rounds += 1
                    resp = await generate(contents, cfg)
                    calls = resp.function_calls
                    if not calls:
                        return {"answer": resp.text, "tools": used}
                    contents.append(resp.candidates[0].content)
                    parts = []
                    for c in calls:
                        args = dict(c.args or {})
                        res = await session.call_tool(c.name, args)
                        TOOLS.labels(tool=c.name).inc()
                        used.append({"tool": c.name, "args": args})
                        parts.append(types.Part.from_function_response(
                            name=c.name, response={"result": res.content[0].text}))
                    contents.append(types.Content(role="user", parts=parts))
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        if rounds:
            ROUNDS.observe(rounds)
    raise HTTPException(status_code=508, detail={"error": "too many tool rounds", "tools": used})
