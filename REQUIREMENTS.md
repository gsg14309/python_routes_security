# Route Security and Authorization Requirements Document

## 1. Project Overview

### 1.1 Purpose
This project demonstrates a **non-invasive, configuration-driven approach** to adding route-level security and authorization to an existing FastAPI application. The implementation will showcase:

- Role-based access control (RBAC)
- Department-based data filtering
- Sensitive data protection with additional permission checks
- Minimal disruption to existing codebase

### 1.2 Approach Priority
- **PRIMARY METHOD**: Configuration-driven approach (YAML/JSON configuration files)
  - Zero code changes to existing routes
  - Security rules defined in configuration
  - Applied automatically via middleware
  
- **ALTERNATIVE EXAMPLE**: Decorator-based approach
  - Shown as a sample/reference implementation
  - Demonstrates explicit route protection with decorators
  - Useful for cases requiring explicit control

### 1.3 Domain Model
**Employee/HR Management System** - A well-understood domain that naturally demonstrates:
- Multiple departments (HR, IT, Finance, Operations, etc.)
- Role hierarchies (Admin, Manager, Employee, Viewer)
- Sensitive data (salary, performance reviews, personal information)
- Department-specific data access requirements

### 1.4 Technology Stack
- **Python 3.11+**
- **FastAPI** - Web framework
- **Pydantic** - Data validation and settings
- **SQLAlchemy** - ORM
- **SQLite** - Database (for simplicity)
- **Uvicorn** - ASGI server
- **UV** - Package management

---

## 2. Core Requirements

### 2.1 Route Protection
- Routes must be accessible only to authenticated users with appropriate roles
- Role validation should be declarative and easy to apply
- Support for multiple roles per route (OR logic)
- Clear error messages for unauthorized access attempts

### 2.2 Department-Based Data Filtering
- Endpoints must automatically filter data based on user's department
- Users should only see data from their own department
- Exception: Users with elevated permissions (e.g., Admin, HR Manager) may access cross-department data

### 2.3 Sensitive Data Protection
- Tables include a `is_sensitive` boolean column
- Sensitive data requires additional permission beyond basic role access
- Permission checks should be granular and configurable
- Clear separation between role-based access and sensitive data permissions

### 2.4 Integration Requirements
- **Zero changes to existing route handlers** - routes remain unchanged
- **Configuration-driven (PRIMARY)** - security rules defined in configuration files (preferred approach)
- **Decorator-based (EXAMPLE)** - decorators shown as alternative example for explicit route protection
- **Dependency injection** - leverage FastAPI's dependency system
- **Backward compatible** - existing routes without security annotations continue to work

---

## 3. Architecture Approach

### 3.1 Design Principles

#### 3.1.1 Separation of Concerns
```
┌─────────────────────────────────────────┐
│   Existing Application Layer            │
│   (Routes, Business Logic)              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   Security Middleware Layer              │
│   (Decorators, Dependencies)            │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   Authorization Service Layer            │
│   (Role/Dept/Permission Checks)         │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   Data Access Layer                      │
│   (SQLAlchemy with Query Filters)       │
└─────────────────────────────────────────┘
```

#### 3.1.2 Dependency Injection Pattern
FastAPI's dependency injection system will be used to:
- Extract user context from request (headers, tokens, etc.)
- Validate roles and derived capabilities (config-driven)
- Inject filtered query parameters
- Provide user context to route handlers

#### 3.1.3 Configuration-First Approach (PRIMARY)
Security rules defined in YAML/JSON configuration files:
- Route paths mapped to required roles
- Department filtering flags
- Sensitive data permission requirements
- Applied automatically via middleware without code changes

#### 3.1.4 Decorator Pattern (ALTERNATIVE EXAMPLE)
Optional decorators for explicit route protection (shown as example):
- `@require_role(roles=["admin", "manager"])`
- `@require_sensitive_permission()`
- `@filter_by_department()` - automatic department filtering

### 3.2 Component Architecture

