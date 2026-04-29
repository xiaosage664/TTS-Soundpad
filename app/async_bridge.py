import asyncio
import threading
from typing import Any, Callable


class AsyncBridge:
    """
    在后台守护线程中运行 asyncio 事件循环，
    提供从 tkinter 主线程提交协程并接收回调的能力。
    """

    def __init__(self, tk_root):
        self._root = tk_root
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(
        self,
        coro,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        """提交一个协程到后台事件循环，完成后在主线程回调。"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_done(fut):
            try:
                result = fut.result()
                if on_success:
                    self._root.after(0, on_success, result)
            except Exception as exc:
                if on_error:
                    self._root.after(0, on_error, exc)

        future.add_done_callback(_on_done)

    def shutdown(self):
        """停止事件循环并等待线程退出。"""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=3)
