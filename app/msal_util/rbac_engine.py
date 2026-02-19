"""
RBAC engine and YAML loader.

Implements the requirements in RBAC_REQUIREMENTS.md using the
roles → permissions → endpoint rules model.

Key ideas:
- Load YAML once at startup (roles + permissions + optional public rules).
- Resolve role inheritance (extends) and detect cycles.
- Precompute effective permissions per role.
- At runtime, answer:
    is_public(method, path)?
    is_allowed(user_roles, method, path)?

This module is pure Python and has no FastAPI dependency. A separate
integration module can plug this into FastAPI dependencies or middleware.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Iterable, Mapping

import yaml

logger = logging.getLogger(__name__)


# ---- Data structures -----------------------------------------------------------------


@dataclass(frozen=True)
class RbacRule:
    """Single rule: which HTTP methods are allowed on a given path pattern."""

    path_template: str
    methods: frozenset[str]


@dataclass(frozen=True)
class PermissionDef:
    """Permission definition loaded from YAML."""

    name: str
    rules: tuple[RbacRule, ...]
    public: bool = False


@dataclass(frozen=True)
class RoleDef:
    """Role definition loaded from YAML (direct permissions and parent link)."""

    name: str
    permissions: frozenset[str]
    extends: str | None = None
    display_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class RbacConfig:
    """Fully-loaded RBAC configuration."""

    roles: Mapping[str, RoleDef]
    permissions: Mapping[str, PermissionDef]
    public_rules: tuple[RbacRule, ...]


# ---- Helpers -------------------------------------------------------------------------


_PATH_PARAM_RE = re.compile(r"\{[^/]+\}")


def _path_template_to_regex(path_template: str) -> re.Pattern[str]:
    """
    Convert a simple path template into a compiled regex.

    Example:
        /content/{id}  ->  ^/content/[^/]+$
    """

    regex = _PATH_PARAM_RE.sub(r"[^/]+", path_template)
    return re.compile(rf"^{regex}$")


def _normalize_methods(methods: Iterable[str]) -> frozenset[str]:
    return frozenset(m.upper() for m in methods)


# ---- Loader and inheritance resolution ----------------------------------------------


class RbacConfigError(ValueError):
    """Raised when the RBAC YAML configuration is invalid."""


def load_rbac_config(path: Path) -> RbacConfig:
    """
    Load and validate RBAC YAML from disk.

    Expected shape (simplified):

        roles:
          reader:
            extends: null | some_role
            permissions: [content.read, ...]

        permissions:
          content.read:
            public: false
            rules:
              - path: /content
                methods: [GET]
              - path: /content/{id}
                methods: [GET]

        public:
          - path: /about
            methods: [GET]
          - path: /status
            methods: [GET]
    """

    raw_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text) or {}

    roles_raw = raw.get("roles") or {}
    perms_raw = raw.get("permissions") or {}
    public_raw = raw.get("public") or []

    if not isinstance(roles_raw, dict):
        raise RbacConfigError("roles must be a mapping")
    if not isinstance(perms_raw, dict):
        raise RbacConfigError("permissions must be a mapping")
    if not isinstance(public_raw, list):
        raise RbacConfigError("public must be a list when present")

    # Parse permissions
    permissions: dict[str, PermissionDef] = {}
    for perm_name, perm_val in perms_raw.items():
        if not isinstance(perm_val, dict):
            raise RbacConfigError(f"permission {perm_name!r} must be a mapping")
        public_flag = bool(perm_val.get("public", False))
        rules_raw = perm_val.get("rules") or []
        if not isinstance(rules_raw, list):
            raise RbacConfigError(f"permission {perm_name!r}.rules must be a list")

        rules: list[RbacRule] = []
        for rule in rules_raw:
            if not isinstance(rule, dict):
                raise RbacConfigError(f"permission {perm_name!r}.rules entries must be mappings")
            path_template = str(rule.get("path", "")).strip()
            methods_raw = rule.get("methods") or []
            if not path_template:
                raise RbacConfigError(f"permission {perm_name!r}.rules requires non-empty path")
            if not isinstance(methods_raw, list) or not methods_raw:
                raise RbacConfigError(f"permission {perm_name!r}.rules[{path_template!r}] must have methods list")
            rules.append(RbacRule(path_template=path_template, methods=_normalize_methods(methods_raw)))

        permissions[perm_name] = PermissionDef(
            name=perm_name,
            rules=tuple(rules),
            public=public_flag,
        )

    # Parse roles
    roles: dict[str, RoleDef] = {}
    for role_name, role_val in roles_raw.items():
        if not isinstance(role_val, dict):
            raise RbacConfigError(f"role {role_name!r} must be a mapping")
        extends = role_val.get("extends")
        if extends is not None:
            extends = str(extends).strip() or None
        perms_list = role_val.get("permissions") or []
        if not isinstance(perms_list, list):
            raise RbacConfigError(f"role {role_name!r}.permissions must be a list when present")
        perms = frozenset(str(p) for p in perms_list)
        display_name = role_val.get("display_name")
        description = role_val.get("description") or role_val.get("Description")

        roles[role_name] = RoleDef(
            name=role_name,
            permissions=perms,
            extends=extends,
            display_name=str(display_name) if display_name is not None else None,
            description=str(description) if description is not None else None,
        )

    # Validate extends targets exist
    for role in roles.values():
        if role.extends and role.extends not in roles:
            raise RbacConfigError(f"role {role.name!r} extends unknown role {role.extends!r}")

    # Validate that permissions referenced by roles exist
    for role in roles.values():
        unknown = role.permissions.difference(permissions.keys())
        if unknown:
            raise RbacConfigError(f"role {role.name!r} references unknown permissions: {sorted(unknown)}")

    # Compute public rules (from top-level public section)
    public_rules: list[RbacRule] = []
    for entry in public_raw:
        if not isinstance(entry, dict):
            raise RbacConfigError("public entries must be mappings")
        path_template = str(entry.get("path", "")).strip()
        methods_raw = entry.get("methods") or []
        if not path_template:
            raise RbacConfigError("public rule requires non-empty path")
        if not isinstance(methods_raw, list) or not methods_raw:
            raise RbacConfigError(f"public rule {path_template!r} must have methods list")
        public_rules.append(RbacRule(path_template=path_template, methods=_normalize_methods(methods_raw)))

    # Also treat any permission with public: true as contributing public rules
    for perm in permissions.values():
        if perm.public:
            public_rules.extend(perm.rules)

    return RbacConfig(
        roles=roles,
        permissions=permissions,
        public_rules=tuple(public_rules),
    )


def _compute_effective_permissions(config: RbacConfig) -> dict[str, frozenset[str]]:
    """
    Resolve role inheritance and compute effective permissions per role.

    Detect cycles in extends and raise RbacConfigError if found.
    """

    effective: dict[str, frozenset[str]] = {}
    visiting: set[str] = set()

    def dfs(role_name: str) -> frozenset[str]:
        if role_name in effective:
            return effective[role_name]
        if role_name in visiting:
            raise RbacConfigError(f"cycle detected in role inheritance at {role_name!r}")
        visiting.add(role_name)
        role = config.roles[role_name]
        perms = set(role.permissions)
        if role.extends:
            parent_perms = dfs(role.extends)
            perms.update(parent_perms)
        result = frozenset(perms)
        effective[role_name] = result
        visiting.remove(role_name)
        return result

    for name in config.roles.keys():
        dfs(name)

    return effective


# ---- RBAC engine ---------------------------------------------------------------------


class RbacEngine:
    """
    In-memory RBAC engine built from a validated RbacConfig.

    Usage:
        config = load_rbac_config(Path(\"rbac.yaml\"))
        engine = RbacEngine.from_config(config)
        allowed = engine.is_allowed({\"modeller\"}, \"POST\", \"/content\")
    """

    def __init__(
        self,
        config: RbacConfig,
        effective_permissions: Mapping[str, frozenset[str]],
    ) -> None:
        self._config = config
        self._effective_permissions = dict(effective_permissions)

        # Compile path patterns to regexes for faster matching
        self._public_patterns = [
            (_path_template_to_regex(rule.path_template), rule.methods) for rule in config.public_rules
        ]

        # Precompute permission → list of (regex, methods)
        perm_routes: dict[str, list[tuple[re.Pattern[str], frozenset[str]]]] = {}
        for perm_name, perm in config.permissions.items():
            routes: list[tuple[re.Pattern[str], frozenset[str]]] = []
            for rule in perm.rules:
                routes.append((_path_template_to_regex(rule.path_template), rule.methods))
            perm_routes[perm_name] = routes
        self._perm_routes = perm_routes

    @classmethod
    def from_yaml(cls, path: Path) -> RbacEngine:
        """Convenience: load YAML and build an engine in one step."""
        cfg = load_rbac_config(path)
        eff = _compute_effective_permissions(cfg)
        return cls(cfg, eff)

    @property
    def config(self) -> RbacConfig:
        return self._config

    @property
    def effective_permissions(self) -> Mapping[str, frozenset[str]]:
        """Effective permissions per role (after inheritance)."""
        return dict(self._effective_permissions)

    # ---- Matching helpers -----------------------------------------------------------

    def _matches_any(
        self,
        patterns: list[tuple[re.Pattern[str], frozenset[str]]],
        method: str,
        path: str,
    ) -> bool:
        method = method.upper()
        for regex, methods in patterns:
            if method in methods and regex.match(path):
                return True
        return False

    def _required_permissions_for(self, method: str, path: str) -> frozenset[str]:
        """Return set of permission names whose rules match (method, path)."""
        method = method.upper()
        required: set[str] = set()
        for perm_name, routes in self._perm_routes.items():
            for regex, methods in routes:
                if method in methods and regex.match(path):
                    required.add(perm_name)
                    break
        return frozenset(required)

    # ---- Public vs RBAC-protected ---------------------------------------------------

    def is_public(self, method: str, path: str) -> bool:
        """Return True if (method, path) is marked as public in config."""
        return self._matches_any(self._public_patterns, method, path)

    # ---- Main decision API ----------------------------------------------------------

    def is_allowed(self, user_roles: Iterable[str], method: str, path: str) -> bool:
        """
        Decide if access is allowed for the given user roles, HTTP method and path.

        Algorithm:
        1. If (method, path) is public -> allow.
        2. Find all permissions whose rules match (method, path).
        3. Compute the union of effective permissions for all user roles.
        4. If intersection is non-empty -> allow, else deny.

        Unknown roles are ignored (treated as having no permissions).
        """

        if self.is_public(method, path):
            return True

        required_perms = self._required_permissions_for(method, path)
        if not required_perms:
            # No rule defined -> fail closed; config should be explicit.
            logger.debug("RBAC: no matching rules for method=%s path=%s", method, path)
            return False

        user_perms: set[str] = set()
        for role in user_roles:
            eff = self._effective_permissions.get(role)
            if eff:
                user_perms.update(eff)

        if not user_perms:
            logger.debug(
                "RBAC: user has no effective permissions roles=%s method=%s path=%s",
                sorted(user_roles),
                method,
                path,
            )
            return False

        if user_perms & required_perms:
            logger.debug(
                "RBAC: allowed roles=%s method=%s path=%s perms=%s",
                sorted(user_roles),
                method,
                path,
                sorted(user_perms & required_perms),
            )
            return True

        logger.debug(
            "RBAC: denied roles=%s method=%s path=%s required_perms=%s user_perms=%s",
            sorted(user_roles),
            method,
            path,
            sorted(required_perms),
            sorted(user_perms),
        )
        return False

