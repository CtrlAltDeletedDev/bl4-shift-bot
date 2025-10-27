"""
Borderlands 4 Shift Codes Discord Bot
Fetches and displays BL4 Shift codes using slash commands with pagination
"""

import os
import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
import math

import discord
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv

from scraper import ShiftCodeScraper, ShiftCode
from database import ShiftCodeDatabase

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID')

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env file")

# Optional: Convert TEST_GUILD_ID to discord.Object for faster syncing during development
MY_GUILD = discord.Object(id=int(TEST_GUILD_ID)) if TEST_GUILD_ID else None

# Pagination settings
CODES_PER_PAGE = 5


class CodesPaginationView(View):
    """Pagination view for browsing shift codes"""
    
    def __init__(self, codes: List[ShiftCode], page: int = 0, last_update: Optional[datetime] = None):
        super().__init__(timeout=180)  # 3 minute timeout
        self.codes = codes
        self.page = page
        self.last_update = last_update
        self.total_pages = math.ceil(len(codes) / CODES_PER_PAGE)
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        """Enable/disable buttons based on current page"""
        # Disable first/previous if on first page
        self.first_button.disabled = (self.page == 0)
        self.prev_button.disabled = (self.page == 0)
        
        # Disable next/last if on last page
        self.next_button.disabled = (self.page >= self.total_pages - 1)
        self.last_button.disabled = (self.page >= self.total_pages - 1)
    
    def get_embed(self) -> discord.Embed:
        """Generate embed for current page"""
        start_idx = self.page * CODES_PER_PAGE
        end_idx = min(start_idx + CODES_PER_PAGE, len(self.codes))
        display_codes = self.codes[start_idx:end_idx]
        
        embed = discord.Embed(
            title="🎮 Borderlands 4 Shift Codes",
            description=f"Found {len(self.codes)} code(s) | Page {self.page + 1}/{self.total_pages}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for i, code in enumerate(display_codes, start=start_idx + 1):
            status_emoji = "✅"
            field_name = f"{status_emoji} Code {i}"
            field_value = f"**Code:** `{code.code}`\n"
            field_value += f"**Reward:** {code.reward}\n"
            field_value += f"**Source:** {code.source}"
            
            if code.expires:
                field_value += f"\n**Expires:** {code.expires}"
            
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        if self.last_update:
            embed.set_footer(text=f"Last updated: {self.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        return embed
    
    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.primary, custom_id="first")
    async def first_button(self, interaction: discord.Interaction, button: Button):
        """Go to first page"""
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, custom_id="prev")
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        """Go to previous page"""
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        """Go to next page"""
        self.page = min(self.total_pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.primary, custom_id="last")
    async def last_button(self, interaction: discord.Interaction, button: Button):
        """Go to last page"""
        self.page = self.total_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="🗑️ Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        """Close the pagination view"""
        await interaction.response.edit_message(
            content="Closed shift codes list.",
            embed=None,
            view=None
        )
        self.stop()
    
    async def on_timeout(self):
        """Called when the view times out"""
        # Disable all buttons when timeout occurs
        for item in self.children:
            item.disabled = True


class ShiftCodeBot(discord.Client):
    """Discord bot client for Shift codes"""
    
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # Create a CommandTree instance for app commands
        self.tree = app_commands.CommandTree(self)
        self.scraper = ShiftCodeScraper()
        self.db = ShiftCodeDatabase()
        
        # Cache for codes
        self.codes_cache = []
        self.last_update = None
        self.cache_duration = timedelta(hours=6)
        
    async def setup_hook(self):
        """This is called when the bot is starting up"""
        # Initialize database
        await self.db.connect()
        logger.info("Database initialized")
        
        # Sync commands to the test guild if specified, otherwise sync globally
        if MY_GUILD:
            # Copy global commands to the test guild for faster syncing
            self.tree.copy_global_to(guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
            logger.info(f"Synced commands to guild {TEST_GUILD_ID}")
        else:
            # Sync globally (can take up to 1 hour)
            await self.tree.sync()
            logger.info("Synced commands globally")
        
        # Start background task to refresh codes
        self.bg_task = self.loop.create_task(self.update_codes_background())
        
    async def update_codes_background(self):
        """Background task to refresh codes every 6 hours"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                logger.info("Background: Refreshing shift codes...")
                
                # Track codes before scraping to detect new ones
                old_codes = {code.code for code in self.codes_cache}
                
                # Scrape new codes
                scraped_codes = await self.scraper.get_all_codes()
                
                # Save to database and track new codes
                new_codes_count = 0
                new_codes = []
                for code in scraped_codes:
                    code_id, is_new = await self.db.add_or_update_code(
                        code.code,
                        code.reward,
                        code.expires,
                        code.source
                    )
                    if is_new:
                        new_codes_count += 1
                        new_codes.append(code)
                
                # Update cache from database
                self.codes_cache = await self.get_codes_from_db()
                self.last_update = datetime.now()
                
                logger.info(f"Background: Cached {len(self.codes_cache)} codes ({new_codes_count} new)")
                
                # Send notifications for new codes
                if new_codes:
                    await self.notify_new_codes(new_codes)
                
            except Exception as e:
                logger.error(f"Background: Error refreshing codes: {e}")
            
            # Wait 6 hours before next update
            await asyncio.sleep(21600)  # 6 hours
    
    async def notify_new_codes(self, new_codes: List[ShiftCode]):
        """Send notifications to subscribed channels about new codes"""
        try:
            # Get all subscribed channels
            subscriptions = await self.db.get_notification_subscriptions()
            
            if not subscriptions:
                logger.info("No subscribed channels for notifications")
                return
            
            logger.info(f"Notifying {len(subscriptions)} channel(s) about {len(new_codes)} new code(s)")
            
            # Create notification embed
            embed = discord.Embed(
                title="🔔 New Shift Codes Detected!",
                description=f"Found {len(new_codes)} new code(s)",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Add each new code
            for i, code in enumerate(new_codes[:5], 1):  # Limit to 5 codes per notification
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
                    inline=False
                )
            
            embed.add_field(
                name="🔗 Redeem",
                value="[Click here to redeem](https://shift.gearboxsoftware.com/rewards)",
                inline=False
            )
            
            embed.set_footer(text="Use /unsubscribe to stop notifications")
            
            # Send to all subscribed channels
            success_count = 0
            failed_channels = []
            
            for sub in subscriptions:
                try:
                    channel = self.get_channel(int(sub['channel_id']))
                    if channel:
                        await channel.send(embed=embed)
                        success_count += 1
                    else:
                        # Channel not found, mark for cleanup
                        failed_channels.append(sub['channel_id'])
                        logger.warning(f"Channel {sub['channel_id']} not found, marking for cleanup")
                except discord.Forbidden:
                    failed_channels.append(sub['channel_id'])
                    logger.warning(f"No permission to send to channel {sub['channel_id']}")
                except Exception as e:
                    failed_channels.append(sub['channel_id'])
                    logger.error(f"Error sending to channel {sub['channel_id']}: {e}")
            
            logger.info(f"Notifications sent to {success_count}/{len(subscriptions)} channel(s)")
            
            # Clean up failed channels
            for channel_id in failed_channels:
                await self.db.remove_notification_subscription(channel_id)
            
        except Exception as e:
            logger.error(f"Error in notify_new_codes: {e}", exc_info=True)
    
    async def get_codes_from_db(self) -> List[ShiftCode]:
        """Get codes from database and convert to ShiftCode objects"""
        db_codes = await self.db.get_all_active_codes()
        
        shift_codes = []
        for db_code in db_codes:
            shift_code = ShiftCode(
                code=db_code['code'],
                reward=db_code['reward'],
                expires=db_code['expires'],
                source=db_code['source']
            )
            shift_codes.append(shift_code)
        
        return shift_codes
    
    async def get_codes(self, force_refresh: bool = False):
        """Get codes from cache or scrape fresh"""
        if force_refresh or not self.codes_cache or not self.last_update:
            logger.info("Fetching fresh codes...")
            
            # Scrape new codes
            scraped_codes = await self.scraper.get_all_codes()
            
            # Save to database
            for code in scraped_codes:
                await self.db.add_or_update_code(
                    code.code,
                    code.reward,
                    code.expires,
                    code.source
                )
            
            # Load from database
            self.codes_cache = await self.get_codes_from_db()
            self.last_update = datetime.now()
            return self.codes_cache
        
        # Check if cache is still valid
        if datetime.now() - self.last_update > self.cache_duration:
            logger.info("Cache expired, refreshing...")
            
            # Scrape new codes
            scraped_codes = await self.scraper.get_all_codes()
            
            # Save to database
            for code in scraped_codes:
                await self.db.add_or_update_code(
                    code.code,
                    code.reward,
                    code.expires,
                    code.source
                )
            
            # Load from database
            self.codes_cache = await self.get_codes_from_db()
            self.last_update = datetime.now()
        
        return self.codes_cache


