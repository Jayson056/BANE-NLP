"""
BNP Entry Point
================
Starts the Bane Notebook Pipeline:
1. Launches the WebSocket bridge (browser communication)
2. Starts the Telegram bot polling

Usage:
    python run.py
"""

import asyncio
import os
import sys
from datetime import datetime

from core.bane_core import BaneCore
from channels.telegram_bot import TelegramBot
from channels.messenger_bot import MessengerBot
from core.browser_bridge import BrowserBridge
from pipeline.response_handler import ResponseHandler
from core.logger import system_logger, log_event, log_error, register_error_notifier
import core.database as database


BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║     ██████╗ ███╗   ██╗██████╗                            ║
║     ██╔══██╗████╗  ██║██╔══██╗                           ║
║     ██████╔╝██╔██╗ ██║██████╔╝                           ║
║     ██╔══██╗██║╚██╗██║██╔═══╝                            ║
║     ██████╔╝██║ ╚████║██║                                ║
║     ╚═════╝ ╚═╝  ╚═══╝╚═╝                               ║
║                                                          ║
║     Bane Notebook Pipeline                               ║
║     Telegram → Bane → Chrome → Gemini / NotebookLM      ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    """
    Entry point using python-telegram-bot's built-in run_polling().

    The Telegram library manages the asyncio event loop itself.
    We hook into its post_init to start our WebSocket bridge
    inside the same loop.
    """
    print(BANNER)
    system_logger.info("Initializing BNP...")

    # ── Database Bootstrap (MUST be first) ───────────────────────────────────
    # Runs CREATE TABLE IF NOT EXISTS + any pending ALTER TABLE migrations
    # (e.g. adding the chrome_profile column to an existing DB).
    database.init_database()
    system_logger.info("[DB] Schema verified / migrated.")

    # Create core dependencies
    bridge = BrowserBridge()
    handler = ResponseHandler()
    
    # Create core engine
    core = BaneCore(bridge, handler)
    
    # Wire bridge to handler (for async events/partials)
    bridge.set_response_handler(handler.handle_response)

    # Create the Telegram bot instance and build the app
    bot = TelegramBot(core)
    app = bot.build()




    # Use post_init to start the WebSocket bridge INSIDE the
    # same event loop that python-telegram-bot creates
    async def post_init(application):
        await core.start()

        # ── Register Telegram error notifier ─────────────────────────────────────
        async def _send_error_to_owner(msg: str):
            for uid in ALLOWED_TELEGRAM_USERS:
                try:
                    await application.bot.send_message(
                        chat_id=uid, text=msg, parse_mode="HTML"
                    )
                except Exception:
                    pass
        register_error_notifier(_send_error_to_owner)
        log_event("STARTUP", "Telegram error notifier registered.")

        # Start Messenger Bot with explicit loop sharing
        log_event("STARTUP", "Starting Messenger Webhook server...")
        messenger = MessengerBot(core, loop=asyncio.get_running_loop())
        messenger.start()

        # ── Start Portfolio Gateway (Proxy Entry Point) ──────────────────────────
        log_event("STARTUP", "Checking for existing Portfolio Gateway...")
        import psutil
        portfolio_running = False
        for proc in psutil.process_iter(['cmdline']):
            try:
                cmd = proc.info.get('cmdline')
                if cmd and any("JaysonWebPortfolio.io" in part for part in cmd) and any("app.py" in part for part in cmd):
                    portfolio_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not portfolio_running:
            log_event("STARTUP", "Starting Portfolio Gateway (Port 8000)...")
            import subprocess
            portfolio_path = r"D:\Project_Workspace\JaysonWebPortfolio.io\app.py"
            # Launch using the same Python interpreter as background process
            subprocess.Popen([sys.executable, portfolio_path], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
        else:
            log_event("STARTUP", "Portfolio Gateway is already active. Skipping re-launch.")

        log_event("STARTUP", "Browser bridge is ready, waiting for Chrome extension...")
        log_event("STARTUP", "BNP is fully operational (Telegram + Messenger)!")
        
        # ─── STARTUP NOTIFICATION (LIVE SIGNAL) ───
        from config import ALLOWED_TELEGRAM_USERS, ALLOWED_MESSENGER_USERS, PIPELINE_NAME
        
        # 1. Notify Telegram Owners
        for user_id in ALLOWED_TELEGRAM_USERS:
            try:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🛡️ <b>{PIPELINE_NAME} SYSTEM ONLINE</b>\n"
                        f"───────────────────\n"
                        f"✅ <b>BANE NLP IS ALIVE</b>\n"
                        f"🌐 <b>Status:</b> Fully Operational\n"
                        f"🕒 <b>Time:</b> {datetime.now().strftime('%H:%M')}\n\n"
                        f"<i>Standing by for instructions, Jayson.</i>"
                    ),
                    parse_mode="HTML"
                )
                log_event("STARTUP_NOTIFY_TG", f"Sent to {user_id}")
            except Exception as e: log_error("STARTUP_TG_FAIL", e)

        # 2. Notify Messenger Owners
        for m_id in ALLOWED_MESSENGER_USERS:
            try:
                msg = (
                    f"🛡️ {PIPELINE_NAME} SYSTEM ONLINE\n"
                    f"───────────────────\n"
                    f"✅ BANE NLP IS ALIVE\n"
                    f"🌐 Status: Fully Operational\n"
                    f"🕒 Time: {datetime.now().strftime('%H:%M')}\n\n"
                    f"Standing by for instructions, Jayson."
                )
                # Use the messenger instance created just above
                await messenger._send_messenger_message(m_id, msg)
                log_event("STARTUP_NOTIFY_FB", f"Sent to {m_id}")
            except Exception as e: log_error("STARTUP_FB_FAIL", e)

        print("\n✅ BNP is running. Telegram & Messenger are active!")
        print("   Press Ctrl+C to stop.\n")

    async def post_shutdown(application):
        await core.stop()
        log_event("SHUTDOWN", "BNP stopped cleanly.")

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    system_logger.info("Starting Telegram bot polling...")

    try:
        app.run_polling(drop_pending_updates=True, bootstrap_retries=5)
    except KeyboardInterrupt:

        pass

    print("\n👋 BNP shut down.")


if __name__ == "__main__":
    main()
