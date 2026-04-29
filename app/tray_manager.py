"""系统托盘管理模块，使用 pystray 实现最小化到托盘。"""

import threading
from typing import Callable


class TrayManager:
    """系统托盘图标管理。"""

    def __init__(self, on_show: Callable, on_quit: Callable):
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon = None
        self._thread: threading.Thread | None = None

    def _create_icon(self):
        """创建托盘图标和菜单。"""
        import pystray
        from PIL import Image, ImageDraw

        # 生成一个简单的图标 (绿色圆形带 T 字母)
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(0, 173, 181, 255))
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
        draw.text((18, 8), "T", fill=(255, 255, 255, 255), font=font)

        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._show_action, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit_action),
        )

        self._icon = pystray.Icon("tts_soundpad", img, "TTS Soundpad", menu)

    def _show_action(self, icon=None, item=None):
        if self._on_show:
            self._on_show()

    def _quit_action(self, icon=None, item=None):
        self.stop()
        if self._on_quit:
            self._on_quit()

    def start(self):
        """在后台线程启动托盘图标。"""
        if self._icon is not None:
            return
        try:
            self._create_icon()
        except ImportError:
            return  # pystray 未安装则跳过
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止托盘图标。"""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    @property
    def is_running(self) -> bool:
        return self._icon is not None
