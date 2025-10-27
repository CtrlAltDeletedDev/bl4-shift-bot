"""
Info Cog - Informational commands
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class InfoCog(commands.Cog, name="Info"):
    """Informational and help commands"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats")
    async def stats(self, interaction: discord.Interaction):
        """Show bot statistics"""
        await interaction.response.defer(thinking=True)

        try:
            # Log command usage
            await self.bot.db.log_command_usage(
                "stats",
                str(interaction.user.id),
                str(interaction.guild_id) if interaction.guild else None,
            )

            # Get database statistics
            db_stats = await self.bot.db.get_statistics()
            cmd_stats = await self.bot.db.get_command_stats(days=7)

            embed = discord.Embed(
                title="📊 Bot Statistics",
                description="Usage and code tracking statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(),
            )

            # Code statistics
            code_stats = f"**Total Codes:** {db_stats['total_codes']}\n"
            code_stats += f"**Active:** {db_stats['active_codes']}\n"
            code_stats += f"**Expired:** {db_stats['inactive_codes']}"
            embed.add_field(name="📝 Codes", value=code_stats, inline=True)

            # Source statistics
            source_stats = ""
            for source, count in db_stats["by_source"].items():
                source_stats += f"**{source}:** {count}\n"
            if source_stats:
                embed.add_field(name="🌐 By Source", value=source_stats, inline=True)

            # Command usage (last 7 days)
            cmd_usage = f"**Total Commands:** {cmd_stats['total_commands']}\n"
            cmd_usage += f"**Unique Users:** {cmd_stats['unique_users']}\n"
            if cmd_stats["by_command"]:
                cmd_usage += "\n**Most Used:**\n"
                for cmd, count in list(cmd_stats["by_command"].items())[:3]:
                    cmd_usage += f"  `/{cmd}`: {count}\n"
            embed.add_field(name="📈 Usage (7 days)", value=cmd_usage, inline=False)

            # Top rewards
            if db_stats["top_rewards"]:
                rewards_text = ""
                for reward, count in db_stats["top_rewards"][:3]:
                    rewards_text += f"**{reward}:** {count} codes\n"
                embed.add_field(name="🎁 Top Rewards", value=rewards_text, inline=True)

            # Notification subscriptions
            subscriptions = await self.bot.db.get_notification_subscriptions()
            if subscriptions:
                sub_text = f"**Active Subscriptions:** {len(subscriptions)}\n"
                sub_text += "Channels receiving notifications"
                embed.add_field(name="🔔 Notifications", value=sub_text, inline=True)

            # Last update
            if self.bot.last_update:
                embed.set_footer(
                    text=f"Last scrape: {self.bot.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in /stats command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while fetching statistics."
            )

    @app_commands.command(name="help")
    async def help(self, interaction: discord.Interaction):
        """Display help information"""
        embed = discord.Embed(
            title="🎮 Borderlands 4 Shift Codes Bot - Help",
            description="A bot that automatically fetches and displays Borderlands 4 Shift codes.",
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="/codes",
            value="Get all available Shift codes with pagination (5 per page)",
            inline=False,
        )

        embed.add_field(
            name="/latest", value="Get only the most recent Shift code", inline=False
        )

        embed.add_field(
            name="/refresh",
            value="Force refresh the codes cache (Admin only)",
            inline=False,
        )

        embed.add_field(
            name="/subscribe",
            value="Subscribe this channel to new code notifications",
            inline=False,
        )

        embed.add_field(
            name="/unsubscribe",
            value="Unsubscribe this channel from notifications",
            inline=False,
        )

        embed.add_field(
            name="/stats", value="Show bot statistics and usage data", inline=False
        )

        embed.add_field(name="/help", value="Display this help message", inline=False)

        embed.add_field(
            name="📊 Features",
            value="• 🔄 Auto-updates every 6 hours\n"
            "• 💾 Smart caching\n"
            "• 🌐 Multiple sources\n"
            "• ⚡ Fast responses\n"
            "• 📄 Paginated code browsing\n"
            "• 🔔 Automatic notifications",
            inline=False,
        )

        embed.add_field(
            name="🔗 Redeem Codes",
            value="[Official SHIFT Rewards Site](https://shift.gearboxsoftware.com/rewards)",
            inline=False,
        )

        embed.set_footer(text="Bot made for the Borderlands community")

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(InfoCog(bot))
