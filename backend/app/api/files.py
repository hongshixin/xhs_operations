from __future__ import annotations

from pathlib import Path
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.deps import get_current_user
from backend.app.core.database import get_db
from backend.app.core.security import create_capture_token, decode_token
from backend.app.models import AiGeneratedAsset, Note, NoteAsset, User
from backend.app.services.image_util import compose_cover_image, resize_image_file

router = APIRouter(prefix="/files", tags=["files"])
_capture_pairings: dict[str, tuple[int, float]] = {}
_capture_pairing_lock = threading.Lock()


class ComposeImageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=800)
    width: int = Field(default=1080, ge=320, le=2400)
    height: int = Field(default=1440, ge=320, le=3200)
    background_color: str = Field(default="#fafaf8", max_length=16)
    accent_color: str = Field(default="#111111", max_length=16)


class ResizeImageRequest(BaseModel):
    source_file_name: str = Field(min_length=1, max_length=180)
    width: int = Field(default=1080, ge=128, le=2400)
    height: int = Field(default=1440, ge=128, le=3200)
    mode: Literal["cover", "contain"] = "cover"
    format: Literal["png", "jpeg"] = "png"
    quality: int = Field(default=90, ge=40, le=100)


def _export_media_type(file_name: str) -> str:
    if file_name.endswith(".csv"):
        return "text/csv; charset=utf-8"
    return "application/json"


def _media_dir() -> Path:
    return Path(get_settings().storage_dir) / "media"


def _owner_media_prefix(current_user: User) -> str:
    return f"xhs-image-u{current_user.id}-"


def _validate_owner_media_name(file_name: str, current_user: User) -> str:
    if Path(file_name).name != file_name or ".." in file_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    valid_prefixes = (_owner_media_prefix(current_user), f"xhs-asset-u{current_user.id}-", f"xhs-upload-u{current_user.id}-")
    if not file_name.startswith(valid_prefixes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    return file_name


def _media_type(file_name: str) -> str:
    lower = file_name.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".mov"):
        return "video/quicktime"
    if lower.endswith(".avi"):
        return "video/x-msvideo"
    if lower.endswith(".mkv"):
        return "video/x-matroska"
    return "image/png"


def _upload_title(file: Path) -> str:
    """优先展示上传时的原始名称，旧文件没有元数据时仍可正常列出。"""
    metadata = file.with_suffix(file.suffix + ".json")
    if metadata.is_file():
        try:
            return str(json.loads(metadata.read_text(encoding="utf-8")).get("original_name") or file.name)
        except (OSError, ValueError):
            pass
    return file.name


def _source_platform(source_url: str) -> str:
    host = (urlparse(source_url).hostname or "").lower()
    if host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com"):
        return "xhs"
    if host == "douyin.com" or host.endswith(".douyin.com"):
        return "douyin"
    if host in {"taobao.com", "tmall.com"} or host.endswith(".taobao.com") or host.endswith(".tmall.com"):
        return "taobao"
    if host == "jd.com" or host.endswith(".jd.com"):
        return "jd"
    return "other"


def _upload_metadata(file: Path) -> dict:
    metadata = file.with_suffix(file.suffix + ".json")
    try:
        return json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else {}
    except (OSError, ValueError):
        return {}


def _serialize_media_file(*, file_name: str, width: int, height: int) -> dict:
    return {
        "file_name": file_name,
        "file_path": str(_media_dir() / file_name),
        "download_url": f"/api/files/media/{file_name}",
        "width": width,
        "height": height,
        "media_type": _media_type(file_name),
    }


