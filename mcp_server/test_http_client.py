import asyncio, os, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
TOKEN = os.environ.get("ID_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else None

async def main():
    async with streamablehttp_client(URL, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("TOOLS:", [t.name for t in (await session.list_tools()).tools])
            for name, args in [("get_total_spend", {}),
                               ("merchant_spend", {"merchants": ["Swiggy", "Zomato"]})]:
                r = await session.call_tool(name, args)
                print(f"{name} -> {r.content[0].text}")

asyncio.run(main())
