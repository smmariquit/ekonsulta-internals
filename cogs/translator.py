import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from typing import Optional

from services.ai_service import AIService
from utils.logging_util import get_logger

load_dotenv()

logger = get_logger("translator_cog")

class Translator(commands.Cog):
    """A cog for translation and simplification functionalities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ai_service = AIService()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY not found in .env file.")
        else:
            self.ai_service.set_api_key(api_key)
            logger.info("Translator Cog AI Service initialized.")

    @app_commands.command(name="translate", description="Translates the last n messages in the channel to English.")
    @app_commands.describe(n="The number of recent messages to translate (1-50, default: 15).")
    async def translate(self, interaction: discord.Interaction, n: Optional[int]):
        """Translates the last n messages to English, understanding informal language."""
        if n is None:
            n = 15
        
        if not 1 <= n <= 50:
            await interaction.response.send_message("Please provide a number between 1 and 50.", ephemeral=True)
            return

        if not self.ai_service.api_key:
            await interaction.response.send_message("Sorry, the translation service is not configured correctly. The API key is missing.", ephemeral=True)
            return

        await interaction.response.defer()

        messages = [msg async for msg in interaction.channel.history(limit=n)]
        messages.reverse()

        if not messages:
            await interaction.followup.send("There are no messages to translate in this channel.", ephemeral=True)
            return
            
        formatted_messages = "\n".join([f"{msg.author.display_name}: {msg.content}" for msg in messages])

        prompt = (
            "You are an expert translator specializing in Filipino internet and workplace communication. "
            "Translate the following Discord chat messages from Filipino, Taglish, or any informal Filipino dialect "
            "(including slang, 'jejemon', text-speak, and corporate acronyms) into clear, professional English. "
            "The messages are in chronological order. Preserve the original meaning, nuance, and intent. Please use as little lines as possible. Don't add an introduction or a conclusion. Assume that the reader is already familiar with the context. Assume that blank lines are images. Do not try to parse the image, simply ignore it and state that it is an image. \n"
            f"---BEGIN MESSAGES---\n{formatted_messages}\n---END MESSAGES---"
        )

        try:
            translation = await self.ai_service.generate_response(prompt)
            await interaction.followup.send(f"**English Translation:**\n{translation}")
        except Exception as e:
            logger.error(f"Error during translation for last {n} messages: {e}")
            await interaction.followup.send("Sorry, an error occurred while trying to translate. The AI service may be unavailable.", ephemeral=True)

    @app_commands.command(name="noalien", description="Simplifies the last n messages for non-technical people.")
    @app_commands.describe(n="The number of recent messages to simplify (1-50, default: 15).")
    async def noalien(self, interaction: discord.Interaction, n: Optional[int]):
        """Simplifies technical jargon from the last n messages."""
        if n is None:
            n = 15

        if not 1 <= n <= 50:
            await interaction.response.send_message("Please provide a number between 1 and 50.", ephemeral=True)
            return

        if not self.ai_service.api_key:
            await interaction.response.send_message("Sorry, the simplification service is not configured correctly. The API key is missing.", ephemeral=True)
            return

        await interaction.response.defer()

        messages = [msg async for msg in interaction.channel.history(limit=n)]
        messages.reverse()

        if not messages:
            await interaction.followup.send("There are no messages to simplify in this channel.", ephemeral=True)
            return
            
        formatted_messages = "\n".join([f"{msg.author.display_name}: {msg.content}" for msg in messages])

        prompt = (
            "You are an expert communicator who excels at explaining complex technical topics to a non-technical audience. "
            "Simplify the following Discord chat messages. Your task is to rephrase the conversation, "
            "explaining any jargon, acronyms, or complex technical concepts in very simple, easy-to-understand terms. "
            "The goal is to make the entire conversation accessible to someone with absolutely no technical background. "
            "Focus on clarity and simplicity over technical accuracy if a trade-off is needed. Please use as little lines as possible. Don't add an introduction or a conclusion. Assume that the reader is already familiar with the context. Assume that blank lines are images. Do not try to parse the image, simply ignore it and state that it is an image."
            f"---BEGIN MESSAGES---\n{formatted_messages}\n---END MESSAGES---"
        )

        try:
            simplification = await self.ai_service.generate_response(prompt)
            await interaction.followup.send(f"**Simplified for a non-technical audience:**\n{simplification}")
        except Exception as e:
            logger.error(f"Error during simplification for last {n} messages: {e}")
            await interaction.followup.send("Sorry, an error occurred while trying to simplify the messages. Please try again later.", ephemeral=True)

    @app_commands.command(name="laymanize", description="Alias for /noalien. Simplifies messages for non-technical people.")
    @app_commands.describe(n="The number of recent messages to simplify (1-50, default: 15).")
    async def laymanize(self, interaction: discord.Interaction, n: Optional[int]):
        """Alias for /noalien."""
        await self.noalien(interaction, n)


async def setup(bot: commands.Bot):
    """Sets up the Translator cog."""
    await bot.add_cog(Translator(bot))
    logger.info("Translator cog has been loaded.") 