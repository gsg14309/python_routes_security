# msal_util — coding and maintenance guide

This document describes the **code layout**, **main entry points**, and **design choices** of the `msal_util` package. It is aimed at maintainers and at developers with a **Java background** who need to understand or extend the code.

---

## 1. Why are there two `validate_and_extract`?

In `validator.py` you will see:

1. **Instance method** (on the class):
   ```python
   class EntraTokenValidator:
       def validate_and_extract(self, token: str) -> TokenContext:
           ...
   ```

2. **Module-level function** (standalone):
   ```python
   def validate_and_extract(token: str, config: EntraConfig | None = None) -> TokenContext:
       validator = EntraTokenValidator(config=config)
       return validator.validate_and_extract(token)
   ```

**Reason:**

- The **instance method** is the real implementation. It uses `self._config` and `self._jwks` (the JWKS cache). Use it when you already have an `EntraTokenValidator` and want to reuse it (e.g. one validator instance serving many requests, so the JWKS cache is shared).

- The **module-level function** is a **convenience API**. It constructs a validator (loading config from the environment if you don’t pass `config`), calls the instance method once, and returns. Use it when you want a single call without managing a validator lifecycle — e.g. in a FastAPI dependency that runs per request.

So: one is the implementation (stateful, reusable); the other is a thin wrapper for the common “validate this token with env-based config” case. There is no duplicate logic — the function delegates to the method.

---

## 2. Package layout

```
app/msal_util/
├── __init__.py      # Public API: re-exports TokenContext, EntraConfig, EntraTokenValidator,
│                    #             ValidationError, validate_and_extract
├── config.py        # EntraConfig: configuration from environment variables
├── context.py       # TokenContext: output DTO after validation
├── jwks_cache.py    # JWKSCache: fetch and cache Entra’s signing keys (JWKS)
├── validator.py     # EntraTokenValidator + validate_and_extract; _extract_claims
├── graph_client.py  # Optional: resolve roles via Microsoft Graph when not in token
├── README.md        # User-facing docs: usage, env vars, concepts
└── CODING.md       # This file: code layout and maintainer guidance
```

**Dependency rule:** This package does **not** import from other app packages (`app.security`, `app.db`, etc.). It only uses the standard library, `jwt` (PyJWT), and `requests`.

---

## 3. Main entry points and data flow

### Public API (what callers use)

| Symbol | Where | Purpose |
|--------|--------|--------|
| `validate_and_extract(token, config=None)` | `validator.py`, re-exported in `__init__.py` | Validate bearer token and return `TokenContext`. Easiest entry point. |
| `EntraTokenValidator(config=None)` | `validator.py`, re-exported in `__init__.py` | Stateful validator; use when you want to reuse one instance (and its JWKS cache). |
| `TokenContext` | `context.py` | Immutable result: `user_id`, `roles`, `department`, `scopes`, `preferred_username`. |
| `EntraConfig` | `config.py` | Configuration (tenant, client id, audience, TTLs, Graph flag). |
| `ValidationError` | `validator.py` | Exception raised when validation fails (do not log the token). |

### Data flow (high level)

```
Bearer token string
       │
       ▼
EntraTokenValidator.validate_and_extract(token)
       │
       ├─► _get_kid(token)                    # Read key id from header (no crypto yet)
       ├─► JWKSCache.get_signing_key(kid)     # Get public key; refresh cache if kid unknown
       ├─► jwt.decode(token, key, ...)        # Verify signature, iss, aud, exp, nbf
       ├─► _extract_claims(payload)          # Build TokenContext from payload
       └─► [optional] resolve_roles_via_graph(oid) if no roles and graph_enabled
       │
       ▼
TokenContext
```

---

## 4. Access token: per-user vs application-level

The access token that the **front end sends to your API** (and that this package validates) is **per user**, not per application.

### Per-user (delegated) access token

- **When it’s issued**: When a **specific user** signs in (e.g. via the browser with “Sign in with Microsoft”). Each sign-in produces a token for that user.
- **What it contains**: The token’s claims describe **that user**:
  - **Identity**: `oid`, `sub`, `preferred_username` are that user’s values.
  - **Roles**: The `roles` claim lists the **App Roles assigned to that user** (or to groups they belong to). User A might have `["Admin"]`, User B might have `["Reader"]` — each token reflects that user’s assignments.
  - **Scopes**: The `scp` claim lists the delegated scopes **that user** (or an admin) has consented to for your API.
- **So**: Every request carries the token of the user who is calling. Validation gives you that user’s identity and their own roles/scopes. Permissions are therefore **on a per-user basis** in the token.

### Application-level (app-only) token

- **When it’s used**: When the **application** acts without a user — e.g. a background job or a server-to-server call. In this package, that happens only in **graph_client**: we use a **client credentials** (app-only) token to call Microsoft Graph to resolve a user’s group membership when roles aren’t in the token.
- **Not used for API auth**: The token the browser sends in `Authorization: Bearer ...` is never app-only; it is always the **user’s** (delegated) access token. This package validates that user token and, if needed, uses an app-only token only to call Graph, not to identify the caller.

