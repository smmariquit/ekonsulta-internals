"""
Main Discord bot module for the EPMS Standup Bot.

This module contains the main bot class and initialization logic for a Discord bot
that handles daily standup meetings and related functionality.

Author: EKMC Engineering Team
Version: 1.0.0
"""

# Standard library imports first
import os

# Third-party imports second
import discord
from discord.ext import commands

# Local imports go last
from config.config import DISCORD_BOT_TOKEN, LOG_FILE
from utils.logging_util import get_logger

# Configure logging
logger = get_logger("bot")

class StandupBot(commands.Bot): # Not discord.Client--that's for more basic bots.
    """
    A Discord bot for managing daily standup meetings.
    
    This bot inherits from discord.ext.commands.Bot and provides functionality
    for handling daily standup meetings, including command processing and
    event handling.
    
    Attributes:
        logger: Logger instance for recording bot activities
        token: Discord bot token for authentication
    """
    
    def __init__(self) -> None:
        """
        Initialize the StandupBot with Discord intents and configuration.
        
        Sets up the bot with appropriate Discord intents, validates the bot token,
        and initializes the parent Bot class with command prefix and intents.
        
        Raises:
            ValueError: If DISCORD_BOT_TOKEN environment variable is not set.
        """
        # Configure Discord intents
        intents = self._setup_intents()
        
        # Store the activity to set later (can't use async in __init__)
        self._desired_activity = discord.Activity(type=discord.ActivityType.watching, name="over patients :D")
        
        # Validate and get bot token
        token = self._get_bot_token()
        
        # Initialize parent Bot class
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None  # Disable default help command for custom implementation
        )
        
        logger.info("StandupBot initialized successfully")
    
    def _setup_intents(self) -> discord.Intents:
        """
        Configure Discord intents for the bot.
        
        Sets up the necessary permissions and access levels for the bot
        to function properly within Discord servers.
        
        Returns:
            discord.Intents: Configured intents object with required permissions.
        """
        intents = discord.Intents.default()
        
        # Enable message content access for command processing
        intents.message_content = True
        
        # Enable member access for user management features
        intents.members = True
        
        logger.debug("Discord intents configured")
        return intents
    
    def _get_bot_token(self) -> str:
        """
        Retrieve and validate the Discord bot token from configuration.
        
        Returns:
            str: The Discord bot token.
            
        Raises:
            ValueError: If DISCORD_BOT_TOKEN is not set in configuration.
        """
        if not DISCORD_BOT_TOKEN:
            error_msg = "DISCORD_BOT_TOKEN is not set in configuration"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.debug("Bot token retrieved from configuration")
        return DISCORD_BOT_TOKEN
    
    async def setup_hook(self) -> None:
        """
        Set up the bot during startup.
        
        This method is called automatically by Discord.py during bot initialization.
        It loads cogs (extensions) and syncs commands with Discord's API.
        
        Note:
            This is a lifecycle method called by Discord.py, not directly by user code.
        """
        try:
            logger.info("Starting bot setup...")
            
            # Load bot extensions (cogs)
            await self._load_extensions()
            
            # Sync slash commands with Discord API
            logger.info("Syncing slash commands with Discord...")
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s) with Discord")
            
            # Log all registered commands
            for command in self.tree.get_commands():
                logger.info(f"Registered command: /{command.name}")
            
            logger.info("Bot setup completed successfully")
            
        except Exception as e:
            logger.error(f"Error during bot setup: {e}", exc_info=True)
            raise
    
    async def _load_extensions(self) -> None:
        """
        Load all bot extensions (cogs).
        
        Extensions are modular components that contain related commands and functionality.
        This method loads each extension and logs the process.
        """
        extensions = [
            'cogs.dsm',  # Daily Standup Meeting functionality
            'cogs.translator' # Translator functionality
            # Add more extensions here as needed
        ]
        
        logger.info(f"Attempting to load {len(extensions)} extensions: {extensions}")
        
        for extension in extensions:
            try:
                logger.info(f"Loading extension: {extension}")
                await self.load_extension(extension)
                logger.info(f"Successfully loaded extension: {extension}")
                
                # Log commands from this extension
                cog = self.get_cog(extension.split('.')[-1])
                if cog:
                    commands = [cmd for cmd in self.tree.get_commands() if hasattr(cmd, 'callback') and cmd.callback.__module__.startswith(extension)]
                    logger.info(f"Extension {extension} added {len(commands)} commands")
                
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}", exc_info=True)
                raise
    
    async def on_ready(self) -> None:
        """
        Handle the bot ready event.
        
        This method is called when the bot successfully connects to Discord.
        It logs the successful connection and sets the bot's presence.
        
        Note:
            This is a lifecycle method called by Discord.py when the bot is ready.
        """
        # Set the bot's presence/activity
        if hasattr(self, '_desired_activity'):
            await self.change_presence(activity=self._desired_activity)
            logger.info(f"Bot presence set to: {self._desired_activity.name}")
        
        logger.info(f"Bot logged in successfully as: {self.user.name}")
        logger.info(f"Bot ID: {self.user.id}")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        
        # Sync commands again to ensure they're up to date
        try:
            await self.tree.sync()
            logger.info("Commands synced with Discord API")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")
    
    async def on_command_error(self, context: commands.Context, error: commands.CommandError) -> None:
        """
        Handle command errors globally.
        
        This method catches and handles errors that occur during command execution,
        providing appropriate error messages to users.
        
        Args:
            context: The command context containing information about the command.
            error: The error that occurred during command execution.

        Note:
            This function is called by Discord.py when an error occurs during command execution
        """
        if isinstance(error, commands.CommandNotFound):
            await context.send("❌ Command not found. Use `!help` to see available commands.")
        elif isinstance(error, commands.MissingPermissions):
            await context.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await context.send("❌ I don't have the required permissions to execute this command.")
        else:
            logger.error(f"Unhandled command error: {error}")
            await context.send("❌ An unexpected error occurred. Please try again later.")


def main() -> None:
    """
    Main entry point for the Discord bot application.
    
    Creates a StandupBot instance and starts the bot with the Discord token.
    Handles any startup errors and ensures proper cleanup.
    """
    try:
        # Create bot instance
        bot = StandupBot()
        
        # Get token for bot startup from config
        if not DISCORD_BOT_TOKEN:
            logger.error("Cannot start bot: DISCORD_BOT_TOKEN not found in configuration")
            return
        
        # Start the bot
        logger.info("Starting StandupBot...")
        bot.run(DISCORD_BOT_TOKEN)
        
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error during bot startup: {e}")
        raise


if __name__ == "__main__":
    main()