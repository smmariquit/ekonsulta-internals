"""Main bot file."""
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.logger import get_logger

# Load environment variables
load_dotenv()

# Configure logging
logger = get_logger("bot")

class StandupBot(commands.Bot):
    """Standup bot class."""
    
    def __init__(self):
        """Initialize the bot."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        # Get configuration from environment variables
        self.channel_id = os.getenv('CHANNEL_ID')
        token = os.getenv('DISCORD_BOT_TOKEN')
        
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
        
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        logger.info("Bot initialized")

    async def setup_hook(self):
        """Set up the bot."""
        # Load cogs
        await self.load_extension('cogs.dsm')
        logger.info("Cogs loaded")

    async def on_ready(self):
        """Handle bot ready event."""
        logger.info(f"Logged in as {self.user.name}")
        await self.tree.sync()

def main():
    """Run the bot."""
    bot = StandupBot()
    # Get token directly from environment when needed
    token = os.getenv('DISCORD_BOT_TOKEN')
    bot.run(token)

if __name__ == "__main__":
    main()