import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=".venv/bin/python",
                                   args=["mcp_server/wallettracker_mcp.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:")
            for t in tools.tools:
                print(f"  {t.name}: {t.description}")
            print("RESULTS:")
            for name, args in [("get_total_spend", {}),
                               ("merchant_spend", {"merchants": ["Swiggy", "Zomato"]}),
                               ("spend_by_category", {"exclude": ["Rent", "Investment"]})]:
                res = await session.call_tool(name, args)
                print(f"  {name} -> {res.content[0].text}")

asyncio.run(main())
