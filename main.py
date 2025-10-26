"""
Borderlands 4 Shift Code Discord Bot
Uses slash commands to fetch and display Shift codes
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

from scraper import ShiftCodeScraper, ShiftCode

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID')

if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables!")

# Create bot instance
intents = discord.Intents.default()
intents.message_content = True  # Required for some features


class ShiftCodeBot(commands.Bot):
    """Custom Discord Bot for Borderlands 4 Shift Codes"""
    
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.scraper = None
        self.cached_codes = []
        self.last_update = None
    
    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Initialize the scraper
        self.scraper = ShiftCodeScraper()
        
        # Start background tasks
        self.update_codes_task.start()
        
        # Sync commands (for testing, use guild; for production, sync globally)
        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Commands synced to test guild {TEST_GUILD_ID}")
        else:
            await self.tree.sync()
            logger.info("Commands synced globally")
    
    async def close(self):
        """Cleanup when bot shuts down"""
        if self.scraper and self.scraper.session:
            await self.scraper.session.close()
        await super().close()
    
    @tasks.loop(hours=6)
    async def update_codes_task(self):
        """Background task to update codes every 6 hours"""
        logger.info("Updating Shift codes cache...")
        try:
            codes = await self.scraper.get_all_codes()
            self.cached_codes = codes
            self.last_update = datetime.now(timezone.utc)
            logger.info(f"Updated cache with {len(codes)} codes")
        except Exception as e:
            logger.error(f"Error updating codes: {str(e)}")
    
    @update_codes_task.before_loop
    async def before_update_task(self):
        """Wait until bot is ready before starting the update task"""
        await self.wait_until_ready()


# Create bot instance
bot = ShiftCodeBot()


# Pagination View for code embeds
class CodePaginationView(discord.ui.View):
    """Pagination view for browsing through multiple code embeds"""
    
    def __init__(self, embeds: list[discord.Embed], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.max_pages = len(embeds)
        
        # Disable buttons if only one page
        if self.max_pages <= 1:
            self.previous_button.disabled = True
            self.next_button.disabled = True
            self.first_button.disabled = True
            self.last_button.disabled = True
        else:
            self.previous_button.disabled = True
            self.first_button.disabled = True
    
    def update_buttons(self):
        """Update button states based on current page"""
        self.first_button.disabled = self.current_page == 0
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1
        self.last_button.disabled = self.current_page >= self.max_pages - 1
    
    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.blurple)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.max_pages - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.blurple)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.max_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            item.disabled = True


@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler for application commands"""
    # Ignore NotFound errors (interaction expired) - these are harmless
    if isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.errors.NotFound):
            logger.debug(f"Interaction expired for command {interaction.command.name if interaction.command else 'unknown'}")
            return
    
    # Log other errors
    logger.error(f"Command error: {error}", exc_info=error)


@bot.tree.command(name="codes", description="Get all available Borderlands 4 Shift codes")
async def get_codes(interaction: discord.Interaction):
    """Slash command to get all Shift codes with pagination"""
    # Respond immediately to avoid timeout
    await interaction.response.defer(thinking=True)
    
    try:
        # Use cached codes if available and recent (less than 1 hour old)
        if bot.cached_codes and bot.last_update:
            time_diff = (datetime.now(timezone.utc) - bot.last_update).total_seconds()
            if time_diff < 3600:  # 1 hour
                codes = bot.cached_codes
                logger.info("Using cached codes")
            else:
                codes = await bot.scraper.get_all_codes()
                bot.cached_codes = codes
                bot.last_update = datetime.now(timezone.utc)
        else:
            codes = await bot.scraper.get_all_codes()
            bot.cached_codes = codes
            bot.last_update = datetime.now(timezone.utc)
        
        if not codes:
            embed = discord.Embed(
                title="❌ No Shift Codes Found",
                description="Sorry, couldn't find any Shift codes at the moment. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create paginated embeds
        # Discord limits: 25 fields per embed, 1024 chars per field value
        # Each code uses 1 field with ~150 chars, so 6 codes = 6 fields (safe)
        embeds = []
        codes_per_page = 6  # Safe limit while still showing good amount
        total_pages = (len(codes) + codes_per_page - 1) // codes_per_page
        
        for page in range(total_pages):
            start_idx = page * codes_per_page
            end_idx = min(start_idx + codes_per_page, len(codes))
            page_codes = codes[start_idx:end_idx]
            
            # Create embed for this page
            embed = discord.Embed(
                title=f"🎮 Borderlands 4 Shift Codes",
                description=f"Page {page + 1} of {total_pages} • Total: {len(codes)} codes",
                color=discord.Color.gold()
            )
            
            # Add each code as a field
            for i, code in enumerate(page_codes, start=start_idx + 1):
                field_name = f"📋 Code #{i}"
                field_value = (
                    f"**Code:** `{code.code}`\n"
                    f"**Reward:** {code.reward}\n"
                    f"**Expires:** {code.expires or 'Unknown'}\n"
                    f"**Source:** {code.source}"
                )
                embed.add_field(name=field_name, value=field_value, inline=False)
            
            # Add footer with cache info
            if bot.last_update:
                embed.set_footer(text=f"Last updated: {bot.last_update.strftime('%Y-%m-%d %H:%M UTC')} • Use /refresh to update")
            
            embeds.append(embed)
        
        # Send with pagination if multiple pages
        if len(embeds) > 1:
            view = CodePaginationView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)
        else:
            await interaction.followup.send(embed=embeds[0])
        
        logger.info(f"Sent {len(codes)} codes ({total_pages} pages) to {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error in get_codes command: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Try to send error message
        try:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}\nPlease try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except:
            # If followup fails, interaction probably expired
            logger.error("Could not send error message - interaction may have expired")


