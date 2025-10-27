"""
Helper utilities for the bot
"""

from datetime import datetime
from typing import Optional, Tuple


def check_code_expiration(expires: Optional[str]) -> Tuple[bool, str]:
    """
    Check if a code is expired based on its expiration string.

    Args:
        expires: Expiration string (None, "Never", or date string)

    Returns:
        Tuple of (is_expired, emoji)
        - is_expired: True if code is definitely expired
        - emoji: Status emoji to display
    """
    if not expires:
        # No expiration info - assume active
        return False, "✅"

    expires_lower = expires.lower().strip()

    # Check for "never" or similar
    if expires_lower in ["never", "no expiration", "permanent", "n/a", "none"]:
        return False, "✅"

    # Try to parse as date
    # Common formats: "2025-12-31", "Dec 31, 2025", "12/31/2025", etc.
    try:
        # Try various date formats
        date_formats = [
            "%Y-%m-%d",           # 2025-12-31
            "%m/%d/%Y",           # 12/31/2025
            "%d/%m/%Y",           # 31/12/2025
            "%B %d, %Y",          # December 31, 2025
            "%b %d, %Y",          # Dec 31, 2025
            "%Y-%m-%d %H:%M:%S",  # 2025-12-31 23:59:59
        ]

        expiration_date = None
        for fmt in date_formats:
            try:
                expiration_date = datetime.strptime(expires, fmt)
                break
            except ValueError:
                continue

        if expiration_date:
            # Compare with current date
            if expiration_date < datetime.now():
                return True, "❌"  # Expired
            else:
                return False, "✅"  # Still active
        else:
            # Couldn't parse date, assume active but mark as unknown
            return False, "⚠️"

    except Exception:
        # If anything fails, assume active but show warning
        return False, "⚠️"


def format_code_field(code_str: str, reward: str, source: str, expires: Optional[str]) -> Tuple[str, str]:
    """
    Format a code's field for display in Discord embed.

    Args:
        code_str: The shift code
        reward: Reward description
        source: Source of the code
        expires: Expiration info

    Returns:
        Tuple of (status_emoji, field_value)
    """
    is_expired, emoji = check_code_expiration(expires)

    # Build field value
    field_value = f"**Code:** `{code_str}`\n"
    field_value += f"**Reward:** {reward}\n"
    field_value += f"**Source:** {source}"

    if expires:
        if is_expired:
            field_value += f"\n**Status:** ❌ Expired ({expires})"
        else:
            field_value += f"\n**Expires:** {expires}"

    return emoji, field_value
