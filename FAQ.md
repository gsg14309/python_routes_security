## FAQ

### When do FastAPI dependencies get resolved? After the endpoint method call?

**Dependencies run before your endpoint function is called**, on every request, after routing has selected the matching endpoint.

For this project, the global dependency is set here:

```13:16:/Users/gsr/dev/learning/GitHub/python_routes_security/app/main.py
def create_app() -> FastAPI:
    # Global dependency: applies security with zero changes to route handlers.
    app = FastAPI(dependencies=[Depends(enforce_security)])
```

**Request lifecycle (simplified):**
- **Request received**
- **Routing** (path + method → endpoint function)
- **Dependency injection / resolution**
  - app-level dependencies (like `enforce_security`)
  - router/endpoint dependencies
  - parameter dependencies (e.g., `db: Session = Depends(get_db)`)
- **Endpoint function executes**
- **Response serialization**

Why dependency (vs middleware) matters here:
- Because dependencies run **after routing**, `enforce_security` can read `request.scope["endpoint"]` and see decorator metadata.

---

### How does `enforce_security` get access to the `Request` object?

FastAPI/Starlette already has a `Request` object for each incoming HTTP call. FastAPI will **inject** that object into any dependency (or endpoint) parameter annotated as `Request`.

In this repo, `enforce_security` declares `request: Request`:

```27:31:/Users/gsr/dev/learning/GitHub/python_routes_security/app/security/dependencies.py
def enforce_security(
    request: Request,
    config: SecurityConfig = Depends(get_security_config),
    db: Session = Depends(get_db, use_cache=False),
) -> None:
```

**What happens (simplified):**
- Request arrives → Starlette creates a `Request` object.
- FastAPI routes to an endpoint.
- FastAPI resolves dependencies.
- When it sees `request: Request`, it passes the current `Request` object into `enforce_security`.

**Important gotcha:** the annotation must be exactly `Request`. If you use `Request | None` (or other unions), FastAPI may stop treating it as the special request type and try to parse it like regular input (causing confusing errors).

---

### What’s the difference between middleware and dependencies in FastAPI?

They both can run “before your endpoint”, but they sit at **different layers**.

#### Middleware (Starlette/FastAPI middleware)
- **When it runs**: wraps the whole request/response. Runs **before routing** (incoming) and **after the endpoint** (outgoing).
- **What it sees**: raw `Request` + the eventual `Response`.
  - It generally **does not know which endpoint will run** unless you do extra work.
- **What it’s good for**:
  - CORS, gzip, timing/metrics, request/response logging, correlation IDs
  - “Global” cross-cutting concerns not tied to a particular route signature
- **How you write it**: `@app.middleware("http")` or `app.add_middleware(...)`

#### Dependencies (`Depends(...)`)
- **When it runs**: after routing selects the endpoint, during dependency injection, **before the endpoint function executes**.
- **What it sees**:
  - Can access `request.scope["endpoint"]` (so it can see decorator metadata in this project).
  - Can depend on other dependencies (`Depends(get_db)`, settings, etc.).
- **What it’s good for**:
  - Authn/authz checks
  - Loading a user, tenant, department, feature flags
  - Providing strongly-typed “inputs” to the endpoint
- **How you attach it**:
  - globally: `FastAPI(dependencies=[...])`
  - router-level: `APIRouter(dependencies=[...])`
  - endpoint-level: `@router.get(..., dependencies=[...])` or function params

#### Why this repo uses a dependency (not middleware) for security
- It needs to run **after routing** so it can optionally read decorator metadata from the resolved endpoint.
- It composes naturally with FastAPI DI and can attach per-request state (`request.state.authz`) used later by the DB layer.

---

### When does `startup()` run in FastAPI?

In this repo, startup is defined here:

```16:24:/Users/gsr/dev/learning/GitHub/python_routes_security/app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    app.state.security_config = load_security_config(settings.resolved_security_config_path())
    init_db()

    yield
    # Shutdown (nothing to clean up in this demo)
```

**When it runs:**
- **Once per process**, when the ASGI server starts and completes the application startup sequence.
- It runs **before the app begins serving requests**.

**Important operational notes:**
- If you run uvicorn with `--reload`, uvicorn uses a reloader process that spawns a server process; **startup runs in the server process** and will run again after each reload.
- If you run multiple workers (`--workers N`), **startup runs once in each worker process**.