```
security/
├── __init__.py
├── config.py              # Security configuration
├── dependencies.py         # FastAPI dependencies for auth
├── decorators.py           # Route protection decorators
├── services/
│   ├── __init__.py
│   ├── auth_service.py      # Authentication logic
│   ├── role_service.py      # Role validation
│   └── capability_service.py # Role->capability mapping (config-only)
├── models/
│   ├── __init__.py
│   ├── user.py             # User model with roles
│   └── security.py          # Security-related models
└── middleware/
    └── data_filter.py       # Department-based filtering
```

### 3.3 Integration Points

#### 3.3.1 Configuration-Driven Approach (PRIMARY - RECOMMENDED)

**Before (Existing Route - No Changes Needed):**
```python
@router.get("/employees")
async def get_employees(db: Session = Depends(get_db)):
    return db.query(Employee).all()
```

**After (Configuration-Only - Route Code Unchanged):**
```yaml
# security_config.yaml
security:
  routes:
    - path: "/employees"
      methods: ["GET"]
      required_roles: ["manager", "hr"]
      filter_by_department: true
      require_sensitive_permission: false
```

The route handler code remains **completely unchanged**. Security is applied automatically via:
- Middleware that reads configuration
- Dependency injection that applies filters
- Automatic query modification based on user context

#### 3.3.2 Decorator-Based Approach (ALTERNATIVE EXAMPLE)

**Example showing decorator pattern (for reference):**
```python
@router.get("/employees")
@require_role(["manager", "hr"])
@filter_by_department()
async def get_employees(
    user: User = Depends(get_current_user),
    query: Query = Depends(get_filtered_query)
):
    return query.all()
```

**Note**: This decorator approach is provided as an example/alternative, but the **configuration-driven approach is preferred** for minimal disruption to existing code.

---

## 4. Database Schema

### 4.1 Core Tables

#### 4.1.1 Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    department_id INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);
```

#### 4.1.2 Departments Table
```sql
CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    code VARCHAR(10) UNIQUE NOT NULL,
    description TEXT
);
```

#### 4.1.3 Roles Table
```sql
CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);
```

#### 4.1.4 User Roles (Many-to-Many)
```sql
CREATE TABLE user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id)
);
```

#### 4.1.5 Capabilities / Permissions (Config Only)
Permissions are **not stored in the database**. Instead, capabilities (e.g. `view_sensitive_data`, `view_cross_department`) are derived from the user’s **roles** via configuration (see `config/security_config.yaml`).

#### 4.1.7 Employees Table (Domain Entity)
```sql
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    department_id INTEGER NOT NULL,
    position VARCHAR(100),
    salary DECIMAL(10, 2),
    is_sensitive BOOLEAN DEFAULT FALSE,
    hire_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);
