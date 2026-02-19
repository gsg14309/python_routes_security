## RBAC implementation overview (`app/msal_util/rbac_engine.py`)

This document describes the code added to implement the RBAC requirements in `RBAC_REQUIREMENTS.md`, using the **roles → permissions → endpoint rules** model and keeping roles and permissions separate.

---

## 1. New files and their responsibilities

### 1.1 `app/msal_util/rbac_engine.py`

**Purpose:** Core RBAC engine and YAML loader, independent of FastAPI.

**Main features:**

- **YAML loader**: `load_rbac_config(path: Path) -> RbacConfig`
  - Loads a YAML file with the following structure:
    ```yaml
    roles:
      reader:
        extends: null
        permissions:
          - content.read
      modeller:
        extends: reader
        permissions:
          - content.create
          - content.update

    permissions:
      content.read:
        public: false
        rules:
          - path: /content
            methods: [GET]
          - path: /content/{id}
            methods: [GET]

      content.create:
        rules:
          - path: /content
            methods: [POST]

    public:
      - path: /about
        methods: [GET]
      - path: /status
        methods: [GET]
    ```
  - Validates:
    - `roles` and `permissions` are mappings.
    - `public` (if present) is a list.
    - Each permission has a `rules` list with `path` and non-empty `methods` list.
    - Each role’s `permissions` list refers only to known permissions.
    - Any `extends` target exists (no role extending an unknown role).
  - Aggregates:
    - All top-level `public` rules.
    - All rules from permissions marked `public: true` into a single `public_rules` list.

- **Config and model types:**
  - `RbacRule` – one rule: `path_template` and `methods` (HTTP verbs).
  - `PermissionDef` – name, rules, and `public` flag.
  - `RoleDef` – role name, direct permissions, optional `extends`, and optional `display_name` / `description`.
  - `RbacConfig` – container for all roles, permissions, and public rules.
  - `RbacConfigError` – raised on invalid YAML configuration.

- **Inheritance resolution:**
  - `_compute_effective_permissions(config: RbacConfig) -> dict[str, frozenset[str]]`
    - Performs a depth‑first search over `extends` to compute **effective permissions** per role (direct + inherited).
    - Detects **cycles in `extends`** and raises `RbacConfigError` if found.
    - Produces a mapping: `role_name -> frozenset[permission_name]`.

- **Path template handling:**
  - `_path_template_to_regex(path_template: str) -> Pattern`
    - Converts templates like `/content/{id}` to a compiled regex `^/content/[^/]+$`.
    - Used both for public rules and permission rules.

- **RBAC engine:**
  - `class RbacEngine`:
    - Internal state:
      - `self._config`: the loaded `RbacConfig`.
      - `self._effective_permissions`: effective perms per role (after inheritance).
      - `self._public_patterns`: list of `(regex, methods)` for all public rules.
      - `self._perm_routes`: mapping `permission_name -> list[(regex, methods)]`.
    - Factories:
      - `RbacEngine.from_yaml(path: Path) -> RbacEngine`
        - One-call helper: load config from YAML and build the engine (including inheritance resolution).
    - Properties:
      - `config` – returns the underlying `RbacConfig`.
      - `effective_permissions` – returns a copy of `role -> effective permission set`.
    - Core methods:
      - `is_public(method: str, path: str) -> bool`
        - Returns `True` if `(method, path)` matches any public rule (from `public` section or from permissions with `public: true`).
      - `is_allowed(user_roles: Iterable[str], method: str, path: str) -> bool`
        - Main decision API:
          1. If the endpoint is public → **allow**.
          2. Find all permissions whose rules match `(method, path)`.
          3. Compute the union of effective permissions for all user roles (ignoring unknown roles).
          4. If intersection of user permissions and required permissions is non‑empty → **allow**, else **deny**.
        - If no permission rules match `(method, path)`, the engine **fails closed** (deny) and logs a debug message.

**Design notes:**

- **Roles and permissions are kept separate** in the YAML and in code:
  - Roles refer to permissions by **name**.
  - Permissions own the mapping to `(method, path)` rules.
- **Inheritance is resolved at startup** via `_compute_effective_permissions`; runtime checks never recurse across roles.
- **Public endpoints** are handled before RBAC: if public, no role or permission checks are needed.

---

## 2. How to use the RBAC engine

Basic usage (e.g. in an app startup module):

```python
from pathlib import Path

from app.msal_util.rbac_engine import RbacEngine

rbac_engine = RbacEngine.from_yaml(Path(\"config/rbac.yaml\"))
```

At request time (pseudo‑code, e.g. inside a FastAPI dependency or middleware):