@router.get("/images")
def list_user_images(current_user: User = Depends(get_current_user)):
    prefix = f"xhs-upload-u{current_user.id}-"
    media_dir = _media_dir()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    files = []
    if media_dir.is_dir():
        for f in sorted(media_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.name.startswith(prefix) and f.suffix.lower() in image_exts:
                files.append({"file_name": f.name, "title": _upload_title(f), "url": f"/api/files/media/{f.name}", "size": f.stat().st_size, "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
    return {"items": files}


@router.get("/library")
def list_asset_library(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """按统一格式汇集三种来源，原始文件仍由各自模块管理。"""
    items: list[dict] = []
    media_dir = _media_dir()
    if media_dir.is_dir():
        for file in media_dir.iterdir():
            if file.is_file() and file.name.startswith(f"xhs-upload-u{current_user.id}-") and file.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS:
                stat = file.stat()
                metadata = _upload_metadata(file)
                items.append({"id": f"upload:{file.name}", "source": "web" if metadata.get("origin") == "web" else "upload", "source_platform": metadata.get("source_platform", ""), "source_url": metadata.get("source_url", ""), "asset_type": "video" if file.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"} else "image", "title": metadata.get("title") or metadata.get("original_name") or file.name, "url": f"/api/files/media/{file.name}", "local_path": file.name, "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(), "size": stat.st_size})

    generated = db.scalars(select(AiGeneratedAsset).where(AiGeneratedAsset.user_id == current_user.id)).all()
    for asset in generated:
        if asset.file_path:
            items.append({"id": f"ai:{asset.id}", "source": "ai", "asset_type": "image", "title": asset.prompt or "AI 生成图片", "url": asset.file_path, "local_path": "", "created_at": asset.created_at.isoformat(), "size": None})

    # 通过笔记归属过滤素材，避免把其他用户采集的图片展示到当前素材库。
    note_assets = db.execute(select(NoteAsset, Note).join(Note, Note.id == NoteAsset.note_id).where(Note.user_id == current_user.id)).all()
    for asset, note in note_assets:
        url = f"/api/files/media/{Path(asset.local_path).name}" if asset.local_path else asset.url
        if url:
            items.append({"id": f"note:{asset.id}", "source": "note", "asset_type": asset.asset_type, "title": note.title or "笔记素材", "url": url, "local_path": Path(asset.local_path).name if asset.local_path else "", "created_at": note.created_at.isoformat(), "size": None})
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


def find_duplicate_upload(media_dir: Path, user_id: int, content: bytes) -> Path | None:
    """仅对当前用户上传的同字节文件去重，不把视觉相似图片误判为同一素材。"""
    if not media_dir.is_dir():
        return None
    digest = hashlib.sha256(content).digest()
    prefix = f"xhs-upload-u{user_id}-"
    for file in media_dir.iterdir():
        if file.is_file() and file.name.startswith(prefix) and file.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS and file.stat().st_size == len(content):
            # 流式读取旧素材，避免多个大视频使上传请求占用过多内存。
            hasher = hashlib.sha256()
            with file.open("rb") as existing:
                for block in iter(lambda: existing.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.digest() == digest:
                return file
    return None


@router.delete("/images/{file_name}")
def delete_user_image(file_name: str, current_user: User = Depends(get_current_user)):
    prefix = f"xhs-upload-u{current_user.id}-"
    if Path(file_name).name != file_name or ".." in file_name or not file_name.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    file_path = _media_dir() / file_name
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    file_path.unlink()
    file_path.with_suffix(file_path.suffix + ".json").unlink(missing_ok=True)
    return {"file_name": file_name, "status": "deleted"}


@router.post("/images/compose")
def compose_image(payload: ComposeImageRequest, current_user: User = Depends(get_current_user)):
    file_name = f"{_owner_media_prefix(current_user)}{uuid4().hex}.png"
    output_path = _media_dir() / file_name
    compose_cover_image(
        output_path=output_path,
        title=payload.title,
        body=payload.body,
        width=payload.width,
        height=payload.height,
        background_color=payload.background_color,
        accent_color=payload.accent_color,
    )
    return _serialize_media_file(file_name=file_name, width=payload.width, height=payload.height)


@router.post("/images/resize")
def resize_image(payload: ResizeImageRequest, current_user: User = Depends(get_current_user)):
    source_file_name = _validate_owner_media_name(payload.source_file_name, current_user)
    source_path = _media_dir() / source_file_name
    if not source_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")

    extension = "jpg" if payload.format == "jpeg" else "png"
    file_name = f"{_owner_media_prefix(current_user)}{uuid4().hex}.{extension}"
    output_path = _media_dir() / file_name
    resize_image_file(
        source_path=source_path,
        output_path=output_path,
        width=payload.width,
        height=payload.height,
        mode=payload.mode,
        image_format=payload.format,
        quality=payload.quality,
    )
    return _serialize_media_file(file_name=file_name, width=payload.width, height=payload.height)


@router.get("/media/{file_name}")
def download_media(file_name: str):
    if Path(file_name).name != file_name or ".." in file_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    file_path = _media_dir() / file_name
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    return FileResponse(file_path, filename=file_name, media_type=_media_type(file_name))


@router.get("/exports/{file_name}")
def download_export(file_name: str, current_user: User = Depends(get_current_user)):
    if Path(file_name).name != file_name or ".." in file_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")

    owner_prefixes = (f"xhs-notes-u{current_user.id}-", f"xhs-report-u{current_user.id}-")
    if not file_name.startswith(owner_prefixes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")

    export_dir = Path(get_settings().storage_dir) / "exports"
    file_path = export_dir / file_name
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")

    return FileResponse(file_path, filename=file_name, media_type=_export_media_type(file_name))


ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024


class CapturePairRequest(BaseModel):
    code: str = Field(min_length=8, max_length=32)


@router.post("/capture/pair/start")
def start_capture_pair(current_user: User = Depends(get_current_user)):
    # 配对码只在当前服务进程内存中保存五分钟，重启后自然失效。
    code = secrets.token_urlsafe(9)
    with _capture_pairing_lock:
        now = time.monotonic()
        for old_code, (_, expires_at) in list(_capture_pairings.items()):
            if expires_at <= now:
                _capture_pairings.pop(old_code, None)
        _capture_pairings[code] = (current_user.id, now + 300)
    return {"code": code, "expires_in_seconds": 300}


@router.post("/capture/pair/complete")
def complete_capture_pair(payload: CapturePairRequest, request: Request, db: Session = Depends(get_db)):
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="只能在本机配对浏览器插件")
    with _capture_pairing_lock:
        pairing = _capture_pairings.pop(payload.code, None)
    if pairing is None or pairing[1] <= time.monotonic():
        raise HTTPException(status_code=400, detail="配对码错误或已过期")
    if db.get(User, pairing[0]) is None:
        raise HTTPException(status_code=400, detail="用户已不存在")
    return {"capture_token": create_capture_token(pairing[0]), "expires_in_days": 30}


@router.post("/capture/collect")
async def collect_browser_asset(
    file: UploadFile,
    request: Request,
    source_url: str = Form(...),
    title: str = Form(""),
    authorization: str = Header(""),
    db: Session = Depends(get_db),
):
    """只接收插件已下载的文件，不由服务器请求任意网页地址。"""
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="只能从本机导入素材")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先配对浏览器插件")
    token = decode_token(authorization.removeprefix("Bearer "))
    if token.get("token_type") != "capture" or db.get(User, token["user_id"]) is None:
        raise HTTPException(status_code=401, detail="插件授权已失效，请重新配对")
    parsed_url = urlparse(source_url)
    if len(source_url) > 2048 or parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise HTTPException(status_code=400, detail="来源页面地址无效")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持该图片或视频格式")
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="单个素材不能超过 100MB")
    media_dir = _media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_upload(media_dir, token["user_id"], content)
    if duplicate:
        # 重复素材仍记录新来源，但不覆盖原来的上传来源和文件内容。
        metadata = _upload_metadata(duplicate)
        sources = metadata.get("source_urls", [])
        if source_url not in sources:
            sources.append(source_url)
        metadata["source_urls"] = sources
        metadata.setdefault("source_url", source_url)
        metadata.setdefault("source_platform", _source_platform(source_url))
        duplicate.with_suffix(duplicate.suffix + ".json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return {"file_name": duplicate.name, "duplicate": True}

    file_name = f"xhs-upload-u{token['user_id']}-{uuid4().hex}{ext}"
    output_path = media_dir / file_name
    output_path.write_bytes(content)
    # 来源信息与媒体文件同名保存，素材库能按平台筛选并追溯原网页。
    output_path.with_suffix(ext + ".json").write_text(
        json.dumps({"origin": "web", "original_name": Path(file.filename or file_name).name, "title": title[:240], "source_url": source_url, "source_urls": [source_url], "source_platform": _source_platform(source_url)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"file_name": file_name, "duplicate": False}


@router.post("/upload")
async def upload_file(file: UploadFile, current_user: User = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名不能为空")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小超过 100MB 限制")

    asset_type = "video" if ext in {".mp4", ".mov", ".avi", ".mkv"} else "image"
    file_name = f"xhs-upload-u{current_user.id}-{uuid4().hex}{ext}"
    media_dir = _media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_upload(media_dir, current_user.id, content)
    if duplicate:
        # 返回已有素材地址，前端可提示复用且不会产生重复文件。
        return {"file_name": duplicate.name, "original_name": _upload_title(duplicate), "file_path": str(duplicate.resolve()), "download_url": f"/api/files/media/{duplicate.name}", "asset_type": asset_type, "size": len(content), "duplicate": True}
    output_path = media_dir / file_name
    output_path.write_bytes(content)
    # 原始文件名用于素材库搜索，实际存储名仍使用随机 ID 防止重名冲突。
    output_path.with_suffix(output_path.suffix + ".json").write_text(json.dumps({"origin": "upload", "original_name": Path(file.filename).name}, ensure_ascii=False), encoding="utf-8")

    return {
        "file_name": file_name,
        "original_name": Path(file.filename).name,
        "file_path": str(output_path.resolve()),
        "download_url": f"/api/files/media/{file_name}",
        "asset_type": asset_type,
        "size": len(content),
        "duplicate": False,
    }
