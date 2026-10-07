import asyncio, boto3
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "us.amazon.nova-lite-v1:0"
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
server = StdioServerParameters(command=".venv/bin/python", args=["mcp_server/wallettracker_mcp.py"])
SYS = [{"text": "You are WalletTracker. Use the tools for every number. If the tools can't answer, say so."}]
MAX_ROUNDS = 5

QUESTIONS = [
    "What is my total spend this month?",
    "How much did I spend on Swiggy and Zomato combined?",
    "Which category is highest, excluding Rent and Investment?",
    "If I cut my Swiggy and Zomato spend by 30%, how much do I save?",
    "What is my credit score?",
]

async def ask(session, tool_config, question):
    messages = [{"role": "user", "content": [{"text": question}]}]
    used, tokens = [], 0
    for _ in range(MAX_ROUNDS):
        resp = bedrock.converse(modelId=MODEL, system=SYS, messages=messages,
                                toolConfig=tool_config, inferenceConfig={"temperature": 0})
        tokens += resp["usage"]["totalTokens"]
        msg = resp["output"]["message"]
        messages.append(msg)
        if resp["stopReason"] != "tool_use":                       # model is done
            text = " ".join(b["text"] for b in msg["content"] if "text" in b)
            return used, text, tokens
        results = []
        for block in msg["content"]:
            if "toolUse" in block:
                tu = block["toolUse"]
                r = await session.call_tool(tu["name"], tu["input"])
                used.append(f"{tu['name']}({tu['input']})")
                results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                               "content": [{"text": r.content[0].text}]}})
        messages.append({"role": "user", "content": results})
    return used, "Stopped: too many tool rounds", tokens

async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            tool_config = {"tools": [{"toolSpec": {"name": t.name, "description": t.description,
                                                   "inputSchema": {"json": t.inputSchema}}}
                                     for t in tools]}
            for q in QUESTIONS:
                used, answer, tokens = await ask(session, tool_config, q)
                print(f"\nQ: {q}\n  tools: {used or 'none'}  tokens: {tokens}\n  A: {answer}")

asyncio.run(main())

