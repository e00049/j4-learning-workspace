import asyncio, sys, httpx, boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL, REGION = sys.argv[1], "us-east-1"
creds = boto3.Session().get_credentials().get_frozen_credentials()

class SigV4(httpx.Auth):
    """Signs every request with your AWS credentials (service = lambda)."""
    requires_request_body = True
    def auth_flow(self, request):
        aws_req = AWSRequest(method=request.method, url=str(request.url), data=request.content)
        SigV4Auth(creds, "lambda", REGION).add_auth(aws_req)
        for k, v in aws_req.headers.items():
            request.headers[k] = v
        yield request

async def main():
    async with streamablehttp_client(URL, auth=SigV4()) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("TOOLS:", [t.name for t in (await session.list_tools()).tools])
            for name, args in [("get_total_spend", {}),
                               ("merchant_spend", {"merchants": ["Swiggy", "Zomato"]})]:
                r = await session.call_tool(name, args)
                print(f"{name} -> {r.content[0].text}")

asyncio.run(main())
