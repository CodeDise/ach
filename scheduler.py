"""
Automated Weekly Scheduler module using APScheduler (AsyncIOScheduler).
Publishes an automated bilingual poll every Sunday at 10:00 PM IST (22:00 IST)
containing all unique titles uploaded during the preceding week.
"""

import logging
from typing import List
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import Config
from database import db

logger = logging.getLogger(__name__)


class WeeklyPollScheduler:
    """Manages scheduled background jobs including the Sunday bilingual poll."""

    def __init__(self, bot=None):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    def start(self, bot=None):
        """Configure and start the APScheduler instance."""
        if bot:
            self.bot = bot

        tz = pytz.timezone(Config.WEEKLY_POLL_TIMEZONE)
        # Schedule every Sunday at 22:00 (10:00 PM) IST
        trigger = CronTrigger(
            day_of_week="sun",
            hour=Config.WEEKLY_POLL_HOUR,
            minute=Config.WEEKLY_POLL_MINUTE,
            timezone=tz,
        )

        self.scheduler.add_job(
            self.publish_weekly_poll,
            trigger=trigger,
            id="weekly_sunday_poll",
            name="Weekly Sunday Bilingual Poll",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            "Weekly Poll Scheduler started. Trigger set for Sundays at %02d:%02d (%s).",
            Config.WEEKLY_POLL_HOUR,
            Config.WEEKLY_POLL_MINUTE,
            Config.WEEKLY_POLL_TIMEZONE,
        )

    def stop(self):
        """Shutdown the scheduler cleanly."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Weekly Poll Scheduler stopped.")

    async def publish_weekly_poll(self) -> bool:
        """
        Gathers all unique titles uploaded over the week,
        publishes the bilingual poll to all configured Update Channels,
        and resets the tracking list.
        """
        logger.info("Starting Sunday weekly poll execution...")

        # 1. Fetch tracked titles
        records = await db.get_weekly_titles()
        if not records:
            logger.info("No titles uploaded during this week. Skipping poll.")
            return False

        titles: List[str] = [r["title"] for r in records if r.get("title")]
        # Deduplicate while preserving order
        unique_titles = list(dict.fromkeys(titles))

        if not unique_titles:
            logger.info("No unique titles found. Skipping poll.")
            return False

        # 2. Get target Update Channels
        update_channels = await db.get_channels(channel_type="update")
        if not update_channels and Config.UPDATE_CHANNEL_ID:
            update_channels = [{"chat_id": Config.UPDATE_CHANNEL_ID}]

        if not update_channels:
            logger.warning("No Update Channels configured to receive the weekly poll.")
            return False

        # 3. Bilingual Question Header (Strict specification requirement)
        question_header = (
            "[English] What was your favorite episode this week?\n"
            "[Hindi] इस हफ्ते का आपका पसंदीदा एपिसोड कौन सा था?"
        )

        # Telegram polls limit options to max 10, min 2
        # If count == 1, add a fallback option
        if len(unique_titles) == 1:
            unique_titles.append("None / Others")

        # Chunk titles if more than 10
        chunks = [unique_titles[i : i + 10] for i in range(0, len(unique_titles), 10)]

        success = False
        for channel in update_channels:
            chat_id = channel["chat_id"]
            for idx, chunk in enumerate(chunks):
                # Ensure each chunk has at least 2 options
                if len(chunk) == 1:
                    chunk.append("None / Others")

                poll_question = question_header
                if len(chunks) > 1:
                    poll_question = f"{question_header}\n(Part {idx + 1}/{len(chunks)})"

                try:
                    await self.bot.send_poll(
                        chat_id=chat_id,
                        question=poll_question[:300],  # Max length 300
                        options=[opt[:100] for opt in chunk],  # Max length 100 per option
                        is_anonymous=True,
                        allows_multiple_answers=True,
                    )
                    logger.info("Weekly poll chunk %d sent to channel %s", idx + 1, chat_id)
                    success = True
                except Exception as e:
                    logger.error("Failed sending poll to channel %s: %s", chat_id, str(e))

        # 4. Reset weekly titles tracker upon successful broadcast
        if success:
            cleared = await db.clear_weekly_titles()
            logger.info("Cleared %d tracked titles for the new week.", cleared)

        return success


# Global scheduler instance
poll_scheduler = WeeklyPollScheduler()