@bot.tree.command(name="refresh", description="Force refresh the Shift codes cache")
async def refresh_codes(interaction: discord.Interaction):
    """Slash command to manually refresh codes (ephemeral response)"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        codes = await bot.scraper.get_all_codes()
        bot.cached_codes = codes
        bot.last_update = datetime.now(timezone.utc)
        
        embed = discord.Embed(
            title="✅ Cache Refreshed",
            description=f"Successfully updated cache with {len(codes)} Shift codes!",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Updated at {bot.last_update.strftime('%Y-%m-%d %H:%M UTC')}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Cache refreshed by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error in refresh command: {str(e)}")
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while refreshing the cache. Please try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="latest", description="Get the most recent Borderlands 4 Shift code")
async def latest_code(interaction: discord.Interaction):
    """Slash command to get only the latest code"""
    # Defer immediately to avoid timeout
    try:
        await interaction.response.defer(thinking=True)
    except (discord.errors.NotFound, discord.errors.HTTPException) as e:
        logger.warning(f"Could not defer latest command: {e}")
        return
    
    try:
        # Use cached or fetch new
        if bot.cached_codes and bot.last_update:
            time_diff = (datetime.now(timezone.utc) - bot.last_update).total_seconds()
            if time_diff < 3600:
                codes = bot.cached_codes
                logger.info("Using cached codes for latest")
            else:
                codes = await bot.scraper.get_all_codes()
                bot.cached_codes = codes
                bot.last_update = datetime.now(timezone.utc)
        else:
            codes = await bot.scraper.get_all_codes()
            bot.cached_codes = codes
            bot.last_update = datetime.now(timezone.utc)
        
        if not codes:
            embed = discord.Embed(
                title="❌ No Shift Codes Found",
                description="Sorry, couldn't find any Shift codes at the moment.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Get the most recent code
        latest = codes[0]
        
        embed = discord.Embed(
            title="🎮 Latest Shift Code",
            color=discord.Color.gold()
        )
        embed.add_field(name="Code", value=f"`{latest.code}`", inline=False)
        embed.add_field(name="Reward", value=latest.reward, inline=True)
        embed.add_field(name="Expires", value=latest.expires or "Unknown", inline=True)
        embed.add_field(name="Source", value=latest.source, inline=True)
        embed.set_footer(text=f"Scraped at {latest.scraped_at.strftime('%Y-%m-%d %H:%M UTC')}")
        
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent latest code to {interaction.user}")
        
    except (discord.errors.NotFound, discord.errors.HTTPException) as e:
        logger.warning(f"Interaction issue in latest command: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in latest command: {str(e)}")
        try:
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while fetching the latest code.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except:
            pass  # Silently fail if we can't send error message


@bot.tree.command(name="help", description="Get help with bot commands")
async def help_command(interaction: discord.Interaction):
    """Slash command to display help information (ephemeral response)"""
    embed = discord.Embed(
        title="🎮 Borderlands 4 Shift Code Bot - Help",
        description="Get Shift codes for Borderlands 4 from multiple sources!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/codes",
        value="Get all available Shift codes with pagination support",
        inline=False
    )
    embed.add_field(
        name="/latest",
        value="Get only the most recent Shift code",
        inline=False
    )
    embed.add_field(
        name="/refresh",
        value="Force refresh the codes cache (only you can see the result)",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="Show this help message (only you can see it)",
        inline=False
    )
    
    embed.set_footer(text="Codes are cached for 1 hour and auto-updated every 6 hours")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


def main():
    """Main entry point"""
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")


if __name__ == "__main__":
    main()
