"""
Database management module using Motor (Async MongoDB).
Includes Multi-Cluster Redundancy with automated failover, dynamic connection management,
caching, aggregation tracking, dynamic admin persistence, and status telemetry.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import Config

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Normalize text into an alphanumeric identifier slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class DatabaseManager:
    """
    Manages MongoDB connections with multi-cluster redundancy,
    transparent failover, in-memory caching, and domain operations.
    """

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.active_uri_index: int = 0
        self.configured_uris: List[str] = list(Config.MONGO_URIS)
        self.cached_admins: Set[int] = set(Config.ADMIN_IDS)
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the first available healthy MongoDB cluster."""
        if not self.configured_uris:
            logger.error("No MongoDB URIs configured.")
            return False

        for idx, uri in enumerate(self.configured_uris):
            try:
                masked_uri = self._mask_uri(uri)
                logger.info("Attempting connection to MongoDB cluster [%d]: %s", idx, masked_uri)
                client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                )
                # Test ping
                await client.admin.command("ping")
                self.client = client
                self.db = client[Config.DATABASE_NAME]
                self.active_uri_index = idx
                self._connected = True
                logger.info("Successfully connected to MongoDB cluster [%d].", idx)
                await self._init_indexes()
                await self.load_admins()
                return True
            except Exception as e:
                logger.warning("Failed connecting to cluster [%d]: %s", idx, str(e))

        logger.critical("All configured MongoDB clusters failed to connect!")
        self._connected = False
        return False

    async def _ensure_connection(self) -> bool:
        """Verify current connection or trigger failover."""
        if self._connected and self.client:
            try:
                await self.client.admin.command("ping")
                return True
            except Exception as e:
                logger.warning("Active cluster check failed: %s. Initiating failover...", str(e))

        # Attempt reconnect across list
        return await self.connect()

    async def _init_indexes(self):
        """Create needed database indexes for rapid lookups."""
        try:
            await self.db.admins.create_index("user_id", unique=True)
            await self.db.channels.create_index("chat_id", unique=True)
            await self.db.posters.create_index("title_slug", unique=True)
            await self.db.posts.create_index("slug", unique=True)
            await self.db.weekly_titles.create_index("title_slug")
        except Exception as e:
            logger.warning("Index initialization notice: %s", str(e))

    def _mask_uri(self, uri: str) -> str:
        """Mask credentials in MongoDB connection string for safe display."""
        try:
            return re.sub(r"://([^:]+):([^@]+)@", r"://***:***@", uri)
        except Exception:
            return "mongodb://***"

    # =========================================================================
    # MULTI-CLUSTER MANAGEMENT & TELEMETRY
    # =========================================================================

    async def add_mongo_uri(self, uri: str) -> bool:
        """Add a new MongoDB URI to the multi-cluster pool."""
        if uri in self.configured_uris:
            return False
        self.configured_uris.append(uri)
        await self.update_settings({"mongo_uris": self.configured_uris})
        return True

    async def remove_mongo_uri(self, uri: str) -> bool:
        """Remove a MongoDB URI from the pool."""
        if uri not in self.configured_uris:
            return False
        if len(self.configured_uris) <= 1:
            return False  # Do not remove the only available node
        self.configured_uris.remove(uri)
        await self.update_settings({"mongo_uris": self.configured_uris})
        # If removing currently active cluster, failover to first remaining
        if self.active_uri_index >= len(self.configured_uris):
            await self.connect()
        return True

    async def get_db_status(self) -> Dict[str, Any]:
        """Obtain detailed live health telemetry across database collections."""
        is_alive = await self._ensure_connection()
        latency_ms = -1.0
        if is_alive and self.client:
            start_t = time.time()
            try:
                await self.client.admin.command("ping")
                latency_ms = round((time.time() - start_t) * 1000, 2)
            except Exception:
                is_alive = False

        counts = {
            "admins": 0,
            "channels": 0,
            "update_channels": 0,
            "posts": 0,
            "posters": 0,
            "weekly_titles": 0,
        }

        if is_alive and self.db is not None:
            try:
                counts["admins"] = await self.db.admins.count_documents({})
                counts["channels"] = await self.db.channels.count_documents({"type": "main"})
                counts["update_channels"] = await self.db.channels.count_documents({"type": "update"})
                counts["posts"] = await self.db.posts.count_documents({})
                counts["posters"] = await self.db.posters.count_documents({})
                counts["weekly_titles"] = await self.db.weekly_titles.count_documents({})
            except Exception as e:
                logger.error("Error fetching record counts: %s", str(e))

        current_uri = (
            self.configured_uris[self.active_uri_index]
            if self.active_uri_index < len(self.configured_uris)
            else "None"
        )

        return {
            "status": "Online" if is_alive else "Offline",
            "latency_ms": latency_ms,
            "active_node": self._mask_uri(current_uri),
            "node_index": self.active_uri_index + 1,
            "total_nodes": len(self.configured_uris),
            "counts": counts,
        }

    # =========================================================================
    # DYNAMIC ADMIN MANAGEMENT
    # =========================================================================

    async def load_admins(self):
        """Load all persisted admin records into in-memory cache."""
        admins = set(Config.ADMIN_IDS)
        if self.db is not None:
            try:
                cursor = self.db.admins.find({})
                async for doc in cursor:
                    admins.add(int(doc["user_id"]))
            except Exception as e:
                logger.error("Error loading admins: %s", str(e))
        self.cached_admins = admins
        logger.info("Loaded %d admins into cache.", len(self.cached_admins))

    def is_admin(self, user_id: int) -> bool:
        """Sub-millisecond in-memory verification for admin authorization."""
        return user_id in self.cached_admins or user_id == Config.OWNER_ID

    async def add_admin(self, user_id: int, username: str = "", added_by: int = 0) -> bool:
        """Grant and persist admin privileges."""
        await self._ensure_connection()
        self.cached_admins.add(user_id)
        if self.db is not None:
            try:
                await self.db.admins.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "user_id": user_id,
                            "username": username or "",
                            "added_by": added_by,
                            "updated_at": datetime.utcnow(),
                        },
                        "$setOnInsert": {
                            "created_at": datetime.utcnow(),
                        },
                    },
                    upsert=True,
                )
                return True
            except Exception as e:
                logger.error("Error adding admin: %s", str(e))
        return False

    async def remove_admin(self, user_id: int) -> bool:
        """Demote an admin and remove from database and cache."""
        if user_id == Config.OWNER_ID:
            return False  # Owner cannot be demoted
        await self._ensure_connection()
        self.cached_admins.discard(user_id)
        if self.db is not None:
            try:
                await self.db.admins.delete_one({"user_id": user_id})
                return True
            except Exception as e:
                logger.error("Error removing admin: %s", str(e))
        return False

    async def get_all_admins(self) -> List[Dict[str, Any]]:
        """List all registered admins."""
        await self._ensure_connection()
        res = []
        if self.db is not None:
            try:
                cursor = self.db.admins.find({})
                async for doc in cursor:
                    res.append(doc)
            except Exception as e:
                logger.error("Error fetching admins: %s", str(e))
        return res

    # =========================================================================
    # CHANNEL SETUP & INVITE LINKS
    # =========================================================================

    async def add_channel(
        self,
        chat_id: int,
        title: str,
        username: str = "",
        invite_link: str = "",
        channel_type: str = "main",
    ) -> bool:
        """Register or update a Target Main Channel or Update Channel."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                await self.db.channels.update_one(
                    {"chat_id": chat_id},
                    {
                        "$set": {
                            "chat_id": chat_id,
                            "title": title,
                            "username": username or "",
                            "invite_link": invite_link or "",
                            "type": channel_type,
                            "updated_at": datetime.utcnow(),
                        },
                        "$setOnInsert": {"created_at": datetime.utcnow()},
                    },
                    upsert=True,
                )
                return True
            except Exception as e:
                logger.error("Error adding channel: %s", str(e))
        return False

    async def remove_channel(self, chat_id: int) -> bool:
        """Unlink a channel."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                res = await self.db.channels.delete_one({"chat_id": chat_id})
                return res.deleted_count > 0
            except Exception as e:
                logger.error("Error removing channel: %s", str(e))
        return False

    async def get_channels(self, channel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all linked channels, optionally filtered by type."""
        await self._ensure_connection()
        res = []
        if self.db is not None:
            try:
                query = {"type": channel_type} if channel_type else {}
                cursor = self.db.channels.find(query)
                async for doc in cursor:
                    res.append(doc)
            except Exception as e:
                logger.error("Error fetching channels: %s", str(e))
        return res

    async def get_channel(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get channel details by chat ID."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                return await self.db.channels.find_one({"chat_id": chat_id})
            except Exception as e:
                logger.error("Error finding channel: %s", str(e))
        return None

    # =========================================================================
    # POSTER MANAGEMENT
    # =========================================================================

    async def set_poster(self, title: str, file_id: str, media_type: str = "photo") -> bool:
        """Map a poster media file to a title."""
        await self._ensure_connection()
        slug = slugify(title)
        if self.db is not None:
            try:
                await self.db.posters.update_one(
                    {"title_slug": slug},
                    {
                        "$set": {
                            "title_slug": slug,
                            "title": title.strip(),
                            "file_id": file_id,
                            "media_type": media_type,
                            "updated_at": datetime.utcnow(),
                        },
                        "$setOnInsert": {"created_at": datetime.utcnow()},
                    },
                    upsert=True,
                )
                return True
            except Exception as e:
                logger.error("Error saving poster: %s", str(e))
        return False

    async def get_poster(self, title: str) -> Optional[Dict[str, Any]]:
        """Retrieve poster mapping for a title."""
        await self._ensure_connection()
        slug = slugify(title)
        if self.db is not None:
            try:
                # Exact slug match
                doc = await self.db.posters.find_one({"title_slug": slug})
                if doc:
                    return doc
                # Partial regex match
                return await self.db.posters.find_one(
                    {"title_slug": {"$regex": re.escape(slug), "$options": "i"}}
                )
            except Exception as e:
                logger.error("Error fetching poster: %s", str(e))
        return None

    async def delete_poster(self, title: str) -> bool:
        """Delete poster mapping."""
        await self._ensure_connection()
        slug = slugify(title)
        if self.db is not None:
            try:
                res = await self.db.posters.delete_one({"title_slug": slug})
                return res.deleted_count > 0
            except Exception as e:
                logger.error("Error deleting poster: %s", str(e))
        return False

    async def get_all_posters(self) -> List[Dict[str, Any]]:
        """List all stored posters."""
        await self._ensure_connection()
        res = []
        if self.db is not None:
            try:
                cursor = self.db.posters.find({})
                async for doc in cursor:
                    res.append(doc)
            except Exception as e:
                logger.error("Error fetching poster list: %s", str(e))
        return res

    # =========================================================================
    # AGGREGATED POSTS & DYNAMIC BUTTON EDITING
    # =========================================================================

    async def get_post_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Fetch existing aggregation post metadata by unique key."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                return await self.db.posts.find_one({"slug": slug})
            except Exception as e:
                logger.error("Error retrieving aggregated post: %s", str(e))
        return None

    async def save_aggregated_post(
        self,
        slug: str,
        title: str,
        season: str,
        episode: str,
        audio: str,
        qualities: Dict[str, Dict[str, Any]],
        main_posts: List[Dict[str, Any]],
        update_posts: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Persist or update an aggregated post entry."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                await self.db.posts.update_one(
                    {"slug": slug},
                    {
                        "$set": {
                            "slug": slug,
                            "title": title,
                            "season": season,
                            "episode": episode,
                            "audio": audio,
                            "qualities": qualities,
                            "main_posts": main_posts,
                            "update_posts": update_posts or [],
                            "updated_at": datetime.utcnow(),
                        },
                        "$setOnInsert": {"created_at": datetime.utcnow()},
                    },
                    upsert=True,
                )
                return True
            except Exception as e:
                logger.error("Error saving aggregated post: %s", str(e))
        return False

    # =========================================================================
    # WEEKLY TITLE TRACKING (SUNDAY POLL)
    # =========================================================================

    async def add_weekly_title(self, title: str, season: str = "", episode: str = ""):
        """Track titles uploaded throughout the week for the Sunday poll."""
        await self._ensure_connection()
        slug = slugify(title)
        if self.db is not None:
            try:
                # Add or update title tracking
                await self.db.weekly_titles.update_one(
                    {"title_slug": slug},
                    {
                        "$set": {
                            "title_slug": slug,
                            "title": title.strip(),
                            "season": season,
                            "last_episode": episode,
                            "updated_at": datetime.utcnow(),
                        },
                        "$setOnInsert": {"created_at": datetime.utcnow()},
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.error("Error adding weekly title: %s", str(e))

    async def get_weekly_titles(self) -> List[Dict[str, Any]]:
        """Retrieve all unique titles tracked during the current week."""
        await self._ensure_connection()
        res = []
        if self.db is not None:
            try:
                cursor = self.db.weekly_titles.find({}).sort("title", 1)
                async for doc in cursor:
                    res.append(doc)
            except Exception as e:
                logger.error("Error fetching weekly titles: %s", str(e))
        return res

    async def clear_weekly_titles(self) -> int:
        """Reset weekly title tracker after the Sunday poll is posted."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                res = await self.db.weekly_titles.delete_many({})
                return res.deleted_count
            except Exception as e:
                logger.error("Error clearing weekly titles: %s", str(e))
        return 0

    # =========================================================================
    # SETTINGS & CONFIGURATION PERSISTENCE
    # =========================================================================

    async def get_settings(self) -> Dict[str, Any]:
        """Fetch dynamic bot settings stored in MongoDB."""
        await self._ensure_connection()
        defaults = {
            "external_storage_bot": Config.EXTERNAL_STORAGE_BOT,
            "external_db_channel_id": Config.EXTERNAL_DB_CHANNEL_ID,
            "storage_start_param_format": Config.STORAGE_START_PARAM_FORMAT,
            "normal_format": Config.DEFAULT_NORMAL_FORMAT,
            "update_format": Config.DEFAULT_UPDATE_FORMAT,
            "enable_watermark": Config.ENABLE_WATERMARK,
            "watermark_text": Config.WATERMARK_TEXT,
            "watermark_position": Config.WATERMARK_POSITION,
            "watermark_font_size": Config.WATERMARK_FONT_SIZE,
            "watermark_font_color": Config.WATERMARK_FONT_COLOR,
            "mongo_uris": self.configured_uris,
        }
        if self.db is not None:
            try:
                doc = await self.db.settings.find_one({"_id": "global_settings"})
                if doc:
                    defaults.update({k: v for k, v in doc.items() if k != "_id"})
            except Exception as e:
                logger.error("Error fetching settings: %s", str(e))
        return defaults

    async def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update dynamic bot settings."""
        await self._ensure_connection()
        if self.db is not None:
            try:
                await self.db.settings.update_one(
                    {"_id": "global_settings"},
                    {"$set": updates},
                    upsert=True,
                )
                return True
            except Exception as e:
                logger.error("Error updating settings: %s", str(e))
        return False

    # =========================================================================
    # COMPLETE DATA WIPE ("CLEAR ALL")
    # =========================================================================

    async def clear_all_data(self) -> bool:
        """
        Wipe all configured channels, tracked titles, aggregated posts, and posters.
        Preserves owner admin ID and MongoDB connection configurations.
        """
        await self._ensure_connection()
        if self.db is not None:
            try:
                await self.db.channels.delete_many({})
                await self.db.posters.delete_many({})
                await self.db.posts.delete_many({})
                await self.db.weekly_titles.delete_many({})
                # Reset dynamic channel settings
                await self.db.settings.update_one(
                    {"_id": "global_settings"},
                    {
                        "$unset": {
                            "main_channel_id": "",
                            "update_channel_id": "",
                        }
                    },
                )
                logger.warning("Complete database data wipe executed successfully.")
                return True
            except Exception as e:
                logger.error("Error performing data wipe: %s", str(e))
        return False


# Singleton instance
db = DatabaseManager()
