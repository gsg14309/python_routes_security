from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    provider: str = "dummy"
    authorization_header: str = "Authorization"
    bearer_prefix: str = "Bearer"


class DefaultRule(BaseModel):
    auth_required: bool = True
    required_roles: list[str] = Field(default_factory=list)
    filter_by_department: bool = False
    require_sensitive_permission: bool = False


class RouteRule(BaseModel):
    path: str
    methods: list[str] = Field(default_factory=lambda: ["GET"])

    auth_required: bool | None = None
    required_roles: list[str] = Field(default_factory=list)
    filter_by_department: bool | None = None
    require_sensitive_permission: bool | None = None

    def normalized_methods(self) -> set[str]:
        return {m.upper() for m in self.methods}


class PermissionRule(BaseModel):
    roles: list[str] = Field(default_factory=list)


class SecurityConfigModel(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    default: DefaultRule = Field(default_factory=DefaultRule)
    routes: list[RouteRule] = Field(default_factory=list)
    permissions: dict[str, PermissionRule] = Field(default_factory=dict)


@dataclass(frozen=True)
class EffectiveRule:
    """
    Fully-resolved rule (defaults applied) for a particular request.
    """

    auth_required: bool
    required_roles: frozenset[str]
    filter_by_department: bool
    require_sensitive_permission: bool


def _path_template_to_regex(path_template: str) -> re.Pattern[str]:
    # Convert "/employees/{id}" -> r"^/employees/[^/]+$"
    # Keep it intentionally small/safe for a demo project.
    regex = re.sub(r"\{[^/]+\}", r"[^/]+", path_template)
    return re.compile(rf"^{regex}$")


class SecurityConfig:
    """
    Runtime helper around validated config + route matching.
    """

    def __init__(self, model: SecurityConfigModel):
        self.model = model

        compiled: list[tuple[str, re.Pattern[str], RouteRule]] = []
        for rule in self.model.routes:
            compiled.append((rule.path, _path_template_to_regex(rule.path), rule))

        # Prefer exact matches over templates.
        self._exact_rules: dict[str, list[RouteRule]] = {}
        for r in self.model.routes:
            self._exact_rules.setdefault(r.path, []).append(r)
        self._compiled_rules = compiled

    @property
    def auth(self) -> AuthConfig:
        return self.model.auth

    def permission_roles(self, permission_name: str) -> frozenset[str]:
        perm = self.model.permissions.get(permission_name)
        if not perm:
            return frozenset()
        return frozenset(perm.roles)

    def match(self, path: str, method: str) -> EffectiveRule:
        """
        Find the best matching rule for (path, method), then apply defaults.
        """

        method = method.upper()
        default = self.model.default

        # 1) exact path match
        exact_candidates = self._exact_rules.get(path, [])
        for candidate in exact_candidates:
            if method in candidate.normalized_methods():
                return _effective(candidate, default)

        # 2) template match
        for _template, regex, candidate in self._compiled_rules:
            if method not in candidate.normalized_methods():
                continue
            if regex.match(path):
                return _effective(candidate, default)

        # 3) no match -> defaults
        return EffectiveRule(
            auth_required=default.auth_required,
            required_roles=frozenset(default.required_roles),
            filter_by_department=default.filter_by_department,
            require_sensitive_permission=default.require_sensitive_permission,
        )


def _effective(rule: RouteRule, default: DefaultRule) -> EffectiveRule:
    # If a rule has any security requirements, treat it as auth-required even if
    # the global default is "public".
    inferred_auth_required = (
        default.auth_required
        or bool(rule.required_roles)
        or bool(rule.filter_by_department)
        or bool(rule.require_sensitive_permission)
    )

    return EffectiveRule(
        auth_required=inferred_auth_required if rule.auth_required is None else rule.auth_required,
        required_roles=frozenset(rule.required_roles or default.required_roles),
        filter_by_department=default.filter_by_department if rule.filter_by_department is None else rule.filter_by_department,
        require_sensitive_permission=default.require_sensitive_permission
        if rule.require_sensitive_permission is None
        else rule.require_sensitive_permission,
    )


def load_security_config(path: Path) -> SecurityConfig:
    raw_text = path.read_text(encoding="utf-8")
    raw: dict[str, Any] = yaml.safe_load(raw_text) or {}

    if "security" not in raw:
        raise ValueError(f"Missing top-level 'security' key in config: {path}")

    model = SecurityConfigModel.model_validate(raw["security"])
    return SecurityConfig(model)

