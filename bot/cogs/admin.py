"""
Admin Cog - Administrative commands
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Administrative commands for bot management"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="refresh")
    async def refresh(self, interaction: discord.Interaction):
        """Force refresh the codes cache"""
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "⛔ You need administrator permissions to use this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            logger.info(f"Manual refresh triggered by {interaction.user}")
            codes = await self.bot.get_codes(force_refresh=True)

            await interaction.followup.send(
                f"✅ Cache refreshed! Found {len(codes)} code(s).", ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /refresh command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while refreshing codes. Please try again later.",
                ephemeral=True,
            )


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(AdminCog(bot))
