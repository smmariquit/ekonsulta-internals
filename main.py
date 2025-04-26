import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file
# Set up logging            
token = os.getenv("DISCORD_BOT_TOKEN")

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w") 
# Intents are required for certain events
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")

@bot.command()
async def hello(ctx):
    """Responds with Hello!"""
    await ctx.send("Hello!")

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Set your bot token as an environment variable
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")