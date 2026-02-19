## RBAC usage guide (YAML + engine)

This file explains how to **use** the RBAC engine implemented in `rbac_engine.py`, where the **sample YAML** lives, and how to **run the tests**.

This is a practical companion to:
- `RBAC_REQUIREMENTS.md` — what the RBAC system must do.
- `RBAC_IMPLEMENTATION.md` — how the engine is implemented.

---

## 1. Files involved

- `config/rbac.yaml`  
  Sample RBAC configuration file (roles, permissions, public endpoints).

- `app/msal_util/rbac_engine.py`  
  Pure-Python RBAC engine and YAML loader (`RbacEngine`, `load_rbac_config`, `RbacConfigError`).

- `app/msal_util/RBAC_REQUIREMENTS.md`  
  Detailed requirements (roles ↔ permissions ↔ endpoint rules, hierarchy, public endpoints).

- `app/msal_util/RBAC_IMPLEMENTATION.md`  
  Implementation overview and how code maps to the requirements.

- `tests/test_msal_util/test_rbac_engine.py`  
  Unit tests for the RBAC engine using the sample YAML.

---

## 2. YAML shape and sample (`config/rbac.yaml`)

The RBAC engine expects YAML where **roles** and **permissions** are defined separately.

### 2.1 Roles

Each role:
- Has a **name** under `roles:`.
- Can `extends` a parent role (single-parent hierarchy).
- Lists its direct `permissions` (permissions are defined by name in `permissions:`).
- May have optional `display_name` and `description`.

Example (simplified from `config/rbac.yaml`):

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

  manager:
    display_name: Manager
    description: Can publish and assign content
    extends: modeller
    permissions:
      - content.publish
      - content.assign

  admin:
    display_name: Admin
    description: Full administrative access
    extends: manager
    permissions:
      - content.delete
```

### 2.2 Permissions and endpoint rules

Each permission appears once under `permissions:`:

- `rules`: list of HTTP **method + path** patterns allowed for that permission.
- Optional `public: true` to mark those rules as **RBAC-free** endpoints.

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

  content.update:
    rules:
      - path: /content/{id}
        methods: [PUT, PATCH]

  content.publish:
    rules:
      - path: /content/{id}/publish
        methods: [POST]
```

### 2.3 Public endpoints

You can mark endpoints as **public** (no RBAC) in either of two ways:

1. Top-level `public` section:

   ```yaml
   public:
     - path: /about
       methods: [GET]
     - path: /status
       methods: [GET]
     - path: /live
       methods: [GET]
   ```

2. A `permission` with `public: true`:

   ```yaml
   permissions:
     public.info:
       public: true
       rules:
         - path: /about
           methods: [GET]
   ```

The engine merges both into a single internal list of **public rules** and checks those *before* role/permission logic.

---

## 3. Loading the RBAC engine

In application startup code (or a small integration module), you typically do:

```python
from pathlib import Path

from app.msal_util.rbac_engine import RbacEngine

rbac_engine = RbacEngine.from_yaml(Path("config/rbac.yaml"))
```

This will:
- Load and validate `config/rbac.yaml`.
- Compute effective permissions per role (resolving `extends`).
- Precompile path templates to regexes for fast matching.

On any YAML error (unknown role/permission, bad shapes, cycles in `extends`), a `RbacConfigError` is raised at startup.

---

## 4. Integrating with FastAPI (high level)

The RBAC engine is framework-agnostic. To use it with FastAPI, create a small wrapper that:

1. Holds a global `rbac_engine` instance (loaded at startup).
2. Extracts user roles from the request (e.g. from an Entra `TokenContext`, DB, or `request.state`).
3. Calls `rbac_engine.is_allowed(user_roles, method, path)` and raises if denied.

Example pseudo-code:

```python
# app/security/rbac_dependency.py
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.msal_util.rbac_engine import RbacEngine

rbac_engine = RbacEngine.from_yaml(Path("config/rbac.yaml"))


def get_user_roles(request: Request) -> set[str]:
    # Example only: you decide where roles come from.
    #   - From Entra access token claims
    #   - From DB-backed roles
    #   - From request.state set by previous middleware
    return set(getattr(getattr(request, "state", None), "roles", []) or [])


def require_rbac(request: Request, roles: set[str] = Depends(get_user_roles)) -> None:
    method = request.method
    path = request.url.path

    if not rbac_engine.is_allowed(roles, method, path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden by RBAC")
```

Then add this dependency to routes or as a global dependency:

```python
from fastapi import FastAPI, Depends

from app.security.rbac_dependency import require_rbac

app = FastAPI()

@app.get("/content", dependencies=[Depends(require_rbac)])
def list_content():
    ...
```

This leaves **authentication** (who the user is) to your existing auth layer, and uses RBAC purely for **authorization** (what the user can do).

---

## 5. Using the engine directly (without FastAPI)

You can also use the engine in plain Python code, e.g. for background jobs:

```python
from pathlib import Path

from app.msal_util.rbac_engine import RbacEngine

engine = RbacEngine.from_yaml(Path("config/rbac.yaml"))

roles = {"modeller"}  # from some external context

if engine.is_allowed(roles, "POST", "/content"):
    # Proceed with creating content
    ...
else:
    # Deny or log
    ...
```

Check if an endpoint is public:

```python
if engine.is_public("GET", "/about"):
    # no RBAC needed
    ...
```

---

## 6. Running the RBAC tests

The engine is tested in `tests/test_msal_util/test_rbac_engine.py` using `config/rbac.yaml`.

From the project root:

```bash
pytest tests/test_msal_util/test_rbac_engine.py -v
```

Or run the full suite (RBAC + MSAL + data layer tests):

```bash
pytest tests -v
```

The RBAC tests cover:
- YAML loading (`load_rbac_config`) with the sample file.
- Effective permissions per role (after inheritance).
- Public endpoint detection (`is_public`).
- Access decisions for different roles and endpoints (`is_allowed`).
- Fail-closed behaviour when no permission rules match an endpoint.

---

## 7. Where to edit / extend RBAC

- **Add or change roles**: edit `roles:` in `config/rbac.yaml`.
- **Add or change permissions**: edit `permissions:` and their `rules` in `config/rbac.yaml`.
- **Add public endpoints**: edit the `public:` section, or add `public: true` to a permission.
- **Change decision logic**: see `RbacEngine.is_allowed` in `rbac_engine.py`.
- **Adjust path matching**: see `_path_template_to_regex` in `rbac_engine.py` if you need more complex patterns.

After changes, re-run:

```bash
pytest tests/test_msal_util/test_rbac_engine.py -v
```

to ensure configuration and behaviour still match expectations.

