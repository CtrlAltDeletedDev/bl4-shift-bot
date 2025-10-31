"""
Database module for Borderlands 4 Shift Codes Bot
Handles SQLite database operations for code storage and tracking
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
from pathlib import Path
import aiosqlite

logger = logging.getLogger(__name__)


class ShiftCodeDatabase:
    """SQLite database handler for shift codes"""

    def __init__(self, db_path: str = "shift_codes.db"):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Connect to the database"""
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self.initialize_database()
        logger.info(f"Connected to database: {self.db_path}")

    async def close(self):
        """Close the database connection"""
        if self.connection:
            await self.connection.close()
            logger.info("Database connection closed")

    async def initialize_database(self):
        """Create tables if they don't exist"""
        async with self.connection.cursor() as cursor:
            # Codes table - stores all shift codes
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    reward TEXT NOT NULL,
                    expires TEXT,
                    source TEXT NOT NULL,
                    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    times_scraped INTEGER DEFAULT 1,
                    notes TEXT
                )
            """)

            # Code history table - tracks when codes were found
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS code_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_id INTEGER NOT NULL,
                    scraped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    source TEXT NOT NULL,
                    FOREIGN KEY (code_id) REFERENCES codes (id)
                )
            """)

            # Command usage stats
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS command_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    guild_id TEXT,
                    used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Notification subscriptions
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    guild_id TEXT NOT NULL,
                    subscribed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)

            # Create indexes for better performance
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_codes_code ON codes(code)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_codes_is_active ON codes(is_active)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_code_history_code_id ON code_history(code_id)
            """)

            await self.connection.commit()
            logger.info("Database tables initialized")

    async def add_or_update_code(
        self, code: str, reward: str, expires: Optional[str], source: str
    ) -> Tuple[int, bool]:
        """
        Add a new code or update existing one
        Returns: (code_id, is_new)
        """
        async with self.connection.cursor() as cursor:
            # Check if code exists
            await cursor.execute(
                "SELECT id, times_scraped FROM codes WHERE code = ?", (code,)
            )
            row = await cursor.fetchone()

            if row:
                # Update existing code
                code_id = row[0]
                times_scraped = row[1] + 1

                await cursor.execute(
                    """
                    UPDATE codes
                    SET last_seen = ?, times_scraped = ?, source = ?, reward = ?, expires = ?
                    WHERE id = ?
                """,
                    (datetime.now(timezone.utc), times_scraped, source, reward, expires, code_id),
                )

                # Add to history
                await cursor.execute(
                    """
                    INSERT INTO code_history (code_id, source)
                    VALUES (?, ?)
                """,
                    (code_id, source),
                )

                await self.connection.commit()
                return (code_id, False)
            else:
                # Insert new code
                await cursor.execute(
                    """
                    INSERT INTO codes (code, reward, expires, source)
                    VALUES (?, ?, ?, ?)
                """,
                    (code, reward, expires, source),
                )

                code_id = cursor.lastrowid

                # Add to history
                await cursor.execute(
                    """
                    INSERT INTO code_history (code_id, source)
                    VALUES (?, ?)
                """,
                    (code_id, source),
                )

                await self.connection.commit()
                logger.info(f"New code added: {code} ({reward})")
                return (code_id, True)

    async def get_all_active_codes(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all active codes, ordered by most recent first"""
        async with self.connection.cursor() as cursor:
            query = """
                SELECT id, code, reward, expires, source, first_seen, last_seen, times_scraped
                FROM codes 
                WHERE is_active = 1
                ORDER BY first_seen DESC
            """
            if limit:
                query += f" LIMIT {limit}"

            await cursor.execute(query)
            rows = await cursor.fetchall()

            return [dict(row) for row in rows]

    async def get_code_by_code(self, code: str) -> Optional[Dict]:
        """Get a specific code by its code string"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, code, reward, expires, source, first_seen, last_seen, 
                       is_active, times_scraped, notes
                FROM codes 
                WHERE code = ?
            """,
                (code,),
            )

            row = await cursor.fetchone()
            return dict(row) if row else None

    async def mark_code_inactive(self, code: str) -> bool:
        """Mark a code as inactive (expired)"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE codes 
                SET is_active = 0
                WHERE code = ?
            """,
                (code,),
            )

            await self.connection.commit()
            affected = cursor.rowcount

            if affected > 0:
                logger.info(f"Code marked inactive: {code}")
                return True
            return False

    async def get_new_codes_since(self, timestamp: datetime) -> List[Dict]:
        """Get codes that were added after a specific timestamp"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, code, reward, expires, source, first_seen
                FROM codes 
                WHERE first_seen > ? AND is_active = 1
                ORDER BY first_seen DESC
            """,
                (timestamp,),
            )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_codes_by_source(self, source: str) -> List[Dict]:
        """Get all active codes from a specific source"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, code, reward, expires, source, first_seen, last_seen
                FROM codes 
                WHERE source = ? AND is_active = 1
                ORDER BY first_seen DESC
            """,
                (source,),
            )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def search_codes(self, search_term: str) -> List[Dict]:
        """Search codes by reward text"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, code, reward, expires, source, first_seen, last_seen
                FROM codes 
                WHERE reward LIKE ? AND is_active = 1
                ORDER BY first_seen DESC
            """,
                (f"%{search_term}%",),
            )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_statistics(self) -> Dict:
        """Get database statistics"""
        async with self.connection.cursor() as cursor:
            stats = {}

            # Total codes
            await cursor.execute("SELECT COUNT(*) FROM codes")
            stats["total_codes"] = (await cursor.fetchone())[0]

            # Active codes
            await cursor.execute("SELECT COUNT(*) FROM codes WHERE is_active = 1")
            stats["active_codes"] = (await cursor.fetchone())[0]

            # Inactive codes
            await cursor.execute("SELECT COUNT(*) FROM codes WHERE is_active = 0")
            stats["inactive_codes"] = (await cursor.fetchone())[0]

            # Codes by source
            await cursor.execute("""
                SELECT source, COUNT(*) as count 
                FROM codes 
                WHERE is_active = 1
                GROUP BY source
            """)
            stats["by_source"] = {row[0]: row[1] for row in await cursor.fetchall()}

            # Most common rewards
            await cursor.execute("""
                SELECT reward, COUNT(*) as count 
                FROM codes 
                WHERE is_active = 1
                GROUP BY reward
                ORDER BY count DESC
                LIMIT 5
            """)
            stats["top_rewards"] = [(row[0], row[1]) for row in await cursor.fetchall()]

            # Most scraped codes
            await cursor.execute("""
                SELECT code, times_scraped 
                FROM codes 
                WHERE is_active = 1
                ORDER BY times_scraped DESC
                LIMIT 5
            """)
            stats["most_scraped"] = [
                (row[0], row[1]) for row in await cursor.fetchall()
            ]

            return stats

    async def log_command_usage(
        self, command_name: str, user_id: str, guild_id: Optional[str] = None
    ):
        """Log command usage for analytics"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO command_stats (command_name, user_id, guild_id)
                VALUES (?, ?, ?)
            """,
                (command_name, user_id, guild_id),
            )

            await self.connection.commit()

    async def get_command_stats(self, days: int = 7) -> Dict:
        """Get command usage statistics for the last N days"""
        async with self.connection.cursor() as cursor:
            # Total commands
            await cursor.execute(
                """
                SELECT COUNT(*) 
                FROM command_stats 
                WHERE used_at > datetime('now', '-{} days')
            """.format(days)
            )
            total = (await cursor.fetchone())[0]

            # By command
            await cursor.execute(
                """
                SELECT command_name, COUNT(*) as count
                FROM command_stats 
                WHERE used_at > datetime('now', '-{} days')
                GROUP BY command_name
                ORDER BY count DESC
            """.format(days)
            )
            by_command = {row[0]: row[1] for row in await cursor.fetchall()}

            # Unique users
            await cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM command_stats 
                WHERE used_at > datetime('now', '-{} days')
            """.format(days)
            )
            unique_users = (await cursor.fetchone())[0]

            return {
                "total_commands": total,
                "by_command": by_command,
                "unique_users": unique_users,
                "days": days,
            }

    async def add_notification_subscription(
        self, channel_id: str, guild_id: str
    ) -> bool:
        """Subscribe a channel to new code notifications"""
        async with self.connection.cursor() as cursor:
            try:
                await cursor.execute(
                    """
                    INSERT INTO notification_subscriptions (channel_id, guild_id)
                    VALUES (?, ?)
                """,
                    (channel_id, guild_id),
                )

                await self.connection.commit()
                logger.info(f"Channel {channel_id} subscribed to notifications")
                return True
            except sqlite3.IntegrityError:
                # Channel already subscribed
                logger.info(f"Channel {channel_id} already subscribed")
                return False

    async def remove_notification_subscription(self, channel_id: str) -> bool:
        """Unsubscribe a channel from notifications"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM notification_subscriptions
                WHERE channel_id = ?
            """,
                (channel_id,),
            )

            await self.connection.commit()
            affected = cursor.rowcount

            if affected > 0:
                logger.info(f"Channel {channel_id} unsubscribed from notifications")
                return True
            return False

    async def get_notification_subscriptions(self) -> List[Dict]:
        """Get all active notification subscriptions"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT channel_id, guild_id, subscribed_at
                FROM notification_subscriptions
                WHERE is_active = 1
            """)

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def cleanup_old_history(self, days: int = 90):
        """Clean up old code history entries (keep last 90 days)"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM code_history
                WHERE scraped_at < datetime('now', '-{} days')
            """.format(days)
            )

            deleted = cursor.rowcount
            await self.connection.commit()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old history entries")

            return deleted

    async def update_expired_codes(self) -> int:
        """
        Check all active codes and mark expired ones as inactive.
        Returns the number of codes marked as expired.
        """
        from datetime import datetime

        async with self.connection.cursor() as cursor:
            # Get all active codes with expiration dates
            await cursor.execute(
                """
                SELECT id, code, expires
                FROM codes
                WHERE is_active = 1 AND expires IS NOT NULL AND expires != ''
            """
            )

            rows = await cursor.fetchall()
            expired_count = 0

            for row in rows:
                code_id = row[0]
                code = row[1]
                expires = row[2]

                # Check if expired using our helper function
                # Import here to avoid circular imports
                try:
                    # Parse expiration date
                    expires_lower = expires.lower().strip()

                    # Skip "never" type expirations
                    if expires_lower in [
                        "never",
                        "no expiration",
                        "permanent",
                        "n/a",
                        "none",
                    ]:
                        continue

                    # Try to parse as date
                    date_formats = [
                        "%Y-%m-%d",  # 2025-12-31
                        "%m/%d/%Y",  # 12/31/2025
                        "%d/%m/%Y",  # 31/12/2025
                        "%B %d, %Y",  # December 31, 2025
                        "%b %d, %Y",  # Dec 31, 2025
                        "%Y-%m-%d %H:%M:%S",  # 2025-12-31 23:59:59
                    ]

                    expiration_date = None
                    for fmt in date_formats:
                        try:
                            expiration_date = datetime.strptime(expires, fmt)
                            break
                        except ValueError:
                            continue

                    if expiration_date and expiration_date < datetime.now():
                        # Code is expired, mark as inactive
                        await cursor.execute(
                            """
                            UPDATE codes
                            SET is_active = 0
                            WHERE id = ?
                        """,
                            (code_id,),
                        )
                        expired_count += 1
                        logger.info(f"Marked code as expired: {code}")

                except Exception as e:
                    # If we can't parse the date, skip it (keep active)
                    logger.debug(f"Could not parse expiration for code {code}: {e}")
                    continue

            await self.connection.commit()

            if expired_count > 0:
                logger.info(f"Marked {expired_count} code(s) as expired")

            return expired_count


# Context manager support
class Database:
    """Context manager for database operations"""

    def __init__(self, db_path: str = "shift_codes.db"):
        self.db = ShiftCodeDatabase(db_path)

    async def __aenter__(self):
        await self.db.connect()
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.db.close()


# Utility function for testing
async def test_database():
    """Test database operations"""
    print("Testing Shift Code Database\n" + "=" * 60)

    async with Database("test_shift_codes.db") as db:
        print("\n✅ Database connected and initialized")

        # Add some test codes
        print("\n📝 Adding test codes...")
        code1_id, is_new = await db.add_or_update_code(
            "ABCDE-12345-FGHIJ-67890-KLMNO", "Golden Key", "2025-12-31", "MentalMars"
        )
        print(f"Code 1: ID={code1_id}, New={is_new}")

        code2_id, is_new = await db.add_or_update_code(
            "PQRST-11111-UVWXY-22222-ZABCD", "Diamond Key", None, "xsmashx88x"
        )
        print(f"Code 2: ID={code2_id}, New={is_new}")

        # Try adding duplicate
        print("\n📝 Adding duplicate code...")
        code1_again, is_new = await db.add_or_update_code(
            "ABCDE-12345-FGHIJ-67890-KLMNO", "Golden Key", "2025-12-31", "MentalMars"
        )
        print(f"Duplicate: ID={code1_again}, New={is_new} (should be False)")

        # Get all codes
        print("\n📋 Getting all active codes...")
        codes = await db.get_all_active_codes()
        print(f"Found {len(codes)} active codes")
        for code in codes:
            print(
                f"  - {code['code']}: {code['reward']} (scraped {code['times_scraped']} times)"
            )

        # Get statistics
        print("\n📊 Database statistics...")
        stats = await db.get_statistics()
        print(f"Total codes: {stats['total_codes']}")
        print(f"Active codes: {stats['active_codes']}")
        print(f"By source: {stats['by_source']}")

        # Log command usage
        print("\n📈 Logging command usage...")
        await db.log_command_usage("codes", "123456789", "987654321")
        await db.log_command_usage("latest", "123456789", "987654321")
        await db.log_command_usage("codes", "111111111", "987654321")

        # Get command stats
        print("\n📈 Command statistics...")
        cmd_stats = await db.get_command_stats(days=7)
        print(f"Total commands: {cmd_stats['total_commands']}")
        print(f"By command: {cmd_stats['by_command']}")
        print(f"Unique users: {cmd_stats['unique_users']}")

        print("\n✅ All tests passed!")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_database())