```

#### 4.1.8 Performance Reviews Table (Sensitive Data Example)
```sql
CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    department_id INTEGER NOT NULL,
    review_date DATE NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comments TEXT,
    is_sensitive BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (department_id) REFERENCES departments(id)
);
```

### 4.2 Sample Data Requirements
- **Departments**: HR, IT, Finance, Operations, Sales
- **Roles**: admin, hr_manager, department_manager, employee, viewer
- **Capabilities (config-derived)**:
  - `view_sensitive_data`
  - `edit_employee_data`
  - `view_cross_department`
  - `manage_users`

---

## 5. Security Model

### 5.1 Authentication
- **Bearer token authentication** (integration-aligned)
- Request format: `Authorization: Bearer <token>`
- **Demo stub (this project)**: treat `<token>` as an integer `user_id`, then load user + roles from the local DB.
- **Production target (documented only; NOT implemented)**: validate the token and resolve roles via Microsoft Azure AD (e.g., group/role claims).

### 5.2 Authorization Layers

#### 5.2.1 Role-Based Access Control (RBAC)
- Users have one or more roles
- Routes specify required roles
- Access granted if user has ANY of the required roles (OR logic)

#### 5.2.2 Department-Based Filtering
- Users belong to a department
- Queries automatically filter by `department_id = user.department_id`
- Exception: Users with `view_cross_department` capability (derived from roles via config) see all departments

#### 5.2.3 Sensitive Data Protection
- Tables have `is_sensitive` column
- Accessing sensitive data requires:
  1. Valid role for the route
  2. Additional permission: `view_sensitive_data`
- Query automatically excludes sensitive rows if permission missing

### 5.3 Permission Matrix

| Role | View Own Dept | View Cross-Dept | View Sensitive | Edit Data |
|------|---------------|-----------------|----------------|-----------|
| admin | ✅ | ✅ | ✅ | ✅ |
| hr_manager | ✅ | ✅ | ✅ | ✅ |
| dept_manager | ✅ | ❌ | ⚠️* | ⚠️* |
| employee | ✅ | ❌ | ❌ | ❌ |
| viewer | ✅ | ❌ | ❌ | ❌ |

*Requires additional permission

---

## 6. Implementation Strategy

### 6.1 Phase 1: Core Security Infrastructure
1. Create database models (SQLAlchemy)
2. Implement dummy authentication service
3. Create role and permission services
4. Build configuration loader and validator
5. Build dependency injection functions

### 6.2 Phase 2: Configuration-Driven Route Protection (PRIMARY)
1. Implement configuration file parser (YAML/JSON)
2. Create route-to-configuration mapper
3. Build middleware that applies security from configuration
4. Create FastAPI dependencies for authorization
5. Build query filtering middleware
6. Add error handling and responses

### 6.3 Phase 3: Data Filtering
1. Implement department-based query filtering
2. Add sensitive data filtering logic
3. Create reusable query builders
4. Test filtering with various scenarios

### 6.4 Phase 4: Integration Examples
1. Create sample routes demonstrating configuration approach
2. Create example showing decorator approach (for reference)
3. Show before/after examples
4. Document configuration options
5. Create comprehensive documentation

### 6.5 Key Implementation Patterns

#### 6.5.1 Configuration-Driven Pattern (PRIMARY)
```python
# Configuration loader at startup
security_config = load_security_config("security_config.yaml")

# Middleware that applies security based on configuration
@app.middleware("http")
async def security_middleware(request, call_next):
    route_path = request.url.path
    route_config = security_config.get_route_config(route_path)
    
    if route_config:
        # Apply role check
        user = await get_current_user(request)
        validate_roles(user, route_config.required_roles)
        
        # Apply department filtering if configured
        if route_config.filter_by_department:
            request.state.filter_by_department = True
            request.state.user_department = user.department_id
        
        # Apply sensitive data filtering if configured
        if route_config.require_sensitive_permission:
            request.state.filter_sensitive = True
            request.state.has_sensitive_permission = check_permission(
                user, "view_sensitive_data"
            )
    
    return await call_next(request)

# Dependency that reads from request state
def get_filtered_query(
    model: Type[Base],
    request: Request,
    session: Session = Depends(get_db)
) -> Query:
    """Return query filtered based on configuration and user context"""
    query = session.query(model)
    
    # Department filtering (from configuration)
    if getattr(request.state, 'filter_by_department', False):
        dept_id = request.state.user_department
        query = query.filter(model.department_id == dept_id)
    
    # Sensitive data filtering (from configuration)
    if getattr(request.state, 'filter_sensitive', False):
        if not getattr(request.state, 'has_sensitive_permission', False):
            query = query.filter(model.is_sensitive == False)
    
    return query
```

#### 6.5.2 Dependency Injection Pattern (Supporting Configuration)
```python
# FastAPI dependency for user context
async def get_current_user(
    request: Request,
    authorization: str = Header(None, alias="Authorization")
) -> User:
    """Extract and validate user from request"""
    # Demo: Authorization: Bearer <token>, where token is an integer user_id
    # Production: validate token and resolve roles via Azure AD
    user_id = parse_bearer_token_to_user_id(authorization)
    return auth_service.get_user_and_roles(user_id)
