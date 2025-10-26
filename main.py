"""
Borderlands 4 Shift Code Discord Bot
Uses slash commands to fetch and display Shift codes
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import logging
from datetime import datetime
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
            self.last_update = datetime.utcnow()
            logger.info(f"Updated cache with {len(codes)} codes")
        except Exception as e:
            logger.error(f"Error updating codes: {str(e)}")
    
    @update_codes_task.before_loop
    async def before_update_task(self):
        """Wait until bot is ready before starting the update task"""
        await self.wait_until_ready()


# Create bot instance
bot = ShiftCodeBot()


@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')


@bot.tree.command(name="codes", description="Get all available Borderlands 4 Shift codes")
async def get_codes(interaction: discord.Interaction):
    """Slash command to get all Shift codes"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Use cached codes if available and recent (less than 1 hour old)
        if bot.cached_codes and bot.last_update:
            time_diff = (datetime.utcnow() - bot.last_update).total_seconds()
            if time_diff < 3600:  # 1 hour
                codes = bot.cached_codes
                logger.info("Using cached codes")
            else:
                codes = await bot.scraper.get_all_codes()
                bot.cached_codes = codes
                bot.last_update = datetime.utcnow()
        else:
            codes = await bot.scraper.get_all_codes()
            bot.cached_codes = codes
            bot.last_update = datetime.utcnow()
        
        if not codes:
            embed = discord.Embed(
                title="❌ No Shift Codes Found",
                description="Sorry, couldn't find any Shift codes at the moment. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create embeds for each code (Discord limits to 10 embeds per message)
        embeds = []
        for i, code in enumerate(codes[:10]):  # Limit to 10 codes
            embed = discord.Embed(
                title=f"🎮 Shift Code #{i+1}",
                color=discord.Color.gold()
            )
            embed.add_field(name="Code", value=f"`{code.code}`", inline=False)
            embed.add_field(name="Reward", value=code.reward, inline=True)
            embed.add_field(name="Expires", value=code.expires or "Unknown", inline=True)
            embed.add_field(name="Source", value=code.source, inline=True)
            embed.set_footer(text=f"Scraped at {code.scraped_at.strftime('%Y-%m-%d %H:%M UTC')}")
            embeds.append(embed)
        
        # Send response
        if len(codes) > 10:
            warning_embed = discord.Embed(
                title="ℹ️ Note",
                description=f"Showing 10 of {len(codes)} codes. Use `/refresh` to update the cache.",
                color=discord.Color.blue()
            )
            embeds.insert(0, warning_embed)
        
        await interaction.followup.send(embeds=embeds)
        logger.info(f"Sent {len(embeds)} codes to {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error in get_codes command: {str(e)}")
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while fetching Shift codes. Please try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="refresh", description="Force refresh the Shift codes cache")
async def refresh_codes(interaction: discord.Interaction):
    """Slash command to manually refresh codes"""
    await interaction.response.defer(thinking=True)
    
    try:
        codes = await bot.scraper.get_all_codes()
        bot.cached_codes = codes
        bot.last_update = datetime.utcnow()
        
        embed = discord.Embed(
            title="✅ Cache Refreshed",
            description=f"Successfully updated cache with {len(codes)} Shift codes!",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Updated at {bot.last_update.strftime('%Y-%m-%d %H:%M UTC')}")
        
        await interaction.followup.send(embed=embed)
        logger.info(f"Cache refreshed by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error in refresh command: {str(e)}")
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while refreshing the cache. Please try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="latest", description="Get the most recent Borderlands 4 Shift code")
async def latest_code(interaction: discord.Interaction):
    """Slash command to get only the latest code"""
    await interaction.response.defer(thinking=True)
    
    try:
        # Use cached or fetch new
        if bot.cached_codes and bot.last_update:
            time_diff = (datetime.utcnow() - bot.last_update).total_seconds()
            if time_diff < 3600:
                codes = bot.cached_codes
            else:
                codes = await bot.scraper.get_all_codes()
                bot.cached_codes = codes
                bot.last_update = datetime.utcnow()
        else:
            codes = await bot.scraper.get_all_codes()
            bot.cached_codes = codes
            bot.last_update = datetime.utcnow()
        
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
        
    except Exception as e:
        logger.error(f"Error in latest command: {str(e)}")
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while fetching the latest code.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="help", description="Get help with bot commands")
async def help_command(interaction: discord.Interaction):
    """Slash command to display help information"""
    embed = discord.Embed(
        title="🎮 Borderlands 4 Shift Code Bot - Help",
        description="Get Shift codes for Borderlands 4 from multiple sources!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/codes",
        value="Get all available Shift codes (up to 10)",
        inline=False
    )
    embed.add_field(
        name="/latest",
        value="Get only the most recent Shift code",
        inline=False
    )
    embed.add_field(
        name="/refresh",
        value="Force refresh the codes cache",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="Show this help message",
        inline=False
    )
    
    embed.set_footer(text="Codes are cached and auto-updated every 6 hours")
    
    await interaction.response.send_message(embed=embed)


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
