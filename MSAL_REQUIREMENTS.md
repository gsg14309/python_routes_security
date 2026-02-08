# MSAL / Entra ID integration requirements

This document defines requirements for a **standalone backend utility** that validates Azure Entra ID (Microsoft identity) tokens and extracts claims for use by this application. It reflects standard MSAL/Entra connectivity and security practices.

See also: [PRODUCTION.md](PRODUCTION.md) for end-to-end SSO flow and API security patterns.

---

## 1. Purpose and scope

- **Backend utility**: Validate Entra-signed JWT (access token), extract claims, and optionally resolve roles via Microsoft Graph when not present in the token.
- **Standalone package**: Implement in a new package with minimal dependencies and **no dependency on existing app packages** (so it can be reused or tested in isolation).
- **Integration point**: The rest of the app (e.g. FastAPI security layer) will call this utility to obtain a small, serializable context (user id, roles, department, scopes) after validating the bearer token.

---

## 2. Token and flow

- The front end performs SSO against **Azure Entra ID** and sends a token to the API in the `Authorization` header.
- The API must receive and use the **access token** only:
  - **Access token**: Issued for your API (audience = your API’s app ID). Use this for **API authorization**.
  - **ID token**: Issued for the client app; used to identify the user in the front end. **Must not be used for backend API authorization.**
- Flow: `Authorization: Bearer <access_token>` → validate token → extract claims → (if needed) call Microsoft Graph for roles → return context.

For SPA flow (Authorization Code + PKCE, obtaining the access token), see [PRODUCTION.md](PRODUCTION.md).

---

## 3. Functional requirements

### 3.1 Token validation (before using any claim)

- **Signature**: Verify JWT signature using keys from Azure Entra ID’s JWKS endpoint.
- **Issuer**: Verify `iss` matches the tenant authority (e.g. `https://login.microsoftonline.com/<tenant_id>/v2.0`).
- **Audience**: Verify `aud` (or `azp` where applicable) matches the API’s application (client) ID or configured audience.
- **Lifetime**: Verify `exp` and `nbf` with acceptable clock skew; reject expired or not-yet-valid tokens.
- **Reject** any token that fails validation before using its claims for authorization.

### 3.2 Claims to extract

- **User identity**: From token — `sub` and/or `oid` (and optionally `preferred_username` for display only). Map to a canonical “user id” for the app.
- **Roles**: From token — `roles` claim (App Roles) when present. If roles are not in the token (e.g. not configured, or groups overage), **call Microsoft Graph** with appropriate auth to resolve group membership or app-specific roles (see Graph fallback below).
- **Department**: From token if a custom claim is configured; otherwise from Microsoft Graph or a separate back-end lookup. Document that department may not be in the token by default.
- **Scopes / permissions**: From token — `scp` (scopes) for delegated access. For app roles, use `roles`. Use consistent terminology: “scopes” for OAuth2 scopes in the token; “permissions” or “capabilities” for app-level authorization concepts if needed.

### 3.3 Microsoft Graph fallback for roles

- **When**: Roles are required but not present in the token (e.g. groups not in token, overage, or only App Roles used and not configured in token).
- **How**: Call Microsoft Graph with appropriate authentication (e.g. On-Behalf-Of flow using the access token, or app-only with application permission) to resolve group membership or role data.
- **Document**: Required Graph scope/permission (e.g. `User.Read`, `GroupMember.Read.All` or app role) and error handling (e.g. no roles vs. Graph failure).

### 3.4 Output

- Produce a small, **serializable context** (e.g. user id, roles, department, scopes) for use by the rest of the application (e.g. FastAPI `request.state` or equivalent).

---

## 4. Security and operational requirements

- **Configuration**: All Azure/Entra configuration (tenant id, client id, client secret or certificate, API audience, Graph scope/permission) MUST be read from **environment variables** (e.g. `.env`). No hardcoded secrets.
- **Logging**: Do **not** log the token or sensitive claims. Log only non-PII (e.g. validation failure reason, path, and optionally `sub`/`oid` if policy allows).
- **JWKS**: Cache the JWKS with a TTL to avoid fetching keys on every request.
- **HTTPS**: Tokens must only be sent over HTTPS in production; document that the API must be served over HTTPS when using bearer tokens.
- **Libraries**: Use standard, maintained libraries (e.g. PyJWT with JWKS fetch, or a library that validates Entra tokens) and keep the dependency set minimal for the standalone utility.

---

## 5. Deliverables

- **Standalone package**: Implement the utility in a new package (e.g. new top-level package or `app/msal_util/` with a clear boundary and no dependency on other app packages).
- **Tests**: Unit tests (and optionally integration tests with mocked Entra/Graph) for validation, claim extraction, and Graph fallback behavior.
- **README**: Document the utility’s usage, required environment variables, validation behavior, and when/how Microsoft Graph is called.
- **Code quality**: Code must be readable and pythonic.

---

## 6. FAQ / Open points

**Q: The user does SSO on the front end against Azure Entra ID. What token does the user pass to the API — access token or ID token?**

**A: Access token.** The client must send the **access token** (issued for your API’s audience) in `Authorization: Bearer <access_token>`. The ID token is for the client application to identify the user and must not be used for backend API authorization.

---

## 7. References

- [PRODUCTION.md](PRODUCTION.md) — Production SSO flow, token handling, and validation minimums for this project.
- [Microsoft identity platform access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens) — Token structure and claims.
- [Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference) — For Graph fallback (e.g. group membership).
