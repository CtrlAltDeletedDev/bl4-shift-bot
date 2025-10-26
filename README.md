# Borderlands 4 Shift Code Discord Bot

A Discord bot that automatically fetches and displays Borderlands 4 Shift codes from multiple sources using slash commands.

## Features

- 🎮 **Slash Commands** - Modern Discord interactions
- 🔄 **Auto-Update** - Codes automatically refresh every 6 hours
- 💾 **Caching** - Smart caching to reduce unnecessary requests
- 🌐 **Multiple Sources** - Scrapes from multiple websites for comprehensive coverage
- 📊 **Rich Embeds** - Beautiful formatted code displays
- ⚡ **UV Package Manager** - Fast, modern Python package management

## Slash Commands

- `/codes` - Get all available Shift codes (up to 10)
- `/latest` - Get only the most recent Shift code
- `/refresh` - Force refresh the codes cache
- `/help` - Display help information

## Prerequisites

- Python 3.12 or higher
- UV package manager (installed automatically with Python in most setups)
- A Discord Bot Token (see setup below)

## Setup

### 1. Clone/Download the Project

```bash
cd borderlands-shift-bot
```

### 2. Configure Environment Variables

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Edit `.env` and add your Discord bot token:

```env
DISCORD_TOKEN=your_bot_token_here
TEST_GUILD_ID=your_server_id_here  # Optional, for faster testing
```

### 3. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Under "Token", click "Reset Token" and copy it to your `.env` file
5. Enable these **Privileged Gateway Intents**:
   - Message Content Intent (if needed)
6. Go to "OAuth2" > "URL Generator"
7. Select scopes:
   - `bot`
   - `applications.commands`
8. Select bot permissions:
   - Send Messages
   - Embed Links
   - Use Slash Commands
9. Copy the generated URL and use it to invite the bot to your server

### 4. Install Dependencies

The project uses UV for package management:

```bash
# UV will automatically create a virtual environment and install dependencies
uv sync
```

Or manually with UV:

```bash
uv venv
uv pip install -r pyproject.toml
```

### 5. Run the Bot

```bash
# Using UV
uv run main.py

# Or activate the virtual environment first
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python main.py
```

## Project Structure

```
borderlands-shift-bot/
├── main.py              # Main bot file with slash commands
├── scraper.py           # Web scraping logic for Shift codes
├── .env                 # Environment variables (create from .env.example)
├── .env.example         # Example environment configuration
├── pyproject.toml       # UV/Python project configuration
├── README.md            # This file
└── .venv/               # Virtual environment (created by UV)
```

## Customizing the Scraper

The bot currently scrapes from two sources:

1. **MentalMars** (https://mentalmars.com/game-news/borderlands-4-shift-codes/) - A popular gaming wiki with regularly updated Shift codes
2. **xsmashx88x Tracker** (https://xsmashx88x.github.io/Shift-Codes/) - A community-maintained Shift code tracker with active/expired status

### Adding More Sources

To add additional sources:

1. Open `scraper.py`
2. Add a new scraping method to the `ShiftCodeScraper` class
3. Update the `get_all_codes()` method to include your new source

### Example: Adding a New Source

```python
async def scrape_new_source(self) -> List[ShiftCode]:
    """Scrape from a new website"""
    url = "https://example.com/bl4-codes"
    codes = []
    
    try:
        html = await self.fetch_page(url)
        if not html:
            return codes
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Your parsing logic here
        # ...
        
    except Exception as e:
        logger.error(f"Error scraping new source: {str(e)}")
    
    return codes
```

Then add it to `get_all_codes()`:

```python
async def get_all_codes(self) -> List[ShiftCode]:
    all_codes = []
    
    mentalmars_codes = await self.scrape_mentalmars()
    xsmashx_codes = await self.scrape_xsmashx88x()
    new_codes = await self.scrape_new_source()  # Add this
    
    all_codes.extend(mentalmars_codes)
    all_codes.extend(xsmashx_codes)
    all_codes.extend(new_codes)  # Add this
    
    # ... rest of the method
```

## Testing the Scraper

You can test the scraper independently:

```bash
uv run scraper.py
```

This will run the scraper and print all found codes to the console.

## Development Tips

### Fast Command Syncing (Testing)

For faster command syncing during development, add your server ID to `.env`:

```env
TEST_GUILD_ID=123456789012345678
```

This will sync commands only to your test server instead of globally (which can take up to an hour).

### Logging

The bot uses Python's logging module. Adjust the log level in `main.py`:

```python
logging.basicConfig(level=logging.DEBUG)  # For more detailed logs
```

## Troubleshooting

### Commands Not Showing Up

- Wait up to 1 hour for global command sync (first time only)
- OR set `TEST_GUILD_ID` in `.env` for instant syncing to your test server
- Make sure the bot has the `applications.commands` scope

### Bot Not Responding

- Check that the bot is online in your Discord server
- Verify your `DISCORD_TOKEN` is correct
- Check the console logs for errors

### No Codes Found

- The websites may have changed their structure
- Update the parsing logic in `scraper.py`
- Check if the websites are accessible

### Rate Limiting

If you get rate limited:
- Increase the cache time in `main.py`
- Reduce the frequency of the background update task

## Dependencies

- **discord.py** - Discord API wrapper
- **aiohttp** - Async HTTP client for web requests
- **beautifulsoup4** - HTML parsing
- **python-dotenv** - Environment variable management

## Contributing

Feel free to fork and improve the bot! Some ideas:

- Add more scraping sources
- Implement a database for code history
- Add notifications for new codes
- Create a web dashboard
- Add code redemption tracking

## License

This project is open source and available for personal use. Please respect the Terms of Service of any websites you scrape.

## Disclaimer

This bot scrapes publicly available Shift codes from various websites. Please ensure you comply with the terms of service of both Discord and the websites being scraped. The bot is provided as-is with no warranties.

## Support

For issues or questions:
1. Check the logs for error messages
2. Verify your setup matches this README
3. Ensure all dependencies are installed correctly

## Credits

Created for the Borderlands community. Shift codes are provided by Gearbox Software and various community websites.
