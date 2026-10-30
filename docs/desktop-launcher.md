# 桌面启动图标

项目依赖已安装后，Windows 和 Mac 用户可以双击“小红书运营平台”图标启动本地服务。服务就绪后会自动打开浏览器。再次双击会直接打开已有服务。

## 制作图标

在**需要交付的对应系统**上、项目根目录执行：

```bash
python -m pip install pillow pyinstaller
python build_desktop_launcher.py
```

Windows 会生成 `小红书运营平台.exe`，macOS 会生成 `小红书运营平台.app`。请把生成的文件保留在项目根目录；不要单独移走图标。Windows 和 Mac 产物须分别在各自系统构建。Mac 首次打开未签名 App 时，可能需要通过“右键 → 打开”确认。

## 使用前准备

先按主 README 安装 Python 与 Node.js 依赖，包括根目录及 `frontend` 目录的 npm 依赖。启动器会优先使用项目 `.venv` 中的 Python，否则使用系统 Python。Mac 从桌面启动时可能读不到终端配置的 Node 路径；请确保 `npm` 可从应用环境访问。

双击图标后等待约一分钟。如果失败，会出现中文提示。管理员可查看项目根目录的 `desktop-launcher.log`。如需关闭服务，可在任务管理器或活动监视器中结束对应 Python 进程。

图标原图位于 `assets/desktop/cat-dog.png`，由内置 imagegen 生成。最终提示词：金渐层猫与橘白柯基的简洁头像一起抱着红色笔记本，封面写小写 `rrzz`，扁平几何卡通图形、奶油色圆角方形底板、有限配色、无场景，缩小后仍可辨认。
