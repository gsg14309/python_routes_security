## RBAC requirements for FastAPI endpoints

This document defines requirements for a **role-based access control (RBAC)** layer for a FastAPI application, based on the initial notes in `rbac.txt`. The goal is a **simple, pythonic, clear** design that:

- Supports a small, **hierarchical role set** (`reader`, `modeller`, `manager`, `admin`).
- Drives **endpoint access** (path + HTTP method) from a **YAML configuration file**.
- Avoids complex, hard-to-reason-about recursion in role inheritance.

The RBAC layer is conceptually separate from authentication (e.g. token validation). It assumes that for each request we already know **which roles** the caller has.

---

## 1. Roles and hierarchy (conceptual model)

### 1.1 Role set

Initial roles (domain: content/document management):

- **reader** – can view existing content and metadata.
- **modeller** – can do everything a `reader` can, plus create and update models/content structures.
- **manager** – can do everything a `modeller` can, plus approve or publish content, manage assignments.
- **admin** – can do everything a `manager` can, plus administrative operations (user/role assignment, bulk operations, maintenance).

The roles are **hierarchical**:

- `modeller` ⊇ `reader`
- `manager` ⊇ `modeller` ⊇ `reader`
- `admin` ⊇ `manager` ⊇ `modeller` ⊇ `reader`

> **Requirement R1:** The RBAC system must support **role hierarchy**, where a \"higher\" role automatically inherits all permissions of lower roles.

### 1.2 Permissions (privileges)

Permissions are **named capabilities** that are later mapped to HTTP methods and paths. Example permissions in a content domain:

- **`content.read`** – view content and metadata.
- **`content.create`** – create new content.
- **`content.update`** – update existing content.
- **`content.delete`** – delete content.
- **`content.publish`** – publish or approve content.
- **`content.assign`** – assign content to users/teams.
- **`admin.user.manage`** – manage users/roles (admin-level).
- **`admin.system.maintenance`** – maintenance operations (e.g. reindexing).

> **Requirement R2:** Permissions must be named strings (dot-separated is recommended, e.g. `content.read`), and roles are defined as **sets of permissions**.

### 1.3 Example role-to-permission mapping

Conceptual mapping (can be refined later):

- **reader**
  - `content.read`
- **modeller**
  - Inherits all `reader` permissions.
  - Adds: `content.create`, `content.update`
- **manager**
  - Inherits all `modeller` permissions.
  - Adds: `content.publish`, `content.assign`
- **admin**
  - Inherits all `manager` permissions.
  - Adds: `content.delete`, `admin.user.manage`, `admin.system.maintenance`

> **Requirement R3:** The system must make it easy to see, for each role, the **effective permission set** after hierarchy is applied (for debugging and documentation).

---

## 2. YAML configuration

### 2.1 Requirements for the YAML file

The YAML must:

- Define **roles** and their **direct permissions**.
- Describe **role inheritance** in a way that is easy to reason about.
- Map **permissions to endpoints** (method + path), or map **roles directly to endpoints** (but permissions are preferred for reuse).
- Be **readable and maintainable** by humans.

> **Requirement R4:** YAML is the **single source of truth** for role definitions and endpoint access. No hard-coded permission lists in Python.

### 2.2 Role definitions with inheritance (extends)

Initial idea in `rbac.txt`: each role may have an `extends` clause to inherit from another role, to avoid duplication. For example:

```yaml
roles:
  reader:
    permissions:
      - content.read

  modeller:
    extends: reader
    permissions:
      - content.create
      - content.update

  manager:
    extends: modeller
    permissions:
      - content.publish
      - content.assign

  admin:
    extends: manager
    permissions:
      - content.delete
      - admin.user.manage
      - admin.system.maintenance
```

> **Requirement R5:** The YAML role model may include **single-parent inheritance** via an `extends` field, forming a simple tree (no multiple inheritance, no cycles).

### 2.3 Avoiding complex recursive logic

The original note: *\"to avoid duplication, the yaml has extends clauses... verify if this is a good approach, because the role checker checks for recursive extends and makes logic complex.\"*

Design decision:

