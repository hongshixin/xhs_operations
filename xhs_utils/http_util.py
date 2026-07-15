import random
import re
import time

import requests

REQUEST_TIMEOUT = 15

# 每次请求后随机等待 0.5 ~ 2.0 秒，模拟正常用户行为
_DELAY_MIN = 0.5
_DELAY_MAX = 2.0

# 存储 Cookie 时需要剥离的高风险字段（设备指纹 / 登录态标识）
_STRIP_COOKIE_PATTERNS = [
    r"(?:^|(?<=;\s))webId=[^;]*",
    r"(?:^|(?<=;\s))web_session=[^;]*",
]


def _random_delay():
    time.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))


def xhs_get(url, **kwargs):
    """带随机延迟的 GET 请求，替代 requests.get"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    response = requests.get(url, **kwargs)
    _random_delay()
    return response


def xhs_post(url, **kwargs):
    """带随机延迟的 POST 请求，替代 requests.post"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    response = requests.post(url, **kwargs)
    _random_delay()
    return response


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
    # 清理多余分号和空格
    result = re.sub(r";\s*;", ";", result)
    result = re.sub(r";\s*$", "", result)
    return result.strip("; ")