### How this is configured in Azure

**App Roles (per-user roles in the token):**

1. **Define roles**: In **Azure portal → Microsoft Entra ID → App registrations → your API app → App roles**, create roles (e.g. “Admin”, “Reader”, “HRManager”).
2. **Assign to users or groups**: In **Enterprise applications → your API app → Users and groups** (or via **App registrations → your API app → Enterprise application** link), **assign** users or groups to those app roles. Each user (or member of an assigned group) will see the corresponding role(s) in their access token’s `roles` claim when they get a token for your API.
3. **Result**: User A assigned “Admin” gets a token with `roles: ["Admin"]`; User B assigned “Reader” gets `roles: ["Reader"]`. Same app, different tokens per user.

**Scopes (delegated permissions, per user):**

- In the API’s app registration, **Expose an API** defines scopes (e.g. `User.Read`). When users sign in, they (or an admin) consent to those scopes. The token’s `scp` then contains the scopes that **that user** has for your API.

**Summary for this package:**

| Token type        | Who it represents | Where used in this package                          |
|-------------------|-------------------|-----------------------------------------------------|
| Delegated (user)  | The signed-in user| The token we validate; `TokenContext` is per user. |
| App-only          | The application   | Only inside `graph_client` to call Graph.           |

So: **the access token we validate is always per user**; roles and permissions in it are that user’s. Azure configures that by defining App Roles (and optionally groups) and assigning users/groups to those roles in the portal.

---

## 5. Module-by-module summary

### `config.py`

- **EntraConfig**: Immutable configuration (dataclass). All Azure/Entra settings (tenant id, client id, audience, clock skew, JWKS TTL, Graph enabled, client secret).
- **EntraConfig.from_environ()**: Build config from environment variables; raises `ValueError` if `AZURE_TENANT_ID` or `AZURE_CLIENT_ID` are missing.
- **Properties**: `expected_audience`, `issuer`, `jwks_uri` — derived from tenant/client id for validation and JWKS URL.

No other modules depend on app-specific code; config is env-only.

### `context.py`

- **TokenContext**: Frozen dataclass (immutable). Fields: `user_id`, `roles`, `department`, `scopes`, `preferred_username`.
- **to_dict()**: Returns a JSON-serializable dict for logging or serialization.

This is the **output type** of validation. The rest of the app (e.g. FastAPI) uses this to attach identity and roles to the request.

### `jwks_cache.py`

- **JWKSCache(jwks_uri, ttl_seconds)**: In-memory cache of the JSON Web Key Set.
- **get_signing_key(kid)**: Returns a `PyJWK` for the given key id. If `kid` is not in the cached set, the cache is **refreshed once** (to handle Azure key rotation) and the lookup is retried.
- **Internal**: `_fetch()`, `_refresh()`, `_ensure_fresh()`, `_find_key()`. Uses `requests.get` to hit the Entra discovery URL.

Important for correctness: Azure rotates signing keys; the “refresh on cache miss” avoids rejecting valid new tokens until the next TTL expiry.

### `validator.py`

- **ValidationError**: Exception type; do not log the token when catching it.
- **_get_kid(token)**: Reads JWT header without verification; returns `kid` or None. Used to select the right key from the JWKS.
- **_extract_claims(payload)**: Maps validated JWT payload to `TokenContext` (oid/sub → user_id, roles, scp → scopes, department, preferred_username). Prefers `oid` over `sub` for Azure.
- **EntraTokenValidator**: Holds config and a `JWKSCache`. `validate_and_extract(self, token)` does signature/lifetime/issuer/audience checks, then claim extraction, then optional Graph role resolution.
- **validate_and_extract(token, config=None)**: Convenience function; creates a validator and calls its `validate_and_extract`.

All validation logic lives here; `graph_client` and `jwks_cache` are used as helpers.

### `graph_client.py`

- **resolve_roles_via_graph(user_oid, config)**: If `config.client_secret` and `user_oid` are set, gets an app-only token (cached), calls `GET /users/{oid}/memberOf`, and returns a list of group/directory-role display names. Filters by `@odata.type` (group, directoryRole); follows `@odata.nextLink` for pagination.
- **_request_app_token(config)**: Client-credentials token for `https://graph.microsoft.com/.default`.
- **_AppTokenCache**: Module-level cache for the Graph token so we don’t request a new one on every call.

Only used when `config.graph_enabled` is True and the token has no `roles` claim.

### `__init__.py`

Re-exports the public API so callers can do:

```python
from app.msal_util import validate_and_extract, ValidationError, TokenContext, EntraConfig, EntraTokenValidator
```

---

## 6. For developers with a Java background

### Package and modules

- **Python package** = directory with `__init__.py` → analogous to a Java package. `app.msal_util` is the package name.
- **Module** = one `.py` file → like a Java class file or a small set of related classes. Import with `from app.msal_util import validator` or `from app.msal_util.validator import EntraTokenValidator`.

### Types and nullability

