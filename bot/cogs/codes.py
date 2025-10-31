"""
Codes Cog - Commands for viewing shift codes
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.views import CodesPaginationView
from ..utils.helpers import format_code_field

logger = logging.getLogger(__name__)


class CodesCog(commands.Cog, name="Codes"):
    """Commands for viewing and browsing shift codes"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="codes")
    async def codes(self, interaction: discord.Interaction):
        """Get all available Shift codes with pagination"""
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "codes",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            codes = await self.bot.get_codes()

            if not codes:
                await interaction.followup.send("No Shift codes found at this time.", ephemeral=True)
                return

            # Create pagination view
            view = CodesPaginationView(codes, page=0, last_update=self.bot.last_update)
            embed = view.get_embed()

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /codes command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while fetching codes. Please try again later.", ephemeral=True
            )

    @app_commands.command(name="latest")
    async def latest(self, interaction: discord.Interaction):
        """Get only the most recent Shift code"""
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "latest",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            codes = await self.bot.get_codes()

            if not codes:
                await interaction.followup.send("No Shift codes found at this time.", ephemeral=True)
                return

            code = codes[0]

            # Check expiration status
            status_emoji, _ = format_code_field(
                code.code,
                code.reward,
                code.source,
                code.expires
            )

            # Set color based on status
            if status_emoji == "❌":
                embed_color = discord.Color.red()
            elif status_emoji == "⚠️":
                embed_color = discord.Color.orange()
            else:
                embed_color = discord.Color.green()

            embed = discord.Embed(
                title=f"{status_emoji} Latest Borderlands 4 Shift Code",
                color=embed_color,
                timestamp=datetime.now(),
            )

            embed.add_field(name="Code", value=f"`{code.code}`", inline=False)
            embed.add_field(name="Reward", value=code.reward, inline=True)
            embed.add_field(name="Source", value=code.source, inline=True)

            # Add expiration info with proper status
            if code.expires:
                from ..utils.helpers import check_code_expiration
                is_expired, _ = check_code_expiration(code.expires)

                if is_expired:
                    embed.add_field(
                        name="Status",
                        value=f"❌ Expired ({code.expires})",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Expires",
                        value=code.expires,
                        inline=False
                    )

            if self.bot.last_update:
                embed.set_footer(
                    text=f"Last updated: {self.bot.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /latest command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while fetching the latest code. Please try again later.", ephemeral=True
            )


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(CodesCog(bot))
