import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PROJECT    = os.environ["GCP_PROJECT"]
LOCATION   = os.environ.get("GCP_LOCATION", "us-east4")
MODEL      = os.environ.get("MODEL", "gemini-2.5-flash")
MCP_URL    = os.environ.get("MCP_URL", "http://wallettracker-mcp:8080/mcp")
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", "5"))
SYS = ("You are WalletTracker. Use the tools for every number. "
       "If the tools can't answer, say so.")

# Credentials come from Workload Identity via the GKE metadata server: no keys.
client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
app = FastAPI(title="WalletTracker agent API")


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/ask")
async def ask(body: Ask):
    used = []
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                               parameters_json_schema=t.inputSchema)
                     for t in tools]
            cfg = types.GenerateContentConfig(system_instruction=SYS,
                                              tools=[types.Tool(function_declarations=decls)],
                                              temperature=0)
            contents = [types.Content(role="user", parts=[types.Part(text=body.question)])]
            for _ in range(MAX_ROUNDS):
                resp = await client.aio.models.generate_content(model=MODEL, contents=contents, config=cfg)
                calls = resp.function_calls
                if not calls:
                    return {"answer": resp.text, "tools": used}
                contents.append(resp.candidates[0].content)
                parts = []
                for c in calls:
                    args = dict(c.args or {})
                    res = await session.call_tool(c.name, args)
                    used.append({"tool": c.name, "args": args})
                    parts.append(types.Part.from_function_response(
                        name=c.name, response={"result": res.content[0].text}))
                contents.append(types.Content(role="user", parts=parts))
    raise HTTPException(status_code=508, detail={"error": "too many tool rounds", "tools": used})
