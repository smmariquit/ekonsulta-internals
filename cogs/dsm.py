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
from models.dsm_session import DSMSession

logger = get_logger("dsm_cog")

class TaskModal(discord.ui.Modal, title='Add New Task'):
    """Modal for adding a new task."""
    
    def __init__(self, dsm_cog):
        super().__init__()
        self.dsm_cog = dsm_cog
        self.description = discord.ui.TextInput(
            label='Task Description',
            placeholder='Enter your task description here...',
            required=True,
            max_length=1000
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        await self.dsm_cog._add_task(interaction, self.description.value)

class RemarkModal(discord.ui.Modal, title='Add Remark'):
    """Modal for adding a remark to a task."""
    
    def __init__(self, dsm_cog, task_id: str):
        super().__init__()
        self.dsm_cog = dsm_cog
        self.task_id = task_id
        self.remark = discord.ui.TextInput(
            label='Remark',
            placeholder='Enter your remark here...',
            required=True,
            max_length=1000
        )
        self.add_item(self.remark)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find task by ID
            task = next((t for t in self.dsm_cog.user_tasks[user_id]["tasks"] if t.task_id == self.task_id.lower()), None)
            
            if task:
                task.remarks = self.remark.value
                await self.dsm_cog.firebase_service.save_tasks(self.dsm_cog.user_tasks)
                await self.dsm_cog.update_task_message(interaction.channel, user_id)
                logger.info(f"[COMMAND] Added remark to task {self.task_id} for {interaction.user.name}")
                await interaction.followup.send(f"Remark added to task {self.task_id}!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {self.task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"[COMMAND] Error in add_remark: {str(e)}")
            try:
                await interaction.followup.send("Failed to add remark. Please try again.", ephemeral=True)
            except:
                pass

class TaskSelectView(discord.ui.View):
    """View for selecting tasks with pagination."""
    
    def __init__(self, tasks, title, callback, dsm_cog):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.title = title
        self.callback = callback
        self.dsm_cog = dsm_cog
        self.current_page = 0
        self.items_per_page = 25
        
        # Sort tasks by creation date (newest first)
        def get_created_at(task):
            if hasattr(task, 'created_at') and task.created_at:
                if isinstance(task.created_at, str):
                    return datetime.datetime.fromisoformat(task.created_at)
                return task.created_at
            return datetime.datetime.min
        
        self.tasks = sorted(self.tasks, key=get_created_at, reverse=True)  # Added reverse=True for newest first
        
        # Create initial select menu
        self.update_select_menu()
    
    def update_select_menu(self):
        """Update the select menu with current page of tasks."""
        # Clear existing items
        self.clear_items()
        
        # Calculate start and end indices for current page
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.tasks))
        
        # Create new select menu
        select = discord.ui.Select(
            placeholder=f"{self.title} (Page {self.current_page + 1})",
            options=[
                discord.SelectOption(
                    label=f"[{task.task_id}] {task.description[:80]}...",
                    value=f"{task.task_id}_{i}",  # Make value unique by adding index
                    description=self._format_task_description(task)
                )
                for i, task in enumerate(self.tasks[start_idx:end_idx])
            ]
        )
        
        async def select_callback(interaction: discord.Interaction):
            # Extract the actual task_id from the value (remove the index)
            task_id = select.values[0].split('_')[0]
            await self.callback(interaction, task_id)
        
        select.callback = select_callback
        self.add_item(select)
        
        # Add pagination buttons with unique custom_ids
        prev_button = discord.ui.Button(
            label="◀️",
            custom_id=f"prev_page_{id(self)}",  # Make custom_id unique
            style=discord.ButtonStyle.secondary
        )
        
        next_button = discord.ui.Button(
            label="▶️",
            custom_id=f"next_page_{id(self)}",  # Make custom_id unique
            style=discord.ButtonStyle.secondary
        )
        
        async def prev_callback(interaction: discord.Interaction):
            if self.current_page > 0:
                self.current_page -= 1
                self.update_select_menu()
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.defer()
        
        async def next_callback(interaction: discord.Interaction):
            max_page = (len(self.tasks) - 1) // self.items_per_page
            if self.current_page < max_page:
                self.current_page += 1
                self.update_select_menu()
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.defer()
        
        prev_button.callback = prev_callback
        next_button.callback = next_callback
        
        self.add_item(prev_button)
        self.add_item(next_button)

    def _format_task_description(self, task):
        """Format the task description with date."""
        try:
            if hasattr(task, 'created_at') and task.created_at:
                if isinstance(task.created_at, str):
                    created_at = datetime.datetime.fromisoformat(task.created_at)
                else:
                    created_at = task.created_at
                return f"{created_at.strftime('%b %d')} - {task.description[:100]}"
            return task.description[:100]
        except Exception as e:
            logger.error(f"Error formatting task description: {str(e)}")
            return task.description[:100]

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh the task view."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            logger.info(f"[DEBUG] Starting refresh for user {user_id} ({interaction.user.name})")
            
            if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
                logger.info(f"[DEBUG] No tasks found for user {user_id}")
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find the current DSM thread
            current_thread = None
            if isinstance(interaction.channel, discord.TextChannel):
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                logger.info(f"[DEBUG] Searching for DSM thread for date {today}")
                # Check archived threads
                async for thread in interaction.channel.archived_threads():
                    if thread.name == f"DAILY STANDUP MEETING - {today}":
                        current_thread = thread
                        logger.info(f"[DEBUG] Found archived thread: {thread.id}")
                        break
                # Check active threads
                if not current_thread:
                    for thread in interaction.channel.threads:
                        if thread.name == f"DAILY STANDUP MEETING - {today}":
                            current_thread = thread
                            logger.info(f"[DEBUG] Found active thread: {thread.id}")
                            break
            
            # Delete existing messages and resend them
            if current_thread:
                logger.info(f"[DEBUG] Deleting and resending messages in thread {current_thread.id}")
                # Get stored message IDs
                message_data = await self.dsm_cog.get_latest_dsm_message(interaction.guild.id, user_id)
                if message_data:
                    # Try to delete existing messages
                    for msg_id in message_data.get('completed_messages', []) + message_data.get('pending_messages', []):
                        try:
                            msg = await current_thread.fetch_message(msg_id)
                            await msg.delete()
                            logger.info(f"[DEBUG] Deleted message {msg_id}")
                        except (discord.NotFound, discord.Forbidden):
                            logger.info(f"[DEBUG] Could not delete message {msg_id}")
                
                # Send new messages
                await self.dsm_cog.send_initial_task_embeds(current_thread, user_id)
            else:
                logger.info(f"[DEBUG] No thread found, updating in channel {interaction.channel.id}")
                # Get stored message IDs
                message_data = await self.dsm_cog.get_latest_dsm_message(interaction.guild.id, user_id)
                if message_data:
                    # Try to delete existing messages
                    for msg_id in message_data.get('completed_messages', []) + message_data.get('pending_messages', []):
                        try:
                            msg = await interaction.channel.fetch_message(msg_id)
                            await msg.delete()
                            logger.info(f"[DEBUG] Deleted message {msg_id}")
                        except (discord.NotFound, discord.Forbidden):
                            logger.info(f"[DEBUG] Could not delete message {msg_id}")
                
                # Send new messages
                await self.dsm_cog.send_initial_task_embeds(interaction.channel, user_id)
            
            logger.info(f"[DEBUG] Refresh completed for {interaction.user.name}")
            await interaction.followup.send("Task messages refreshed!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in refresh: {str(e)}")
            try:
                await interaction.followup.send("Failed to refresh task messages. Please try again.", ephemeral=True)
            except:
                pass

