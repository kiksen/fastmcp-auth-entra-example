# fastmcp-auth-entra-example

> See the official [FastMCP Azure (Microsoft Entra ID) OAuth
> documentation](https://gofastmcp.com/integrations/azure) for the full
> `AzureProvider` reference this example is based on.

A minimal [FastMCP](https://gofastmcp.com/) server example showing how to:

1. Authenticate MCP clients against **Microsoft Entra ID** (Azure AD) using OAuth 2.0.
2. Authorize individual MCP tools based on **Entra group membership** and/or
   **OAuth scopes**, not just a valid login.

It ships four tools that illustrate the difference: `get_user_info` (open to
any authenticated caller), `say_hello` (restricted to members of one Entra
group), and `searching` / `write` (restricted by OAuth scope, via
`require_scopes()`).

## How it works

The server wires `fastmcp`'s built-in `AzureProvider` in as the MCP auth backend
(`server.py`):

```python
required_scopes = os.environ["AZURE_REQUIRED_SCOPES"].split(",")

auth_provider = AzureProvider(
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"],
    tenant_id=os.environ["AZURE_TENANT_ID"],
    base_url=os.environ["AZURE_BASE_URL"],
    required_scopes=required_scopes,
    require_authorization_consent=False,
)
mcp = FastMCP("fastmcp-auth-entra-example", auth=auth_provider)
```

`AzureProvider` acts as a full OAuth **Authorization Code + PKCE** proxy in front
of Entra's `v2.0` endpoints. When a client connects:

1. The client is redirected to Entra to sign in and consent.
2. The provider exchanges the resulting code for an Entra access token.
3. That token is verified against Entra's JWKS endpoint (RS256 signature),
   with the issuer, audience, and `required_scopes` all checked.
4. A subset of the verified Entra claims (`sub`, `oid`, `tid`, `name`,
   `preferred_username`, `email`, `roles`, `groups`, ...) is copied into a new,
   FastMCP-issued JWT. Tools never see the raw Entra token — they read claims
   off this re-signed token via `ctx.token.claims` / `get_access_token()`.

`required_scopes` on `AzureProvider` is enforced at this token-exchange step,
**not per tool** — Azure's OAuth API requires at least one scope on every
authorization request, and FastMCP refuses to issue a token at all unless it
carries *every* scope listed here. In other words, it's a floor that applies
to the whole server: if a scope is missing, no tool is reachable, not just
the ones that ask for it. Scope names here are unprefixed (e.g. `"read"`);
FastMCP automatically prefixes them with `identifier_uri` (defaults to
`api://{client_id}`) both when requesting authorization and when validating
the token.

Per-tool authorization is layered on top of this authentication. `server.py`
defines a reusable check for group membership, and also uses FastMCP's
built-in `require_scopes()` for scope-based per-tool checks:

```python
def require_entra_group(group_id: str) -> AuthCheck:
    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return False
        groups = ctx.token.claims.get("groups")
        if groups is None:
            raise AuthorizationError("'groups' claim missing from token – check Entra token configuration")
        if "_claim_names" in ctx.token.claims and "groups" in ctx.token.claims["_claim_names"]:
            raise AuthorizationError("Group overage detected – groups claim not usable, Graph lookup required or reduce groups")
        return group_id in groups
    return check
```

This reads the `groups` claim straight off the already-verified token — no
extra Microsoft Graph call. It also correctly handles Entra's **group overage**
behavior: once a user belongs to more than ~200 groups, Entra replaces the
`groups` claim with a `_claim_names` indirection pointing at Graph instead of
listing groups directly. The check detects that case and raises instead of
silently treating the user as "not a member."

## Tools

| Tool | Authorization | Description |
|---|---|---|
| `get_user_info` | None — any authenticated caller | Returns the caller's own identity claims (`azure_id`, `email`, `name`, `job_title`) from the verified token. |
| `say_hello` | `require_entra_group(greet_group)` | Returns a greeting, only if the caller is a member of the Entra group configured as `greet_group` in `server.py`. |
| `searching` | `require_scopes(*required_scopes)` | Per-tool scope check mirroring the provider's own `required_scopes` list — see note below. |
| `write` | `require_scopes("example_write")` | Per-tool scope check for a single, narrower scope. |

> **Note on `job_title`:** it's typically `None` in the response of
> `get_user_info`. `AzureProvider`'s default claim extraction only copies a
> fixed set of standard claims onto the FastMCP token, and `job_title` isn't
> part of it — populating it would require custom claim configuration on the
> Entra app registration.
>
> **Note on `searching`/`write`:** because the `AzureProvider`'s own
> `required_scopes` is set to *all* of `AZURE_REQUIRED_SCOPES`
> (`example_read,example_write` by default), a token can't be issued at all
> unless it already carries both scopes. That means, in this exact
> configuration, both per-tool `require_scopes()` checks are trivially
> satisfied by any valid token — they don't actually narrow access further.
> They're included to show the mechanism. In a real deployment you'd
> typically set the provider's `required_scopes` to a small common baseline
> (or a single shared scope) and use per-tool `require_scopes()` to demand
> additional, more specific scopes on top of that baseline.

## Prerequisites: Entra app registration

You need an Entra ID (Azure AD) **app registration** with:

- A **client secret** created under *Certificates & secrets*.
- One or more **exposed API scopes** (under *Expose an API*) matching whatever
  you put in `AZURE_REQUIRED_SCOPES` (e.g. `readeverything`, `writenetbox`).
- A **redirect URI** registered that matches `AZURE_BASE_URL` (the FastMCP
  OAuth proxy appends its own callback path).
- **Group claims** enabled so tokens include a `groups` claim — configure this
  under *Token configuration* → *Add groups claim* on the app registration
  (or via the corresponding Enterprise Application settings), and assign users
  to the group(s) you want to gate tools with.
- Note the **group overage limit**: if a signing-in user belongs to more than
  ~200 groups, Entra will not include the group list directly in the token
  (see "How it works" above) — keep test users under that limit, or add a
  Graph-based lookup if you need to support overage in a real deployment.

## Configuration

Copy the example env file and fill in your app registration's values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `AZURE_CLIENT_ID` | Application (client) ID of the Entra app registration. |
| `AZURE_CLIENT_SECRET` | Client secret for the app registration. |
| `AZURE_TENANT_ID` | Directory (tenant) ID. |
| `AZURE_BASE_URL` | Public base URL of this MCP server (used to build the OAuth redirect URI), e.g. `http://localhost:8000` for local development. |
| `AZURE_REQUIRED_SCOPES` | Comma-separated list of API scopes the exchanged token must carry to authenticate **at all** — enforced by `AzureProvider` itself, before any tool is reachable (not a per-tool setting; see "How it works"). |

Also update `greet_group` in `server.py` to the object ID of an Entra group in
your tenant, so `say_hello` has a real group to check against.

## Running

Install dependencies and run the server with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run fastmcp run server.py --transport http --port 8000 --reload
```

The MCP server listens on `AZURE_BASE_URL` (default `http://localhost:8000`).

In a separate terminal, run the example client, which drives the OAuth login
in a browser and calls the tools:

```bash
uv run test_client.py
```

On first run it opens a browser window for Entra sign-in, then prints the
authenticated user's info from `get_user_info` and lists the available tools.

## Security considerations

This example is deliberately built to show **both** sides of MCP auth:
authentication (who is calling?) and authorization (are they allowed to call
*this*?). Keep the following in mind before adapting it:

- **`get_user_info` is authenticated but not authorized.** It cannot be
  reached without a token that already passed real signature (JWKS), issuer,
  audience, and scope validation, and it never returns raw tokens or secrets —
  only allow-listed identity claims. But it has **no group/role gate**: any
  user who can obtain a token for this app (i.e. anyone holding the required
  scopes) can call it, as the code comment above it states explicitly. That's
  intentional here, to contrast with `say_hello`'s gated access — don't copy
  `get_user_info`'s pattern for a tool that should be restricted; use
  `require_entra_group` (or a similar check) instead.
- **Provider-level `required_scopes` vs. per-tool `require_scopes()`.** The
  scopes passed to `AzureProvider(required_scopes=...)` gate authentication
  itself — a token can't be issued unless it carries all of them, so every
  tool implicitly requires them. `require_scopes()` on an individual tool
  only adds a *meaningful* restriction if it asks for scopes beyond that
  provider-level baseline; if the baseline already includes everything a
  tool's `require_scopes()` call checks for (as with `searching` and `write`
  in this example's default `.env.example`), the per-tool check never
  actually denies anyone.
- **`require_authorization_consent=False`** disables the local OAuth proxy's
  consent screen. This is meant for local development/testing only — remove
  it (or set it to `True`) for any shared/production deployment.
- **Never commit `.env`.** It holds real secrets; `.gitignore` already
  excludes it, and `.env.example` is the template to share instead. If a real
  `.env` was ever exposed (e.g. copied outside this repo, pasted somewhere),
  rotate the client secret in Entra.
- **Group checks trust the token's `groups` claim as-is.** That's fine as long
  as the token has been through `AzureProvider`'s JWKS/issuer/audience
  verification (which it has, by the time a tool call reaches `ctx.token`),
  but it means Entra-side group assignment changes only take effect the next
  time a user re-authenticates and gets a fresh token, not instantly.