```python
def require_rbac(request: Request, roles: set[str]) -> None:
    method = request.method  # e.g. \"GET\"
    path = request.url.path  # e.g. \"/content/123\"

    if not rbac_engine.is_allowed(roles, method, path):
        raise HTTPException(status_code=403, detail=\"Forbidden by RBAC\")
```

You are responsible for deciding **where the user roles come from** (e.g. from an Entra ID access token, from a DB lookup, or from `request.state` set by earlier middleware).

---

## 3. YAML expectations (recap)

The engine expects YAML shaped according to `RBAC_REQUIREMENTS.md`, with **roles** and **permissions** separate.

### 3.1 Roles

Each role is defined under `roles:` and may:

- `extends`: name of a parent role (or omitted/`null`).
- `permissions`: list of permission names.
- `display_name`: optional human‑readable name.
- `description` / `Description`: optional description (either key is accepted).

Example:

```yaml
roles:
  reader:
    display_name: Reader
    description: Can view content
    permissions:
      - content.read

  modeller:
    display_name: Modeller
    description: Can create and update content
    extends: reader
    permissions:
      - content.create
      - content.update
```

### 3.2 Permissions

Each permission appears once under `permissions:`:

- `public`: optional boolean (if true, its rules are treated as public endpoints).
- `rules`: list of rule objects:
  - `path`: path template (e.g. `/content`, `/content/{id}`).
  - `methods`: list of HTTP verbs (e.g. `[GET]`, `[POST, PUT]`).

Example:

```yaml
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
```

### 3.3 Public rules

Public endpoints (no RBAC) can be specified in two ways:

1. As a dedicated `public` section:

   ```yaml
   public:
     - path: /about
       methods: [GET]
     - path: /status
       methods: [GET]
     - path: /live
       methods: [GET]
   ```

2. Or by marking a permission as `public: true`:

   ```yaml
   permissions:
     public.info:
       public: true
       rules:
         - path: /about
           methods: [GET]
   ```

The engine merges both sources into a single internal `public_rules` list and checks those **before** RBAC rules.

---

## 4. How this maps back to the requirements

- **R1–R3 (role hierarchy and permissions)**  
  - Roles are defined as sets of permission names; inheritance is captured via `extends`.  
  - `_compute_effective_permissions` computes the effective permission sets per role.

- **R4 (YAML as single source of truth)**  
  - All roles, permissions, and public rules are loaded from YAML via `load_rbac_config`.

- **R5–R6 (extends, hierarchy, and cycles)**  
  - Only single‑parent `extends` is supported.
  - Cycles in role inheritance are detected and raise `RbacConfigError` at load time.

- **R7–R8 (permissions → endpoint rules, path patterns)**  
  - Each permission has a list of rules with `path` + `methods`.  
  - Path templates like `/content/{id}` are converted into regex using `_path_template_to_regex`.

- **R9 (multiple roles per user)**  
  - `is_allowed` accepts an iterable of user roles, computes the union of their effective permissions, and allows if any permission applies.

- **R9a (public endpoints)**  
  - Public endpoints are recognised via `public` entries or `public: true` permissions; `is_public` and `is_allowed` check these first.

- **R10–R11 (startup validation and fast runtime)**  
  - Validation (types, unknown roles/permissions, cycles) happens inside `load_rbac_config` / `_compute_effective_permissions`.  
  - Runtime `is_allowed` uses only in‑memory data and precompiled regexes; no YAML parsing or recursion at request time.

- **R12–R13 (integration and fail‑closed behavior)**  
  - Integration is left to a thin wrapper (e.g. FastAPI dependency/middleware) that calls `is_allowed`.  
  - If no permission rules match an endpoint, `is_allowed` denies (fails closed) and logs at debug level.

- **R14–R16 (extends, combined structure, and recommendations)**  
  - This implementation follows the **separate `permissions:` section** model, as recommended.  
  - If a team prefers the combined structure (roles + rules only), they can implement a separate loader that builds a compatible `RbacEngine` from that shape, reusing the same decision logic.

---

## 5. Next steps (optional)

- Add a small **FastAPI integration module** (e.g. `fastapi_rbac.py`) that:
  - Loads an `RbacEngine` at startup.
  - Provides a `require_rbac` dependency that reads roles from `request.state` or from an Entra token context and calls `engine.is_allowed`.
- Add **unit tests** for:
  - YAML parsing and error conditions (`RbacConfigError` on bad input).
  - Role inheritance and effective permission sets.
  - Path/method matching (including template parameters).
  - Public endpoint handling and fail‑closed behavior.