- **Type hints** (e.g. `token: str`, `config: EntraConfig | None`) are like Java types; they don’t change runtime behavior but help IDEs and tools.
- **None** = Java `null`. So `config: EntraConfig | None` means “config or null”.
- **Optional[X]** is equivalent to `X | None` (or `Union[X, None]` in older style).

### Classes and instances

- **dataclass** (e.g. `EntraConfig`, `TokenContext`): A class used mainly to hold data; the decorator generates `__init__`, and often `__eq__`. Similar to a Java record or a POJO with a constructor and getters. `TokenContext` is also `frozen=True` (immutable).
- **No “private” keyword**: A leading underscore means “internal to the package” (e.g. `_get_kid`, `_extract_claims`, `self._jwks`). It’s convention, not enforced.
- **No “new”**: You construct with `EntraTokenValidator(config=cfg)` or `TokenContext(user_id="x", roles=(), ...)`.

### Exceptions

- **ValidationError** is a custom exception (subclass of `Exception`). Raise with `raise ValidationError("message")`. Catch with `except ValidationError as e:`.

### Testing

- Tests live **outside** the package, under `tests/test_msal_util/`, in files like `test_validator.py`, `test_config.py`. This mirrors the common Java pattern of `src/` vs `test/`.
- **pytest** is used: test functions named `test_*` are discovered and run. No need for a test class unless you want one.
- **Mocking**: `unittest.mock.patch` is used to replace `requests.get`/`requests.post` or `JWKSCache` so tests don’t call real Azure or the network.

### Where things live (quick map)

| Java-ish idea | In this package |
|---------------|------------------|
| Application config from env | `EntraConfig.from_environ()` in `config.py` |
| DTO / result object | `TokenContext` in `context.py` |
| Service class with dependencies | `EntraTokenValidator` in `validator.py` (holds config + JWKS cache) |
| Static utility / facade | `validate_and_extract(token, config=None)` in `validator.py` |
| External HTTP call | `requests` in `jwks_cache.py` (JWKS) and `graph_client.py` (Graph API) |
| Custom exception | `ValidationError` in `validator.py` |

---

## 7. Maintainer guidance

### Adding or changing a claim

- **Validator**: Edit `_extract_claims` in `validator.py` to read the new claim from `payload` and pass it into `TokenContext`.
- **Context**: Add the field to the `TokenContext` dataclass in `context.py` and to `to_dict()`.
- **Tests**: Extend or add tests in `tests/test_msal_util/test_validator.py` (e.g. a payload that includes the new claim).

### Changing validation rules

- **Signature / issuer / audience / exp / nbf**: All are enforced in `validator.py` inside `EntraTokenValidator.validate_and_extract` via `jwt.decode(..., audience=..., issuer=..., options=...)`. Adjust parameters or options there.
- **New checks after decode**: Add them after `jwt.decode` and before `_extract_claims`; raise `ValidationError` on failure.

### Adding a new environment variable

- **Config**: Add the field to `EntraConfig` in `config.py` and set it in `from_environ()` (e.g. with a helper like `_getenv_int`). Document in `README.md` and in the `EntraConfig` docstring.

### JWKS or key handling

- **URL / TTL**: Config comes from `EntraConfig` (`jwks_uri`, `jwks_cache_ttl_seconds`). Cache logic and “refresh on kid miss” are in `jwks_cache.py`.

### Graph fallback behavior

- **When it runs**: In `validator.py`, only if `not ctx.roles and self._config.graph_enabled` and the payload has an `oid` (or `sub`).
- **What it calls**: `graph_client.resolve_roles_via_graph(oid, config)`. To change permissions or endpoint, edit `graph_client.py` (and document required Graph permissions in README).

### Testing after changes

From the project root:

```bash
pytest tests/test_msal_util/ -v
```

Keep tests isolated: use env overrides (e.g. `_env` in `test_config.py`) and mocks for JWKS and Graph so no real Azure or network is required.

### Code style

- **Readable, pythonic** code; no business logic in `__init__.py`.
- **No logging of the token or sensitive claims**; log only non-PII (e.g. “Token expired”, “Invalid token: audience”).
- **Secrets only from environment**; no hardcoded tenant id, client id, or client secret.

---

## 8. Quick reference: where to look

| Goal | File / symbol |
|------|----------------|
| Validate a token (one-off, config from env) | `validate_and_extract(token)` in `validator.py` |
| Reuse a validator (e.g. shared JWKS cache) | `EntraTokenValidator(config)` then `.validate_and_extract(token)` |
| Change what we read from the token | `_extract_claims` in `validator.py` |
| Change validation rules (iss, aud, exp, etc.) | `jwt.decode(...)` call in `validator.py` |
| Add/change config keys | `EntraConfig` and `from_environ()` in `config.py` |
| Change JWKS fetch or cache | `JWKSCache` in `jwks_cache.py` |
| Change Graph role resolution | `resolve_roles_via_graph` and helpers in `graph_client.py` |
| Change the shape of the result | `TokenContext` in `context.py` |
| Public API surface | `__init__.py` (and the symbols above) |
