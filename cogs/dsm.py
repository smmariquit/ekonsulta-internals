"""Daily Standup Meeting cog."""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import random
import string
from typing import Dict, Any, Optional
from models.task import Task
from services.firebase_service import FirebaseService
from utils.logger import get_logger
from config.default_config import DEFAULT_CONFIG

logger = get_logger("dsm_cog")

class DSM(commands.Cog):
    """Daily Standup Meeting cog."""
    
    def __init__(self, bot: commands.Bot, firebase_service: FirebaseService):
        """Initialize the DSM cog."""
        self.bot = bot
        self.firebase_service = firebase_service
        self.user_tasks: Dict[int, Dict] = {}
        self.daily_standup.start()
        logger.info("DSM cog initialized")

    def generate_task_id(self) -> str:
        """Generate a random six-letter lowercase task ID."""
        return ''.join(random.choices(string.ascii_lowercase, k=6))

    def get_available_task_id(self, user_tasks: list) -> str:
        """Get an available task ID that's not already in use."""
        used_ids = {task.task_id for task in user_tasks if hasattr(task, 'task_id')}
        max_attempts = 10  # Prevent infinite loops
        attempts = 0
        
        while attempts < max_attempts:
            task_id = self.generate_task_id()
            if task_id not in used_ids:
                return task_id
            attempts += 1
            
        # If we couldn't find a unique ID after max attempts, add a timestamp
        timestamp = datetime.datetime.now().strftime('%H%M%S')
        return f"{self.generate_task_id()}{timestamp}"

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.daily_standup.cancel()
        logger.info("DSM cog unloaded")

    async def send_initial_task_embeds(self, thread: discord.Thread):
        """Send initial task embeds for all users in the thread."""
        try:
            # Get all tasks from Firebase
            tasks = await self.firebase_service.load_tasks()
            
            # Send an embed for each user's tasks
            for user_id, user_data in tasks.items():
                # Get member instead of user to access nickname
                member = thread.guild.get_member(int(user_id))
                if not member:
                    continue
                
                # Separate tasks into completed and pending
                completed_tasks = []
                pending_tasks = []
                
                for task in user_data.get("tasks", []):
                    task_text = f"[`{task.task_id}`] {task.description}"
                    if task.remarks:
                        task_text += f"\n   📝 {task.remarks}"
                    if task.status == "done":
                        # Add completion timestamp if available
                        if hasattr(task, 'completed_at'):
                            completion_time = datetime.datetime.fromisoformat(task.completed_at).strftime('%Y-%m-%d %H:%M')
                            task_text += f"\n   ✅ Completed at: {completion_time}"
                        completed_tasks.append(task_text)
                    else:
                        pending_tasks.append(task_text)
                
                # Create embed with two columns
                embed = discord.Embed(
                    title=f"{member.display_name}'s Tasks",  # Use display_name (nickname or username)
                    color=discord.Color.blue()
                )
                
                # Add completed tasks field
                completed_text = "\n\n".join(completed_tasks) if completed_tasks else "No completed tasks"
                embed.add_field(
                    name="✅ Completed Tasks",
                    value=completed_text,
                    inline=True
                )
                
                # Add pending tasks field
                pending_text = "\n\n".join(pending_tasks) if pending_tasks else "No pending tasks"
                embed.add_field(
                    name="⏳ Pending Tasks",
                    value=pending_text,
                    inline=True
                )
                
                # Add task counts
                total_tasks = len(user_data.get("tasks", []))
                embed.set_footer(text=f"Total Tasks: {total_tasks} | Completed: {len(completed_tasks)} | Pending: {len(pending_tasks)}")
                
                embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
                embed.timestamp = datetime.datetime.now()
                
                # Send the embed and store the message ID
                message = await thread.send(embed=embed)
                user_data["message_id"] = message.id
                await self.firebase_service.save_tasks(tasks)
                
            logger.info(f"Sent initial task embeds in thread {thread.name}")
            
        except Exception as e:
            logger.error(f"Error sending initial task embeds: {str(e)}")

    @tasks.loop(hours=24)
    async def daily_standup(self):
        """Create daily standup thread."""
        try:
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_config(guild.id)
                now = datetime.datetime.now()
                
                # Check if today is a skipped date
                today = now.strftime('%Y-%m-%d')
                if today in config.get('skipped_dates', []):
                    logger.info(f"Skipping DSM for {today} as it's in the skipped dates list")
                    continue
                
                if now.hour == config['standup_hour'] and now.minute == config['standup_minute']:
                    channel = guild.get_channel(int(self.bot.channel_id))
                    if channel:
                        # Calculate end time and deadline
                        end_time = now + datetime.timedelta(hours=1)
                        deadline = now + datetime.timedelta(hours=config.get('deadline_hours', 12))
                        
                        # Get all members who should participate
                        members = [member for member in guild.members if not member.bot]
                        member_mentions = "\n".join([f"- {member.mention}" for member in members])
                        
                        # Create initial message in the channel
                        initial_embed = discord.Embed(
                            title="Daily Standup Meeting",
                            description=(
                                f"A new daily standup meeting has been initiated.\n"
                                f"Please check the thread below for details and updates."
                            ),
                            color=discord.Color.blue()
                        )
                        initial_embed.timestamp = now
                        initial_message = await channel.send(embed=initial_embed)
                        
                        # Create the thread as a reply to the initial message
                        thread_name = f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}"
                        thread = await initial_message.create_thread(
                            name=thread_name,
                            auto_archive_duration=config['thread_auto_archive_duration']
                        )
                        logger.info(f"Created standup thread: {thread_name}")
                        
                        # Create and send the opening message in the thread
                        embed = discord.Embed(
                            title=f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}",
                            description=(
                                f"Good morning! To the following, please complete the DSM for today, "
                                f"until {end_time.strftime('%H:%M')} + 1 hour. Mention the tasks you "
                                f"accomplished since the last DSM, the tasks you plan to do today, "
                                f"and any blockers you encountered. Feel free to chat with any notes in the thread.\n\n"
                                f"⚠️ **DEADLINE**: {deadline.strftime('%Y-%m-%d %H:%M')} ⚠️\n"
                                f"After this time, late updates will be logged.\n\n"
                                f"{member_mentions}\n\n"
                                f"Thank you to the following for completing today's DSM:\n"
                                f"(This will be updated as people complete their standups)\n\n"
                                f"Tasks Done From Last Time: 0\n"
                                f"Tasks To Do Today: 0"
                            ),
                            color=discord.Color.blue()
                        )
                        
                        # Add timestamp
                        embed.timestamp = now
                        
                        # Add footer with thread ID for reference
                        embed.set_footer(text=f"Thread ID: {thread.id}")
                        
                        await thread.send(embed=embed)
                        logger.info("Sent opening message to thread")
                        
                        # Send initial task embeds
                        await self.send_initial_task_embeds(thread)
                        
                        # Schedule deadline check
                        await asyncio.sleep(config.get('deadline_hours', 12) * 3600)  # Convert hours to seconds
                        await self.check_deadline(thread, config)
        except Exception as e:
            logger.error(f"Error in daily standup: {str(e)}")

    async def check_deadline(self, thread: discord.Thread, config: dict):
        """Check who hasn't completed their tasks by the deadline."""
        try:
            # Get all members who should participate
            members = [member for member in thread.guild.members if not member.bot]
            completed_members = set()
            
            # Check messages in thread for task updates
            async for message in thread.history(limit=None):
                if not message.author.bot and message.author in members:
                    completed_members.add(message.author)
            
            # Find members who haven't completed tasks
            missing_members = [member for member in members if member not in completed_members]
            
            if missing_members:
                # Create warning message
                warning_embed = discord.Embed(
                    title="⚠️ Deadline Passed ⚠️",
                    description=(
                        "The following members have not completed their daily tasks:\n" +
                        "\n".join([f"- {member.mention}" for member in missing_members]) +
                        "\n\nThis has been logged for record-keeping."
                    ),
                    color=discord.Color.red()
                )
                warning_embed.timestamp = datetime.datetime.now()
                
                await thread.send(embed=warning_embed)
                logger.info(f"Deadline passed for {len(missing_members)} members in thread {thread.name}")
                
                # Log the late updates
                for member in missing_members:
                    await self.log_late_update(member, thread)
        except Exception as e:
            logger.error(f"Error checking deadline: {str(e)}")

    async def log_late_update(self, member: discord.Member, thread: discord.Thread):
        """Log a late task update to Firebase."""
        try:
            log_ref = self.firebase_service.db.collection('late_updates')
            await asyncio.to_thread(log_ref.add, {
                'user_id': str(member.id),
                'username': member.name,
                'date': thread.name.split('-')[-1].strip(),
                'thread_id': str(thread.id),
                'timestamp': datetime.datetime.now().isoformat()
            })
            logger.info(f"Logged late update for {member.name}")
        except Exception as e:
            logger.error(f"Error logging late update: {str(e)}")

    @daily_standup.before_loop
    async def before_daily_standup(self):
        """Wait until the bot is ready before starting the daily standup task."""
        await self.bot.wait_until_ready()
        logger.info("Daily standup task started")

    @commands.Cog.listener()
    async def on_ready(self):
        """Load tasks when bot is ready."""
        self.user_tasks = await self.firebase_service.load_tasks()
        logger.info("Tasks loaded from Firebase")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Save user information when they join."""
        user_data = {
            'id': member.id,
            'name': member.name,
            'discriminator': member.discriminator,
            'avatar_url': str(member.avatar.url) if member.avatar else None,
            'joined_at': member.joined_at.isoformat(),
            'last_active': datetime.datetime.now().isoformat(),
            'last_updated': datetime.datetime.now().isoformat()
        }
        await self.firebase_service.save_user(user_data)
        logger.info(f"New member joined: {member.name}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Update user activity when they send a message."""
        if not message.author.bot:
            await self.firebase_service.update_user_activity(message.author.id)
            logger.debug(f"Updated activity for {message.author.name}")

    @app_commands.command(name="add", description="Add a new task")
    async def add_task(self, interaction: discord.Interaction, task: str):
        """Add a new task."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = {"tasks": [], "message_id": None}
            
            # Generate a unique task ID
            task_id = self.get_available_task_id(self.user_tasks[user_id]["tasks"])
            
            # Create new task with the generated ID
            new_task = Task(description=task, task_id=task_id)
            self.user_tasks[user_id]["tasks"].append(new_task)
            
            # Update user data
            user_data = {
                'id': interaction.user.id,
                'name': interaction.user.name,
                'discriminator': interaction.user.discriminator,
                'avatar_url': str(interaction.user.avatar.url) if interaction.user.avatar else None,
                'joined_at': interaction.user.joined_at.isoformat(),
                'last_active': datetime.datetime.now().isoformat(),
                'last_updated': datetime.datetime.now().isoformat()
            }
            await self.firebase_service.save_user(user_data)
            
            # Save tasks
            await self.firebase_service.save_tasks(self.user_tasks)
            
            # Update message in the current DSM thread
            await self.update_task_message(interaction.channel, user_id)
            logger.info(f"Added task {task_id} for {interaction.user.name}: {task}")
            
            # Send followup message instead of response
            await interaction.followup.send(f"Task added with ID: `{task_id}`", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in add_task: {str(e)}")
            # Try to send error message as followup if possible
            try:
                await interaction.followup.send("Failed to add task. Please try again.", ephemeral=True)
            except:
                pass

    @app_commands.command(name="done", description="Mark a task as done")
    async def mark_done(self, interaction: discord.Interaction, task_id: str):
        """Mark a task as done."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find task by ID
            task = next((t for t in self.user_tasks[user_id]["tasks"] if t.task_id == task_id.lower()), None)
            
            if task:
                # Mark the task as done and add completion timestamp
                task.status = "done"
                task.completed_at = datetime.datetime.now().isoformat()
                
                # Save to Firebase
                await self.firebase_service.save_tasks(self.user_tasks)
                
                # Update the task message in the current DSM thread
                await self.update_task_message(interaction.channel, user_id)
                
                logger.info(f"Marked task {task_id} as done for {interaction.user.display_name}")
                await interaction.followup.send(f"Task {task_id} marked as done!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in mark_done: {str(e)}")
            try:
                await interaction.followup.send("Failed to mark task as done. Please try again.", ephemeral=True)
            except:
                pass

    @app_commands.command(name="remark", description="Add a remark to a task")
    async def add_remark(self, interaction: discord.Interaction, task_id: str, remark: str):
        """Add a remark to a task."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find task by ID
            task = next((t for t in self.user_tasks[user_id]["tasks"] if t.task_id == task_id.lower()), None)
            
            if task:
                task.remarks = remark
                await self.firebase_service.save_tasks(self.user_tasks)
                await self.update_task_message(interaction.channel, user_id)
                logger.info(f"Added remark to task {task_id} for {interaction.user.name}")
                await interaction.followup.send(f"Remark added to task {task_id}!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in add_remark: {str(e)}")
            try:
                await interaction.followup.send("Failed to add remark. Please try again.", ephemeral=True)
            except:
                pass

    @app_commands.command(name="config", description="Configure standup settings")
    @app_commands.default_permissions(administrator=True)
    async def configure(self, interaction: discord.Interaction,
                       hour: int = None,
                       minute: int = None,
                       thread_name: str = None,
                       auto_archive: int = None):
        """Configure standup settings."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        updates = {}
        if hour is not None:
            if not 0 <= hour <= 23:
                await interaction.response.send_message("Hour must be between 0 and 23!", ephemeral=True)
                return
            updates['standup_hour'] = hour
        
        if minute is not None:
            if not 0 <= minute <= 59:
                await interaction.response.send_message("Minute must be between 0 and 59!", ephemeral=True)
                return
            updates['standup_minute'] = minute
        
        if thread_name is not None:
            updates['thread_name_template'] = thread_name
        
        if auto_archive is not None:
            if auto_archive not in [60, 1440, 4320, 10080]:
                await interaction.response.send_message("Auto-archive duration must be one of: 60, 1440, 4320, 10080 minutes!", ephemeral=True)
                return
            updates['thread_auto_archive_duration'] = auto_archive
        
        if updates:
            config = await self.firebase_service.update_config(interaction.guild_id, updates)
            logger.info(f"Updated config for guild {interaction.guild_id}: {updates}")
            await interaction.response.send_message("Configuration updated!", ephemeral=True)
        else:
            await interaction.response.send_message("No changes provided!", ephemeral=True)

    @app_commands.command(name="simulate_dsm", description="Manually trigger a DSM thread")
    @app_commands.default_permissions(administrator=True)
    async def simulate_dsm(self, interaction: discord.Interaction):
        """Manually trigger a DSM thread."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Defer the response since this might take a moment
            await interaction.response.defer(ephemeral=True)
            
            # Get current time
            now = datetime.datetime.now()
            
            # Calculate end time and deadline
            end_time = now + datetime.timedelta(hours=1)
            deadline = now + datetime.timedelta(hours=12)  # Default 12-hour deadline
            
            # Get all members who should participate
            members = [member for member in interaction.guild.members if not member.bot]
            member_mentions = "\n".join([f"- {member.mention}" for member in members])
            
            # Create initial message in the channel
            initial_embed = discord.Embed(
                title="Daily Standup Meeting (Manual)",
                description=(
                    f"A daily standup meeting has been manually initiated by {interaction.user.mention}.\n"
                    f"Please check the thread below for details and updates."
                ),
                color=discord.Color.blue()
            )
            initial_embed.timestamp = now
            initial_message = await interaction.channel.send(embed=initial_embed)
            
            # Create the thread as a reply to the initial message
            thread_name = f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}"
            thread = await initial_message.create_thread(
                name=thread_name,
                auto_archive_duration=10080  # 7 days
            )
            logger.info(f"Manually created standup thread: {thread_name}")
            
            # Create and send the opening message in the thread
            embed = discord.Embed(
                title=f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}",
                description=(
                    f"Good morning! To the following, please complete the DSM for today, "
                    f"until {end_time.strftime('%H:%M')} + 1 hour. Mention the tasks you "
                    f"accomplished since the last DSM, the tasks you plan to do today, "
                    f"and any blockers you encountered. Feel free to chat with any notes in the thread.\n\n"
                    f"⚠️ **DEADLINE**: {deadline.strftime('%Y-%m-%d %H:%M')} ⚠️\n"
                    f"After this time, late updates will be logged.\n\n"
                    f"{member_mentions}\n\n"
                    f"Thank you to the following for completing today's DSM:\n"
                    f"(This will be updated as people complete their standups)\n\n"
                    f"Tasks Done From Last Time: 0\n"
                    f"Tasks To Do Today: 0"
                ),
                color=discord.Color.blue()
            )
            
            # Add timestamp
            embed.timestamp = now
            
            # Add footer with thread ID for reference
            embed.set_footer(text=f"Thread ID: {thread.id}")
            
            await thread.send(embed=embed)
            logger.info("Sent opening message to thread")
            
            # Send initial task embeds
            await self.send_initial_task_embeds(thread)
            
            # Send confirmation to the command user
            await interaction.followup.send(
                f"Successfully created DSM thread: {thread.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            await interaction.followup.send(
                f"Failed to create DSM thread: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="resend_dsm", description="Resend the opening message in a DSM thread")
    @app_commands.default_permissions(administrator=True)
    async def resend_dsm(self, interaction: discord.Interaction):
        """Resend the opening message in a DSM thread."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        # Check if the command is used in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("This command can only be used in a DSM thread!", ephemeral=True)
            return
        
        try:
            # Defer the response since this might take a moment
            await interaction.response.defer(ephemeral=True)
            
            # Get current time
            now = datetime.datetime.now()
            
            # Calculate end time (current time + 1 hour)
            end_time = now + datetime.timedelta(hours=1)
            
            # Get all members who should participate
            members = [member for member in interaction.guild.members if not member.bot]
            member_mentions = "\n".join([f"- {member.mention}" for member in members])
            
            # Create and send the opening message
            embed = discord.Embed(
                title=f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}",
                description=(
                    f"Good morning! To the following, please complete the DSM for today, "
                    f"until {end_time.strftime('%H:%M')} + 1 hour. Mention the tasks you "
                    f"accomplished since the last DSM, the tasks you plan to do today, "
                    f"and any blockers you encountered. Feel free to chat with any notes in the thread.\n\n"
                    f"{member_mentions}\n\n"
                    f"Thank you to the following for completing today's DSM:\n"
                    f"(This will be updated as people complete their standups)\n\n"
                    f"Tasks Done From Last Time: 0\n"
                    f"Tasks To Do Today: 0"
                ),
                color=discord.Color.blue()
            )
            
            # Add timestamp
            embed.timestamp = now
            
            # Add footer with thread ID for reference
            embed.set_footer(text=f"Thread ID: {interaction.channel.id}")
            
            # Send the message
            message = await interaction.channel.send(embed=embed)
            logger.info(f"Resent opening message in thread {interaction.channel.name}")
            
            # Send confirmation to the command user
            await interaction.followup.send(
                "Successfully resent the opening message!",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error in resend_dsm: {str(e)}")
            await interaction.followup.send(
                f"Failed to resend the opening message: {str(e)}",
                ephemeral=True
            )

    async def update_task_message(self, channel: discord.TextChannel, user_id: int = None):
        """Update the task message with current tasks."""
        try:
            # Get the current DSM thread if it exists
            current_thread = None
            if isinstance(channel, discord.TextChannel):
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                # Check archived threads
                async for thread in channel.archived_threads():
                    if thread.name == f"DAILY STANDUP MEETING - {today}":
                        current_thread = thread
                        break
                # Check active threads
                if not current_thread:
                    for thread in channel.threads:
                        if thread.name == f"DAILY STANDUP MEETING - {today}":
                            current_thread = thread
                            break

            # If we're updating for a specific user
            if user_id:
                if user_id not in self.user_tasks:
                    return
                
                # Get member instead of user to access nickname
                member = channel.guild.get_member(user_id)
                if not member:
                    return
                
                user_data = self.user_tasks[user_id]
                
                # Separate tasks into completed and pending
                completed_tasks = []
                pending_tasks = []
                
                for task in user_data["tasks"]:
                    task_text = f"[`{task.task_id}`] {task.description}"
                    if task.remarks:
                        task_text += f"\n   📝 {task.remarks}"
                    if task.status == "done":
                        # Add completion timestamp if available
                        if hasattr(task, 'completed_at'):
                            completion_time = datetime.datetime.fromisoformat(task.completed_at).strftime('%Y-%m-%d %H:%M')
                            task_text += f"\n   ✅ Completed at: {completion_time}"
                        completed_tasks.append(task_text)
                    else:
                        pending_tasks.append(task_text)
                
                # Create embed with two columns
                embed = discord.Embed(
                    title=f"{member.display_name}'s Tasks",  # Use display_name (nickname or username)
                    color=discord.Color.blue()
                )
                
                # Add completed tasks field
                completed_text = "\n\n".join(completed_tasks) if completed_tasks else "No completed tasks"
                embed.add_field(
                    name="✅ Completed Tasks",
                    value=completed_text,
                    inline=True
                )
                
                # Add pending tasks field
                pending_text = "\n\n".join(pending_tasks) if pending_tasks else "No pending tasks"
                embed.add_field(
                    name="⏳ Pending Tasks",
                    value=pending_text,
                    inline=True
                )
                
                # Add task counts
                embed.set_footer(text=f"Total Tasks: {len(user_data['tasks'])} | Completed: {len(completed_tasks)} | Pending: {len(pending_tasks)}")
                
                embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
                embed.timestamp = datetime.datetime.now()
                
                # Send to appropriate channel
                target_channel = current_thread if current_thread else channel
                if user_data.get("message_id"):
                    try:
                        message = await target_channel.fetch_message(user_data["message_id"])
                        await message.edit(embed=embed)
                        logger.info(f"Updated task message for {member.display_name}")
                    except (discord.NotFound, discord.Forbidden) as e:
                        logger.warning(f"Could not update message for {member.display_name}: {str(e)}")
                        # If message not found or can't edit, create new message
                        message = await target_channel.send(embed=embed)
                        user_data["message_id"] = message.id
                        await self.firebase_service.save_tasks(self.user_tasks)
                        logger.info(f"Created new task message for {member.display_name}")
                else:
                    message = await target_channel.send(embed=embed)
                    user_data["message_id"] = message.id
                    await self.firebase_service.save_tasks(self.user_tasks)
                    logger.info(f"Created new task message for {member.display_name}")
            
            # If we're updating all users
            else:
                for user_id, user_data in self.user_tasks.items():
                    await self.update_task_message(channel, user_id)
                    
        except Exception as e:
            logger.error(f"Error updating task message: {str(e)}")

    @app_commands.command(name="skip_dsm", description="Skip DSM on a specific date")
    @app_commands.default_permissions(administrator=True)
    async def skip_dsm(self, interaction: discord.Interaction, date: str):
        """Skip DSM on a specific date."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Validate date format
            datetime.datetime.strptime(date, '%Y-%m-%d')
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Add date to skipped dates if not already present
            if date not in config.get('skipped_dates', []):
                skipped_dates = config.get('skipped_dates', []) + [date]
                await self.firebase_service.update_config(interaction.guild_id, {'skipped_dates': skipped_dates})
                await interaction.response.send_message(f"DSM will be skipped on {date}", ephemeral=True)
                logger.info(f"Added {date} to skipped dates")
            else:
                await interaction.response.send_message(f"DSM is already scheduled to be skipped on {date}", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-21)",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in skip_dsm: {str(e)}")
            await interaction.response.send_message(
                f"Failed to skip DSM: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="unskip_dsm", description="Remove a date from the skipped DSM list")
    @app_commands.default_permissions(administrator=True)
    async def unskip_dsm(self, interaction: discord.Interaction, date: str):
        """Remove a date from the skipped DSM list."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Validate date format
            datetime.datetime.strptime(date, '%Y-%m-%d')
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Remove date from skipped dates if present
            skipped_dates = config.get('skipped_dates', [])
            if date in skipped_dates:
                skipped_dates.remove(date)
                await self.firebase_service.update_config(interaction.guild_id, {'skipped_dates': skipped_dates})
                await interaction.response.send_message(f"DSM will no longer be skipped on {date}", ephemeral=True)
                logger.info(f"Removed {date} from skipped dates")
            else:
                await interaction.response.send_message(f"DSM was not scheduled to be skipped on {date}", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-21)",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in unskip_dsm: {str(e)}")
            await interaction.response.send_message(
                f"Failed to unskip DSM: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="list_skipped_dsm", description="List all dates where DSM is skipped")
    @app_commands.default_permissions(administrator=True)
    async def list_skipped_dsm(self, interaction: discord.Interaction):
        """List all dates where DSM is skipped."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            skipped_dates = config.get('skipped_dates', [])
            
            if skipped_dates:
                # Sort dates
                skipped_dates.sort()
                
                # Create embed
                embed = discord.Embed(
                    title="Skipped DSM Dates",
                    description="The following dates are scheduled to skip DSM:",
                    color=discord.Color.blue()
                )
                
                # Add dates to embed
                for date in skipped_dates:
                    embed.add_field(
                        name=date,
                        value="DSM will be skipped",
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("No dates are currently scheduled to skip DSM.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in list_skipped_dsm: {str(e)}")
            await interaction.response.send_message(
                f"Failed to list skipped dates: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="generate_report", description="Generate a report of all tasks")
    @app_commands.default_permissions(administrator=True)
    async def generate_report(self, interaction: discord.Interaction, days: int = 7):
        """Generate a report of all tasks."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get all tasks from Firebase
            tasks = await self.firebase_service.load_tasks()
            
            # Create report embed
            embed = discord.Embed(
                title="Task Report",
                description=f"Task report for the last {days} days",
                color=discord.Color.blue()
            )
            
            # Process each user's tasks
            for user_id, user_data in tasks.items():
                user = self.bot.get_user(int(user_id))
                if not user:
                    continue
                
                # Filter tasks by date
                recent_tasks = []
                for task in user_data.get("tasks", []):
                    if hasattr(task, 'created_at'):
                        task_date = datetime.datetime.fromisoformat(task.created_at)
                        if (datetime.datetime.now() - task_date).days <= days:
                            recent_tasks.append(task)
                
                if recent_tasks:
                    tasks_text = ""
                    for task in recent_tasks:
                        status = "✅ Done" if task.status == "done" else "⏳ Pending"
                        created_at = datetime.datetime.fromisoformat(task.created_at).strftime('%Y-%m-%d %H:%M')
                        tasks_text += f"**{task.description}**\n"
                        tasks_text += f"Status: {status}\n"
                        tasks_text += f"Created: {created_at}\n"
                        if task.remarks:
                            tasks_text += f"Remarks: {task.remarks}\n"
                        tasks_text += "\n"
                    
                    embed.add_field(
                        name=f"{user.name}'s Tasks",
                        value=tasks_text,
                        inline=False
                    )
            
            # Add timestamp
            embed.timestamp = datetime.datetime.now()
            
            # Send report
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Generated task report for {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            await interaction.followup.send(
                f"Failed to generate report: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="add_admin", description="Add an administrator to the bot")
    @app_commands.default_permissions(administrator=True)
    async def add_admin(self, interaction: discord.Interaction, user: discord.Member):
        """Add an administrator to the bot."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Initialize admins list if it doesn't exist
            if 'admins' not in config:
                config['admins'] = []
            
            # Add user to admins if not already present
            if str(user.id) not in config['admins']:
                config['admins'].append(str(user.id))
                await self.firebase_service.update_config(interaction.guild_id, {'admins': config['admins']})
                await interaction.response.send_message(f"Added {user.mention} as an administrator!", ephemeral=True)
                logger.info(f"Added {user.name} as an administrator")
            else:
                await interaction.response.send_message(f"{user.mention} is already an administrator!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error adding admin: {str(e)}")
            await interaction.response.send_message(
                f"Failed to add administrator: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="remove_admin", description="Remove an administrator from the bot")
    @app_commands.default_permissions(administrator=True)
    async def remove_admin(self, interaction: discord.Interaction, user: discord.Member):
        """Remove an administrator from the bot."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Remove user from admins if present
            if 'admins' in config and str(user.id) in config['admins']:
                config['admins'].remove(str(user.id))
                await self.firebase_service.update_config(interaction.guild_id, {'admins': config['admins']})
                await interaction.response.send_message(f"Removed {user.mention} from administrators!", ephemeral=True)
                logger.info(f"Removed {user.name} from administrators")
            else:
                await interaction.response.send_message(f"{user.mention} is not an administrator!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error removing admin: {str(e)}")
            await interaction.response.send_message(
                f"Failed to remove administrator: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="list_admins", description="List all bot administrators")
    @app_commands.default_permissions(administrator=True)
    async def list_admins(self, interaction: discord.Interaction):
        """List all bot administrators."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Create embed
            embed = discord.Embed(
                title="Bot Administrators",
                description="The following users are bot administrators:",
                color=discord.Color.blue()
            )
            
            if 'admins' in config and config['admins']:
                for admin_id in config['admins']:
                    admin = interaction.guild.get_member(int(admin_id))
                    if admin:
                        embed.add_field(
                            name=admin.name,
                            value=f"ID: {admin_id}",
                            inline=False
                        )
            else:
                embed.description = "No administrators have been set."
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing admins: {str(e)}")
            await interaction.response.send_message(
                f"Failed to list administrators: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="refresh_tasks", description="Refresh your task message")
    async def refresh_tasks(self, interaction: discord.Interaction):
        """Refresh your task message."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Update the task message
            await self.update_task_message(interaction.channel, user_id)
            logger.info(f"Manually refreshed task message for {interaction.user.name}")
            
            await interaction.followup.send("Task message refreshed!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in refresh_tasks: {str(e)}")
            try:
                await interaction.followup.send("Failed to refresh task message. Please try again.", ephemeral=True)
            except:
                pass

async def setup(bot: commands.Bot):
    """Set up the DSM cog."""
    firebase_service = FirebaseService('firebase-credentials.json')
    await bot.add_cog(DSM(bot, firebase_service))