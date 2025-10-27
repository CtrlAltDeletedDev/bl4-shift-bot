"""
Discord UI Views and Components
"""

import math
from typing import List, Optional
from datetime import datetime

import discord
from discord.ui import View, Button

from .scraper import ShiftCode
from .helpers import format_code_field

# Pagination settings
CODES_PER_PAGE = 5


class CodesPaginationView(View):
    """Pagination view for browsing shift codes"""

    def __init__(
        self,
        codes: List[ShiftCode],
        page: int = 0,
        last_update: Optional[datetime] = None,
    ):
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
        self.first_button.disabled = self.page == 0
        self.prev_button.disabled = self.page == 0

        # Disable next/last if on last page
        self.next_button.disabled = self.page >= self.total_pages - 1
        self.last_button.disabled = self.page >= self.total_pages - 1

    def get_embed(self) -> discord.Embed:
        """Generate embed for current page"""
        start_idx = self.page * CODES_PER_PAGE
        end_idx = min(start_idx + CODES_PER_PAGE, len(self.codes))
        display_codes = self.codes[start_idx:end_idx]

        embed = discord.Embed(
            title="🎮 Borderlands 4 Shift Codes",
            description=f"Found {len(self.codes)} code(s) | Page {self.page + 1}/{self.total_pages}",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        for i, code in enumerate(display_codes, start=start_idx + 1):
            # Format code with proper expiration status
            status_emoji, field_value = format_code_field(
                code.code,
                code.reward,
                code.source,
                code.expires
            )

            field_name = f"{status_emoji} Code {i}"
            embed.add_field(name=field_name, value=field_value, inline=False)

        if self.last_update:
            embed.set_footer(
                text=f"Last updated: {self.last_update.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

        return embed

    @discord.ui.button(
        label="⏮️ First", style=discord.ButtonStyle.primary, custom_id="first"
    )
    async def first_button(self, interaction: discord.Interaction, button: Button):
        """Go to first page"""
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(
        label="◀️ Previous", style=discord.ButtonStyle.primary, custom_id="prev"
    )
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        """Go to previous page"""
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(
        label="▶️ Next", style=discord.ButtonStyle.primary, custom_id="next"
    )
    async def next_button(self, interaction: discord.Interaction, button: Button):
        """Go to next page"""
        self.page = min(self.total_pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(
        label="⏭️ Last", style=discord.ButtonStyle.primary, custom_id="last"
    )
    async def last_button(self, interaction: discord.Interaction, button: Button):
        """Go to last page"""
        self.page = self.total_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(
        label="🗑️ Close", style=discord.ButtonStyle.danger, custom_id="close"
    )
    async def close_button(self, interaction: discord.Interaction, button: Button):
        """Close the pagination view"""
        await interaction.response.edit_message(
            content="Closed shift codes list.", embed=None, view=None
        )
        self.stop()

    async def on_timeout(self):
        """Called when the view times out"""
        # Disable all buttons when timeout occurs
        for item in self.children:
            item.disabled = True
