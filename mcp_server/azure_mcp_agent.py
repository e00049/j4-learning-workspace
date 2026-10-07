import asyncio, json
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ENDPOINT = "https://aif-j4-ai-learning-sid.cognitiveservices.azure.com/"
DEPLOYMENT = "gpt-4.1-mini"
token = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
client = AzureOpenAI(azure_endpoint=ENDPOINT, azure_ad_token_provider=token, api_version="2024-10-21")

server = StdioServerParameters(command=".venv/bin/python", args=["mcp_server/wallettracker_mcp.py"])
SYS = "You are WalletTracker. Use the tools for every number. If the tools can't answer, say so."
MAX_ROUNDS = 5

QUESTIONS = [
    "What is my total spend this month?",
    "How much did I spend on Swiggy and Zomato combined?",
    "Which category is highest, excluding Rent and Investment?",
    "If I cut my Swiggy and Zomato spend by 30%, how much do I save?",
    "What is my credit score?",
]

async def ask(session, tools, question):
    messages = [{"role": "system", "content": SYS}, {"role": "user", "content": question}]
    used, tokens = [], 0
    for _ in range(MAX_ROUNDS):
        resp = client.chat.completions.create(model=DEPLOYMENT, messages=messages,
                                              tools=tools, temperature=0)
        tokens += resp.usage.total_tokens
        msg = resp.choices[0].message
        if not msg.tool_calls:                              # model is done
            return used, msg.content, tokens
        messages.append(msg)                                # keep the model's request
        for tc in msg.tool_calls:                           # run each tool via MCP
            args = json.loads(tc.function.arguments or "{}")
            r = await session.call_tool(tc.function.name, args)
            if r.isError:
                print(f"  ⚠️ tool error from {tc.function.name}: {r.content[0].text}")
            used.append(f"{tc.function.name}({args})")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": r.content[0].text})
    return used, "Stopped: too many tool rounds", tokens

async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = [{"type": "function",
                      "function": {"name": t.name, "description": t.description,
                                   "parameters": t.inputSchema}} for t in mcp_tools]
            for q in QUESTIONS:
                used, answer, tokens = await ask(session, tools, q)
                print(f"\nQ: {q}\n  tools: {used or 'none'}  tokens: {tokens}\n  A: {answer}")

asyncio.run(main())

