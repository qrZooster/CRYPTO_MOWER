# ======================================================================================================================
# 📁 file        : bb_app_sys_control.py
# 🕒 created     : 18.10.2025 14:02
# 🎉 contains    : TappSysControl & its components
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
import asyncio
from bb_sys import *
from bb_application import TApplication, asset_url
from bb_ctrl_pages import *
from bb_ctrl_base import *
from bb_ctrl_atom import *
from bb_ctrl_custom import *
from _sys import *
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TappSysControl — Приложение System Control
# ----------------------------------------------------------------------------------------------------------------------
class TappSysControl(TApplication):
    def __init__(self, service_name="bbscan.service"):
        super().__init__()
        self.service_name = service_name
        self.ws = None

    def generate_name(self) -> str:
        return "bb_app_sys_control.html"

    def setup_subscriptions(self):
        """Настраивает подписки на события Tradition Core"""
        try:
            service_card = self.find("service_status")
            status_badge = self.find("system_status")

            if service_card:
                service_card.subscribe_event("system.status")
            if status_badge:
                status_badge.subscribe_event("system.status")

            self.log("setup_subscriptions", "✅ Event subscriptions configured")
        except Exception as e:
            self.log("setup_subscriptions", f"❌ Subscription error: {e}")

    async def do_start(self):
        self.log("do_start", "⚙️ Boot sequence starting...")
        self.run_db()
        self.run_web(host="0.0.0.0", port=8082)
        #self.setup_subscriptions()
        self.log("do_start", "🚀 System Control fully initialized")
        self.add_link("https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler.min.css", rel="stylesheet")
        self.add_link("https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-flags.min.css", rel="stylesheet")
        self.add_link("https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-payments.min.css", rel="stylesheet")
        self.add_script(asset_url("tc_ws_monitor.js"))  # один раз
    def do_pages(self):
        TlySysControl(self, "default")
        TpgMain(self, "main")
        TpgDatabase(self, "database")
        TpgEcho(self, "echo")
        self.log("do_pages", f"🧭 Pages registered: {list(self.Pages.keys())}")
        self.echo("TappSysControl.do_pages()")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TlySysControl — системный Layout Tradition Core
# ----------------------------------------------------------------------------------------------------------------------
class TlySysControl(TLayout):
    # ---
    def render_header(self):
        # Brand
        self.header.tg("a", cls="navbar-brand fw-bold text-primary", attr="href='/'")
        self.header.text("Tradition Core 2025")
        self.header.etg("a")
        pnl = panel(self, "PanelTop")
        lbl = label(pnl, "Test")
    # ---
    def render_footer(self):
        self.footer.tg("div", cls="container text-center text-muted small")
        self.footer.text("Tradition Core 2025 © Учитель")
        self.footer.etg("div")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TpgMain — Главная страница
