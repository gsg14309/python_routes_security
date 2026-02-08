# MSAL utility (Entra ID token validation)

Standalone utility to validate Azure Entra ID (Microsoft identity) **access tokens** and extract claims. Used by the backend to authenticate and authorize API requests after the front end sends `Authorization: Bearer <access_token>`.

This package has **no dependency on other app packages** (e.g. `app.security`, `app.db`). It only depends on PyJWT, requests, and the standard library.

---

## Key concepts for newcomers to Azure Entra ID

If you're new to Azure identity, here's a plain-English summary of the terms and ideas used in this package.

### What is Azure Entra ID?

Azure Entra ID (formerly Azure Active Directory / Azure AD) is Microsoft's cloud identity service. When a user signs in to your web app via "Sign in with Microsoft", Entra ID is the system that checks their credentials and issues **tokens** proving who they are.

### What is a JWT?

A **JWT** (JSON Web Token, pronounced "jot") is a compact string like `eyJhbGciOi...` that contains three base64-encoded parts separated by dots:

```
HEADER.PAYLOAD.SIGNATURE
```

- **Header**: Metadata — which algorithm was used to sign, and the `kid` (Key ID) identifying which key signed it.
- **Payload**: The claims — user info, permissions, expiry, etc. (see "Claims" below).
- **Signature**: A cryptographic hash that proves the token was issued by Entra ID and hasn't been tampered with.

### Access token vs. ID token — which one does the API use?

Entra ID issues **two** tokens during login:

| Token | Who it's for | Purpose |
|-------|-------------|---------|
| **ID token** | The **front end** (browser) | "Who is the user?" — display name, email, etc. |
| **Access token** | The **API** (backend) | "Is this user allowed to call me?" — scopes, roles, etc. |

**This API uses the access token only.** The front end sends it as `Authorization: Bearer <access_token>`. We never use the ID token for backend authorization.

### What are claims?

Claims are key-value pairs inside the JWT payload. Important ones for this API:

| Claim | Meaning | Example value |
|-------|---------|---------------|
| `iss` | **Issuer** — who created the token | `https://login.microsoftonline.com/{tenant}/v2.0` |
| `aud` | **Audience** — who the token is *for* | Your API's app registration ID |
| `exp` | **Expiration** — Unix timestamp when token expires | `1706140800` |
| `nbf` | **Not Before** — token is not valid before this time | `1706137200` |
| `oid` | **Object ID** — immutable, tenant-wide user ID | `a1b2c3d4-...` |
| `sub` | **Subject** — pairwise user ID (different per app) | `e5f6g7h8-...` |
| `roles` | **App Roles** assigned to the user | `["Admin", "Reader"]` |
| `scp` | **Scopes** — delegated permissions the client was granted | `"User.Read Files.Read"` |
| `preferred_username` | Display name / email (for UI only) | `user@contoso.com` |

> **oid vs. sub**: For Azure Entra tokens, `oid` is the stable user ID (same across all apps in the tenant). `sub` is pairwise (different value for each app registration). This utility uses **`oid`** as the canonical `user_id` because it's consistent and is what Microsoft Graph expects.

### What is JWKS?

**JWKS** (JSON Web Key Set) is a public endpoint where Entra publishes the **public keys** used to sign tokens. URL pattern:

```
https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
```

We fetch these keys and use them to verify the token's signature (step 1 of validation). Keys are **cached** with a TTL so we don't call Entra on every request.

**Key rotation**: Azure periodically retires old keys and publishes new ones. If a token arrives signed with a key we haven't seen, the cache automatically refreshes once before rejecting.

### What are App Roles?

App Roles are custom roles you define in your API's **app registration** in the Azure portal (e.g. "Admin", "Reader", "HRManager"). You then assign users or groups to those roles. When a user gets a token for your API, the `roles` claim lists which roles they have.

### What if roles aren't in the token?

Sometimes the `roles` claim is empty or missing — for example, if you use Azure **security groups** instead of App Roles, or if the user is in so many groups that Azure can't fit them in the token ("groups overage"). In that case, this utility can call the **Microsoft Graph API** to ask "what groups is this user in?" and use those group names as roles. This is called the **Graph fallback** (see section below).

### What is Microsoft Graph?

Microsoft Graph (`https://graph.microsoft.com`) is Microsoft's REST API for reading data from Azure AD — users, groups, org structure, etc. This utility only uses it when it needs to resolve roles that aren't in the token.

