## python_routes_security

Minimal FastAPI demo of **configuration-driven route security**:
- Role-based access control (RBAC)
- Department-scoped data access
- Sensitive-data filtering via `is_sensitive`

Also includes a **small decorator-based sample** as a reference style (but the primary approach is config-driven).

### Quick start

- **Install (uv)**

```bash
uv sync
```

- **Run**

```bash
uv run uvicorn app.main:app --reload
```

The app will create `app.db` and seed sample data on startup.

### Notes

- If your editor shows `Import ... could not be resolved`, make sure it is using this interpreter:
  - `.venv/bin/python`

### Logging

- Default log level is `INFO`.
- To enable more detailed security/filter logs:

```bash
APP_LOG_LEVEL=DEBUG uv run uvicorn app.main:app --reload
```

### Seeded demo users

- `1`: `alice_admin` (role: `admin`, dept: HR)
- `2`: `harry_hr` (role: `hr_manager`, dept: HR)
- `3`: `mona_mgr_it` (role: `department_manager`, dept: IT)
- `4`: `ed_it` (role: `employee`, dept: IT)
- `5`: `fran_fin` (role: `employee`, dept: FIN)

### How auth works (demo)

Send a bearer token via:
- Header: `Authorization: Bearer <token>`

Demo behavior: `<token>` is treated as an **integer `user_id`** (this is the stub for the future Azure AD integration).

### Try it

- **Health (public)**

```bash
curl -s localhost:8000/health
```

- **Employees (department-filtered)**

```bash
curl -s -H 'Authorization: Bearer 3' localhost:8000/employees
```

- **Employee detail (may hide sensitive rows)**

```bash
curl -s -H 'Authorization: Bearer 3' localhost:8000/employees/1
```

- **Performance reviews (sensitive + department-filtered)**

```bash
curl -s -H 'Authorization: Bearer 3' localhost:8000/performance-reviews
```

- **Decorator demo routes (no config entry required)**

```bash
curl -s -H 'Authorization: Bearer 3' localhost:8000/decorator-demo/employees
curl -s -H 'Authorization: Bearer 2' localhost:8000/decorator-demo/performance-reviews
```

### Configuration

Edit `config/security_config.yaml` to define route rules (roles, department filtering, sensitive filtering).

