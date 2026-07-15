"""
HTML 降级解析模块
当签名算法失效或 Cookie 过期时，直接请求小红书网页 URL，
从 window.__INITIAL_STATE__ 中提取笔记数据，无需签名和 Cookie。

参考：XHS-Downloader 的 Converter 实现
"""
from __future__ import annotations

import re
from typing import Any

import requests
from lxml.etree import HTML
from yaml import safe_load

from xhs_utils.http_util import REQUEST_TIMEOUT

USERAGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
)

_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9",
    "referer": "https://www.xiaohongshu.com/explore",
    "user-agent": USERAGENT,
}

# window.__INITIAL_STATE__ 里笔记数据的路径（PC 版和手机版两种结构）
_PC_KEYS = ("note", "noteDetailMap", "[-1]", "note")
_PHONE_KEYS = ("noteData", "data", "noteData")

_YAML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_NOTE_ID_RE = re.compile(r"(?:explore|item)/([a-zA-Z0-9]+)")


def _extract_note_id(url: str) -> str:
    m = _NOTE_ID_RE.search(url)
    return m.group(1) if m else url.rstrip("/").split("/")[-1]


def _fetch_html(url: str, cookie: str = "") -> str:
    headers = _HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _extract_initial_state(html: str) -> str:
    tree = HTML(html)
    scripts = tree.xpath("//script/text()")
    scripts.reverse()
    return next(
        (s for s in scripts if s.startswith("window.__INITIAL_STATE__")),
        "",
    )


def _parse_initial_state(script: str) -> dict:
    cleaned = _YAML_ILLEGAL.sub("", script.lstrip("window.__INITIAL_STATE__="))
    return safe_load(cleaned) or {}


def _deep_get(data: Any, keys: tuple) -> Any:
    try:
        for key in keys:
            if key.startswith("[") and key.endswith("]"):
                idx = int(key[1:-1])
                data = list(data.values())[idx] if isinstance(data, dict) else data[idx]
            else:
                data = data[key]
        return data
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _get_note_data(state: dict) -> dict:
    return _deep_get(state, _PHONE_KEYS) or _deep_get(state, _PC_KEYS) or {}


def _extract_image_token(url: str) -> str:
    """从图片 URL 提取 token，用于拼接无水印 CDN 地址"""
    return "/".join(url.split("/")[5:]).split("!")[0]


def _image_url(token: str, fmt: str = "jpeg") -> str:
    return f"https://ci.xiaohongshu.com/{token}?imageView2/format/{fmt}"


def _safe_extract(data: Any, path: str, default: Any = None) -> Any:
    """点路径取值，支持 list[0] 写法"""
    keys = path.split(".")
    cur = data
    try:
        for key in keys:
            if key.endswith("]") and "[" in key:
                k, idx = key.split("[")
                if k:
                    cur = cur[k]
                cur = cur[int(idx.rstrip("]"))]
            elif isinstance(cur, dict):
                cur = cur[key]
            elif isinstance(cur, list):
                cur = cur[int(key)]
            else:
                return default
        return cur if cur is not None else default
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def _parse_note(note_data: dict, note_url: str = "") -> dict:
    """把 __INITIAL_STATE__ 里的笔记数据归一化为标准格式"""
    note_id = _safe_extract(note_data, "noteId", "")
    title = _safe_extract(note_data, "title", "")
    desc = _safe_extract(note_data, "desc", "")
    note_type = _safe_extract(note_data, "type", "normal")

    # 作者
    user = _safe_extract(note_data, "user", {}) or {}
    author_id = _safe_extract(user, "userId", "")
    author_name = _safe_extract(user, "nickname", "") or _safe_extract(user, "nickName", "")
    author_avatar = _safe_extract(user, "avatar", "") or _safe_extract(user, "avatarUrl", "")

    # 互动数据
    interact = _safe_extract(note_data, "interactInfo", {}) or {}
    likes = _safe_extract(interact, "likedCount", 0)
    collects = _safe_extract(interact, "collectedCount", 0)
    comments_count = _safe_extract(interact, "commentCount", 0)
    shares = _safe_extract(interact, "shareCount", 0)

    # 标签
    tag_list = _safe_extract(note_data, "tagList", []) or []
    tags = [t.get("name", "") for t in tag_list if isinstance(t, dict) and t.get("name")]

    # 发布时间
    publish_time = _safe_extract(note_data, "time", 0)

    # 图片列表（含 Live Photo 动图）
    image_list = _safe_extract(note_data, "imageList", []) or []
    image_urls: list[str] = []
    live_photo_urls: list[str] = []

    for img in image_list:
        if not isinstance(img, dict):
            continue
        raw_url = img.get("urlDefault") or img.get("url") or ""
        if raw_url:
            try:
                token = _extract_image_token(raw_url)
                image_urls.append(_image_url(token))
            except Exception:
                image_urls.append(raw_url)
        # Live Photo 动图地址
        live_url = (
            _safe_extract(img, "stream.h264[0].masterUrl", "")
            or _safe_extract(img, "livePhoto", "")
        )
        live_photo_urls.append(live_url or "")

    # 视频地址
    video_url = ""
    if note_type == "video":
        video_url = (
            _safe_extract(note_data, "video.media.stream.h264[0].masterUrl", "")
            or _safe_extract(note_data, "video.consumer.originVideoKey", "")
        )
        if not video_url:
            origin_key = _safe_extract(note_data, "video.consumer.originVideoKey", "")
            if origin_key:
                video_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"

    cover_url = image_urls[0] if image_urls else ""

    return {
        "note_id": note_id,
        "note_url": note_url or f"https://www.xiaohongshu.com/explore/{note_id}",
        "title": title,
        "content": desc,
        "type": note_type,
        "author_id": author_id,
        "author_name": author_name,
        "author_avatar": author_avatar,
        "cover_url": cover_url,
        "image_urls": image_urls,
        "live_photo_urls": live_photo_urls,
        "video_url": video_url,
        "tags": tags,
        "likes": likes,
        "collects": collects,
        "comments": comments_count,
        "shares": shares,
        "publish_time": publish_time,
        "_source": "html_fallback",
    }


def get_note_by_url(url: str, cookie: str = "") -> dict | None:
    """
    通过笔记 URL 直接解析网页获取笔记数据。
    不需要签名，Cookie 可选（有 Cookie 能获取更完整数据）。
    返回归一化的笔记 dict，失败返回 None。
    """
    try:
        html = _fetch_html(url, cookie)
        script = _extract_initial_state(html)
        if not script:
            return None
        state = _parse_initial_state(script)
        note_data = _get_note_data(state)
        if not note_data:
            return None
        return _parse_note(note_data, note_url=url)
    except Exception:
        return None
