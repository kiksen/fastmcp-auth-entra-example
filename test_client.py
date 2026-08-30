import asyncio

from fastmcp import Client


async def main():

    # The client will automatically handle Azure OAuth
    async with Client("http://localhost:8000/mcp", auth="oauth") as client:
        # First-time connection will open Azure login in your browser
        print("✓ Authenticated with Azure!")
        
        # Test the protected tool
        result = await client.call_tool("get_user_info")
        user_info = result.data
        print(f"Azure user: {user_info['email']}")
        print(f"Name: {user_info['name']}")

        tools = await client.list_tools()

        print(f"Based on your permissionyou have {len(tools)}")
        for t in tools:
            print("->", t.name)
        


if __name__ == "__main__":
    asyncio.run(main())