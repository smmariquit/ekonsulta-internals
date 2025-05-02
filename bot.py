import discord  # discord.py
from discord import app_commands  # slash commands
from discord.ext import commands  # prefix commands
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import logging  # logging framework
from dotenv import load_dotenv  # for loading environment variables
import os
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize Firebase
cred = credentials.Certificate("internals-bot-firebase-adminsdk-fbsvc-04121b2125.json")
app = firebase_admin.initialize_app(cred)
fs_client = firebase_admin.firestore.client()

# Load environment variables
load_dotenv()
token = os.getenv("DISCORD_BOT_TOKEN")

# Set up logging
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# Intents are required for certain events
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Slash commands
@bot.tree.command(name="saveme", description="Add my user ID to Firestore")
async def saveme(interaction: discord.Interaction):
    try:
        user_doc = fs_client.collection('users').document(str(interaction.user.id))  # Convert to string
        user_doc.set({
            "name": interaction.user.display_name,
        })
    except Exception as e:
        print(e)
    await interaction.response.send_message(f"Successfully saved your user ID to Cloud Firestore! {interaction.user.id}", ephemeral=True)


@bot.tree.command(name="hello", description="Say hello!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.mention}! This is a slash command :D", ephemeral=True)


@bot.tree.command(name="say", description="What should I say?")
@app_commands.describe(message="What should I say?")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(f"{interaction.user.name} said: `{message}`")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    try:
        # Sync commands globally
        synced_commands = await bot.tree.sync()
        print(f"Successfully synced {len(synced_commands)} global commands.")
        print("Synced global commands:")
        for command in synced_commands:
            print(f"- {command.name}: {command.description}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Set your bot token as an environment variable
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")