"""
Main Bot Module - Core bot setup and background tasks
"""

import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands

from .utils.database import ShiftCodeDatabase
from .utils.scraper import ShiftCodeScraper, ShiftCode

logger = logging.getLogger(__name__)


class ShiftCodeBot(commands.Bot):
    """Discord bot for Borderlands 4 Shift codes"""

    def __init__(
        self,
        command_prefix: str = "!",
        intents: discord.Intents = None,
        test_guild: Optional[discord.Object] = None,
        owner_id: Optional[int] = None,
    ):
        if intents is None:
            intents = discord.Intents.default()
            intents.message_content = True

        super().__init__(command_prefix=command_prefix, intents=intents, owner_id=owner_id)

        # Initialize utilities
        self.scraper = ShiftCodeScraper()
        self.db = ShiftCodeDatabase()

        # Cache for codes
        self.codes_cache = []
        self.last_update = None
        self.cache_duration = timedelta(hours=1)

        # Test guild for faster command syncing
        self.test_guild = test_guild

        # Background task reference
        self.bg_task = None

    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Initialize database
        await self.db.connect()
        logger.info("Database initialized")

        # Load all cogs
        await self.load_cogs()

        # NOTE: Commands are NOT synced automatically!
        # Use the !sync command to manually sync slash commands
        logger.info("Bot ready. Use !sync to sync slash commands to Discord.")

        # Start background task
        self.bg_task = self.loop.create_task(self.update_codes_background())
        logger.info("Background code refresh task started")

    async def load_cogs(self):
        """Load all cogs from the cogs directory"""
        cogs_dir = Path(__file__).parent / "cogs"
        cog_files = [f.stem for f in cogs_dir.glob("*.py") if f.stem != "__init__"]

        for cog_name in cog_files:
            try:
                await self.load_extension(f"bot.cogs.{cog_name}")
                logger.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)

    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("------")
        logger.info(f"Bot is ready and serving in {len(self.guilds)} guild(s)")

    async def get_codes_from_db(self) -> List[ShiftCode]:
        """Get codes from database and convert to ShiftCode objects"""
        db_codes = await self.db.get_all_active_codes()

        shift_codes = []
        for db_code in db_codes:
            shift_code = ShiftCode(
                code=db_code["code"],
                reward=db_code["reward"],
                expires=db_code["expires"],
                source=db_code["source"],
            )
            shift_codes.append(shift_code)

        return shift_codes

    async def _refresh_codes_cache(self):
        """Refresh codes cache by scraping and updating database"""
        # Check for expired codes first
        await self.db.update_expired_codes()

        # Scrape new codes
        scraped_codes = await self.scraper.get_all_codes()

        # Save to database
        for code in scraped_codes:
            await self.db.add_or_update_code(
                code.code, code.reward, code.expires, code.source
            )

        # Load from database (excludes expired codes)
        self.codes_cache = await self.get_codes_from_db()
        self.last_update = datetime.now()

    async def get_codes(self, force_refresh: bool = False):
        """Get codes from cache or scrape fresh"""
        # Refresh if forced, no cache exists, or cache is expired
        should_refresh = (
            force_refresh
            or not self.codes_cache
            or not self.last_update
            or datetime.now() - self.last_update > self.cache_duration
        )

        if should_refresh:
            reason = "forced" if force_refresh else "cache expired" if self.last_update else "initial load"
            logger.info(f"Fetching fresh codes ({reason})...")
            await self._refresh_codes_cache()

        return self.codes_cache

    async def update_codes_background(self):
        """Background task to refresh codes every hour"""
        await self.wait_until_ready()

        while not self.is_closed():
            try:
                logger.info("Background: Refreshing shift codes...")

                # Check for expired codes
                expired_count = await self.db.update_expired_codes()
                if expired_count > 0:
                    logger.info(f"Background: Marked {expired_count} code(s) as expired")

                # Scrape new codes
                scraped_codes = await self.scraper.get_all_codes()

                # Save to database and track new codes
                new_codes = []
                for code in scraped_codes:
                    code_id, is_new = await self.db.add_or_update_code(
                        code.code, code.reward, code.expires, code.source
                    )
                    if is_new:
                        new_codes.append(code)

                # Update cache from database
                self.codes_cache = await self.get_codes_from_db()
                self.last_update = datetime.now()

                logger.info(
                    f"Background: Cached {len(self.codes_cache)} codes ({len(new_codes)} new)"
                )

                # Send notifications for new codes
                if new_codes:
                    await self.notify_new_codes(new_codes)

            except Exception as e:
                logger.error(f"Background: Error refreshing codes: {e}", exc_info=True)

            # Wait 1 hour before next update
            await asyncio.sleep(3600)  # 1 hour

    async def notify_new_codes(self, new_codes: List[ShiftCode]):
        """Send notifications to subscribed channels about new codes"""
        try:
            # Get all subscribed channels
            subscriptions = await self.db.get_notification_subscriptions()

            if not subscriptions:
                logger.info("No subscribed channels for notifications")
                return

            logger.info(
                f"Notifying {len(subscriptions)} channel(s) about {len(new_codes)} new code(s)"
            )

            # Create notification embed
            embed = discord.Embed(
                title="🔔 New Shift Codes Detected!",
                description=f"Found {len(new_codes)} new code(s)",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )

            # Add each new code
            for i, code in enumerate(
                new_codes[:5], 1
            ):  # Limit to 5 codes per notification
                field_name = f"✨ Code {i}"
                field_value = f"**Code:** `{code.code}`\n"
                field_value += f"**Reward:** {code.reward}\n"
                field_value += f"**Source:** {code.source}"

                if code.expires:
                    field_value += f"\n**Expires:** {code.expires}"

                embed.add_field(name=field_name, value=field_value, inline=False)

            if len(new_codes) > 5:
                embed.add_field(
                    name="📋 More Codes",
                    value=f"And {len(new_codes) - 5} more! Use `/codes` to see all.",
                    inline=False,
                )

            embed.add_field(
                name="🔗 Redeem",
                value="[Click here to redeem](https://shift.gearboxsoftware.com/rewards)",
                inline=False,
            )

            embed.set_footer(text="Use /unsubscribe to stop notifications")

            # Send to all subscribed channels
            success_count = 0
            failed_channels = []

            for sub in subscriptions:
                try:
                    # Use fetch_channel instead of get_channel for more reliable retrieval
                    channel = await self.fetch_channel(int(sub["channel_id"]))
                    if channel:
                        await channel.send(embed=embed)
                        success_count += 1
                    else:
                        # Channel not found, mark for cleanup
                        failed_channels.append(sub["channel_id"])
                        logger.warning(
                            f"Channel {sub['channel_id']} not found, marking for cleanup"
                        )
                except discord.Forbidden:
                    failed_channels.append(sub["channel_id"])
                    logger.warning(
                        f"No permission to send to channel {sub['channel_id']}"
                    )
                except Exception as e:
                    failed_channels.append(sub["channel_id"])
                    logger.error(f"Error sending to channel {sub['channel_id']}: {e}")

            logger.info(
                f"Notifications sent to {success_count}/{len(subscriptions)} channel(s)"
            )

            # Clean up failed channels
            for channel_id in failed_channels:
                await self.db.remove_notification_subscription(channel_id)

        except Exception as e:
            logger.error(f"Error in notify_new_codes: {e}", exc_info=True)

    async def close(self):
        """Clean up when bot is closing"""
        # Cancel background task
        if self.bg_task:
            self.bg_task.cancel()

        # Close database connection
        if self.db.connection:
            await self.db.close()

        await super().close()