- **Yes** to `extends`, but:
  - Limit it to **single-parent** inheritance (each role extends at most one other role).
  - Detect and reject **cycles** at **load time**, not at request time.
  - Compute a **flattened, effective permission set per role** once when loading YAML.

> **Requirement R6:** The RBAC loader must:
> - Detect and raise an error on **cyclic `extends`** at startup (e.g. `reader → manager → reader`).
> - Precompute **effective permissions per role** (direct + inherited) so the runtime checker never needs recursion.

If this proves too complex, an alternative is to **remove `extends` in YAML** and fully list all permissions per role. That is simpler to implement but more verbose.

---

## 3. Endpoint access model

We want to decide, for each incoming request:

- **Given**: HTTP method (e.g. `GET`), path (e.g. `/content/123`), and the caller's **role(s)** (e.g. `modeller`).
- **Answer**: Is access **allowed** or **denied**?

### 3.1 Strategy A: Permissions → Endpoints

One clear design is:

1. Roles map to permissions.
2. Permissions map to endpoints.

Example YAML snippet:

```yaml
roles:
  reader:
    permissions:
      - content.read
  modeller:
    extends: reader
    permissions:
      - content.create
      - content.update
  manager:
    extends: modeller
    permissions:
      - content.publish
      - content.assign
  admin:
    extends: manager
    permissions:
      - content.delete
      - admin.user.manage
      - admin.system.maintenance

permissions:
  content.read:
    rules:
      - path: /content
        methods: [GET]
      - path: /content/{id}
        methods: [GET]

  content.create:
    rules:
      - path: /content
        methods: [POST]

  content.update:
    rules:
      - path: /content/{id}
        methods: [PUT, PATCH]

  content.delete:
    rules:
      - path: /content/{id}
        methods: [DELETE]

  content.publish:
    rules:
      - path: /content/{id}/publish
        methods: [POST]

  content.assign:
    rules:
      - path: /content/{id}/assign
        methods: [POST]
```

> **Requirement R7:** The RBAC configuration must support mapping permissions to (path pattern, HTTP method list) pairs.

### 3.2 Path patterns

- Paths should be expressed as **templates** (e.g. `/content/{id}`) rather than hard-coding all variants.
- The RBAC system needs basic matching (exact path or simple `{param}` placeholders), similar to the route config in `config/security_config.yaml`.

> **Requirement R8:** Path matching can use a simple template syntax (`/content/{id}`) and does not need full FastAPI path parsing. Regular expressions are optional and can be added later if needed.

### 3.3 Multiple roles per user

Although the initial roles are hierarchical, a user may still have **multiple roles** (e.g. `reader` and `modeller`). The RBAC checker should:

- Compute the union of all permissions from all roles the user has.
- Decide access if **any** of the user’s roles grants the required permission.

> **Requirement R9:** The role checker must support multiple roles per user and treat access as allowed if at least one role’s effective permission set covers the permission for the requested endpoint.

### 3.4 Public (RBAC-free) endpoints

Some endpoints do **not** require RBAC checks at all — for example:

- Static or informational endpoints: `/about`, `/status`, `/live`, `/healthz`
- Public documentation or landing pages

These should be explicitly marked as **public** in the configuration so the checker can quickly skip role evaluation.

Two options:

- A global `public` flag on rules:

  ```yaml
  permissions:
    public.info:
      public: true
      rules:
        - path: /about
          methods: [GET]
        - path: /status
          methods: [GET]
        - path: /live
          methods: [GET]
  ```

- Or a dedicated `public_rules` / `public` section (for the combined structure case):

  ```yaml
  public:
    - path: /about
      methods: [GET]
    - path: /status
      methods: [GET]
    - path: /live
      methods: [GET]
  ```

At runtime the RBAC layer should:

1. Check if the request (method, path) matches a **public** rule → if yes, allow immediately without roles/permissions.
2. Otherwise, fall back to the normal RBAC logic (roles/permissions as described above).

> **Requirement R9a:** The configuration must support an explicit notion of **public endpoints** (no RBAC required), and the runtime checker must short‑circuit those before applying role/permission rules.

---

## 4. Components and responsibilities

