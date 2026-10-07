import asyncio
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

client = genai.Client(vertexai=True, project="nexusforge-ai-dev", location="us-east4")
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

async def ask(session, decls, question):
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    used = []
    for _ in range(MAX_ROUNDS):
        resp = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYS,
                tools=[types.Tool(function_declarations=decls)],
                temperature=0,
            ),
        )
        calls = resp.function_calls
        if not calls:                                   # model is done
            return used, resp.text
        contents.append(resp.candidates[0].content)     # keep the model's request
        results = []
        for c in calls:                                 # run each requested tool via MCP
            args = dict(c.args or {})
            r = await session.call_tool(c.name, args)
            used.append(f"{c.name}({args})")
            results.append(types.Part.from_function_response(
                name=c.name, response={"result": r.content[0].text}))
        contents.append(types.Content(role="user", parts=results))
    return used, "Stopped: too many tool rounds"

async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                               parameters_json_schema=t.inputSchema)
                     for t in tools]
            for q in QUESTIONS:
                used, answer = await ask(session, decls, q)
                print(f"\nQ: {q}\n  tools: {used or 'none'}\n  A: {answer}")

asyncio.run(main())

