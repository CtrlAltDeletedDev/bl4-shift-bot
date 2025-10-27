"""
Borderlands 4 Shift Codes Discord Bot
Entry point for the bot
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from dotenv import load_dotenv

from bot.bot import ShiftCodeBot

# Load environment variables
load_dotenv()

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging
# Create formatters
detailed_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
)

# File handler with rotation (10MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    LOGS_DIR / "bot.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(detailed_formatter)

# Error file handler for errors only
error_handler = RotatingFileHandler(
    LOGS_DIR / "errors.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

# Console handler for terminal output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

# Configure the root logger (this applies to all loggers including discord.py)
# Clear any existing handlers first to avoid duplicates
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(error_handler)
root_logger.addHandler(console_handler)

# Get logger for this module
logger = logging.getLogger(__name__)

# Get environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env file")

# Optional: Convert TEST_GUILD_ID to discord.Object for faster syncing during development
MY_GUILD = discord.Object(id=int(TEST_GUILD_ID)) if TEST_GUILD_ID else None


def main():
    """Main entry point for the bot"""
    # Initialize intents
    intents = discord.Intents.default()
    intents.message_content = True

    # Create bot instance with optional test guild
    bot = ShiftCodeBot(intents=intents, test_guild=MY_GUILD)

    logger.info("Starting BL4 Shift Code Bot...")

    try:
        # Run the bot
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
    finally:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
