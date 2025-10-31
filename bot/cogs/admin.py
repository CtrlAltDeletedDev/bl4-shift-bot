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

    # --- Prefix Commands (Owner Only) ---
    # These use ! prefix and are NOT slash commands

    @commands.command(name="refresh")
    @commands.is_owner()
    async def force_refresh(self, ctx):
        """Force refresh shift codes from all sources (Owner only)"""
        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # Don't fail if we can't delete

        await ctx.author.send("🔄 Force refreshing shift codes...")

        try:
            # Update expired codes first
            expired_count = await self.bot.db.update_expired_codes()
            if expired_count > 0:
                await ctx.author.send(f"📋 Marked {expired_count} code(s) as expired")

            # Force refresh from sources
            codes = await self.bot.get_codes(force_refresh=True)

            await ctx.author.send(f"✅ Refreshed! Found {len(codes)} active code(s)")
            logger.info(f"Manual force refresh by {ctx.author}")
        except Exception as e:
            await ctx.author.send(f"❌ Error refreshing: {e}")
            logger.error(f"Error in !refresh command: {e}", exc_info=True)

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync_commands(self, ctx):
        """Sync slash commands (Owner only)"""
        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # Don't fail if we can't delete

        await ctx.author.send("🔄 Syncing slash commands...")

        try:
            if self.bot.test_guild:
                # Sync to test guild
                self.bot.tree.copy_global_to(guild=self.bot.test_guild)
                await self.bot.tree.sync(guild=self.bot.test_guild)
                await ctx.author.send(f"✅ Synced commands to guild {self.bot.test_guild.id}")
            else:
                # Sync globally
                await self.bot.tree.sync()
                await ctx.author.send("✅ Synced commands globally (may take up to 1 hour)")
        except Exception as e:
            await ctx.author.send(f"❌ Error syncing: {e}")
            logger.error(f"Error syncing commands: {e}", exc_info=True)

    @commands.command(name="shutdown")
    @commands.is_owner()
    async def shutdown_bot(self, ctx):
        """Shutdown the bot (Owner only)"""
        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # Don't fail if we can't delete

        await ctx.author.send("👋 Shutting down...")
        logger.info(f"Shutdown command issued by {ctx.author}")
        await self.bot.close()

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_cog(self, ctx, cog_name: str = None):
        """Reload a specific cog or all cogs (Owner only)"""
        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # Don't fail if we can't delete

        if cog_name:
            # Reload specific cog
            try:
                await self.bot.reload_extension(f"bot.cogs.{cog_name}")
                await ctx.author.send(f"✅ Reloaded cog: {cog_name}")
                logger.info(f"Reloaded cog: {cog_name}")
            except Exception as e:
                await ctx.author.send(f"❌ Error reloading {cog_name}: {e}")
                logger.error(f"Error reloading cog {cog_name}: {e}", exc_info=True)
        else:
            # Reload all cogs
            await ctx.author.send("🔄 Reloading all cogs...")
            try:
                for ext in list(self.bot.extensions.keys()):
                    if ext.startswith("bot.cogs."):
                        await self.bot.reload_extension(ext)
                await ctx.author.send("✅ All cogs reloaded")
                logger.info("All cogs reloaded")
            except Exception as e:
                await ctx.author.send(f"❌ Error reloading cogs: {e}")
                logger.error(f"Error reloading cogs: {e}", exc_info=True)

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(AdminCog(bot))