# ----------------------------------------------------------------------------------------------------------------------
class TpgMain(TPage):
    def do_init(self):
        super().do_init()
        self.title = "TpgMain"
        self.layout = "default"

    def render(self):
        """Генерация визуального содержимого страницы."""
        # Заголовок
        self.h(1, "Tradition UI Elements Demo")
        app = self.app()
        # === Отладочная панель с данными запроса ===
        req_data = getattr(app, "request", None)
        aid = app.actions.register(self, lambda: app.echo("clicked!"), redirect="/?page=echo")
        self.text(f"<a class='btn btn-danger' href='/__act?aid={aid}'>Danger</a>")
        self.text('<div class="tc-dbg-frame tc-dbg-f-red-3" style="height:40px;margin:8px;">probe</div>')
        # рамка на всей карточке
        self.div("tc-dbg-frame tc-dbg-f-red-3")#card my-3 shadow-sm
        # рамка на хедере карточки
        self.tg("div", cls="tc-dbg-frame tc-dbg-f-blue-2")#card-header fw-bold text-primary
        self.text("🔍 Request Debug Info")
        self.etg("div")

        self.tg("div", cls="card-body text-monospace small")
        if req_data:
            self.text(f"<b>path:</b> {req_data.path}<br>")
            self.text(f"<b>get:</b> {req_data.get}<br>")
        else:
            self.text("<i>request object not available</i>")
        self.etg("div")
        self.etg("div")
        # === echo панель с данными запроса ===
        echo_data = getattr(app, "Echo", None)
        self.tg("div", cls="card-body text-monospace small")
        if echo_data:
            self.tg("ul", cls="list-unstyled mb-0")
            for line in getattr(app, "Echo", []):
                self.tg("li")
                self.text(f"🔹 {line}")
                self.etg("li")
            self.etg("ul")
        else:
            self.tg("div", cls="text-muted")
            self.text("Echo: (пусто)")
            self.etg("div")
        self.etg("div")

        crd = card(self, "TopCard")
        crd.icon = "🌐"
        crd.title = "System Core"
        crd.sub_title = "мониторинг состояния ядра"
        crd.mark()
        # === ГЛАВНЫЙ GRID ===
        grd = grid(self, "MainGrid")
        grd.mark('gray')
        grd.border = "2px dashed lime"
        # Верхняя строка (панель)
        top = grd.tr().td()
        # Кнопки внутри панели
        b = button(crd, "warning")
        b.page = "echo"
        b.mark()
        b = button(crd)
        b.kind = "danger"
        b = button(crd)
        b.kind = "success"
        b.inc_size()
        b.mark()
        b = button(crd, "info")
        b.size = "sm"
        btn = button(crd, "twitter")
        btn.size = "lg"
        button(crd, "Close", style="outline")
        button(crd, "github")
        button(crd, "🔔", style="icon")
        button(crd, "Test", style="indigo")
        button(crd, "got it!!!", style="pill danger sm")
        # Нижняя строка с 3 колонками
        bottom = grd.tr()
        td1 = bottom.td(0)
        td2 = bottom.td()
        td3 = bottom.td()

        crd = card(td1)
        crd.header.add_left("🔥 System Core")
        crd.footer.add_right("status: OK")
        crd.mark()


        pnl = panel(td2)
        td = pnl.td()
        lbl = label(td)
        lbl = label(td)
        lbl = label(td)
        lbl.mark()
        ic = icon(td)
        td = pnl.td()
        ic = icon(td)
        ic.icon = "🧩"
        pnl.mark()

        ic = icon(td3)
        ico2 = icon(td3)
        ico2.img_url = "https://example.com/favicon.ico"
        ico2.size = 17  # отрисуем как 16x16
        ico2.inc_size(12)
        ico2.h = 1

        ico3 = icon(td3)
        ico3.svg_html = "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='icon icon-tabler icons-tabler-outline icon-tabler-database'><path stroke='none' d='M0 0h24v24H0z' fill='none'/><path d='M12 6m-8 0a8 3 0 1 0 16 0a8 3 0 1 0 -16 0' /><path d='M4 6v6a8 3 0 0 0 16 0v-6' /><path d='M4 12v6a8 3 0 0 0 16 0v-6' /></svg>"
        ico3.size = 20
        ico3.h = 0
        bdg = badge(td3, "azure ⭐ outline sm")
        bdg_online = badge(td2, style="green notification blink")
        #bdg.style = "azure ⭐ outline"
        #bdg.icon = "⭐"
        #bdg.mark()
        # --- Navigation menu (TMenu) ---
        mn =menu(td3, "MainMenu")
        mn.add_class("navbar-nav", "ms-auto")
        mn.variant = "plain"
        mn.orientation = "horizontal"
        mn.auto_active = True

        mn.item("Main", "page=main")
        mn.item("Database", "page=database")
        mn.item("Echo", "page=echo")

        av = avatar(td3,"/assets/Igor.jpg", style="lg rounded online")
        av.status = "online"  # зелёная точка


        #av = TAvatar(td3, "Igor Kuzmichev")
        #av.src = "/assets/Igor.jpg"
        #av.status = "online"  # зелёная точка


        av2 = TAvatar(td3, "Jane Doe")
        av2.initials = "JD"
        av2.style = "blue sm rounded"
        av2.status = "busy"

        av3 = TAvatar(td3, "System")
        av3.icon = "👤"
        av3.style = "green sm square"
        av3.status = "gray"
        av3.status_text = "5"
        # Рендерим всех детей

        mon = TCardMonitor(self)
        mon.screen_class = "tc-mon-screen-dark"
        mon.font_class = "tc-mon-font-amber"

        crd = TCard(self)
        self.render_children()
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TpgDatabase — Управление базой данных
# ----------------------------------------------------------------------------------------------------------------------
class TpgDatabase(TPage):
    def do_init(self):
        super().do_init()
        self.title = "Database Control"
        self.layout = "default"

    def render(self):
        """Отрисовывает страницу управления базой данных."""
        self.h(1, "🗄 Database Management Panel")
        self.br()
        pnl = panel(self, "DbPanel")
        pnl.text("<b>Database:</b> connection status, schema, and settings will appear here.")
        self.render_children()
        self.log("render", "database page rendered")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TpgEcho — Вывод TApplication.echo()
# ----------------------------------------------------------------------------------------------------------------------
class TpgEcho(TPage):
    def do_init(self):
        super().do_init()
        self.title = "Echo Monitor"
        self.layout = "default"
    # ------------------------------------------------------------------------------------------------------------------
    # 🎨 Рендеринг страницы
    # ------------------------------------------------------------------------------------------------------------------
    def render(self):
        """Отрисовывает страницу мониторинга системы."""
        self.h(1, "📡 System Echo Monitor")
        self.br()
        pnl = panel(self, "EchoPanel")
        pnl.text("<b>Echo:</b> live WebSocket messages and system signals will appear here.")
        self.render_children()
        self.log("render", "echo page rendered")
# ----------------------------------------------------------------------------------------------------------------------
# 🚀 main() - запуск программы
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    async def main():
        app = TappSysControl(service_name="bbscan.service")
        app.log("main", "🚀 RUN: bb_app_sys_control starting")
        await app.start()

    asyncio.run(main())
# ======================================================================================================================
# 📁🌄 bb_app_sys_control.py 🜂 The End — See You Next Session 2025 💹 126 -> 82 -> 138 -> 231 -> 312
# ======================================================================================================================
