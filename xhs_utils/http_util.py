"""
HTTP 工具模块

功能：
1. xhs_get / xhs_post  带限速 + 随机延迟的请求封装
2. clean_cookie         存储前剥离高风险 Cookie 字段
3. RateLimiter          令牌桶限速器，全局控制请求频率
"""
from __future__ import annotations

import random
import re
import threading
import time
from typing import Optional

import requests

REQUEST_TIMEOUT = 15

# ==================== 随机延迟配置 ====================
# 每次请求后随机等待，模拟正常用户浏览间隔
_DELAY_MIN = 1.0   # 最短等待秒数
_DELAY_MAX = 3.0   # 最长等待秒数

# ==================== Cookie 清洗 ====================
_STRIP_COOKIE_PATTERNS = [
    r"(?:^|(?<=;\s))webId=[^;]*",
    r"(?:^|(?<=;\s))web_session=[^;]*",
]


# ==================== 令牌桶限速器 ====================

class RateLimiter:
    """
    令牌桶算法：
    - capacity    桶容量（最多积累的令牌数）
    - rate        每秒补充的令牌数
    - 每次请求消耗 1 个令牌，无令牌时阻塞等待
    """

    def __init__(self, rate: float = 0.5, capacity: int = 3):
        """
        rate=0.5  → 每 2 秒最多 1 个请求（平均）
        capacity=3 → 最多积累 3 个令牌（允许短暂突发）
        """
        self._rate     = rate
        self._capacity = capacity
        self._tokens   = float(capacity)
        self._last     = time.monotonic()
        self._lock     = threading.Lock()

    def acquire(self) -> None:
        """阻塞直到获取到令牌"""
        with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                # 等待到下一个令牌产生
                wait = (1.0 - self._tokens) / self._rate
        time.sleep(wait)

    def set_rate(self, rate: float, capacity: Optional[int] = None) -> None:
        with self._lock:
            self._rate = rate
            if capacity is not None:
                self._capacity = capacity


# 全局限速器：默认每 2 秒 1 个请求，允许短暂突发最多 3 个
_global_limiter = RateLimiter(rate=0.5, capacity=3)


def configure_rate(requests_per_second: float, burst: int = 3) -> None:
    """动态调整全局限速，可在应用启动时或设置页调用"""
    _global_limiter.set_rate(requests_per_second, burst)


# ==================== 请求封装 ====================

def _random_delay() -> None:
    time.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))


def xhs_get(url: str, **kwargs) -> requests.Response:
    """带全局限速 + 随机延迟的 GET 请求"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    _global_limiter.acquire()
    response = requests.get(url, **kwargs)
    _random_delay()
    return response


def xhs_post(url: str, **kwargs) -> requests.Response:
    """带全局限速 + 随机延迟的 POST 请求"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    _global_limiter.acquire()
    response = requests.post(url, **kwargs)
    _random_delay()
    return response


# ==================== Cookie 清洗 ====================

def clean_cookie(cookie_string: str) -> str:
    """
    存储前清洗 Cookie，剥离 webId 和 web_session。
    这两个字段是设备指纹和登录态标识，存储或传输时去掉降低封号风险。
    """
    if not cookie_string:
        return cookie_string
    result = cookie_string
    for pattern in _STRIP_COOKIE_PATTERNS:
        result = re.sub(pattern, "", result)
    result = re.sub(r";\s*;", ";", result)
    result = re.sub(r";\s*$", "", result)
    return result.strip("; ")
