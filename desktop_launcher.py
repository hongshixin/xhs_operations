"""给非技术用户使用的跨平台桌面启动入口。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


BACKEND_URL = "http://127.0.0.1:1314/api/health"
FRONTEND_URL = "http://127.0.0.1:5173"


def find_project_root(executable: Path) -> Path:
    """启动器可放在项目根目录，也可放在根目录下的 macOS App 包中。"""
    for candidate in (executable.parent, *executable.parents):
        if (candidate / "main.py").is_file() and (candidate / "frontend/package.json").is_file():
            return candidate
    raise FileNotFoundError("找不到项目文件。请把启动图标放在项目文件夹中。")


def find_python(root: Path) -> str:
    # 优先使用项目虚拟环境，避免系统 Python 缺少依赖。
    relative = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    local_python = root / relative
    if local_python.is_file():
        return str(local_python)
    python = shutil.which("python3") or shutil.which("python")
    if python:
        return python
    raise FileNotFoundError("找不到 Python。请先安装 Python 3.10 或更高版本。")


def is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def show_error(message: str) -> None:
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror("小红书运营平台启动失败", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def launch() -> int:
    try:
        executable = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
        root = find_project_root(executable)
        if is_ready(FRONTEND_URL) and is_ready(BACKEND_URL):
            webbrowser.open(FRONTEND_URL)
            return 0

        if is_ready(FRONTEND_URL) or is_ready(BACKEND_URL):
            raise RuntimeError("检测到服务只启动了一部分。请先关闭已有的项目服务，再双击图标。")
        if not (root / "frontend/node_modules").is_dir():
            raise FileNotFoundError("前端依赖尚未安装。请让管理员在项目的 frontend 文件夹运行 npm install。")
        # macOS 图形应用不继承终端 PATH，补上常见的 Homebrew 和系统安装位置。
        environment = os.environ.copy()
        if sys.platform == "darwin":
            environment["PATH"] = os.pathsep.join(
                ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", environment.get("PATH", ""))
            )
            os.environ["PATH"] = environment["PATH"]
        python = find_python(root)
        if not shutil.which("npm", path=environment.get("PATH")):
            raise FileNotFoundError("找不到 Node.js 的 npm。请先安装 Node.js 20 或更高版本。")
        # 配置文件默认监听所有网卡；桌面入口只向本机浏览器提供服务。
        environment["SERVER_HOST"] = "127.0.0.1"
        log_path = root / "desktop-launcher.log"
        # 后台启动后保留服务进程，启动器退出不会让网页立刻断开。
        with log_path.open("a", encoding="utf-8") as log:
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(
                [python, "main.py", "--with-frontend", "--host", "127.0.0.1", "--port", "1314"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment,
                **options,
            )
        # 等两个服务均可访问才打开网页，避免用户看到浏览器连接失败。
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if is_ready(FRONTEND_URL) and is_ready(BACKEND_URL):
                webbrowser.open(FRONTEND_URL)
                return 0
            if process.poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError(f"服务没有在 60 秒内启动成功。请把日志发给管理员：{log_path}")
    except (OSError, RuntimeError) as error:
        show_error(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(launch())