---

## What token does the client send?

**Access token.** The front end must obtain an access token issued **for your API** (audience = your API's app ID) and send it in `Authorization: Bearer <access_token>`. The ID token is for the client to identify the user and must **not** be used for backend API authorization.

---

## Usage

```python
from app.msal_util import validate_and_extract, ValidationError, TokenContext

# Token comes from the request header: Authorization: Bearer <token>
bearer_token = "eyJ0eXAiOiJKV1QiLCJhbGc..."

try:
    ctx: TokenContext = validate_and_extract(bearer_token)
    # ctx.user_id  — the oid (stable user ID)
    # ctx.roles    — e.g. ("Admin",)
    # ctx.scopes   — e.g. ("User.Read",)
    # ctx.department — from token or None
except ValidationError as e:
    # Invalid or expired token; do not log the token itself
    return 401
```

With explicit config (e.g. for tests):

```python
from app.msal_util import EntraTokenValidator
from app.msal_util.config import EntraConfig

config = EntraConfig(tenant_id="...", client_id="...", ...)
validator = EntraTokenValidator(config=config)
ctx = validator.validate_and_extract(token)
```

---

## Environment variables

All Azure/Entra configuration must come from the environment (e.g. `.env`). No secrets in code.

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | Yes | Your Azure tenant (directory) ID. Found in Azure portal > Entra ID > Overview. |
| `AZURE_CLIENT_ID` | Yes | The application (client) ID of your **API's** app registration. Also the default audience. |
| `AZURE_AUDIENCE` | No | If set, used as expected `aud` instead of client id. Use when audience is a URI like `api://my-app`. |
| `CLOCK_SKEW_SECONDS` | No | Tolerance for `exp`/`nbf` validation (default: 120 seconds). |
| `JWKS_CACHE_TTL_SECONDS` | No | How long to cache JWKS keys (default: 3600 = 1 hour). |
| `MSAL_GRAPH_ENABLED` | No | Set to `1` or `true` to resolve roles via Microsoft Graph when the `roles` claim is missing. |
| `AZURE_CLIENT_SECRET` | For Graph | Required if Graph fallback is enabled. The client secret from your app registration's "Certificates & secrets" page. |

### Where to find these values in Azure portal

1. **Tenant ID and Client ID**: Go to *Azure portal > Microsoft Entra ID > App registrations > your API app > Overview*.
2. **Audience**: Usually the same as Client ID. If you configured an Application ID URI (e.g. `api://my-app`), use that.
3. **Client Secret**: *App registrations > your API app > Certificates & secrets > New client secret*.

---

## How validation works (step by step)

When `validate_and_extract(token)` is called, the following happens in order:

```
token string
    │
    ▼
1. Read JWT header (unverified) → extract "kid" (Key ID)
    │
    ▼
2. Look up kid in JWKS cache → get the public key
   (if not found: refresh cache once for key rotation, then look up again)
    │
    ▼
3. Verify SIGNATURE with the public key (proves token came from Entra)
    │
    ▼
4. Verify ISSUER (iss) matches https://login.microsoftonline.com/{tenant}/v2.0
    │
    ▼
5. Verify AUDIENCE (aud) matches your API's app registration
    │
    ▼
6. Verify LIFETIME: token not expired (exp) and not used too early (nbf)
    │
    ▼
7. Extract claims → build TokenContext
    │
    ▼
8. (Optional) If no roles in token and Graph enabled → call Graph API
    │
    ▼
Return TokenContext(user_id, roles, department, scopes, preferred_username)
```

If **any** step fails, `ValidationError` is raised. The token itself is never logged.

---

## Claims extracted

| Source | Claim | Maps to | Notes |
|--------|-------|---------|-------|
| Token | `oid` | `TokenContext.user_id` | Preferred. Immutable, tenant-wide. Used for Graph calls. |
| Token | `sub` | `TokenContext.user_id` (fallback) | Only used if `oid` is absent (non-Azure issuers). Pairwise per app. |
| Token | `roles` | `TokenContext.roles` | App Roles from app registration. If missing, see Graph fallback. |
| Token | `scp` | `TokenContext.scopes` | Delegated scopes, space-separated string. |
| Token | `department` | `TokenContext.department` | Not present by default. Must be added as an optional claim in Azure. |
| Token | `preferred_username` | `TokenContext.preferred_username` | For display only; do not use for authorization. |

---

## Microsoft Graph fallback (roles)

### When is it used?

When **all** of these are true:
- The token's `roles` claim is empty or missing
- `MSAL_GRAPH_ENABLED` is set to `true`
- `AZURE_CLIENT_SECRET` is configured

### What happens?

1. The utility obtains an **app-only** token using client credentials (`client_id` + `client_secret` + `grant_type=client_credentials`).
2. It calls `GET https://graph.microsoft.com/v1.0/users/{oid}/memberOf` to get the user's group and directory role memberships.
3. It collects the `displayName` from entries whose `@odata.type` is `#microsoft.graph.group` or `#microsoft.graph.directoryRole`. Other types (e.g. administrative units) are skipped.
4. Paginated responses (`@odata.nextLink`) are followed so all groups are collected.
5. The Graph token is cached in memory (valid ~1 hour) to avoid requesting a new one on every call.

### Required Azure permissions

Your app registration needs an **application** permission (not delegated) for Graph:
- `User.Read.All` or `GroupMember.Read.All` (or `Directory.Read.All`)
- Grant admin consent in Azure portal > App registrations > API permissions > Grant admin consent.

### Error handling

On Graph or network errors, the utility logs a warning and returns no extra roles. It **does not** fail the request — you'll just see an empty roles list and can decide how to handle that in your API logic.

---

## Output: `TokenContext`

Small, frozen (immutable) dataclass for the rest of the app:

```python
@dataclass(frozen=True)
class TokenContext:
    user_id: str              # oid (stable, tenant-wide)
    roles: tuple[str, ...]    # e.g. ("Admin", "Reader")
    department: str | None    # from token or None
    scopes: tuple[str, ...]   # e.g. ("User.Read",)
    preferred_username: str | None  # display only
```

Use `ctx.to_dict()` for a JSON-serializable dictionary.

---

## Security and operations

- **HTTPS**: In production, serve the API over HTTPS only. Bearer tokens sent over plain HTTP can be intercepted.
- **Logging**: Never log the raw token or sensitive claims. Log only non-PII (validation failure reason, request path).
- **JWKS caching**: Keys are cached in memory with a configurable TTL (default 1 hour). On cache miss, a single refresh is attempted to handle key rotation.
- **Graph token caching**: The app-only Graph token is cached in memory until near expiry to avoid a token request on every Graph call.
- **No secrets in code**: All secrets (client secret, tenant id, client id) come from environment variables.

---

## Azure setup checklist (high level)

For this utility to work in production, you need the following in Azure portal:

1. **App registration for your API** — this gives you the `AZURE_CLIENT_ID` and `AZURE_TENANT_ID`.
2. **Expose an API** — set an Application ID URI (becomes the audience, e.g. `api://my-app`). Add scopes your front end will request.
3. **(Optional) App Roles** — define roles like "Admin", "Reader" under *App roles*. Assign users/groups to them. These appear in the token's `roles` claim.
4. **(Optional) Client secret** — create under *Certificates & secrets* if you need Graph fallback.
5. **(Optional) API permissions for Graph** — add `User.Read.All` (application type) and grant admin consent if Graph fallback is enabled.
6. **Front-end app registration** — the SPA that calls your API. Configure it to request tokens for your API's scope (e.g. `api://my-app/.default`).

---

## Tests

From the project root:

```bash
pytest tests/test_msal_util/ -v
```

Tests cover:
- Config loading from environment
- Claim extraction (`oid` preference, scopes parsing, department handling)
- Full validation roundtrip (mocked JWKS with real RSA key pair)
- Invalid / expired / missing-kid tokens
- Graph fallback (mocked): success, odata.type filtering, pagination, error handling

---

## References

- [MSAL_REQUIREMENTS.md](../../MSAL_REQUIREMENTS.md) — Full requirements for this utility.
- [PRODUCTION.md](../../PRODUCTION.md) — SSO flow and API security for this project.
- [Microsoft identity platform access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens) — Token structure, claims, and validation.
- [Configure optional claims](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims) — How to add claims like `department` to tokens.
- [App roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps) — How to define and assign App Roles.
- [Microsoft Graph memberOf API](https://learn.microsoft.com/en-us/graph/api/user-list-memberof) — The endpoint used for Graph role fallback.
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference) — For Graph fallback permission setup.
