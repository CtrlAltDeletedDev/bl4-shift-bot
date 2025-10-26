"""
Shift code scraper for Borderlands 4
Fetches shift codes from MentalMars and xsmashx88x tracker
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)


class ShiftCode:
    """Represents a Borderlands 4 Shift Code"""
    
    def __init__(self, code: str, reward: str, expires: Optional[str] = None, source: str = ""):
        self.code = code
        self.reward = reward
        self.expires = expires
        self.source = source
        self.scraped_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "reward": self.reward,
            "expires": self.expires,
            "source": self.source,
            "scraped_at": self.scraped_at.isoformat()
        }
    
    def __str__(self):
        return f"**Code:** `{self.code}`\n**Reward:** {self.reward}\n**Expires:** {self.expires or 'Unknown'}\n**Source:** {self.source}"


class ShiftCodeScraper:
    """Scrapes Shift codes from multiple sources"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch HTML content from a URL"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None
    
    async def scrape_mentalmars(self) -> List[ShiftCode]:
        """
        Scrape Shift codes from MentalMars.com
        MentalMars maintains a table with: Reward | Expire Date | Borderlands 4 SHiFT Code
        """
        url = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"
        codes = []
        
        try:
            html = await self.fetch_page(url)
            if not html:
                return codes
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # MentalMars uses a markdown-style table
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        # Structure: Reward | Expire Date | Borderlands 4 SHiFT Code
                        reward_text = cells[0].get_text(strip=True)
                        expires_text = cells[1].get_text(strip=True)
                        code_text = cells[2].get_text(strip=True)
                        
                        # Validate: shift codes are 25 chars with 4 dashes (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
                        if code_text and len(code_text) >= 20 and code_text.count('-') >= 4:
                            # Skip placeholder entries
                            if code_text.lower() not in ['coming soon', '…', 'tba', 'tbd', 'n/a']:
                                codes.append(ShiftCode(
                                    code=code_text,
                                    reward=reward_text if reward_text else "Golden Key",
                                    expires=expires_text if expires_text and expires_text != '…' else None,
                                    source="MentalMars"
                                ))
            
            logger.info(f"Scraped {len(codes)} codes from MentalMars")
            
        except Exception as e:
            logger.error(f"Error scraping MentalMars: {str(e)}")
        
        return codes
    
    async def scrape_xsmashx88x(self) -> List[ShiftCode]:
        """
        Scrape Shift codes from xsmashx88x's GitHub Pages Shift Code tracker
        This is a community-maintained tracker with active/expired status
        """
        url = "https://xsmashx88x.github.io/Shift-Codes/"
        codes = []
        
        try:
            html = await self.fetch_page(url)
            if not html:
                return codes
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Method 1: Look for tables containing Borderlands 4 codes
            # The site organizes codes by game in sections
            tables = soup.find_all('table')
            
            for table in tables:
                # Check if this table is for Borderlands 4
                # Look at headings or table attributes
                table_context = str(table.find_previous(['h1', 'h2', 'h3', 'h4']))
                
                if 'borderlands 4' in table_context.lower() or 'bl4' in table_context.lower():
                    rows = table.find_all('tr')
                    
                    for row in rows[1:]:  # Skip header
                        cells = row.find_all(['td', 'th'])
                        
                        if len(cells) >= 2:
                            # Extract code - usually in a code tag or button
                            code_elem = cells[0].find(['code', 'button', 'span']) or cells[0]
                            code_text = code_elem.get_text(strip=True)
                            
                            # Extract reward info
                            reward_text = cells[1].get_text(strip=True) if len(cells) > 1 else "Golden Key"
                            
                            # Extract expiration if available
                            expires_text = cells[2].get_text(strip=True) if len(cells) > 2 else None
                            
                            # Validate shift code format
                            if code_text and len(code_text) >= 20 and code_text.count('-') >= 4:
                                # Check if marked as expired/active
                                row_html = str(row).lower()
                                is_expired = 'expired' in row_html or 'inactive' in row_html
                                
                                # Only add active codes
                                if not is_expired:
                                    codes.append(ShiftCode(
                                        code=code_text,
                                        reward=reward_text,
                                        expires=expires_text,
                                        source="xsmashx88x Tracker"
                                    ))
            
            # Method 2: If no tables found, use pattern matching as fallback
            if not codes:
                # Look for Borderlands 4 section
                bl4_found = False
                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
                    heading_text = heading.get_text().lower()
                    if 'borderlands 4' in heading_text or 'bl4' in heading_text:
                        bl4_found = True
                        
                        # Get the section after this heading
                        section = heading.find_next_sibling()
                        if section:
                            section_text = section.get_text()
                            
                            # Find shift codes using regex pattern
                            # Pattern: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
                            pattern = r'\b([A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5})\b'
                            matches = re.findall(pattern, section_text)
                            
                            for match in matches:
                                codes.append(ShiftCode(
                                    code=match,
                                    reward="Golden Key",
                                    expires=None,
                                    source="xsmashx88x Tracker"
                                ))
                        
                        if bl4_found:
                            break
            
            logger.info(f"Scraped {len(codes)} codes from xsmashx88x tracker")
            
        except Exception as e:
            logger.error(f"Error scraping xsmashx88x: {str(e)}")
        
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
            normalized_code = code.code.strip().upper().replace(' ', '')
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(test_scraper())