# Initialize intents
intents = discord.Intents.default()
intents.message_content = True  # May not be needed for slash commands only

# Create bot instance
client = ShiftCodeBot(intents=intents)


@client.event
async def on_ready():
    """Called when bot is ready"""
    logger.info(f'Logged in as {client.user} (ID: {client.user.id})')
    logger.info('------')
    logger.info(f'Bot is ready and serving in {len(client.guilds)} guild(s)')


# --- Slash Commands ---

@client.tree.command()
@app_commands.describe()
async def codes(interaction: discord.Interaction):
    """Get all available Shift codes with pagination"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Log command usage
        await client.db.log_command_usage(
            "codes",
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None
        )
        
        codes = await client.get_codes()
        
        if not codes:
            await interaction.followup.send("No Shift codes found at this time.")
            return
        
        # Create pagination view
        view = CodesPaginationView(codes, page=0, last_update=client.last_update)
        embed = view.get_embed()
        
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Error in /codes command: {e}", exc_info=True)
        await interaction.followup.send("An error occurred while fetching codes. Please try again later.")


@client.tree.command()
@app_commands.describe()
async def latest(interaction: discord.Interaction):
    """Get only the most recent Shift code"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Log command usage
        await client.db.log_command_usage(
            "latest",
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None
        )
        
        codes = await client.get_codes()
        
        if not codes:
            await interaction.followup.send("No Shift codes found at this time.")
            return
        
        code = codes[0]
        
        # All scraped codes are assumed active
        status_emoji = "✅"
        
        embed = discord.Embed(
            title=f"{status_emoji} Latest Borderlands 4 Shift Code",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Code", value=f"`{code.code}`", inline=False)
        embed.add_field(name="Reward", value=code.reward, inline=True)
        embed.add_field(name="Source", value=code.source, inline=True)
        
        # Use 'expires' attribute, not 'expiration'
        if code.expires:
            embed.add_field(name="Expires", value=code.expires, inline=False)
        
        if client.last_update:
            embed.set_footer(text=f"Last updated: {client.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in /latest command: {e}", exc_info=True)
        await interaction.followup.send("An error occurred while fetching the latest code. Please try again later.")


@client.tree.command()
@app_commands.describe()
async def refresh(interaction: discord.Interaction):
    """Force refresh the codes cache"""
    # Check if user has administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "⛔ You need administrator permissions to use this command.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        logger.info(f"Manual refresh triggered by {interaction.user}")
        codes = await client.get_codes(force_refresh=True)
        
        await interaction.followup.send(
            f"✅ Cache refreshed! Found {len(codes)} code(s).",
            ephemeral=True
        )
        
    except Exception as e:
        logger.error(f"Error in /refresh command: {e}", exc_info=True)
        await interaction.followup.send(
            "An error occurred while refreshing codes. Please try again later.",
            ephemeral=True
        )


@client.tree.command()
@app_commands.describe()
async def subscribe(interaction: discord.Interaction):
    """Subscribe this channel to new code notifications"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Log command usage
        await client.db.log_command_usage(
            "subscribe",
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None
        )
        
        # Check if user has manage channels permission
        if interaction.guild and not interaction.user.guild_permissions.manage_channels:
            await interaction.followup.send(
                "⛔ You need 'Manage Channels' permission to subscribe to notifications.",
                ephemeral=True
            )
            return
        
        # Subscribe the channel
        success = await client.db.add_notification_subscription(
            str(interaction.channel_id),
            str(interaction.guild_id) if interaction.guild else "DM"
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Subscribed to Notifications",
                description="This channel will now receive notifications when new Shift codes are discovered!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="📬 What you'll get",
                value="• Automatic alerts for new codes\n"
                      "• Updates every 6 hours\n"
                      "• Direct redemption links",
                inline=False
            )
            embed.add_field(
                name="🔕 Unsubscribe",
                value="Use `/unsubscribe` to stop notifications",
                inline=False
            )
            embed.set_footer(text="Notifications will appear in this channel")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Channel {interaction.channel_id} subscribed to notifications")
        else:
            await interaction.followup.send(
                "ℹ️ This channel is already subscribed to notifications.",
                ephemeral=True
            )
        
    except Exception as e:
        logger.error(f"Error in /subscribe command: {e}", exc_info=True)
        await interaction.followup.send(
            "An error occurred while subscribing to notifications.",
            ephemeral=True
        )


@client.tree.command()
@app_commands.describe()
async def unsubscribe(interaction: discord.Interaction):
    """Unsubscribe this channel from new code notifications"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Log command usage
        await client.db.log_command_usage(
            "unsubscribe",
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None
        )
        
        # Check if user has manage channels permission
        if interaction.guild and not interaction.user.guild_permissions.manage_channels:
            await interaction.followup.send(
                "⛔ You need 'Manage Channels' permission to unsubscribe from notifications.",
                ephemeral=True
            )
            return
        
        # Unsubscribe the channel
        success = await client.db.remove_notification_subscription(str(interaction.channel_id))
        
        if success:
            embed = discord.Embed(
                title="🔕 Unsubscribed from Notifications",
                description="This channel will no longer receive new code notifications.",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="🔔 Want to re-subscribe?",
                value="Use `/subscribe` to enable notifications again",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Channel {interaction.channel_id} unsubscribed from notifications")
        else:
            await interaction.followup.send(
                "ℹ️ This channel is not subscribed to notifications.",
                ephemeral=True
            )
        
    except Exception as e:
        logger.error(f"Error in /unsubscribe command: {e}", exc_info=True)
        await interaction.followup.send(
            "An error occurred while unsubscribing from notifications.",
            ephemeral=True
        )


@client.tree.command()
@app_commands.describe()
async def stats(interaction: discord.Interaction):
    """Show bot statistics"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Log command usage
        await client.db.log_command_usage(
            "stats",
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None
        )
        
        # Get database statistics
        db_stats = await client.db.get_statistics()
        cmd_stats = await client.db.get_command_stats(days=7)
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            description="Usage and code tracking statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Code statistics
        code_stats = f"**Total Codes:** {db_stats['total_codes']}\n"
        code_stats += f"**Active:** {db_stats['active_codes']}\n"
        code_stats += f"**Expired:** {db_stats['inactive_codes']}"
        embed.add_field(name="📝 Codes", value=code_stats, inline=True)
        
        # Source statistics
        source_stats = ""
        for source, count in db_stats['by_source'].items():
            source_stats += f"**{source}:** {count}\n"
        if source_stats:
            embed.add_field(name="🌐 By Source", value=source_stats, inline=True)
        
        # Command usage (last 7 days)
        cmd_usage = f"**Total Commands:** {cmd_stats['total_commands']}\n"
        cmd_usage += f"**Unique Users:** {cmd_stats['unique_users']}\n"
        if cmd_stats['by_command']:
            cmd_usage += "\n**Most Used:**\n"
            for cmd, count in list(cmd_stats['by_command'].items())[:3]:
                cmd_usage += f"  `/{cmd}`: {count}\n"
        embed.add_field(name="📈 Usage (7 days)", value=cmd_usage, inline=False)
        
        # Top rewards
        if db_stats['top_rewards']:
            rewards_text = ""
            for reward, count in db_stats['top_rewards'][:3]:
                rewards_text += f"**{reward}:** {count} codes\n"
            embed.add_field(name="🎁 Top Rewards", value=rewards_text, inline=True)
        
        # Notification subscriptions
        subscriptions = await client.db.get_notification_subscriptions()
        if subscriptions:
            sub_text = f"**Active Subscriptions:** {len(subscriptions)}\n"
            sub_text += "Channels receiving notifications"
            embed.add_field(name="🔔 Notifications", value=sub_text, inline=True)
        
        # Last update
        if client.last_update:
            embed.set_footer(text=f"Last scrape: {client.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in /stats command: {e}", exc_info=True)
        await interaction.followup.send("An error occurred while fetching statistics.")


@client.tree.command()
@app_commands.describe()
async def help(interaction: discord.Interaction):
    """Display help information"""
    embed = discord.Embed(
        title="🎮 Borderlands 4 Shift Codes Bot - Help",
        description="A bot that automatically fetches and displays Borderlands 4 Shift codes.",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="/codes",
        value="Get all available Shift codes with pagination (5 per page)",
        inline=False
    )
    
    embed.add_field(
        name="/latest",
        value="Get only the most recent Shift code",
        inline=False
    )
    
    embed.add_field(
        name="/refresh",
        value="Force refresh the codes cache (Admin only)",
        inline=False
    )
    
    embed.add_field(
        name="/subscribe",
        value="Subscribe this channel to new code notifications",
        inline=False
    )
    
    embed.add_field(
        name="/unsubscribe",
        value="Unsubscribe this channel from notifications",
        inline=False
    )
    
    embed.add_field(
        name="/stats",
        value="Show bot statistics and usage data",
        inline=False
    )
    
    embed.add_field(
        name="/help",
        value="Display this help message",
        inline=False
    )
    
    embed.add_field(
        name="📊 Features",
        value="• 🔄 Auto-updates every 6 hours\n"
              "• 💾 Smart caching\n"
              "• 🌐 Multiple sources\n"
              "• ⚡ Fast responses\n"
              "• 📄 Paginated code browsing\n"
              "• 🔔 Automatic notifications",
        inline=False
    )
    
    embed.add_field(
        name="🔗 Redeem Codes",
        value="[Official SHIFT Rewards Site](https://shift.gearboxsoftware.com/rewards)",
        inline=False
    )
    
    embed.set_footer(text="Bot made for the Borderlands community")
    
    await interaction.response.send_message(embed=embed)


# Run the bot
if __name__ == "__main__":
    try:
        client.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        # Clean up database connection
        import asyncio
        if client.db.connection:
            asyncio.run(client.db.close())
