import asyncio
import os

from app.core.logging import events


def build_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        from telegram.ext import Application
        return Application.builder().token(token).build()
    except Exception as e:
        events.event("ERROR", component="telegram_init", error=str(e))
        return None


async def run_bot():
    """Run the Telegram polling bot as a dedicated Render worker.

    Only one process should call getUpdates for a bot token. The FastAPI web
    service deliberately does not start polling.
    """
    from telegram.ext import CommandHandler

    bot = build_bot()
    if bot is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    async def start(update, context):
        await update.message.reply_text("Pixel Pulse Studio agent is online.")

    bot.add_handler(CommandHandler("start", start))

    await bot.initialize()
    await bot.bot.delete_webhook(drop_pending_updates=True)
    await bot.start()
    await bot.updater.start_polling(drop_pending_updates=True)

    try:
        await asyncio.Event().wait()
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()


def main():
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
