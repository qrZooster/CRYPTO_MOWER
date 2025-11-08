# bb_logger.py
# Rich LogRouter for Delphi.2025
# Created: 2025-10-13


from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import threading
import time


class TLogRouter:
    """Глобальный Rich лог-центр с несколькими окнами."""

    def __init__(self, window_count: int = 3, refresh_rate: float = 0.5):
        self.console = Console()
        self.window_count = window_count
        self.refresh_rate = refresh_rate
        self.buffers = {i: [] for i in range(1, window_count + 1)}
        self.lock = threading.Lock()
        self._stop = False

        # Подписчики на логи: callables вида fn(message: str, window: int)
        self.subscribers = []

        # создаём поток рендера
        self.thread = threading.Thread(target=self._render_loop, daemon=True)
        self.thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------------------------------------------------------
    def write(self, message: str, window: int = 1):
        """Добавляет строку в окно и рассылает подписчикам."""
        # 1) Сохраняем в буфер для Rich-консоли
        # 🔍 ВРЕМЕННАЯ ДИАГНОСТИКА
        print(f"[TLogRouter.write] '{message}' -> window={window}, subscribers={len(self.subscribers)}", flush=True)

        with self.lock:
            buf = self.buffers.get(window, [])
            buf.append(message)
            if len(buf) > 200:
                buf.pop(0)

        # 2) Уведомляем внешних подписчиков (например, TApplication → WebSocket)
        for fn in list(self.subscribers):
            try:
                fn(message, window)
            except Exception:
                # ни один подписчик не должен уронить лог-центр
                pass

    def add_subscriber(self, fn):
        """Регистрирует внешнего подписчика логов.

        fn: callable(message: str, window: int)
        """
        if not fn:
            return
        if fn not in self.subscribers:
            self.subscribers.append(fn)

    def remove_subscriber(self, fn):
        """Отписывает подписчика логов."""
        try:
            self.subscribers.remove(fn)
        except ValueError:
            pass

    def stop(self):
        """Останавливает обновление консоли."""
        self._stop = True
        self.thread.join(timeout=2)

    # ..................................................................................................................
    # 🎨 Render
    # ..................................................................................................................
    def _render_loop(self):
        """Фоновый цикл обновления Rich Live Console."""
        with Live(console=self.console, refresh_per_second=int(1 / self.refresh_rate)) as live:
            while not self._stop:
                layout = self._layout()
                live.update(layout)
                time.sleep(self.refresh_rate)

    def _layout(self):
        """Создаёт layout из панелей (по окнам)."""
        panels = []
        with self.lock:
            for i in range(1, self.window_count + 1):
                lines = self.buffers[i]
                text = "\n".join(lines[-20:]) or "(no logs)"
                panels.append(Panel(Text(text), title=f"Log Window {i}"))

        # объединяем панели вертикально
        return Panel.fit(
            Text("\n\n".join(p.renderable.plain for p in panels)),
            title="Rich Log Console",
        )
# ----------------------------------------------------------------------------------------------------------------------
# 🌍 Global instance
# ----------------------------------------------------------------------------------------------------------------------
LOG_ROUTER: TLogRouter | None = None


def init_log_router():
    global LOG_ROUTER
    if LOG_ROUTER is None:
        LOG_ROUTER = TLogRouter()
    return LOG_ROUTER


# bb_logger.py — дополни внизу файла

class TLogRouterMixin:
    """
    Миксин для классов, которые хотят использовать Rich LogRouter напрямую.
    Добавляет метод route_log() и свойство router.
    """

    @property
    def router(self):
        from bb_logger import LOG_ROUTER
        return LOG_ROUTER

    def route_log(self, msg: str, window: int = 1):
        """Упрощённая отправка строки напрямую в лог-окно."""
        if self.router:
            self.router.write(msg, window)
        else:
            print(msg, flush=True)


class LoggableComponent:
    """
    Базовый миксин, добавляющий поддержку централизованного логгирования.
    Все потомки автоматически используют Rich LogRouter (если активен).
    """

    def log(self, function: str, *parts, window: int = 1):
        from datetime import datetime
        from bb_logger import LOG_ROUTER
        from bb_sys import _key

        project_symbol = _key('PROJECT_SYMBOL', 'BB')
        project_version = _key('PROJECT_VERSION', '3')
        now = datetime.now().strftime('%H:%M:%S')
        msg = ' '.join(str(p) for p in parts)
        text = f'[{project_symbol}_{project_version}][{now}][{self.__class__.__name__}]{function}(): {msg}'

        try:
            if LOG_ROUTER:
                LOG_ROUTER.write(text, window=window)
            else:
                print(text, flush=True)
        except Exception:
            print(text, flush=True)
