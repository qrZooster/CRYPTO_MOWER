// tc_ws_monitor.js — стабильный монитор Tradition Core
// Один глобальный WebSocket + автопереподключение + поддержка TCardMonitor

(function () {
    const WS_PORT = 8082;
    const RECONNECT_DELAY = 3000; // мс

    const state = {
        socket: null,
        reconnectTimer: null,
        url: null,
    };

    // ------------------------------------------------------------
    //  UTILS
    // ------------------------------------------------------------
    function makeWsUrl() {
        if (state.url) return state.url;
        const proto = (location.protocol === "https:") ? "wss://" : "ws://";
        const host = location.hostname || "localhost";
        state.url = proto + host + ":" + WS_PORT;
        return state.url;
    }

    function logDebug(msg) {
        // Можно выключить, если надоест
        console.debug("[tc_ws_monitor]", msg);
    }

    function setStatus(online) {
        const nodes = document.querySelectorAll("[data-tws-status]");
        nodes.forEach(el => {
            el.textContent = online ? "ONLINE" : "OFFLINE";
            // Лёгкая подсветка: онлайн ярко, оффлайн приглушён
            el.style.opacity = online ? "1" : "0.4";
        });
    }

    // ------------------------------------------------------------
    //  РАБОТА С МОНИТОРАМИ
    // ------------------------------------------------------------
    function applyToMonitors(payload) {
        if (!payload || typeof payload !== "object") return;

        const channel = payload.channel || "";
        const type = payload.type || "";

        if (!channel) return; // мусор не обрабатываем

        const monitors = document.querySelectorAll(".tc-monitor-body");
        if (!monitors.length) return;

        monitors.forEach(el => {
            const ch = el.dataset.twsChannel || "log";
            const tp = el.dataset.twsType || "log_line";

            if (ch !== channel) return;
            if (tp && tp !== type) return;

            const mode = (el.dataset.twsMode || "append").toLowerCase();
            const maxLines = parseInt(el.dataset.twsMax || "0", 10) || 0;

            let line =
                payload.text ||
                payload.message ||
                payload.msg ||
                JSON.stringify(payload);

            // Нормализуем перевод строки
            line = String(line).replace(/\r\n/g, "\n").replace(/\r/g, "\n");

            if (mode === "replace") {
                el.textContent = line;
            } else {
                // append
                if (el.textContent) {
                    el.textContent += "\n" + line;
                } else {
                    el.textContent = line;
                }
                if (maxLines > 0) {
                    const lines = el.textContent.split("\n");
                    if (lines.length > maxLines) {
                        el.textContent = lines.slice(lines.length - maxLines).join("\n");
                    }
                }
            }

            // автоскролл вниз
            el.scrollTop = el.scrollHeight;
        });
    }

    function handleMessage(event) {
        let payload = null;
        try {
            payload = JSON.parse(event.data);
        } catch (e) {
            // не JSON — завернём в обёртку и всё равно покажем
            payload = {
                channel: "log",
                type: "log_line",
                text: String(event.data || ""),
            };
        }

        applyToMonitors(payload);
    }

    // ------------------------------------------------------------
    //  WEBSOCKET + RECONNECT
    // ------------------------------------------------------------
    function scheduleReconnect() {
        if (state.reconnectTimer) return;
        state.reconnectTimer = setTimeout(() => {
            state.reconnectTimer = null;
            connect();
        }, RECONNECT_DELAY);
    }

    function connect() {
        // Не плодим несколько сокетов
        if (state.socket &&
            (state.socket.readyState === WebSocket.OPEN ||
             state.socket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        const url = makeWsUrl();
        logDebug("connecting to " + url);

        try {
            const ws = new WebSocket(url);
            state.socket = ws;

            ws.addEventListener("open", () => {
                logDebug("WS open");
                setStatus(true);
            });

            ws.addEventListener("message", handleMessage);

            ws.addEventListener("close", (ev) => {
                logDebug("WS close: code=" + ev.code + " reason=" + ev.reason);
                setStatus(false);
                state.socket = null;
                scheduleReconnect();
            });

            ws.addEventListener("error", (ev) => {
                logDebug("WS error");
                // Ошибка почти всегда приведёт к close → там сделаем reconnect
                try { ws.close(); } catch (_) {}
            });
        } catch (e) {
            logDebug("connect error: " + e);
            setStatus(false);
            scheduleReconnect();
        }
    }

    // ------------------------------------------------------------
    //  ИНИЦИАЛИЗАЦИЯ
    // ------------------------------------------------------------
    document.addEventListener("DOMContentLoaded", () => {
        logDebug("init DOMContentLoaded");
        setStatus(false);  // пока не подключились
        connect();
    });
})();
