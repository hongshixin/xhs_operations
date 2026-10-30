"""在目标系统上生成桌面启动图标。"""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IMAGE = ROOT / "assets/desktop/cat-dog.png"
NAME = "小红书运营平台"


def main() -> None:
    try:
        from PIL import Image
        import PyInstaller  # noqa: F401
    except ImportError as error:
        raise SystemExit("请先安装打包依赖：python -m pip install pillow pyinstaller") from error

    system = platform.system()
    if system not in ("Windows", "Darwin"):
        raise SystemExit("当前只支持在 Windows 或 macOS 上构建启动图标。")

    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        image = Image.open(IMAGE).convert("RGBA")
        if system == "Windows":
            icon = temporary / "app.ico"
            image.save(icon, sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
        else:
            iconset = temporary / "app.iconset"
            iconset.mkdir()
            # iconutil 要求同时提供普通和 Retina 尺寸。
            for size in (16, 32, 128, 256, 512):
                image.resize((size, size), Image.Resampling.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
                image.resize((size * 2, size * 2), Image.Resampling.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
            icon = temporary / "app.icns"
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icon)], check=True)

        # 产物直接放项目根目录，启动器才能定位同目录的 main.py 和前端文件。
        subprocess.run(
            [
                sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                "--name", NAME, "--icon", str(icon), "--distpath", str(ROOT),
                "--workpath", str(temporary / "build"), "--specpath", str(temporary),
                str(ROOT / "desktop_launcher.py"),
            ],
            check=True,
        )
        print(f"已生成：{ROOT / (NAME + ('.exe' if system == 'Windows' else '.app'))}")


if __name__ == "__main__":
    main()
