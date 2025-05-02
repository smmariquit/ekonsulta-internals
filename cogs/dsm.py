import discord
from discord import app_commands
from discord.ext import commands
from google.cloud import firestore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from config import DEFAULT_DSM_TIME

class DsmCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fs_client = firestore.Client()
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        self.schedule_dsm_task()

    async def daily_dsm_task(self):
        print("Running DSM task...")  # Replace with actual DSM logic

    def schedule_dsm_task(self):
        # Retrieve DSM time from Firestore
        config_doc = self.fs_client.collection("config").document("dsm").get()
        dsm_time = config_doc.to_dict().get("time", DEFAULT_DSM_TIME)
        
        # Parse DSM time
        hours, minutes = map(int, dsm_time.split(":"))
        
        # Schedule the task
        self.scheduler.add_job(
            self.daily_dsm_task,
            "cron",
            hour=hours,
            minute=minutes,
            id="dsm_task",
            replace_existing=True,
        )
        print(f"DSM task scheduled at {dsm_time}.")

    @app_commands.command(name="reschedule_dsm", description="Manually reschedule the DSM task with a new time (HH:MM).")
    @app_commands.describe(time="Time in HH:MM format (24-hour clock)")
    async def reschedule_dsm(self, interaction: discord.Interaction, time: str):
        try:
            # Validate time format
            if not time or len(time.split(":")) != 2:
                raise ValueError("Invalid time format. Use HH:MM (24-hour clock).")
            
            hours, minutes = map(int, time.split(":"))
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                raise ValueError("Invalid time. Hours must be 0-23 and minutes 0-59.")
            
            # Save the new time to Firestore
            self.fs_client.collection("config").document("dsm").set({"time": time}, merge=True)
            
            # Reschedule the task
            self.schedule_dsm_task()
            await interaction.response.send_message(f"DSM task rescheduled successfully to {time}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to reschedule DSM task: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        # Sync the slash command 
        await self.bot.tree.sync()
        print("DSM Cog is ready and slash commands are synced.")

def setup(bot):
    bot.add_cog(DsmCog(bot))