### 4.1 YAML loader

**Responsibilities:**

- Load YAML from a configured path (e.g. via environment variable or settings).
- Parse into internal Python structures (e.g. `RolesConfig`, `PermissionsConfig`).
- Validate:
  - `extends` targets exist.
  - No cycles in `extends`.
  - Permissions referenced in roles exist in `permissions`.
  - Methods are valid HTTP verbs.
- Precompute:
  - Effective permissions per role (flattened, including inherited).
  - A fast lookup structure from (method, path) to set of required permissions (or directly to allowed roles).

> **Requirement R10:** YAML loading and validation must happen at **application startup**, and the app must fail to start if the RBAC configuration is invalid.

### 4.2 Role checker

**Responsibilities:**

- Input:
  - HTTP method (uppercase string, e.g. `GET`).
  - Path (string, e.g. `/content/123`).
  - User roles (set of strings, e.g. `{\"modeller\"}`).
- Output:
  - Boolean: `True` if access allowed, `False` (or raises) if not.
  - Optionally: which permission matched (for logging).

**Algorithm (based on precomputed data):**

1. Normalize method and path.
2. Find all permissions whose rules match (method, path) (using the precomputed lookup).
3. Compute the union of effective permissions for all user roles.
4. If intersection of (user permissions) and (required permissions for the endpoint) is non-empty → **allow**; else **deny**.

> **Requirement R11:** The role checker must be **read-only and fast** at request time. No YAML parsing or recursion during a request.

### 4.3 Integration with FastAPI

**Design options:**

- **Dependency**: Have a dependency like `require_rbac(method, path)` that uses `request.method` and `request.url.path` and raises `HTTPException(status_code=403)` when access is denied. This can be added to routes or as a global dependency.
- **Middleware**: Run RBAC checks in a middleware using the route path and method, before hitting the handler. This is similar to how `app/security/dependencies.py` uses `enforce_security`.

> **Requirement R12:** RBAC checks must integrate cleanly with FastAPI, ideally as a reusable dependency or middleware that can be attached without changing business logic in handlers.

---

## 5. Error handling and logging

- Misconfigured YAML (unknown role, unknown permission, cycle in `extends`) should cause a **startup-time error** with a clear message.
- At request time:
  - Missing role(s) for a user → treated as **no permissions** (likely 403).
  - No matching rule for path/method → default decision should be **deny** (fail closed), unless configuration explicitly marks the endpoint as public.
  - Log access denials at INFO level with: user roles, method, path, and which permission was missing (but no sensitive data).

> **Requirement R13:** The system must fail **early and loudly** on misconfiguration, and fail **closed** (deny by default) on ambiguous runtime cases.

---

## 6. Alternatives and critical evaluation of `extends`

### 6.1 Pros of `extends`

- Reduces duplication: higher roles don’t need to list all lower-role permissions explicitly.
- Mirrors the mental model: \"manager is like modeller + extra\".
- Keeps YAML focused on the differences between roles.

### 6.2 Cons of `extends`

- Naive implementations can lead to **recursive logic** in the role checker, especially if inheritance resolution happens at request time.
- Complex `extends` graphs (multiple parents, long chains, or cycles) are hard to reason about and test.

### 6.3 Mitigation strategy (recommended)

- Restrict `extends` to **single-parent inheritance** (a tree, not a DAG).
- Perform **hierarchy resolution at load time**:
  - Build a graph of roles and parent links.
  - Detect cycles and fail fast.
  - For each role, compute its **effective permission set** using a simple depth-first search, once, and cache the result.
- The runtime checker only deals with **flattened sets** (`effective_permissions[role]`) and never recurses.

> **Requirement R14:** Any use of `extends` must be accompanied by **startup-time resolution and validation**, so the runtime code remains simple and non-recursive.

### 6.4 Alternative: no `extends`

If even the above is considered too complex, the simplest alternative is:

- Remove `extends` entirely.
- Require each role definition to **fully list all its permissions**.

Example:

