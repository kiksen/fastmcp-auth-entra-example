import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AuthCheck, AuthContext, require_scopes
from fastmcp.server.auth.providers.azure import AzureProvider

load_dotenv()

greet_group = "0bd07d11-7767-43f9-838f-5bc9fc12acd4"
required_scopes = os.environ["AZURE_REQUIRED_SCOPES"].split(",")

auth_provider = AzureProvider(
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"],
    tenant_id=os.environ["AZURE_TENANT_ID"],
    base_url=os.environ["AZURE_BASE_URL"],
    required_scopes=required_scopes,
    require_authorization_consent=False
)


mcp = FastMCP("fastmcp-auth-entra-example", auth=auth_provider)

if __name__ == "__main__":
    mcp.run()

def require_entra_group(group_id: str) -> AuthCheck:
    """
        require entra id groups_id to access tool
    """
    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return False
        else:
            groups = ctx.token.claims.get("groups")

            if groups is None:
                raise AuthorizationError(
                "'groups' claim missing from token – check Entra token configuration"
                )

            # "_claim_names": {
            #     "groups": "src1"
            # },
            claims = ctx.token.claims
            if "_claim_names" in claims and "groups" in claims["_claim_names"]:
                raise AuthorizationError(
                    "Group overage detected – groups claim not usable, Graph lookup required or reduce groups"
                )
        # return true if found else false            
        return (group_id in groups)
    
    return check


# No require_entra_groups. All users can access this tool!
@mcp.tool()
async def get_user_info() -> dict:
    """Returns information about the authenticated Azure user."""
    from fastmcp.server.dependencies import get_access_token
    
    token = get_access_token()

    # The AzureProvider stores user data in token claims
    return {
        "azure_id": token.claims.get("sub"),
        "email": token.claims.get("email"),
        "name": token.claims.get("name"),
        "job_title": token.claims.get("job_title"),
    }

@mcp.tool(auth=require_entra_group(greet_group))
async def say_hello() -> dict:
    """Greets the user, but only if you are a member of greet_group"""
    return { "message": "Hello! "
    }

@mcp.tool(auth=require_scopes(*required_scopes))
async def searching() -> dict:
    """Both example_read and example_write can search"""
    return { "message": "Hello searching user...."
    }

@mcp.tool(auth=require_scopes("example_write"))
async def write() -> dict:
    """Only writes can write"""
    return { "message": "Hello writer...."
    }