```

#### 6.5.3 Decorator Pattern (ALTERNATIVE EXAMPLE)
```python
def require_role(roles: List[str]):
    """Decorator to require specific roles (example/alternative approach)"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (injected by FastAPI)
            user = kwargs.get('current_user')
            if not user:
                raise HTTPException(401, "Authentication required")
            
            role_service.validate_user_roles(user, roles)
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage example (for reference):
@router.get("/employees")
@require_role(["manager", "hr"])
@filter_by_department()
async def get_employees(
    user: User = Depends(get_current_user),
    query: Query = Depends(get_filtered_query)
):
    return query.all()
```

---

## 7. Configuration Approach (PRIMARY METHOD)

### 7.1 Overview
The **configuration-driven approach is the primary and recommended method** for adding security to existing routes. This approach requires:
- **Zero code changes** to existing route handlers
- Security rules defined in YAML/JSON configuration files
- Automatic application via middleware and dependencies
- Easy maintenance and updates without code deployment

### 7.2 Configuration File Structure
```yaml
# security_config.yaml
security:
  auth:
    provider: "dummy"  # or "jwt", "oauth", etc.
  
  routes:
    "/employees":
      required_roles: ["manager", "hr"]
      filter_by_department: true
      require_sensitive_permission: false
      
    "/employees/{id}":
      required_roles: ["employee"]
      filter_by_department: true
      require_sensitive_permission: true
      
    "/performance-reviews":
      required_roles: ["hr_manager", "admin"]
      filter_by_department: false
      require_sensitive_permission: true

  permissions:
    view_sensitive_data:
      roles: ["admin", "hr_manager"]
    view_cross_department:
      roles: ["admin", "hr_manager"]
```

### 7.3 Configuration Loading and Application
- Load configuration at application startup
- Validate configuration schema using Pydantic
- Cache configuration for performance
- Support hot-reload in development
- Map route paths to security rules
- Apply rules via middleware before route execution

### 7.4 Route Matching Strategy
- Support exact path matching: `/employees`
- Support path parameter matching: `/employees/{id}`
- Support HTTP method-specific rules: `GET /employees` vs `POST /employees`
- Fallback to default security rules for unconfigured routes
- Priority: specific routes override general patterns

### 7.5 Configuration Example with Multiple Routes
```yaml
# security_config.yaml
security:
  auth:
    provider: "dummy"
    authorization_header: "Authorization"
    bearer_prefix: "Bearer"
  
  default:
    # Default rules for unconfigured routes
    required_roles: []
    filter_by_department: false
    require_sensitive_permission: false
  
  routes:
    # Exact path matching
    - path: "/employees"
      methods: ["GET"]
      required_roles: ["manager", "hr", "employee"]
      filter_by_department: true
      require_sensitive_permission: false
    
    # Path with parameter
    - path: "/employees/{id}"
      methods: ["GET"]
      required_roles: ["manager", "hr", "employee"]
      filter_by_department: true
      require_sensitive_permission: true  # Individual records may be sensitive
    
    # Different method, different rules
    - path: "/employees"
      methods: ["POST", "PUT", "DELETE"]
      required_roles: ["hr_manager", "admin"]
      filter_by_department: false
      require_sensitive_permission: false
    
    # Sensitive data endpoint
    - path: "/performance-reviews"
      methods: ["GET"]
      required_roles: ["hr_manager", "admin", "department_manager"]
      filter_by_department: true
      require_sensitive_permission: true
    
    # Admin-only endpoint
    - path: "/users"
      methods: ["GET", "POST", "PUT", "DELETE"]
      required_roles: ["admin"]
      filter_by_department: false
      require_sensitive_permission: false

  permissions:
    view_sensitive_data:
      roles: ["admin", "hr_manager"]
    view_cross_department:
      roles: ["admin", "hr_manager"]
    edit_employee_data:
      roles: ["admin", "hr_manager", "department_manager"]
```

---

## 8. Error Handling

### 8.1 HTTP Status Codes
- **401 Unauthorized**: Missing or invalid authentication
- **403 Forbidden**: Valid authentication but insufficient permissions
- **404 Not Found**: Resource not found (may be filtered out by permissions)

### 8.2 Error Response Format
```json
{
  "error": {
    "code": "INSUFFICIENT_PERMISSIONS",
    "message": "User does not have required role: manager",
    "details": {
      "required_roles": ["manager", "hr"],
      "user_roles": ["employee"]
    }
  }
}
```

---

## 9. Testing Strategy

### 9.1 Test Scenarios
1. **Role-based access**: User with correct role can access route
2. **Role-based denial**: User without role cannot access route
3. **Department filtering**: User sees only their department's data
4. **Cross-department access**: Admin/HR sees all departments
5. **Sensitive data filtering**: User without permission doesn't see sensitive rows
6. **Sensitive data access**: User with permission sees all data
7. **Combined scenarios**: Multiple security layers working together

### 9.2 Test Data Setup
- Multiple users with different roles
- Multiple departments with employees
- Mix of sensitive and non-sensitive records
- Cross-department scenarios

---

## 10. Documentation Requirements

### 10.1 Code Documentation
- **Docstrings**: All functions and classes
- **Type hints**: Full type annotations
- **Inline comments**: Explain complex logic and design decisions
- **Architecture comments**: Document design patterns used

### 10.2 User Documentation
- **README.md**: Project overview, setup, and usage
- **API_DOCUMENTATION.md**: Endpoint documentation with examples
- **SECURITY_GUIDE.md**: How to integrate security into existing routes
- **ARCHITECTURE.md**: Detailed architecture and design decisions

### 10.3 Example Documentation
- Before/after code examples
- Configuration examples
- Integration patterns
- Common use cases

---

## 11. Pythonic Best Practices

### 11.1 Code Style
- Follow PEP 8
- Use type hints throughout
- Leverage dataclasses and Pydantic models
- Use context managers for database sessions
- Implement `__repr__` and `__str__` for models

### 11.2 Design Patterns
- **Dependency Injection**: FastAPI's native DI system
- **Decorator Pattern**: Route protection decorators
- **Strategy Pattern**: Pluggable authentication providers
- **Factory Pattern**: Query builder factory
- **Repository Pattern**: Data access abstraction (optional)

### 11.3 Error Handling
- Use custom exception classes
- Leverage FastAPI's exception handlers
- Provide meaningful error messages
- Log security events appropriately

---

## 12. Integration Checklist

### 12.1 For Existing Routes (Configuration Approach)
- [ ] Identify routes requiring protection
- [ ] Determine required roles per route
- [ ] Identify department-filtered endpoints
- [ ] Mark sensitive data endpoints
- [ ] Add route configuration to `security_config.yaml`
- [ ] **No code changes needed** - security applied automatically
- [ ] Test with various user roles

### 12.2 For New Routes
- [ ] Add route handler (standard FastAPI code)
- [ ] Configure route in `security_config.yaml`
- [ ] Test authorization scenarios
- [ ] (Optional) Use decorator approach if explicit control needed

### 12.3 Decorator Approach (Alternative Example)
- [ ] Apply `@require_role()` decorator if using decorator pattern
- [ ] Add `@filter_by_department()` if needed
- [ ] Add dependencies to route handler signature
- [ ] Test authorization scenarios

---

## 13. Success Criteria

### 13.1 Functional Requirements
✅ Routes are protected by role-based access control  
✅ Department-based data filtering works automatically  
✅ Sensitive data requires additional permissions  
✅ **Zero code changes to existing route handlers**  
✅ **Configuration-driven security rules (primary method)**  
✅ Decorator-based approach available as example/alternative  

### 13.2 Non-Functional Requirements
✅ Code is well-annotated and documented  
✅ Follows Pythonic best practices  
✅ Easy to understand and maintain  
✅ Minimal performance overhead  
✅ Extensible for future requirements  

---

## 14. Future Considerations

### 14.1 Potential Enhancements
- JWT token authentication integration
- OAuth2 support
- Audit logging for security events
- Rate limiting per role
- Dynamic permission assignment
- Multi-tenant support
- Caching for permission checks

### 14.2 Production Readiness
- Replace dummy authentication with real provider
- Add comprehensive logging
- Implement audit trails
- Add monitoring and alerting
- Performance optimization
- Security hardening

---

## 15. Approval and Next Steps

### 15.1 Review Points
- [ ] Architecture approach approved
- [ ] Database schema reviewed
- [ ] Security model validated
- [ ] Integration strategy confirmed
- [ ] Configuration approach accepted

### 15.2 Implementation Phases
1. **Phase 1**: Core infrastructure and models
2. **Phase 2**: Configuration loader and validator
3. **Phase 3**: Configuration-driven route protection (PRIMARY)
4. **Phase 4**: Data filtering middleware
5. **Phase 5**: Decorator-based examples (ALTERNATIVE)
6. **Phase 6**: Documentation and examples

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-24  
**Status**: Pending Approval
