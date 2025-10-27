"""
Notifications Cog - Commands for managing code notifications
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class NotificationsCog(commands.Cog, name="Notifications"):
    """Commands for subscribing to new code notifications"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="subscribe")
    async def subscribe(self, interaction: discord.Interaction):
        """Subscribe this channel to new code notifications"""
        await interaction.response.defer(thinking=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "subscribe",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            # Check if user has manage channels permission
            if (
                interaction.guild
                and not interaction.user.guild_permissions.manage_channels
            ):
                await interaction.followup.send(
                    "⛔ You need 'Manage Channels' permission to subscribe to notifications.",
                    ephemeral=True,
                )
                return

            # Subscribe the channel
            success = await self.bot.db.add_notification_subscription(
                str(interaction.channel_id),
                str(interaction.guild_id) if interaction.guild else "DM",
            )

            if success:
                embed = discord.Embed(
                    title="✅ Subscribed to Notifications",
                    description="This channel will now receive notifications when new Shift codes are discovered!",
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name="📬 What you'll get",
                    value="• Automatic alerts for new codes\n"
                    "• Updates every 6 hours\n"
                    "• Direct redemption links",
                    inline=False,
                )
                embed.add_field(
                    name="🔕 Unsubscribe",
                    value="Use `/unsubscribe` to stop notifications",
                    inline=False,
                )
                embed.set_footer(text="Notifications will appear in this channel")

                await interaction.followup.send(embed=embed)
                logger.info(
                    f"Channel {interaction.channel_id} subscribed to notifications"
                )
            else:
                await interaction.followup.send(
                    "ℹ️ This channel is already subscribed to notifications.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error in /subscribe command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while subscribing to notifications.", ephemeral=True
            )

    @app_commands.command(name="unsubscribe")
    async def unsubscribe(self, interaction: discord.Interaction):
        """Unsubscribe this channel from new code notifications"""
        await interaction.response.defer(thinking=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "unsubscribe",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            # Check if user has manage channels permission
            if (
                interaction.guild
                and not interaction.user.guild_permissions.manage_channels
            ):
                await interaction.followup.send(
                    "⛔ You need 'Manage Channels' permission to unsubscribe from notifications.",
                    ephemeral=True,
                )
                return

            # Unsubscribe the channel
            success = await self.bot.db.remove_notification_subscription(
                str(interaction.channel_id)
            )

            if success:
                embed = discord.Embed(
                    title="🔕 Unsubscribed from Notifications",
                    description="This channel will no longer receive new code notifications.",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="🔔 Want to re-subscribe?",
                    value="Use `/subscribe` to enable notifications again",
                    inline=False,
                )

                await interaction.followup.send(embed=embed)
                logger.info(
                    f"Channel {interaction.channel_id} unsubscribed from notifications"
                )
            else:
                await interaction.followup.send(
                    "ℹ️ This channel is not subscribed to notifications.", ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in /unsubscribe command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while unsubscribing from notifications.",
                ephemeral=True,
            )


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(NotificationsCog(bot))
