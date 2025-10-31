"""
Shift code scraper for Borderlands 4
Fetches shift codes from MentalMars and xsmashx88x tracker
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import logging
import re
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def convert_to_discord_timestamp(dt: datetime, format_type: str = "f") -> str:
    """
    Convert a datetime object to Discord timestamp format

    Args:
        dt: datetime object (should be timezone-aware)
        format_type: Discord timestamp format
            - 't' = short time (16:20)
            - 'T' = long time (16:20:30)
            - 'd' = short date (20/04/2021)
            - 'D' = long date (20 April 2021)
            - 'f' = short date/time (20 April 2021 16:20)
            - 'F' = long date/time (Tuesday, 20 April 2021 16:20)
            - 'R' = relative time (2 months ago)

    Returns:
        Discord timestamp string like <t:1234567890:f>
    """
    # Convert to UTC if not already
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Get Unix timestamp (epoch)
    epoch = int(dt.timestamp())

    return f"<t:{epoch}:{format_type}>"


def parse_date_string(date_str: str) -> Optional[str]:
    """
    Parse various date string formats and convert to Discord timestamp

    Args:
        date_str: Date string in various formats like "Oct 30, 2025", "2025-10-30", etc.

    Returns:
        Discord timestamp string or original string if parsing fails
    """
    if not date_str or date_str == "…":
        return None

    # Try various date formats
    formats = [
        "%b %d, %Y",  # Oct 30, 2025
        "%B %d, %Y",  # October 30, 2025
        "%Y-%m-%d",   # 2025-10-30
        "%m/%d/%Y",   # 10/30/2025
        "%d/%m/%Y",   # 30/10/2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            return convert_to_discord_timestamp(dt, "d")
        except ValueError:
            continue

    # If all parsing fails, return original string
    return date_str


class CircuitBreaker:
    """Circuit breaker to prevent hammering failed sources"""

    def __init__(self, failure_threshold: int = 3, timeout: int = 300):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting again (default 5 minutes)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures: Dict[str, int] = {}
        self.last_failure_time: Dict[str, datetime] = {}
        self.circuit_open: Dict[str, bool] = {}

    def record_failure(self, source: str):
        """Record a failure for a source"""
        self.failures[source] = self.failures.get(source, 0) + 1
        self.last_failure_time[source] = datetime.now(timezone.utc)

        if self.failures[source] >= self.failure_threshold:
            self.circuit_open[source] = True
            logger.warning(
                f"Circuit breaker opened for {source} after {self.failures[source]} failures"
            )

    def record_success(self, source: str):
        """Record a success for a source"""
        self.failures[source] = 0
        self.circuit_open[source] = False

    def can_attempt(self, source: str) -> bool:
        """Check if we can attempt to fetch from this source"""
        if source not in self.circuit_open or not self.circuit_open[source]:
            return True

        # Check if timeout has elapsed
        if source in self.last_failure_time:
            time_since_failure = (
                datetime.now(timezone.utc) - self.last_failure_time[source]
            ).total_seconds()

            if time_since_failure >= self.timeout:
                logger.info(f"Circuit breaker timeout elapsed for {source}, attempting retry")
                self.circuit_open[source] = False
                return True

        return False


class ShiftCode:
    """Represents a Borderlands 4 Shift Code"""

    def __init__(
        self, code: str, reward: str, expires: Optional[str] = None, source: str = ""
    ):
        self.code = code
        self.reward = reward
        self.expires = expires
        self.source = source
        self.scraped_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "reward": self.reward,
            "expires": self.expires,
            "source": self.source,
            "scraped_at": self.scraped_at.isoformat(),
        }

    def __str__(self):
        return f"**Code:** `{self.code}`\n**Reward:** {self.reward}\n**Expires:** {self.expires or 'Unknown'}\n**Source:** {self.source}"


class ShiftCodeScraper:
    """Scrapes Shift codes from multiple sources"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=300)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_page(
        self, url: str, max_retries: int = 3, base_delay: float = 1.0
    ) -> Optional[str]:
        """
        Fetch HTML content from a URL with retry logic and exponential backoff

        Args:
            url: The URL to fetch
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff

        Returns:
            HTML content as string, or None if all retries failed
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        for attempt in range(max_retries):
            try:
                async with self.session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15), headers=headers
                ) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        # Rate limited, wait longer
                        delay = base_delay * (2**attempt) * 2
                        logger.warning(
                            f"Rate limited fetching {url}, waiting {delay:.1f}s before retry"
                        )
                        await asyncio.sleep(delay)
                        continue
                    elif response.status >= 500:
                        # Server error, retry with backoff
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            f"Server error ({response.status}) fetching {url}, retrying in {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            f"Failed to fetch {url}: Status {response.status}"
                        )
                        return None

            except asyncio.TimeoutError:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Timeout fetching {url} (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                continue

            except aiohttp.ClientError as e:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Client error fetching {url}: {e} (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                continue

            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {str(e)}")
                return None

        logger.error(f"All {max_retries} attempts failed for {url}")
        return None

    async def scrape_mentalmars(self) -> List[ShiftCode]:
        """
        Scrape Shift codes from MentalMars.com
        MentalMars maintains a table with: Reward | Expire Date | Borderlands 4 SHiFT Code
        """
        source_name = "MentalMars"
        url = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"
        codes = []

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt(source_name):
            logger.warning(
                f"Circuit breaker is open for {source_name}, skipping scrape"
            )
            return codes

        try:
            logger.info(f"Starting scrape from {url}...")
            html = await self.fetch_page(url)
            if not html:
                self.circuit_breaker.record_failure(source_name)
                return codes

            # Parse HTML in executor to avoid blocking
            import asyncio

            loop = asyncio.get_event_loop()
            soup = await loop.run_in_executor(None, BeautifulSoup, html, "html.parser")

            # MentalMars uses a markdown-style table
            tables = soup.find_all("table")
            logger.info(f"Found {len(tables)} tables in MentalMars")

            for table in tables:
                rows = table.find_all("tr")

                # Get header row to find column indices
                header_row = table.find("tr")
                headers = []
                if header_row:
                    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

                # Find which column has the expire date
                expire_col_idx = None
                for idx, header in enumerate(headers):
                    if "expire" in header:
                        expire_col_idx = idx
                        break

                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 3:
                        continue

                    # Find the code cell (contains pattern XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
                    code_text = None
                    code_col_idx = None
                    for idx, cell in enumerate(cells):
                        text = cell.get_text(strip=True)
                        if text and len(text) >= 20 and text.count("-") >= 4:
                            # Check if it matches shift code pattern
                            if re.match(r'^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$', text):
                                code_text = text
                                code_col_idx = idx
                                break

                    if not code_text:
                        continue

                    # Skip placeholder entries
                    if code_text.lower() in ["coming soon", "…", "tba", "tbd", "n/a"]:
                        continue

                    # Get reward (first column)
                    reward_text = cells[0].get_text(strip=True)

                    # Get expiration date from the expire column if it exists
                    expires_text = None
                    if expire_col_idx is not None and expire_col_idx < len(cells):
                        expires_text = cells[expire_col_idx].get_text(strip=True)

                    logger.info(f"Found code: {code_text}. Adding to database...")

                    # Try to parse and convert expiration date to Discord timestamp
                    expires_formatted = parse_date_string(expires_text) if expires_text else None

                    codes.append(
                        ShiftCode(
                            code=code_text,
                            reward=reward_text if reward_text else "Golden Key",
                            expires=expires_formatted,
                            source="MentalMars",
                        )
                    )
                    logger.info(f"Added code: {code_text}")

            logger.info(f"Scraped {len(codes)} codes from MentalMars")

            # Record success if we got any codes
            if codes:
                self.circuit_breaker.record_success(source_name)
            else:
                # If we got no codes but didn't error, might be a problem
                logger.warning(f"No codes found from {source_name}, but no error occurred")

        except Exception as e:
            logger.error(f"Error scraping MentalMars: {str(e)}")
            self.circuit_breaker.record_failure(source_name)

        return codes

    async def scrape_xsmashx88x(self) -> List[ShiftCode]:
        """
        Scrape Shift codes from xsmashx88x's GitHub Pages Shift Code tracker
        Note: This site uses JavaScript to render codes, so we parse the HTML/JS source
        """
        source_name = "xsmashx88x"
        url = "https://xsmashx88x.github.io/Shift-Codes/"
        codes = []

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt(source_name):
            logger.warning(
                f"Circuit breaker is open for {source_name}, skipping scrape"
            )
            return codes

        try:
            html = await self.fetch_page(url)
            if not html:
                self.circuit_breaker.record_failure(source_name)
                return codes

            # Parse HTML in executor to avoid blocking
            import asyncio

            loop = asyncio.get_event_loop()
            soup = await loop.run_in_executor(None, BeautifulSoup, html, "html.parser")

            # Look for script tags containing ALL_CODES_CONFIG array
            scripts = soup.find_all("script")

            for script in scripts:
                script_text = script.string
                if not script_text or "ALL_CODES_CONFIG" not in script_text:
                    continue

                # Extract individual code objects from ALL_CODES_CONFIG
                # Match each code block within the array
                # Pattern: { code: "...", ... other properties ... }
                code_blocks = re.finditer(r'\{[^}]*?code:\s*"([A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5})"[^}]*?\}', script_text, re.DOTALL)

                for block_match in code_blocks:
                    full_block = block_match.group(0)
                    code_text = block_match.group(1)

                    # Skip placeholder codes
                    if code_text in [
                        "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
                        "3ZXJB-53STT-56T3W-B3TT3-HTS95",
                        "No Code",
                    ]:
                        continue

                    # Extract expires property from the block
                    expires_str = None

                    # Look for createDate() function call first
                    # Format: createDate(year, month, day, hour, minute, second, isPM)
                    date_match = re.search(
                        r'expires:\s*createDate\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)',
                        full_block
                    )
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        hour = int(date_match.group(4))
                        minute = int(date_match.group(5))
                        second = int(date_match.group(6))
                        is_pm = int(date_match.group(7))

                        # Convert to 24-hour format
                        if is_pm and hour < 12:
                            hour += 12
                        elif not is_pm and hour == 12:
                            hour = 0

                        # Create datetime in EDT (America/New_York) timezone
                        # The xsmashx88x site uses EDT/EST
                        try:
                            dt = datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo("America/New_York"))
                            # Convert to Discord timestamp format (short date/time)
                            expires_str = convert_to_discord_timestamp(dt, "f")
                        except Exception as e:
                            logger.warning(f"Error converting date to timestamp: {e}")
                            # Fallback to simple date string
                            expires_str = f"{year}-{month:02d}-{day:02d}"
                    else:
                        # Look for string dates or other formats
                        expires_match = re.search(r'expires:\s*["\']([^"\']+)["\']', full_block)
                        if expires_match:
                            expires_raw = expires_match.group(1).strip()

                            # Check for string date like "2025-10-20"
                            if re.match(r'\d{4}-\d{2}-\d{2}', expires_raw):
                                # Try to convert to Discord timestamp
                                try:
                                    dt = datetime.strptime(expires_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                    expires_str = convert_to_discord_timestamp(dt, "d")
                                except:
                                    expires_str = expires_raw
                            # Check for "UED" (Unknown Expiration Date)
                            elif "UED" in expires_raw:
                                expires_str = None

                    # Extract title property from the block
                    reward = "Golden Key"
                    # Use a more flexible pattern that handles nested HTML tags
                    title_match = re.search(r'title:\s*["\'](.+?)["\'](?=\s*,|\s*\n)', full_block, re.DOTALL)
                    if title_match:
                        title_raw = title_match.group(1)
                        # Clean up title (remove HTML tags and extra whitespace)
                        reward = re.sub(r'<[^>]+>', '', title_raw)
                        reward = re.sub(r'\s+', ' ', reward)  # Normalize whitespace
                        reward = reward.strip()

                    # Only add if not already in codes
                    if code_text not in [c.code for c in codes]:
                        codes.append(
                            ShiftCode(
                                code=code_text,
                                reward=reward,
                                expires=expires_str,
                                source="xsmashx88x Tracker",
                            )
                        )

            # Fallback: Use old method if new method found nothing
            if not codes:
                logger.warning("xsmashx88x: ALL_CODES_CONFIG not found, using fallback method")
                scripts = soup.find_all("script")

                for script in scripts:
                    script_text = script.string
                    if not script_text:
                        continue

                    # Look for shift code patterns in the JavaScript
                    pattern = r"\b([A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5})\b"
                    matches = re.findall(pattern, script_text)

                    for code_text in matches:
                        # Skip example/placeholder codes
                        if code_text in [
                            "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
                            "3ZXJB-53STT-56T3W-B3TT3-HTS95",
                            "No Code",
                        ]:
                            continue

                        if code_text not in [c.code for c in codes]:
                            codes.append(
                                ShiftCode(
                                    code=code_text,
                                    reward="Golden Key",
                                    expires=None,
                                    source="xsmashx88x Tracker",
                                )
                            )

            logger.info(f"Scraped {len(codes)} codes from xsmashx88x tracker")

            # Record success if we got any codes
            if codes:
                self.circuit_breaker.record_success(source_name)
            else:
                # If we got no codes but didn't error, might be a problem
                logger.warning(f"No codes found from {source_name}, but no error occurred")

        except Exception as e:
            logger.error(f"Error scraping xsmashx88x: {str(e)}")
            self.circuit_breaker.record_failure(source_name)

        return codes

    async def get_all_codes(self) -> List[ShiftCode]:
        """Get all Shift codes from all sources"""
        all_codes = []

        # Fetch from all sources concurrently for better performance
        mentalmars_codes = await self.scrape_mentalmars()
        xsmashx_codes = await self.scrape_xsmashx88x()

        all_codes.extend(mentalmars_codes)
        all_codes.extend(xsmashx_codes)

        # Remove duplicates based on code
        seen = set()
        unique_codes = []
        for code in all_codes:
            # Normalize code for comparison (remove whitespace, uppercase)
            normalized_code = code.code.strip().upper().replace(" ", "")
            if normalized_code not in seen:
                seen.add(normalized_code)
                unique_codes.append(code)

        logger.info(f"Total unique codes found: {len(unique_codes)}")
        return unique_codes


# Example usage for testing
async def test_scraper():
    """Test the scraper independently"""
    async with ShiftCodeScraper() as scraper:
        print("Testing Borderlands 4 Shift Code Scraper\n")
        print("=" * 60)

        # Test MentalMars
        print("\n🔍 Scraping MentalMars...")
        mentalmars_codes = await scraper.scrape_mentalmars()
        print(f"Found {len(mentalmars_codes)} codes from MentalMars")
        for code in mentalmars_codes[:3]:  # Show first 3
            print(f"\n{code}")

        # Test xsmashx88x
        print("\n\n🔍 Scraping xsmashx88x tracker...")
        xsmashx_codes = await scraper.scrape_xsmashx88x()
        print(f"Found {len(xsmashx_codes)} codes from xsmashx88x")
        for code in xsmashx_codes[:3]:  # Show first 3
            print(f"\n{code}")

        # Test get_all_codes
        print("\n\n🔍 Getting all unique codes...")
        all_codes = await scraper.get_all_codes()
        print(f"Total unique codes: {len(all_codes)}")
        print("\n" + "=" * 60)
        print("\nAll Codes:")
        for i, code in enumerate(all_codes, 1):
            print(f"\n{i}. {code}")
            print("-" * 60)


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(test_scraper())
