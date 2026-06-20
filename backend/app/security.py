"""单密码门：cookie token + middleware 统一拦截。

启用条件：AHAMVOICE_ACCESS_PASSWORD 非空。
token 存内存（进程级 set），重启失效，不设过期。

设计取舍：
- Cookie 而非 Authorization Header：浏览器原生支持，前端 fetch 加
  credentials:'include' 即可，手机浏览器兼容好。
- token 存内存不存 DB：重启重新登录可接受；存 DB 要加表（与删多用户表冲突）。
- 密码明文比对（hmac.compare_digest 防时序攻击）：单密码门不是用户密码库，
  密码在 .env 也是明文，哈希只是表演。
- 不设过期：单机自用，登录一次一直有效。重置靠重启或改密码。
- middleware 统一拦截而非每路由 Depends：原版每路由 Depends(current_user)，
  改 100 个路由签名不如一个 middleware 检查白名单 + cookie。
"""
from __future__ import annotations

import hmac
import os
import secrets
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

COOKIE_NAME = "aham_token"

# 不需要 token 的路径：登录本身 + 健康检查 + 静态资源（否则登录页打不开）
WHITELIST_PREFIXES = ("/api/auth/login", "/api/health", "/assets/")
WHITELIST_EXACT = ("/", "/favicon.svg", "/favicon.ico", "/index.html", "/login")


class Security:
    """密码门状态：密码 + 已发放的 token 集合（进程级内存）。"""

    def __init__(self, password: str | None) -> None:
        self.enabled = bool(password)
        self._password = password or ""
        self._tokens: set[str] = set()

    def login(self, creds: dict[str, Any]) -> JSONResponse:
        if not self.enabled:
            return JSONResponse({"ok": True})
        password = (creds.get("password") or "").strip()
        if not hmac.compare_digest(password, self._password):
            return JSONResponse({"detail": "密码错误"}, status_code=401)
        token = secrets.token_urlsafe(32)
        self._tokens.add(token)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
        return resp

    def is_authorized(self, request: Request) -> bool:
        if not self.enabled:
            return True
        path = request.url.path
        if path in WHITELIST_EXACT or any(path.startswith(p) for p in WHITELIST_PREFIXES):
            return True
        token = request.cookies.get(COOKIE_NAME)
        return token in self._tokens


class SecurityMiddleware(BaseHTTPMiddleware):
    """拦截所有非白名单 /api/* 请求，校验 cookie token。"""

    def __init__(self, app: ASGIApp, security: Security) -> None:
        super().__init__(app)
        self._security = security

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and not self._security.is_authorized(request):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return await call_next(request)


def build_security() -> Security:
    """从 env 读密码构造 Security。空密码 → 不启用。"""
    return Security(password=os.environ.get("AHAMVOICE_ACCESS_PASSWORD") or None)