```yaml
roles:\n  reader:\n    permissions:\n      - content.read\n  modeller:\n    permissions:\n      - content.read\n      - content.create\n      - content.update\n  manager:\n    permissions:\n      - content.read\n      - content.create\n      - content.update\n      - content.publish\n      - content.assign\n  admin:\n    permissions:\n      - content.read\n      - content.create\n      - content.update\n      - content.publish\n      - content.assign\n      - content.delete\n      - admin.user.manage\n      - admin.system.maintenance\n```

This is extremely easy to implement (no hierarchy logic), but more verbose. It may be acceptable if the number of roles and permissions remains small.

> **Requirement R15 (optional, if simplifying):** The system may choose to drop `extends` and use explicit permissions per role if hierarchy logic proves too complex for the team to maintain.

### 6.5 Alternative: combine roles and permissions into one structure

Another simplification is to **drop the explicit `permissions:` block entirely** and express access control directly in terms of **roles → endpoint rules**, instead of **roles → permissions → endpoint rules**.

Two common shapes:

1. **Rules per role** (no named permissions):

   ```yaml
   roles:
     reader:
       rules:
         - path: /content
           methods: [GET]
         - path: /content/{id}
           methods: [GET]

     modeller:
       extends: reader
       rules:
         - path: /content
           methods: [POST]
         - path: /content/{id}
           methods: [PUT, PATCH]

     manager:
       extends: modeller
       rules:
         - path: /content/{id}/publish
           methods: [POST]
   ```

2. **Rules per endpoint** listing allowed roles:

   ```yaml
   rules:
     - path: /content
       methods: [GET]
       roles: [reader, modeller, manager, admin]

     - path: /content
       methods: [POST]
       roles: [modeller, manager, admin]

     - path: /content/{id}/publish
       methods: [POST]
       roles: [manager, admin]
   ```

**Pros (combined structure):**

- Simpler mental model for small systems: \"for this endpoint, which roles are allowed?\" / \"for this role, which endpoints are allowed?\" — no extra indirection via permission names.
- Fewer moving parts in YAML (no separate `permissions:` section).
- Slightly smaller implementation (no need to map permissions → endpoints).

**Cons:**

- Harder to **reuse semantics** across different frontends or non-HTTP flows. Named permissions like `content.read` cannot easily be reused outside HTTP (e.g. background jobs, CLI tools) without duplicating logic.
- More **duplication** when several endpoints share the same logical permission: you must repeat each endpoint in every role (or rule) that should have it, rather than assigning a single permission to many endpoints and then roles to that permission.
- Less expressive for audit/logging: you lose a stable permission name (`content.publish`) to log or reason about, and instead only have raw `(method, path, role)` triples.

**Evaluation:**

- For a **small API** with a limited number of routes, roles, and no other consumers of permissions, a combined structure is acceptable and may be easier for the team to maintain.
- For a system where:
  - Permissions are used in multiple places (e.g. UI feature flags, reporting, audit logs), or
  - You may add more roles over time,
  a **separate `permissions:` layer** is more maintainable and less repetitive.

> **Requirement R16 (combined-mode guidance):** If a combined `roles + rules` structure is chosen, the design must still:\n> - Support role hierarchy (via `extends` or explicit rule union).\n> - Keep rule matching simple (path + methods, no recursion at runtime).\n> - Acknowledge that logical \"permission\" names are implicit and cannot easily be reused outside the HTTP layer.\n+\n+> **Recommendation:** For this project, retain the **roles → permissions → endpoint rules** separation as the default, but recognize that a combined roles+rules YAML is a valid simplification for smaller deployments that do not need reusable permission names.\n+
---

## 7. Implementation guidelines

- Keep the **YAML schema small and focused** (roles + permissions + rules).
- Separate:
  - **Configuration loading & validation** (startup-time) from
  - **Runtime checking** (fast, read-only).
- Avoid dynamic or implicit rules; prefer explicit permissions and path patterns.
- Add **unit tests** for:
  - Role inheritance (effective permissions).
  - Path/method matching.
  - Negative cases (denials).
  - Misconfigurations (cycles, missing roles/permissions) to ensure clear errors.

These requirements should be sufficient for a clean, maintainable RBAC implementation that matches the outline in `rbac.txt` while keeping logic simple and testable.

