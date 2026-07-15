from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import (
    AiDraft,
    AiGeneratedAsset,
    Note,
    NoteAsset,
    NoteComment,
    PlatformAccount,
    PublishJob,
    Task,
    User,
)

router = APIRouter(prefix="/system/stats", tags=["system-stats"])

_START_TIME = time.time()

# 项目根目录（backend/app/api/system_stats.py → 上三级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _bytes_to_mb(b: int) -> float:
    return round(b / 1024 / 1024, 2)


def _dir_size(path: str | Path) -> int:
    """递归计算目录大小（字节），目录不存在或无权限返回 0"""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _dir_size(entry.path)
            except (PermissionError, OSError):
                pass
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return total


def _resolve_sqlite_path(db_url: str) -> str | None:
    """从 SQLite URL 解析出文件路径，兼容 Windows / Mac / Linux"""
    try:
        parsed = urlparse(db_url)
        if parsed.scheme not in ("sqlite", "sqlite+pysqlite"):
            return None
        # netloc 为空时 path 即文件路径；Windows 绝对路径形如 /C:/...
        path = parsed.path
        if sys.platform == "win32" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]  # 去掉开头多余的斜杠
        return path if path and path != "/" else None
    except Exception:
        return None


def _disk_usage(path: str | Path) -> tuple[float, float, float, float]:
    """返回 (total_gb, used_gb, free_gb, used_pct)"""
    try:
        usage = os.statvfs(str(path)) if hasattr(os, "statvfs") else None
        if usage is None:
            import shutil
            d = shutil.disk_usage(str(path))
            total, used, free = d.total, d.used, d.free
        else:
            total = usage.f_frsize * usage.f_blocks
            free  = usage.f_frsize * usage.f_bavail
            used  = total - free
        pct = round(used / total * 100, 1) if total else 0.0
        return (
            round(total / 1024 ** 3, 1),
            round(used  / 1024 ** 3, 1),
            round(free  / 1024 ** 3, 1),
            pct,
        )
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _storage_stats(db: Session) -> dict:
    from backend.app.core.config import get_settings
    settings = get_settings()

    # 数据库文件大小（仅 SQLite 可直接测量）
    db_size_mb = None
    try:
        db_url = str(settings.database_url or "")
        db_file = _resolve_sqlite_path(db_url)
        if db_file and os.path.isfile(db_file):
            db_size_mb = _bytes_to_mb(os.path.getsize(db_file))
    except Exception:
        pass

    # 媒体存储目录（优先用配置值，否则用项目内默认目录）
    storage_root_cfg = getattr(settings, "storage_root", None)
    if storage_root_cfg:
        storage_root = Path(storage_root_cfg)
    else:
        storage_root = _PROJECT_ROOT / "backend" / "app" / "storage"
    storage_size_mb = _bytes_to_mb(_dir_size(storage_root))

    # 磁盘：Windows 取当前盘符，其他系统取根目录
    disk_path = Path.cwd().anchor if sys.platform == "win32" else "/"
    total_gb, used_gb, free_gb, used_pct = _disk_usage(disk_path)

    return {
        "db_size_mb": db_size_mb,
        "storage_size_mb": storage_size_mb,
        "disk_total_gb": total_gb,
        "disk_used_gb": used_gb,
        "disk_free_gb": free_gb,
        "disk_used_pct": used_pct,
    }


def _memory_stats() -> dict:
    mem = psutil.virtual_memory()
    proc = psutil.Process()
    proc_mem = proc.memory_info()
    # vms 在 macOS 上数值极大（含内存映射文件），仅供参考
    return {
        "system_total_mb": _bytes_to_mb(mem.total),
        "system_used_mb":  _bytes_to_mb(mem.used),
        "system_free_mb":  _bytes_to_mb(mem.available),
        "system_used_pct": round(mem.percent, 1),
        "process_rss_mb":  _bytes_to_mb(proc_mem.rss),
        "process_vms_mb":  _bytes_to_mb(proc_mem.vms),
    }


def _cpu_stats() -> dict:
    return {
        "cpu_pct":        psutil.cpu_percent(interval=0.2),
        "cpu_count":      psutil.cpu_count(logical=True) or 1,
        "uptime_seconds": int(time.time() - _START_TIME),
    }


def _db_stats(db: Session) -> dict:
    def count(model):
        try:
            return db.scalar(select(func.count()).select_from(model)) or 0
        except Exception:
            return 0

    try:
        task_status_rows = db.execute(
            select(Task.status, func.count().label("cnt")).group_by(Task.status)
        ).all()
        task_by_status = {row.status: row.cnt for row in task_status_rows}
    except Exception:
        task_by_status = {}

    return {
        "notes":               count(Note),
        "note_assets":         count(NoteAsset),
        "note_comments":       count(NoteComment),
        "ai_drafts":           count(AiDraft),
        "ai_generated_assets": count(AiGeneratedAsset),
        "accounts":            count(PlatformAccount),
        "publish_jobs":        count(PublishJob),
        "tasks_total":         count(Task),
        "tasks_by_status":     task_by_status,
    }


@router.get("")
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "memory":   _memory_stats(),
        "cpu":      _cpu_stats(),
        "storage":  _storage_stats(db),
        "database": _db_stats(db),
    }