class DSMView(discord.ui.View):
    """View for the DSM interface."""
    
    def __init__(self, dsm_cog):
        super().__init__(timeout=None)
        self.dsm_cog = dsm_cog

    @discord.ui.button(label="Add Task", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the add task modal."""
        modal = TaskModal(self.dsm_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mark Done", style=discord.ButtonStyle.success, emoji="✅")
    async def mark_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the mark done modal."""
        # Get user's tasks
        user_id = interaction.user.id
        if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
            await interaction.response.send_message("You have no tasks to mark as done!", ephemeral=True)
            return

        # Get pending tasks
        pending_tasks = [
            task for task in self.dsm_cog.user_tasks[user_id]["tasks"]
            if task.status != "done"
        ]

        if not pending_tasks:
            await interaction.response.send_message("You have no pending tasks to mark as done!", ephemeral=True)
            return

        # Create paginated view for task selection
        async def mark_done_callback(interaction: discord.Interaction, task_id: str):
            try:
                # Defer the response immediately to prevent timeout
                await interaction.response.defer(ephemeral=True)
                
                user_id = interaction.user.id
                
                if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
                    await interaction.followup.send("You have no tasks!", ephemeral=True)
                    return
                
                # Find task by ID
                task = next((t for t in self.dsm_cog.user_tasks[user_id]["tasks"] if t.task_id == task_id), None)
                
                if task:
                    # Mark the task as done and add completion timestamp
                    task.status = "done"
                    task.completed_at = datetime.datetime.now().isoformat()
                    
                    # Save to Firebase
                    await self.dsm_cog.firebase_service.save_tasks(self.dsm_cog.user_tasks)
                    
                    # Update the task message in the current DSM thread
                    await self.dsm_cog.update_task_message(interaction.channel, user_id)
                    
                    logger.info(f"[COMMAND] Task {task_id} marked as done for {interaction.user.display_name}")
                    await interaction.followup.send(f"Task {task_id} marked as done!", ephemeral=True)
                else:
                    await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                    
            except Exception as e:
                logger.error(f"[COMMAND] Error in mark_done_callback: {str(e)}")
                try:
                    await interaction.followup.send("Failed to mark task as done. Please try again.", ephemeral=True)
                except:
                    pass

        view = TaskSelectView(
            tasks=pending_tasks,
            title="Select a task to mark as done",
            callback=mark_done_callback,
            dsm_cog=self.dsm_cog
        )
        
        await interaction.response.send_message("Select a task to mark as done:", view=view, ephemeral=True)

    @discord.ui.button(label="Add Remark", style=discord.ButtonStyle.secondary, emoji="📝")
    async def add_remark(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the add remark modal."""
        # Get user's tasks
        user_id = interaction.user.id
        if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
            await interaction.response.send_message("You have no tasks!", ephemeral=True)
            return

        # Get all tasks
        tasks = self.dsm_cog.user_tasks[user_id]["tasks"]

        if not tasks:
            await interaction.response.send_message("You have no tasks!", ephemeral=True)
            return

        # Create paginated view for task selection
        async def add_remark_callback(interaction: discord.Interaction, task_id: str):
            modal = RemarkModal(self.dsm_cog, task_id)
            await interaction.response.send_modal(modal)

        view = TaskSelectView(
            tasks=tasks,
            title="Select a task to add a remark",
            callback=add_remark_callback,
            dsm_cog=self.dsm_cog
        )
        
        await interaction.response.send_message("Select a task to add a remark:", view=view, ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh the task view."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            logger.info(f"[DEBUG] Starting refresh for user {user_id} ({interaction.user.name})")
            
            if user_id not in self.dsm_cog.user_tasks or not self.dsm_cog.user_tasks[user_id]["tasks"]:
                logger.info(f"[DEBUG] No tasks found for user {user_id}")
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find the current DSM thread
            current_thread = None
            if isinstance(interaction.channel, discord.TextChannel):
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                logger.info(f"[DEBUG] Searching for DSM thread for date {today}")
                # Check archived threads
                async for thread in interaction.channel.archived_threads():
                    if thread.name == f"DAILY STANDUP MEETING - {today}":
                        current_thread = thread
                        logger.info(f"[DEBUG] Found archived thread: {thread.id}")
                        break
                # Check active threads
                if not current_thread:
                    for thread in interaction.channel.threads:
                        if thread.name == f"DAILY STANDUP MEETING - {today}":
                            current_thread = thread
                            logger.info(f"[DEBUG] Found active thread: {thread.id}")
                            break
            
            # Delete existing messages and resend them
            if current_thread:
                logger.info(f"[DEBUG] Deleting and resending messages in thread {current_thread.id}")
                # Get stored message IDs
                message_data = await self.dsm_cog.get_latest_dsm_message(interaction.guild.id, user_id)
                if message_data:
                    # Try to delete existing messages
                    for msg_id in message_data.get('completed_messages', []) + message_data.get('pending_messages', []):
                        try:
                            msg = await current_thread.fetch_message(msg_id)
                            await msg.delete()
                            logger.info(f"[DEBUG] Deleted message {msg_id}")
                        except (discord.NotFound, discord.Forbidden):
                            logger.info(f"[DEBUG] Could not delete message {msg_id}")
                
                # Send new messages
                await self.dsm_cog.send_initial_task_embeds(current_thread, user_id)
            else:
                logger.info(f"[DEBUG] No thread found, updating in channel {interaction.channel.id}")
                # Get stored message IDs
                message_data = await self.dsm_cog.get_latest_dsm_message(interaction.guild.id, user_id)
                if message_data:
                    # Try to delete existing messages
                    for msg_id in message_data.get('completed_messages', []) + message_data.get('pending_messages', []):
                        try:
                            msg = await interaction.channel.fetch_message(msg_id)
                            await msg.delete()
                            logger.info(f"[DEBUG] Deleted message {msg_id}")
                        except (discord.NotFound, discord.Forbidden):
                            logger.info(f"[DEBUG] Could not delete message {msg_id}")
                
                # Send new messages
                await self.dsm_cog.send_initial_task_embeds(interaction.channel, user_id)
            
            logger.info(f"[DEBUG] Refresh completed for {interaction.user.name}")
            await interaction.followup.send("Task messages refreshed!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in refresh: {str(e)}")
            try:
                await interaction.followup.send("Failed to refresh task messages. Please try again.", ephemeral=True)
            except:
                pass

class DSM(commands.Cog):
    """Daily Standup Meeting cog."""
    
    def __init__(self, bot: commands.Bot, firebase_service: FirebaseService):
        """Initialize the DSM cog."""
        self.bot = bot
        self.firebase_service = firebase_service
        self.user_tasks: Dict[int, Dict] = {}
        self.dsm_messages: Dict[int, Dict[int, int]] = {}  # guild_id -> {user_id -> message_id}
        self.daily_standup.start()
        logger.info("DSM cog initialized")

    def generate_task_id(self) -> str:
        """Generate a random four-character task ID using numbers and lowercase letters."""
        # Using 36 characters (10 numbers + 26 lowercase letters)
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

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
            
        # If we couldn't find a unique ID after max attempts, add a number
        for i in range(1000):  # Try up to 1000 more combinations
            task_id = f"{self.generate_task_id()}{i}"
            if task_id not in used_ids:
                return task_id
            
        raise ValueError("Could not generate a unique task ID after multiple attempts")

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.daily_standup.cancel()
        logger.info("DSM cog unloaded")

    async def get_latest_dsm_message(self, guild_id: int, user_id: int) -> Optional[Dict[str, int]]:
        """Get the latest DSM message IDs for a user from config."""
        try:
            # Get config from Firebase
            config = await self.firebase_service.get_config(guild_id)
            
            # Get message IDs from config
            message_ids = config.get('dsm_messages', {}).get(str(user_id))
            
            # Handle old format (single integer)
            if isinstance(message_ids, int):
                # Convert old format to new format
                return {
                    'completed_messages': [message_ids],
                    'pending_messages': [message_ids + 1]
                }
            
            # Return new format (dictionary)
            return message_ids
            
        except Exception as e:
            logger.error(f"[DEBUG] Error getting latest DSM message: {str(e)}")
            return None

    async def save_dsm_message(self, guild_id: int, user_id: int, message_data: dict):
        """Save DSM message IDs to Firebase config."""
        try:
            # Get current config
            config = await self.firebase_service.get_config(guild_id)
            
            # Initialize dsm_messages if it doesn't exist
            if 'dsm_messages' not in config:
                config['dsm_messages'] = {}
            
            # Update message data for the user
            config['dsm_messages'][str(user_id)] = message_data
            
            # Save updated config
            await self.firebase_service.update_config(guild_id, {'dsm_messages': config['dsm_messages']})
            logger.info(f"[DEBUG] Saved DSM message data to config: {message_data}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error saving DSM message data: {str(e)}")
            raise

    @app_commands.command(name="refresh-tasks", description="Refresh your task message")
    async def refresh_tasks(self, interaction: discord.Interaction):
        """Refresh your task message."""
        logger.info(f"[COMMAND] /refresh-tasks used by {interaction.user.name} ({interaction.user.id}) in {interaction.guild.name} ({interaction.guild.id})")
        await self._refresh_tasks(interaction)

    async def _refresh_tasks(self, interaction: discord.Interaction):
        """Internal method to refresh tasks."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            logger.info(f"[DEBUG] Starting refresh for user {user_id} ({interaction.user.name})")
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                logger.info(f"[DEBUG] No tasks found for user {user_id}")
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find the current DSM thread
            current_thread = None
            if isinstance(interaction.channel, discord.TextChannel):
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                logger.info(f"[DEBUG] Searching for DSM thread for date {today}")
                # Check archived threads
                async for thread in interaction.channel.archived_threads():
                    if thread.name == f"DAILY STANDUP MEETING - {today}":
                        current_thread = thread
                        logger.info(f"[DEBUG] Found archived thread: {thread.id}")
                        break
                # Check active threads
                if not current_thread:
                    for thread in interaction.channel.threads:
                        if thread.name == f"DAILY STANDUP MEETING - {today}":
                            current_thread = thread
                            logger.info(f"[DEBUG] Found active thread: {thread.id}")
                            break
            
            # Update the task message in the appropriate channel
            if current_thread:
                logger.info(f"[DEBUG] Updating message in thread {current_thread.id}")
                await self.update_task_message(current_thread, user_id)
            else:
                logger.info(f"[DEBUG] No thread found, updating in channel {interaction.channel.id}")
                await self.update_task_message(interaction.channel, user_id)
            
            logger.info(f"[DEBUG] Refresh completed for {interaction.user.name}")
            await interaction.followup.send("Task message refreshed!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in _refresh_tasks: {str(e)}")
            try:
                await interaction.followup.send("Failed to refresh task message. Please try again.", ephemeral=True)
            except:
                pass

    def create_task_embeds(self, tasks, user_id):
        """Create embeds for completed and pending tasks."""
        completed_tasks = [t for t in tasks if t.status == "done"]
        pending_tasks = [t for t in tasks if t.status == "pending"]
        
        completed_embeds = []
        pending_embeds = []
        
        # Create completed tasks embeds
        if completed_tasks:
            current_embed = discord.Embed(
                title="✅ Completed Tasks",
                color=discord.Color.green()
            )
            current_tasks = []
            current_length = 0
            
            for task in completed_tasks:
                task_str = f"{task.created_at.split('T')[1][:5]} [`{task.task_id}`] {task.description} ({task.completed_at.split('T')[1][:5] if task.completed_at else 'N/A'})\n"
                if task.remarks:
                    task_str += f"   📝 **Remark:** {task.remarks}\n"
                
                if current_length + len(task_str) > 1024:
                    if current_tasks:
                        current_embed.add_field(
                            name="Tasks",
                            value="\n".join(current_tasks),
                            inline=False
                        )
                        completed_embeds.append(current_embed)
                        current_embed = discord.Embed(
                            title="✅ Completed Tasks",
                            color=discord.Color.green()
                        )
                        current_tasks = []
                        current_length = 0
                
                current_tasks.append(task_str)
                current_length += len(task_str)
            
            if current_tasks:
                current_embed.add_field(
                    name="Tasks",
                    value="\n".join(current_tasks),
                    inline=False
                )
                completed_embeds.append(current_embed)
        
        # Create pending tasks embeds
        if pending_tasks:
            current_embed = discord.Embed(
                title="⏳ Pending Tasks",
                color=discord.Color.orange()
            )
            current_tasks = []
            current_length = 0
            
            for task in pending_tasks:
                task_str = f"{task.created_at.split('T')[1][:5]} [`{task.task_id}`] {task.description}\n"
                if task.remarks:
                    task_str += f"   📝 **Remark:** {task.remarks}\n"
                
                if current_length + len(task_str) > 1024:
                    if current_tasks:
                        current_embed.add_field(
                            name="Tasks",
                            value="\n".join(current_tasks),
                            inline=False
                        )
                        pending_embeds.append(current_embed)
                        current_embed = discord.Embed(
                            title="⏳ Pending Tasks",
                            color=discord.Color.orange()
                        )
                        current_tasks = []
                        current_length = 0
                
                current_tasks.append(task_str)
                current_length += len(task_str)
            
            if current_tasks:
                current_embed.add_field(
                    name="Tasks",
                    value="\n".join(current_tasks),
                    inline=False
                )
                pending_embeds.append(current_embed)
        
        # Add part numbers only if there are multiple embeds
        if len(completed_embeds) > 1:
            for i, embed in enumerate(completed_embeds, 1):
                embed.set_footer(text=f"Part {i}/{len(completed_embeds)}")
        
        if len(pending_embeds) > 1:
            for i, embed in enumerate(pending_embeds, 1):
                embed.set_footer(text=f"Part {i}/{len(pending_embeds)}")
        
        logger.info(f"[DEBUG] Created {len(completed_embeds)} completed embeds and {len(pending_embeds)} pending embeds")
        return completed_embeds, pending_embeds

    async def update_dsm_statistics(self, guild_id):
        """Update DSM statistics in the opening message."""
        try:
            config = await self.firebase_service.get_config(guild_id)
            if not config or 'latest_dsm_thread' not in config:
                return
            
            thread_id = config['latest_dsm_thread']
            stats_message_id = config.get('latest_dsm_stats_message')
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            thread = guild.get_thread(thread_id)
            if not thread:
                return
            
            # Get the statistics message
            stats_message = None
            if stats_message_id:
                try:
                    stats_message = await thread.fetch_message(stats_message_id)
                except:
                    pass
            
            if not stats_message:
                # Find the statistics message
                async for message in thread.history(limit=None):
                    if message.author.id == self.bot.user.id and message.embeds:
                        if "Daily Standup Meeting for" in message.embeds[0].title:
                            stats_message = message
                            break
            
            if not stats_message:
                return
            
            # Calculate statistics
            total_tasks = 0
            completed_tasks = 0
            participants = set()
            updated_participants = set(config.get('updated_participants', []))
            pending_participants = set()
            
            for user_id, tasks in self.user_tasks.items():
                if tasks and "tasks" in tasks:
                    user_tasks = tasks["tasks"]
                    total_tasks += len(user_tasks)
                    completed_tasks += len([t for t in user_tasks if t.status == "done"])
                    if user_tasks:
                        participants.add(user_id)
                        if user_id not in updated_participants:
                            pending_participants.add(user_id)
            
            # Update the statistics message
            embed = stats_message.embeds[0]
            date_str = config.get('dsm_date', datetime.datetime.now().strftime("%B %d, %Y"))
            
            # Update fields
            embed.set_field_at(0, name="Task Statistics", value=f"Total Tasks: {total_tasks}\nCompleted: {completed_tasks}\nPending: {total_tasks - completed_tasks}", inline=False)
            
            # Format participant lists
            updated_list = "\n".join([f"<@{uid}>" for uid in updated_participants]) or "None"
            pending_list = "\n".join([f"<@{uid}>" for uid in pending_participants]) or "None"
            
            embed.set_field_at(1, name="Participants", value=f"Total: {len(participants)}\nUpdated: {len(updated_participants)}\nPending: {len(pending_participants)}\n\n**Updated:**\n{updated_list}\n\n**Pending:**\n{pending_list}", inline=False)
            embed.set_field_at(2, name="Timeline", value=f"Start: {date_str}\nDeadline: {date_str}\nEnd: {date_str}", inline=False)
            
            await stats_message.edit(embed=embed)
            
            # Update config with new message ID if needed
            if stats_message.id != stats_message_id:
                config['latest_dsm_stats_message'] = stats_message.id
                await self.firebase_service.update_config(guild_id, config)
            
            logger.info(f"[DEBUG] Updated DSM statistics for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error updating DSM statistics: {str(e)}")

    async def send_initial_task_embeds(self, channel, user_id=None):
        """Send initial task embeds to the channel."""
        try:
            # Get the member
            member = channel.guild.get_member(user_id)
            if not member:
                logger.error(f"[DEBUG] Member {user_id} not found in guild")
                return
            
            # Get user data
            user_data = self.user_tasks.get(user_id)
            if not user_data or not user_data.get("tasks"):
                logger.info(f"[DEBUG] No tasks found for user {user_id}")
                return
            
            # Create task embeds
            completed_embeds, pending_embeds = await self.create_task_embeds(user_data["tasks"], user_id)
            
            # Get target channel (thread or channel)
            target_channel = channel
            if isinstance(channel, discord.TextChannel):
                # Try to find the current DSM thread
                current_thread = await self.get_current_dsm_thread(channel)
                if current_thread:
                    target_channel = current_thread
                    logger.info(f"[DEBUG] Using DSM thread: {current_thread.id}")
            
            # Send completed tasks embeds
            completed_messages = []
            for embed in completed_embeds:
                msg = await target_channel.send(embed=embed)
                completed_messages.append(msg)
                logger.info(f"[DEBUG] Sent completed tasks message: {msg.id}")
            
            # Send pending tasks embeds
            pending_messages = []
            for embed in pending_embeds:
                msg = await target_channel.send(embed=embed)
                pending_messages.append(msg)
                logger.info(f"[DEBUG] Sent pending tasks message: {msg.id}")
            
            # Get current config
            config = await self.firebase_service.get_config(channel.guild.id)
            
            # Initialize dsm_messages if it doesn't exist
            if 'dsm_messages' not in config:
                config['dsm_messages'] = {}
            
            # Update message IDs for this user
            config['dsm_messages'][str(user_id)] = {
                'completed_messages': [str(msg.id) for msg in completed_messages],
                'pending_messages': [str(msg.id) for msg in pending_messages],
                'last_updated': datetime.datetime.now().isoformat()
            }
            
            # Save updated config
            await self.firebase_service.update_config(channel.guild.id, config)
            logger.info(f"[DEBUG] Saved message IDs to config for user {user_id}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in send_initial_task_embeds: {str(e)}")
            raise

    async def create_dsm_session(self, guild_id: int, thread: discord.Thread, is_manual: bool) -> DSMSession:
        """Create a new DSM session."""
        # Get the last DSM session to count completed tasks
        last_session = await self.firebase_service.get_last_dsm_session(guild_id)
        
        # Count completed tasks since last DSM
        completed_tasks = 0
        if last_session:
            for user_id, user_data in self.user_tasks.items():
                for task in user_data["tasks"]:
                    if task.status == "done" and task.completed_at and task.completed_at > last_session.created_at:
                        completed_tasks += 1

        # Create new session
        session = DSMSession(
            guild_id=guild_id,
            thread_id=thread.id,
            is_manual=is_manual,
            completed_tasks=completed_tasks
        )
        
        # Save to Firebase
        await self.firebase_service.save_dsm_session(session)
        return session

    @tasks.loop(hours=24)
    async def daily_standup(self):
        """Create daily standup (thread or channel based on config)."""
        try:
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_config(guild.id)
                now = datetime.datetime.now()
                today = now.strftime('%Y-%m-%d')
                
                # Check if DSM should be skipped
                if today in config.get('skipped_dates', []):
                    logger.info(f"Skipping DSM for {today} as it's in the skipped dates list")
                    continue
                
                # Check if it's time for DSM
                if now.hour == config['standup_hour'] and now.minute == config['standup_minute']:
                    # Get the configured channel
                    channel_id = config.get('dsm_channel_id')
                    if not channel_id:
                        logger.warning(f"No DSM channel configured for guild {guild.id}")
                        continue
                        
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        logger.error(f"Configured DSM channel {channel_id} not found in guild {guild.id}")
                        continue

                    use_threads = config.get('use_threads', True)
                    end_time = now + datetime.timedelta(hours=1)
                    deadline = now + datetime.timedelta(hours=config.get('deadline_hours', 12))
                    members = [member for member in guild.members if not member.bot]
                    member_mentions = "\n".join([f"- {member.mention}" for member in members])
                    if use_threads:
                        # Thread mode (existing logic)
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
                        thread_name = f"DAILY STANDUP MEETING - {now.strftime('%Y-%m-%d')}"
                        thread = await initial_message.create_thread(
                            name=thread_name,
                            auto_archive_duration=config['thread_auto_archive_duration']
                        )
                        logger.info(f"Created standup thread: {thread_name}")
                        session = await self.create_dsm_session(guild.id, thread, False)
                        embed = discord.Embed(
                            title=f"📊 DSM Statistics - {now.strftime('%Y-%m-%d')}",
                            description=(
                                f"📈 **Task Statistics**\n"
                                f"✅ Completed: {session.completed_tasks}\n"
                                f"📝 New: {session.new_tasks}\n\n"
                                f"⏰ **Timeline**\n"
                                f"🕒 End Time: {end_time.strftime('%H:%M')}\n"
                                f"⚠️ Deadline: {deadline.strftime('%Y-%m-%d %H:%M')}\n\n"
                                f"👥 **Participants**\n"
                                f"{member_mentions}"
                            ),
                            color=discord.Color.blue()
                        )
                        embed.timestamp = now
                        embed.set_footer(text=f"Thread ID: {thread.id}")
                        await thread.send(embed=embed)
                        logger.info("Sent opening message to thread")
                        await self.send_initial_task_embeds(thread)
                        await asyncio.sleep(config.get('deadline_hours', 12) * 3600)
                        await self.check_deadline(thread, config)
                    else:
                        # Channel mode (no threads)
                        embed = discord.Embed(
                            title=f"📊 DSM Statistics - {now.strftime('%Y-%m-%d')}",
                            description=(
                                f"📈 **Task Statistics**\n"
                                f"✅ Completed: 0\n"
                                f"📝 New: 0\n\n"
                                f"⏰ **Timeline**\n"
                                f"🕒 End Time: {end_time.strftime('%H:%M')}\n"
                                f"⚠️ Deadline: {deadline.strftime('%Y-%m-%d %H:%M')}\n\n"
                                f"👥 **Participants**\n"
                                f"{member_mentions}"
                            ),
                            color=discord.Color.blue()
                        )
                        embed.timestamp = now
                        message = await channel.send(embed=embed)
                        logger.info("Sent DSM opening message in channel (no thread mode)")
                        # Create a dummy session object for compatibility
                        session = DSMSession(
                            guild_id=guild.id,
                            thread_id=message.id,  # Use message ID as a stand-in
                            is_manual=False,
                            completed_tasks=0
                        )
                        await self.firebase_service.save_dsm_session(session)
                        # Optionally, send initial task embeds in the channel
                        await self.send_initial_task_embeds(channel)
                        # No deadline check in channel mode (or implement if needed)
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
        logger.info(f"[COMMAND] /add used by {interaction.user.name} ({interaction.user.id}) in {interaction.guild.name} ({interaction.guild.id})")
        await self._add_task(interaction, task)

    async def _add_task(self, interaction: discord.Interaction, task_description: str):
        """Internal method to add a new task."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            logger.info(f"[DEBUG] Starting task addition for user {user_id} ({interaction.user.name})")
            
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = {"tasks": []}
                logger.info(f"[DEBUG] Created new task list for user {user_id}")
            
            # Generate a unique task ID
            task_id = self.get_available_task_id(self.user_tasks[user_id]["tasks"])
            logger.info(f"[DEBUG] Generated task ID: {task_id}")
            
            # Create new task with the generated ID
            new_task = Task(
                description=task_description,
                task_id=task_id,
                status="pending"
            )
            self.user_tasks[user_id]["tasks"].append(new_task)
            logger.info(f"[DEBUG] Added task to user's task list")
            
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
            logger.info(f"[DEBUG] Updated user data in Firebase")
            
            # Save tasks
            await self.firebase_service.save_tasks(self.user_tasks)
            logger.info(f"[DEBUG] Saved tasks to Firebase")
            
            # Update config to mark user as updated
            config = await self.firebase_service.get_config(interaction.guild_id)
            if config:
                updated_participants = set(config.get('updated_participants', []))
                updated_participants.add(user_id)
                config['updated_participants'] = list(updated_participants)
                await self.firebase_service.update_config(interaction.guild_id, config)
            
            # Find the current DSM thread using get_current_dsm_thread
            if isinstance(interaction.channel, discord.TextChannel):
                current_thread = await self.get_current_dsm_thread(interaction.channel)
                if current_thread:
                    logger.info(f"[DEBUG] Using DSM thread: {current_thread.id} ({current_thread.name})")
                    await self.update_task_message(current_thread, user_id)
                    # Update DSM statistics
                    await self.update_dsm_statistics(interaction.guild_id)
                else:
                    logger.info(f"[DEBUG] No DSM thread found, updating in channel {interaction.channel.id}")
                    await self.update_task_message(interaction.channel, user_id)
            else:
                await self.update_task_message(interaction.channel, user_id)
            
            logger.info(f"[DEBUG] Task addition completed for {interaction.user.name}")
            await interaction.followup.send(f"Task added with ID: `{task_id}`", ephemeral=True)
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in _add_task: {str(e)}")
            try:
                await interaction.followup.send("Failed to add task. Please try again.", ephemeral=True)
            except:
                pass

    @app_commands.command(name="done", description="Mark a task as done")
    async def mark_done(self, interaction: discord.Interaction, task_id: str):
        """Mark a task as done."""
        logger.info(f"[COMMAND] /done used by {interaction.user.name} ({interaction.user.id}) in {interaction.guild.name} ({interaction.guild.id}) for task {task_id}")
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
                
                # Update the task messages in the current DSM thread
                await self.update_task_message(interaction.channel, user_id)
                
                logger.info(f"[COMMAND] Task {task_id} marked as done for {interaction.user.display_name}")
                await interaction.followup.send(f"Task {task_id} marked as done!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"[COMMAND] Error in mark_done: {str(e)}")
            try:
                await interaction.followup.send("Failed to mark task as done. Please try again.", ephemeral=True)
            except:
                pass

    @app_commands.command(name="remark", description="Add a remark to a task")
    async def add_remark(self, interaction: discord.Interaction, task_id: str, remark: str):
        """Add a remark to a task."""
        logger.info(f"[COMMAND] /remark used by {interaction.user.name} ({interaction.user.id}) in {interaction.guild.name} ({interaction.guild.id}) for task {task_id}")
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
                logger.info(f"[COMMAND] Added remark to task {task_id} for {interaction.user.name}")
                await interaction.followup.send(f"Remark added to task {task_id}!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"[COMMAND] Error in add_remark: {str(e)}")
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
                       auto_archive: int = None,
                       use_threads: bool = None):
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
        
        if use_threads is not None:
            updates['use_threads'] = use_threads
        
        if updates:
            config = await self.firebase_service.update_config(interaction.guild_id, updates)
            logger.info(f"Updated config for guild {interaction.guild_id}: {updates}")
            await interaction.response.send_message("Configuration updated!", ephemeral=True)
        else:
            await interaction.response.send_message("No changes provided!", ephemeral=True)

    @app_commands.command(name="simulate_dsm", description="Manually trigger a DSM thread")
    @app_commands.default_permissions(administrator=True)
    async def simulate_dsm(self, interaction: discord.Interaction):
        """Manually trigger a DSM thread"""
        try:
            # Log command usage
            logger.info(f"Manual DSM triggered by {interaction.user} in {interaction.guild}")
            
            # Defer the response since this might take a while
            await interaction.response.defer(ephemeral=True)
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Check if there's an existing DSM thread
            current_thread = None
            if config.get('latest_dsm_thread'):
                try:
                    # Handle both old and new thread ID formats
                    thread_id = config['latest_dsm_thread']
                    if isinstance(thread_id, dict):
                        thread_id = thread_id.get('thread_id')
                    
                    if thread_id:
                        # Get the thread using the guild's fetch_channel method
                        current_thread = await interaction.guild.fetch_channel(int(thread_id))
                        if current_thread and isinstance(current_thread, discord.Thread):
                            # Archive the current thread
                            await current_thread.edit(archived=True)
                            logger.info(f"Archived previous DSM thread: {current_thread.name}")
                except discord.NotFound:
                    logger.info("Previous thread not found, proceeding with new thread creation")
                except Exception as e:
                    logger.error(f"Error handling previous thread: {str(e)}")
            
            # Create initial message
            initial_message = await interaction.channel.send(
                f"📋 **Daily Standup Meeting**\n"
                f"React with ✅ when you've updated your tasks!"
            )
            
            # Create new thread
            thread = await initial_message.create_thread(
                name=f"Daily Standup Meeting for {datetime.datetime.now().strftime('%B %d, %Y')}",
                auto_archive_duration=10080  # 7 days
            )
            
            # Get all tasks for today
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            tasks = await self.firebase_service.get_tasks_for_date(interaction.guild_id, today)
            
            # Calculate statistics
            total_tasks = len(tasks)
            completed_tasks = sum(1 for task in tasks if task.get('completed', False))
            participants = len(set(task.get('user_id') for task in tasks))
            
            # Send opening message with statistics
            opening_message = await thread.send(
                f"📊 **DSM Statistics**\n"
                f"Total Tasks: {total_tasks}\n"
                f"Completed Tasks: {completed_tasks}\n"
                f"Participants: {participants}\n\n"
                f"Please update your tasks using the commands below!"
            )
            
            # Update config with new thread info and clear old message IDs
            config['latest_dsm_thread'] = {
                'thread_id': str(thread.id),
                'created_at': datetime.datetime.now().isoformat(),
                'date': today
            }
            config['dsm_messages'] = {}  # Clear old message IDs
            config['updated_participants'] = []  # Clear old participant tracking
            config['pending_participants'] = []  # Clear old participant tracking
            await self.firebase_service.update_config(interaction.guild_id, config)
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ New DSM thread created: {thread.mention}\n"
                f"The previous DSM thread has been archived.",
                ephemeral=True
            )
            
            logger.info(f"Manual DSM thread created: {thread.name} (ID: {thread.id})")
            
        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            await interaction.followup.send(
                "❌ Failed to create DSM thread. Please try again.",
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

    async def get_current_dsm_thread(self, channel: discord.TextChannel) -> Optional[discord.Thread]:
        """Get the current DSM thread for today."""
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        thread_name = f"DAILY STANDUP MEETING - {today}"
        logger.info(f"[DEBUG] Looking for thread: {thread_name}")
        
        # First check the config for the latest thread
        try:
            config = await self.firebase_service.get_config(channel.guild.id)
            latest_thread_info = config.get('latest_dsm_thread', {})
            
            if latest_thread_info and latest_thread_info.get('date') == today:
                thread_id = int(latest_thread_info['thread_id'])
                try:
                    thread = await channel.guild.fetch_channel(thread_id)
                    if isinstance(thread, discord.Thread):
                        logger.info(f"[DEBUG] Found latest thread from config: {thread.id} ({thread.name})")
                        return thread
                except Exception as e:
                    logger.error(f"[DEBUG] Error fetching thread from config: {str(e)}")
        except Exception as e:
            logger.error(f"[DEBUG] Error checking config for latest thread: {str(e)}")
        
        # If no thread found in config or error occurred, fall back to searching
        latest_thread = None
        latest_time = None
        
        # Check active threads first
        for thread in channel.threads:
            logger.info(f"[DEBUG] Checking active thread: {thread.name} ({thread.id})")
            if thread.name == thread_name:
                # Get thread creation time from the first message
                try:
                    async for message in thread.history(limit=1, oldest_first=True):
                        # Convert to naive datetime for comparison
                        msg_time = message.created_at.replace(tzinfo=None)
                        if latest_time is None or msg_time > latest_time:
                            latest_thread = thread
                            latest_time = msg_time
                            logger.info(f"[DEBUG] Found newer active thread: {thread.id} created at {msg_time}")
                except Exception as e:
                    logger.error(f"[DEBUG] Error getting thread history: {str(e)}")
        
        # Then check archived threads
        try:
            async for thread in channel.archived_threads():
                logger.info(f"[DEBUG] Checking archived thread: {thread.name} ({thread.id})")
                if thread.name == thread_name:
                    # Get thread creation time from the first message
                    try:
                        async for message in thread.history(limit=1, oldest_first=True):
                            # Convert to naive datetime for comparison
                            msg_time = message.created_at.replace(tzinfo=None)
                            if latest_time is None or msg_time > latest_time:
                                latest_thread = thread
                                latest_time = msg_time
                                logger.info(f"[DEBUG] Found newer archived thread: {thread.id} created at {msg_time}")
                    except Exception as e:
                        logger.error(f"[DEBUG] Error getting archived thread history: {str(e)}")
        except Exception as e:
            logger.error(f"[DEBUG] Error checking archived threads: {str(e)}")
        
        if latest_thread:
            logger.info(f"[DEBUG] Using most recent DSM thread: {latest_thread.id} ({latest_thread.name}) created at {latest_time}")
            # Update config with the latest thread info
            await self.firebase_service.update_config(channel.guild.id, {
                'latest_dsm_thread': {
                    'thread_id': str(latest_thread.id),
                    'created_at': latest_time.isoformat(),
                    'date': today
                }
            })
            return latest_thread
        
        logger.info(f"[DEBUG] No DSM thread found for today")
        return None

    async def update_task_message(self, channel: discord.TextChannel, user_id: int = None):
        """Update task messages in the channel."""
        try:
            # Get the member
            member = channel.guild.get_member(user_id)
            if not member:
                logger.error(f"[DEBUG] Member {user_id} not found in guild")
                return
            
            # Get user data
            user_data = self.user_tasks.get(user_id)
            if not user_data or not user_data.get("tasks"):
                logger.info(f"[DEBUG] No tasks found for user {user_id}")
                return
            
            # Create task embeds
            completed_embeds, pending_embeds = await self.create_task_embeds(user_data["tasks"], user_id)
            
            # Get target channel (thread or channel)
            target_channel = channel
            if isinstance(channel, discord.TextChannel):
                # Try to find the current DSM thread
                current_thread = await self.get_current_dsm_thread(channel)
                if current_thread:
                    target_channel = current_thread
                    logger.info(f"[DEBUG] Using DSM thread: {current_thread.id}")
            
            # Get existing messages
            messages = []
            try:
                async for msg in target_channel.history(limit=100):
                    if msg.author == self.bot.user and msg.embeds:
                        messages.append(msg)
                        logger.info(f"[DEBUG] Found existing message {msg.id} in thread {current_thread.id}")
            except Exception as e:
                logger.error(f"[DEBUG] Error fetching messages: {str(e)}")
            
            # Get latest message IDs from config
            latest_messages = await self.firebase_service.get_latest_dsm_message(channel.guild.id, str(user_id))
            if latest_messages:
                logger.info(f"[DEBUG] Found latest message IDs in config: {latest_messages}")
                # Filter messages to only include the latest ones
                messages = [msg for msg in messages if str(msg.id) in latest_messages.get('completed_messages', []) + latest_messages.get('pending_messages', [])]
            
            # Separate messages into completed and pending
            completed_messages = []
            pending_messages = []
            
            for msg in messages:
                if msg.embeds and msg.embeds[0].title == f"{member.display_name}'s Completed Tasks":
                    completed_messages.append(msg)
                    logger.info(f"[DEBUG] Found completed message {msg.id}")
                elif msg.embeds and msg.embeds[0].title == f"{member.display_name}'s Pending Tasks":
                    pending_messages.append(msg)
                    logger.info(f"[DEBUG] Found pending message {msg.id}")
            
            # Update or send completed messages
            new_completed_messages = []
            for i, embed in enumerate(completed_embeds):
                if i < len(completed_messages):
                    await completed_messages[i].edit(embed=embed)
                    new_completed_messages.append(completed_messages[i])
                    logger.info(f"[DEBUG] Updated completed message {completed_messages[i].id}")
                else:
                    msg = await target_channel.send(embed=embed)
                    new_completed_messages.append(msg)
                    logger.info(f"[DEBUG] Sent new completed message: {msg.id}")
            
            # Update or send pending messages
            new_pending_messages = []
            for i, embed in enumerate(pending_embeds):
                if i < len(pending_messages):
                    await pending_messages[i].edit(embed=embed)
                    new_pending_messages.append(pending_messages[i])
                    logger.info(f"[DEBUG] Updated pending message {pending_messages[i].id}")
                else:
                    msg = await target_channel.send(embed=embed)
                    new_pending_messages.append(msg)
                    logger.info(f"[DEBUG] Sent new pending message: {msg.id}")
            
            # Save new message IDs to config
            await self.firebase_service.save_dsm_message(channel.guild.id, str(user_id), {
                'completed_messages': [str(msg.id) for msg in new_completed_messages],
                'pending_messages': [str(msg.id) for msg in new_pending_messages]
            })
            logger.info(f"[DEBUG] Saved new message IDs to config for user {user_id}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in update_task_message: {str(e)}")
            raise

    async def mark_done_callback(self, interaction: discord.Interaction, task_id: str):
        """Callback for marking a task as done."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find task by ID
            task = next((t for t in self.user_tasks[user_id]["tasks"] if t.task_id == task_id), None)
            
            if task:
                # Mark the task as done and add completion timestamp
                task.status = "done"
                task.completed_at = datetime.datetime.now().isoformat()
                
                # Save to Firebase
                await self.firebase_service.save_tasks(self.user_tasks)
                
                # Update the task message in the current DSM thread
                await self.update_task_message(interaction.channel, user_id)
                
                logger.info(f"[COMMAND] Task {task_id} marked as done for {interaction.user.display_name}")
                await interaction.followup.send(f"Task {task_id} marked as done!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"[COMMAND] Error in mark_done_callback: {str(e)}")
            try:
                await interaction.followup.send("Failed to mark task as done. Please try again.", ephemeral=True)
            except:
                pass

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            
            if user_id not in self.user_tasks or not self.user_tasks[user_id]["tasks"]:
                await interaction.followup.send("You have no tasks!", ephemeral=True)
                return
            
            # Find task by ID
            task = next((t for t in self.user_tasks[user_id]["tasks"] if t.task_id == self.task_id.lower()), None)
            
            if task:
                task.remarks = self.remark.value
                await self.firebase_service.save_tasks(self.user_tasks)
                await self.update_task_message(interaction.channel, user_id)
                logger.info(f"[COMMAND] Added remark to task {self.task_id} for {interaction.user.name}")
                await interaction.followup.send(f"Remark added to task {self.task_id}!", ephemeral=True)
            else:
                await interaction.followup.send(f"Task with ID {self.task_id} not found!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"[COMMAND] Error in add_remark: {str(e)}")
            try:
                await interaction.followup.send("Failed to add remark. Please try again.", ephemeral=True)
            except:
                pass

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
        """Generate an aggregate report of all tasks."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
            # Get all tasks from Firebase
            tasks = await self.firebase_service.load_tasks()
            total_tasks = 0
            completed_tasks = 0
            pending_tasks = 0
            users_with_tasks = 0
            completed_in_window = 0
            now = datetime.datetime.now()
            for user_id, user_data in tasks.items():
                user_tasks = user_data.get("tasks", [])
                if user_tasks:
                    users_with_tasks += 1
                for task in user_tasks:
                    total_tasks += 1
                    if task.status == "done":
                        completed_tasks += 1
                        # Count if completed in window
                        if hasattr(task, "completed_at"):
                            try:
                                completed_at = datetime.datetime.fromisoformat(task.completed_at)
                                if (now - completed_at).days <= days:
                                    completed_in_window += 1
                            except Exception:
                                pass
                    else:
                        pending_tasks += 1
            avg_tasks_per_user = total_tasks / users_with_tasks if users_with_tasks else 0
            # Create report embed
            embed = discord.Embed(
                title="Task Statistics Report",
                description=f"Aggregate statistics for the last {days} days:",
                color=discord.Color.green()
            )
            embed.add_field(name="Total Tasks", value=str(total_tasks), inline=True)
            embed.add_field(name="Completed Tasks", value=str(completed_tasks), inline=True)
            embed.add_field(name="Pending Tasks", value=str(pending_tasks), inline=True)
            embed.add_field(name="Users with Tasks", value=str(users_with_tasks), inline=True)
            embed.add_field(name="Avg Tasks per User", value=f"{avg_tasks_per_user:.2f}", inline=True)
            embed.add_field(name=f"Tasks Completed in Last {days} Days", value=str(completed_in_window), inline=True)
            embed.timestamp = now
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Generated aggregate task report for {interaction.user.name}")
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

    @app_commands.command(name="dsm", description="Open the DSM task management interface")
    async def dsm(self, interaction: discord.Interaction):
        """Open the DSM task management interface."""
        logger.info(f"[COMMAND] /dsm used by {interaction.user.name} ({interaction.user.id}) in {interaction.guild.name} ({interaction.guild.id})")
        try:
            # Defer the response since this might take a moment
            await interaction.response.defer(ephemeral=True)
            
            # Create the view
            view = DSMView(self)
            
            # Get user's display name (nickname or username)
            display_name = interaction.user.display_name
            
            # Create the embed
            embed = discord.Embed(
                title=f"DSM Task Management - {display_name}",
                description=(
                    f"Welcome to your DSM task management interface, {display_name}! 👋\n\n"
                    "Use the buttons below to:\n"
                    "➕ Add a new task\n"
                    "✅ Mark a task as done\n"
                    "📝 Add a remark to a task\n"
                    "🔄 Refresh your task view\n\n"
                    "Your tasks will be displayed below."
                ),
                color=discord.Color.blue()
            )
            
            # Add timestamp
            embed.timestamp = datetime.datetime.now()
            
            # Send the initial message
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            # Store the message for future edits
            self.last_dsm_message = message
            
            # Find the current DSM thread
            current_thread = None
            if isinstance(interaction.channel, discord.TextChannel):
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                # Check archived threads
                async for thread in interaction.channel.archived_threads():
                    if thread.name == f"DAILY STANDUP MEETING - {today}":
                        current_thread = thread
                        break
                # Check active threads
                if not current_thread:
                    for thread in interaction.channel.threads:
                        if thread.name == f"DAILY STANDUP MEETING - {today}":
                            current_thread = thread
                            break
            
            # Update the task message in the appropriate channel
            if current_thread:
                await self.update_task_message(current_thread, interaction.user.id)
            else:
                await self.update_task_message(interaction.channel, interaction.user.id)
            
        except Exception as e:
            logger.error(f"[COMMAND] Error in dsm command: {str(e)}")
            try:
                await interaction.followup.send(
                    "Failed to open the DSM interface. Please try again.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="dsm_history", description="View DSM history")
    async def dsm_history(self, interaction: discord.Interaction, limit: int = 5):
        """View DSM history."""
        try:
            # Get recent DSM sessions
            sessions = await self.firebase_service.get_dsm_sessions(interaction.guild_id, limit)
            
            if not sessions:
                await interaction.response.send_message("No DSM history found.", ephemeral=True)
                return
            
            # Create embed
            embed = discord.Embed(
                title="DSM History",
                description=f"Last {len(sessions)} DSM sessions:",
                color=discord.Color.blue()
            )
            
            for session in sessions:
                created_at = datetime.datetime.fromisoformat(session.created_at)
                embed.add_field(
                    name=f"{created_at.strftime('%Y-%m-%d %H:%M')} ({'Manual' if session.is_manual else 'Automatic'})",
                    value=(
                        f"Thread ID: {session.thread_id}\n"
                        f"Tasks Completed: {session.completed_tasks}\n"
                        f"New Tasks Added: {session.new_tasks}\n"
                        f"Participants: {len(session.participants)}"
                    ),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in dsm_history: {str(e)}")
            await interaction.response.send_message(
                "Failed to fetch DSM history. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="set_channel", description="Set the channel where DSMs will be posted")
    @app_commands.default_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel where DSMs will be posted."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Update the config with the new channel ID
            await self.firebase_service.update_config(interaction.guild_id, {'dsm_channel_id': channel.id})
            
            # Create confirmation embed
            embed = discord.Embed(
                title="DSM Channel Updated",
                description=f"DSMs will now be posted in {channel.mention}",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Updated DSM channel to {channel.name} ({channel.id})")
            
        except Exception as e:
            logger.error(f"Error setting DSM channel: {str(e)}")
            await interaction.response.send_message(
                f"Failed to set DSM channel: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="delete_task", description="Delete a task or all tasks for a user")
    @app_commands.default_permissions(administrator=True)
    async def delete_task(self, interaction: discord.Interaction, 
                         user: discord.Member = None,
                         task_id: str = None,
                         delete_all: bool = False):
        """Delete a task or all tasks for a user."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Defer the response since this might take a moment
            await interaction.response.defer(ephemeral=True)
            
            if not user and not task_id:
                await interaction.followup.send(
                    "Please provide either a user or a task ID to delete tasks.",
                    ephemeral=True
                )
                return
            
            tasks = await self.firebase_service.load_tasks()
            deleted_count = 0
            
            if task_id:
                # Delete specific task
                task_id = task_id.lower()
                for user_id, user_data in tasks.items():
                    user_tasks = user_data.get("tasks", [])
                    for task in user_tasks[:]:  # Create a copy to safely modify during iteration
                        if task.task_id == task_id:
                            user_tasks.remove(task)
                            deleted_count += 1
                            break
            elif user and delete_all:
                # Delete all tasks for a specific user
                user_id = str(user.id)
                if user_id in tasks:
                    user_tasks = tasks[user_id].get("tasks", [])
                    deleted_count = len(user_tasks)
                    tasks[user_id]["tasks"] = []
            else:
                await interaction.followup.send(
                    "Invalid combination of parameters. Use either task_id or user with delete_all=True.",
                    ephemeral=True
                )
                return
            
            if deleted_count > 0:
                # Save updated tasks
                await self.firebase_service.save_tasks(tasks)
                
                # Update task messages
                if task_id:
                    # Update all users' messages since we don't know which user had the task
                    for user_id in tasks:
                        await self.update_task_message(interaction.channel, int(user_id))
                else:
                    # Update only the specified user's message
                    await self.update_task_message(interaction.channel, user.id)
                
                # Create confirmation embed
                embed = discord.Embed(
                    title="Tasks Deleted",
                    description=(
                        f"Successfully deleted {deleted_count} task(s).\n"
                        f"{'All tasks' if delete_all else f'Task {task_id}'} "
                        f"{f'for {user.mention}' if user else ''} have been removed."
                    ),
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Deleted {deleted_count} task(s) by {interaction.user.name}")
            else:
                await interaction.followup.send(
                    "No tasks were found to delete.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error deleting tasks: {str(e)}")
            await interaction.followup.send(
                f"Failed to delete tasks: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="sync", description="Sync slash commands with Discord")
    @app_commands.default_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        """Sync slash commands with Discord."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
            return
        
        try:
            # Defer the response since syncing might take a moment
            await interaction.response.defer(ephemeral=True)
            
            # Sync commands
            synced = await interaction.client.tree.sync()
            
            # Create confirmation embed
            embed = discord.Embed(
                title="Commands Synced",
                description=f"Successfully synced {len(synced)} command(s).",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Synced {len(synced)} commands by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error syncing commands: {str(e)}")
            await interaction.followup.send(
                f"Failed to sync commands: {str(e)}",
                ephemeral=True
            )

    async def verify_message_ids(self, guild_id: int, channel: discord.TextChannel):
        """Verify and update message IDs in the config."""
        try:
            # Get current config
            config = await self.firebase_service.get_config(guild_id)
            if 'dsm_messages' not in config:
                return
            
            # Get the current DSM thread
            current_thread = await self.get_current_dsm_thread(channel)
            if not current_thread:
                logger.info(f"[DEBUG] No DSM thread found for verification")
                return
            
            logger.info(f"[DEBUG] Verifying messages in thread {current_thread.id} ({current_thread.name})")
            
            # For each user with stored message IDs
            for user_id, message_data in config['dsm_messages'].items():
                try:
                    # Get the member
                    member = channel.guild.get_member(int(user_id))
                    if not member:
                        logger.info(f"[DEBUG] Member {user_id} not found in guild")
                        continue
                    
                    # Get user data
                    user_data = self.user_tasks.get(int(user_id))
                    if not user_data or not user_data.get("tasks"):
                        logger.info(f"[DEBUG] No tasks found for user {user_id}")
                        continue
                    
                    # Create new task embeds
                    completed_embeds, pending_embeds = await self.create_task_embeds(user_data["tasks"], user_id)
                    
                    # Get existing messages
                    existing_messages = []
                    try:
                        async for msg in current_thread.history(limit=100):
                            if msg.author == self.bot.user and msg.embeds:
                                existing_messages.append(msg)
                                logger.info(f"[DEBUG] Found existing message {msg.id} in thread {current_thread.id}")
                    except Exception as e:
                        logger.error(f"[DEBUG] Error fetching messages: {str(e)}")
                    
                    # Filter messages to only include the latest ones
                    latest_messages = message_data
                    if latest_messages:
                        existing_messages = [msg for msg in existing_messages if str(msg.id) in latest_messages.get('completed_messages', []) + latest_messages.get('pending_messages', [])]
                        logger.info(f"[DEBUG] Filtered to {len(existing_messages)} latest messages for user {user_id}")
                    
                    # Separate messages into completed and pending
                    completed_messages = []
                    pending_messages = []
                    
                    for msg in existing_messages:
                        if msg.embeds and msg.embeds[0].title == f"{member.display_name}'s Completed Tasks":
                            completed_messages.append(msg)
                            logger.info(f"[DEBUG] Found completed message {msg.id}")
                        elif msg.embeds and msg.embeds[0].title == f"{member.display_name}'s Pending Tasks":
                            pending_messages.append(msg)
                            logger.info(f"[DEBUG] Found pending message {msg.id}")
                    
                    # Update or send completed messages
                    new_completed_messages = []
                    for i, embed in enumerate(completed_embeds):
                        if i < len(completed_messages):
                            await completed_messages[i].edit(embed=embed)
                            new_completed_messages.append(completed_messages[i])
                            logger.info(f"[DEBUG] Updated completed message {completed_messages[i].id}")
                        else:
                            msg = await current_thread.send(embed=embed)
                            new_completed_messages.append(msg)
                            logger.info(f"[DEBUG] Sent new completed message {msg.id}")
                    
                    # Update or send pending messages
                    new_pending_messages = []
                    for i, embed in enumerate(pending_embeds):
                        if i < len(pending_messages):
                            await pending_messages[i].edit(embed=embed)
                            new_pending_messages.append(pending_messages[i])
                            logger.info(f"[DEBUG] Updated pending message {pending_messages[i].id}")
                        else:
                            msg = await current_thread.send(embed=embed)
                            new_pending_messages.append(msg)
                            logger.info(f"[DEBUG] Sent new pending message {msg.id}")
                    
                    # Update message IDs in config
                    config['dsm_messages'][user_id] = {
                        'completed_messages': [str(msg.id) for msg in new_completed_messages],
                        'pending_messages': [str(msg.id) for msg in new_pending_messages],
                        'last_updated': datetime.datetime.now().isoformat()
                    }
                    logger.info(f"[DEBUG] Updated message IDs for user {user_id} in thread {current_thread.id}")
                    
                except Exception as e:
                    logger.error(f"[DEBUG] Error verifying messages for user {user_id}: {str(e)}")
                    continue
            
            # Save updated config
            await self.firebase_service.update_config(guild_id, config)
            logger.info(f"[DEBUG] Verified and updated message IDs for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in verify_message_ids: {str(e)}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Load tasks and DSM messages when bot is ready."""
        try:
            # Load tasks
            self.user_tasks = await self.firebase_service.load_tasks()
            logger.info("Tasks loaded from Firebase")
            
            # Load DSM messages from config for each guild
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_config(guild.id)
                if 'dsm_messages' in config:
                    self.dsm_messages[guild.id] = config['dsm_messages']
                    logger.info(f"Loaded DSM messages for guild {guild.id}")
                
                # Verify message IDs for each guild
                channel_id = config.get('dsm_channel_id')
                if channel_id:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        await self.verify_message_ids(guild.id, channel)
            
            logger.info("DSM messages loaded from config")
            
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")

    @app_commands.command(name="simulate_dsm", description="Manually trigger a DSM thread")
    @app_commands.default_permissions(administrator=True)
    async def simulate_dsm(self, interaction: discord.Interaction):
        """Manually trigger a DSM thread"""
        try:
            # Log command usage
            logger.info(f"Manual DSM triggered by {interaction.user} in {interaction.guild}")
            
            # Defer the response since this might take a while
            await interaction.response.defer(ephemeral=True)
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Check if there's an existing DSM thread
            current_thread = None
            if config.get('latest_dsm_thread'):
                try:
                    # Handle both old and new thread ID formats
                    thread_id = config['latest_dsm_thread']
                    if isinstance(thread_id, dict):
                        thread_id = thread_id.get('thread_id')
                    
                    if thread_id:
                        # Get the thread using the guild's fetch_channel method
                        current_thread = await interaction.guild.fetch_channel(int(thread_id))
                        if current_thread and isinstance(current_thread, discord.Thread):
                            # Archive the current thread
                            await current_thread.edit(archived=True)
                            logger.info(f"Archived previous DSM thread: {current_thread.name}")
                except discord.NotFound:
                    logger.info("Previous thread not found, proceeding with new thread creation")
                except Exception as e:
                    logger.error(f"Error handling previous thread: {str(e)}")
            
            # Create initial message
            initial_message = await interaction.channel.send(
                f"📋 **Daily Standup Meeting**\n"
                f"React with ✅ when you've updated your tasks!"
            )
            
            # Create new thread
            thread = await initial_message.create_thread(
                name=f"Daily Standup Meeting for {datetime.datetime.now().strftime('%B %d, %Y')}",
                auto_archive_duration=10080  # 7 days
            )
            
            # Get all tasks for today
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            tasks = await self.firebase_service.get_tasks_for_date(interaction.guild_id, today)
            
            # Calculate statistics
            total_tasks = len(tasks)
            completed_tasks = sum(1 for task in tasks if task.get('completed', False))
            participants = len(set(task.get('user_id') for task in tasks))
            
            # Send opening message with statistics
            opening_message = await thread.send(
                f"📊 **DSM Statistics**\n"
                f"Total Tasks: {total_tasks}\n"
                f"Completed Tasks: {completed_tasks}\n"
                f"Participants: {participants}\n\n"
                f"Please update your tasks using the commands below!"
            )
            
            # Update config with new thread info and clear old message IDs
            config['latest_dsm_thread'] = {
                'thread_id': str(thread.id),
                'created_at': datetime.datetime.now().isoformat(),
                'date': today
            }
            config['dsm_messages'] = {}  # Clear old message IDs
            config['updated_participants'] = []  # Clear old participant tracking
            config['pending_participants'] = []  # Clear old participant tracking
            await self.firebase_service.update_config(interaction.guild_id, config)
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ New DSM thread created: {thread.mention}\n"
                f"The previous DSM thread has been archived.",
                ephemeral=True
            )
            
            logger.info(f"Manual DSM thread created: {thread.name} (ID: {thread.id})")
            
        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            await interaction.followup.send(
                "❌ Failed to create DSM thread. Please try again.",
                ephemeral=True
            )

    async def create_dsm_thread(self, channel, guild_id):
        """Create a new DSM thread."""
        try:
            # Get current date in full format
            current_date = datetime.datetime.now()
            date_str = current_date.strftime("%B %d, %Y")
            
            # Create initial message
            initial_message = f"Daily Standup Meeting for {date_str}\nReact with ✅ when you've updated your tasks."
            
            # Create thread with full date format
            thread = await channel.create_thread(
                name=f"Daily Standup Meeting for {date_str}",
                auto_archive_duration=1440
            )
            
            # Create statistics embed
            stats_embed = discord.Embed(
                title=f"Daily Standup Meeting for {date_str}",
                color=discord.Color.blue()
            )
            
            # Add initial statistics
            stats_embed.add_field(
                name="Task Statistics",
                value="Total Tasks: 0\nCompleted: 0\nPending: 0",
                inline=False
            )
            stats_embed.add_field(
                name="Participants",
                value="Total: 0\nUpdated: 0\nPending: 0",
                inline=False
            )
            stats_embed.add_field(
                name="Timeline",
                value=f"Start: {date_str}\nDeadline: {date_str}\nEnd: {date_str}",
                inline=False
            )
            
            # Send statistics message
            stats_message = await thread.send(embed=stats_embed)
            
            # Update config with new thread and message IDs
            config = await self.firebase_service.get_config(guild_id)
            if not config:
                config = {}
            
            config.update({
                'latest_dsm_thread': thread.id,
                'latest_dsm_stats_message': stats_message.id,
                'dsm_date': date_str,
                'updated_participants': [],
                'pending_participants': [],
                'dsm_messages': {}
            })
            
            await self.firebase_service.update_config(guild_id, config)
            logger.info(f"[DEBUG] Created new DSM thread: {thread.id} with stats message: {stats_message.id}")
            
            return thread
            
        except Exception as e:
            logger.error(f"[DEBUG] Error creating DSM thread: {str(e)}")
            raise

# Move setup function outside of the class, at module level
async def setup(bot: commands.Bot):
    """Set up the DSM cog."""
    firebase_service = FirebaseService('firebase-credentials.json')
    await bot.add_cog(DSM(bot, firebase_service))