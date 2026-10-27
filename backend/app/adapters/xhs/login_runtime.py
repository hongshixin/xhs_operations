from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, RLock
from time import monotonic
from typing import Any


@dataclass
class LoginRuntime:
    api: Any
    subject: str | None = None
    created_at: float = field(default_factory=monotonic)
    lock: Lock = field(default_factory=Lock)


class LoginRuntimeStore:
    """Keep one SDK device session alive across QR polling or SMS confirmation."""

    def __init__(self, lifetime_seconds: int = 600):
        self._lifetime_seconds = lifetime_seconds
        self._items: dict[str, LoginRuntime] = {}
        self._lock = RLock()

    def add(self, key: str, api: Any, *, subject: str | None = None) -> None:
        # 登录签名依赖初始设备状态，扫码轮询和短信确认都不能重新构造客户端。
        with self._lock:
            self._discard_expired()
            self._items[str(key)] = LoginRuntime(api, subject=subject)

    def get(self, key: str) -> LoginRuntime:
        with self._lock:
            self._discard_expired()
            runtime = self._items.get(str(key))
            if runtime is None:
                raise RuntimeError("登录会话已失效，请重新获取二维码或验证码")
            return runtime

    def discard(self, key: str) -> None:
        with self._lock:
            runtime = self._items.pop(str(key), None)
        if runtime is not None:
            with runtime.lock:
                runtime.api.close()

    def _discard_expired(self) -> None:
        # 超时会话不能复用旧指纹，释放连接后由用户重新生成二维码。
        now = monotonic()
        expired = [key for key, value in self._items.items() if now - value.created_at > self._lifetime_seconds]
        for key in expired:
            runtime = self._items.pop(key)
            with runtime.lock:
                runtime.api.close()
