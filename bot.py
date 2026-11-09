"""
Main entry point for Telegram Auto-Uploader & Channel Aggregator Bot.
Initializes Pyrogram Client, establishes Multi-Cluster MongoDB connectivity,
synchronizes dynamic admin authorizations, initializes channel invite links,
and starts the APScheduler background engine.
"""

import asyncio
import logging
import sys
from pyrogram import Client, enums
from pyrogram.errors import RPCError

from config import Config
from database import db
from scheduler import poll_scheduler

# Structured Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s : %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("AutoUploaderBot")


class AutoUploaderBot(Client):
    """Production-grade Telegram Bot Client."""

    def __init__(self):
        super().__init__(
            name="AutoUploaderBot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            parse_mode=enums.ParseMode.HTML,
            plugins=dict(root="handlers"),
            workers=16,
            max_concurrent_transmissions=4,
        )

    async def start(self):
        """Startup sequence: DB connection, admin sync, invite link generation, scheduler."""
        logger.info("Initializing Auto-Uploader & Aggregator Bot...")

        # 1. Start Pyrogram Client
        await super().start()
        me = await self.get_me()
        logger.info("Bot started successfully as @%s (ID: %d)", me.username, me.id)

        # 2. Connect to MongoDB (Multi-cluster failover support)
        db_connected = await db.connect()
        if not db_connected:
            logger.critical("Failed to connect to any configured MongoDB cluster! Exiting...")
            sys.exit(1)

        # 3. Dynamic Admin Sync
        await db.load_admins()
        logger.info("Admin authorization list synced from MongoDB.")

        # 4. Check and generate Private Channel Invite Links
        channels = await db.get_channels()
        for ch in channels:
            chat_id = ch.get("chat_id")
            existing_link = ch.get("invite_link")
            if not existing_link:
                try:
                    invite = await self.create_chat_invite_link(chat_id)
                    await db.add_channel(
                        chat_id=chat_id,
                        title=ch.get("title", "Channel"),
                        username=ch.get("username", ""),
                        invite_link=invite.invite_link,
                        channel_type=ch.get("type", "main"),
                    )
                    logger.info("Generated private invite link for channel %d: %s", chat_id, invite.invite_link)
                except RPCError as e:
                    logger.warning("Could not auto-generate invite link for channel %d: %s", chat_id, str(e))

        # 5. Start Background Weekly Poll Scheduler
        poll_scheduler.start(bot=self)
        logger.info("APScheduler initialized for automated Sunday 10:00 PM IST weekly bilingual poll.")

        # 6. Notify Owner or Log Channel
        startup_text = (
            f"<b>🚀 Bot Online and Operational!</b>\n\n"
            f"• <b>Bot:</b> @{me.username}\n"
            f"• <b>ID:</b> <code>{me.id}</code>\n"
            f"• <b>MongoDB:</b> Active Cluster [{db.active_uri_index + 1}/{len(db.configured_uris)}]\n"
            f"• <b>Weekly Poll:</b> Active (Sundays 22:00 IST)\n"
            f"• <b>Admins Synced:</b> {len(db.cached_admins)}"
        )
        if Config.OWNER_ID:
            try:
                await self.send_message(chat_id=Config.OWNER_ID, text=startup_text)
            except Exception as e:
                logger.warning("Could not send startup message to owner %d: %s", Config.OWNER_ID, str(e))

        if Config.LOG_CHANNEL_ID:
            try:
                await self.send_message(chat_id=Config.LOG_CHANNEL_ID, text=startup_text)
            except Exception as e:
                logger.warning("Could not send startup message to log channel: %s", str(e))

    async def stop(self, *args):
        """Graceful shutdown sequence."""
        logger.info("Stopping bot and background services...")
        poll_scheduler.stop()
        if db.client:
            db.client.close()
            logger.info("MongoDB client connections closed.")
        await super().stop()
        logger.info("Bot stopped cleanly.")


def main():
    """Application entrypoint."""
    if not Config.API_ID or not Config.API_HASH or not Config.BOT_TOKEN:
        logger.critical("API_ID, API_HASH, and BOT_TOKEN are required in .env! Please configure them.")
        sys.exit(1)

    bot = AutoUploaderBot()
    bot.run()


if __name__ == "__main__":
    main()
