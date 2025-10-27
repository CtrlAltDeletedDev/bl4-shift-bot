"""
Codes Cog - Commands for viewing shift codes
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.views import CodesPaginationView

logger = logging.getLogger(__name__)


class CodesCog(commands.Cog, name="Codes"):
    """Commands for viewing and browsing shift codes"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="codes")
    async def codes(self, interaction: discord.Interaction):
        """Get all available Shift codes with pagination"""
        await interaction.response.defer(thinking=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "codes",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            codes = await self.bot.get_codes()

            if not codes:
                await interaction.followup.send("No Shift codes found at this time.")
                return

            # Create pagination view
            view = CodesPaginationView(codes, page=0, last_update=self.bot.last_update)
            embed = view.get_embed()

            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error in /codes command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while fetching codes. Please try again later."
            )

    @app_commands.command(name="latest")
    async def latest(self, interaction: discord.Interaction):
        """Get only the most recent Shift code"""
        await interaction.response.defer(thinking=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "latest",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            codes = await self.bot.get_codes()

            if not codes:
                await interaction.followup.send("No Shift codes found at this time.")
                return

            code = codes[0]

            # All scraped codes are assumed active
            status_emoji = "✅"

            embed = discord.Embed(
                title=f"{status_emoji} Latest Borderlands 4 Shift Code",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )

            embed.add_field(name="Code", value=f"`{code.code}`", inline=False)
            embed.add_field(name="Reward", value=code.reward, inline=True)
            embed.add_field(name="Source", value=code.source, inline=True)

            # Use 'expires' attribute, not 'expiration'
            if code.expires:
                embed.add_field(name="Expires", value=code.expires, inline=False)

            if self.bot.last_update:
                embed.set_footer(
                    text=f"Last updated: {self.bot.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in /latest command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while fetching the latest code. Please try again later."
            )


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(CodesCog(bot))
