"""Daily Standup Meeting cog."""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import re
from typing import Dict, Any, Optional, List
from services.firebase_service import FirebaseService
from utils.logger import get_logger
from config.default_config import DEFAULT_CONFIG
import pytz
import logging

logger = logging.getLogger(__name__)
logging.getLogger(__name__).info('dsm.py module imported')

class DSM(commands.Cog):
    """Daily Standup Meeting cog."""
    
    def __init__(self, bot: commands.Bot, firebase_service: FirebaseService):
        self.bot = bot
        self.firebase_service = firebase_service
        self.auto_dsm_task.start()
        self.dsm_reminder_task.start()
        logger.info("DSM cog initialized")

    def extract_tasks_from_message(self, content: str) -> List[str]:
        logger.info(f"[extract_tasks_from_message] Raw content: {repr(content)}")
        # Expanded indicators: 'todo', 'to do', 'to-do', 'tasks', 'task list'
        task_indicators = ['to do', 'to-do', 'todo', 'tasks', 'task list']
        lines = content.splitlines()
        tasks = []
        capture = False
        for line in lines:
            logger.info(f"[extract_tasks_from_message] Line: {repr(line)} | Capture: {capture}")
            if any(indicator in line.lower().replace(':', '').strip() for indicator in task_indicators):
                logger.info(f"[extract_tasks_from_message] Found indicator in line: {repr(line)}")
                capture = True
                continue
            if capture:
                if not line.strip():  # Stop at empty line
                    logger.info(f"[extract_tasks_from_message] Stopping at empty line after indicator.")
                    break
                # Remove bullet points/numbering
                line_clean = re.sub(r'^[-•*]\s*', '', line)
                line_clean = re.sub(r'^\d+[\.\)]\s*', '', line_clean)
                if line_clean.strip() and line_clean.strip() != ':':
                    logger.info(f"[extract_tasks_from_message] Adding task: {repr(line_clean.strip())}")
                    tasks.append(line_clean.strip())
        logger.info(f"[extract_tasks_from_message] Extracted tasks: {tasks}")
        return tasks

    async def get_user_tasks(self, channel: discord.TextChannel, user: discord.Member) -> List[str]:
        """Get tasks for a user from their messages."""
        tasks = []
        last_dsm_time = None
        
        # Get the last DSM time from config
        config = await self.firebase_service.get_config(channel.guild.id)
        if config and 'last_dsm_time' in config:
            last_dsm_time = datetime.datetime.fromisoformat(config['last_dsm_time'])
        
        # If no last DSM time, use 24 hours ago
        if not last_dsm_time:
            last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)
        
        # Get messages after last DSM
        async for message in channel.history(after=last_dsm_time, limit=None):
            if message.author.id == user.id:
                message_tasks = self.extract_tasks_from_message(message.content)
                tasks.extend(message_tasks)
        
        return list(set(tasks))  # Remove duplicates

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        logger.info(f"[on_message] Received message from {message.author} in channel {getattr(message.channel, 'name', None)}: {repr(message.content)}")
        if message.author.bot or not message.guild:
            logger.info("[on_message] Ignored bot or non-guild message.")
            return
        config = await self.firebase_service.get_config(message.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id and message.channel.id != dsm_channel_id:
            logger.info(f"[on_message] Ignored message not in DSM channel (expected {dsm_channel_id}).")
            return
        # Only update the TODO TASKS for Today embed
        await self.update_todo_tasks_for_today(message.guild, message.channel, message)
        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        logger.info(f"[on_message_edit] Message edited by {after.author} in channel {getattr(after.channel, 'name', None)}: {repr(after.content)}")
        if after.author.bot or not after.guild:
            logger.info("[on_message_edit] Ignored bot or non-guild message.")
            return
        config = await self.firebase_service.get_config(after.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id and after.channel.id != dsm_channel_id:
            logger.info(f"[on_message_edit] Ignored message not in DSM channel (expected {dsm_channel_id}).")
            return
        last_dsm_time = config.get('last_dsm_time')
        if last_dsm_time:
            last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
        else:
            last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)
        if after.created_at < last_dsm_time:
            logger.info(f"[on_message_edit] Ignored edit for message before current DSM window.")
            return
        # Only update the TODO TASKS for Today embed
        await self.update_todo_tasks_for_today(after.guild, after.channel, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        logger.info(f"[on_message_delete] Message deleted by {message.author if message.author else 'Unknown'} in channel {getattr(message.channel, 'name', None)}: {repr(message.content) if hasattr(message, 'content') else 'No content'}")
        if not message.guild or message.author is None or message.author.bot:
            return
        config = await self.firebase_service.get_config(message.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id and message.channel.id != dsm_channel_id:
            return
        # Only update the TODO TASKS for Today embed
        await self.update_todo_tasks_for_today(message.guild, message.channel, message, deleted=True)

    async def update_todo_tasks_for_today(self, guild, channel, message, deleted=False):
        config = await self.firebase_service.get_config(guild.id)
        last_dsm_time = config.get('last_dsm_time')
        if last_dsm_time:
            last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
        else:
            last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)
        # Use a mapping: {user_id: [tasks]} for today
        todo_message_map = config.get('todo_message_map', {})
        user_id = str(message.author.id)
        message_id = str(message.id)
        if deleted:
            # Remove tasks for this message
            if user_id in todo_message_map and message_id in todo_message_map[user_id]:
                del todo_message_map[user_id][message_id]
                if not todo_message_map[user_id]:
                    del todo_message_map[user_id]
        else:
            tasks = self.extract_tasks_from_message(message.content)
            if tasks:
                if user_id not in todo_message_map:
                    todo_message_map[user_id] = {}
                todo_message_map[user_id][message_id] = tasks
            else:
                # If the message was edited to remove tasks
                if user_id in todo_message_map and message_id in todo_message_map[user_id]:
                    del todo_message_map[user_id][message_id]
                    if not todo_message_map[user_id]:
                        del todo_message_map[user_id]
        config['todo_message_map'] = todo_message_map
        await self.firebase_service.update_config(guild.id, config)
        await self.update_todo_tasks_embed(guild, channel)

    async def update_todo_tasks_embed(self, guild, channel):
        config = await self.firebase_service.get_config(guild.id)
        todo_message_map = config.get('todo_message_map', {})
        todo_embed_id = config.get('todo_tasks_embed_id')
        embed = discord.Embed(
            title="🚀 Tasks To Do for Today",
            description=(
                "Let us know what you intend to work on for today!\n"
                "Simply send a message containing the following format:"
                "```\nTODO\nTask1\nTask2\nTask3\n<leave last line blank to signify end>\n```"
                "It will automatically be posted here. You can also share what you got done from yesterday, any notes, or blockers."
            ),
            color=discord.Color.orange()
        )
        any_tasks = False
        for user_id, messages in todo_message_map.items():
            member = guild.get_member(int(user_id))
            if member:
                # Get the latest message (by timestamp) for this user
                latest_msg_id = max(messages, key=lambda mid: int(mid))
                try:
                    latest_msg = await channel.fetch_message(int(latest_msg_id))
                    user_link = f"[{member.display_name}]({latest_msg.jump_url})"
                except Exception:
                    user_link = member.display_name
                all_tasks = []
                for task_list in messages.values():
                    all_tasks.extend(task_list)
                if all_tasks:
                    any_tasks = True
                    embed.add_field(
                        name=user_link,
                        value="\n".join(all_tasks),
                        inline=False
                    )
        if not any_tasks:
            embed.description += "\nNo tasks yet."
        if todo_embed_id:
            try:
                msg = await channel.fetch_message(todo_embed_id)
                await msg.edit(embed=embed)
                return
            except Exception as e:
                logger.warning(f"[update_todo_tasks_embed] Could not edit existing TODO embed: {e}")
        msg = await channel.send(embed=embed)
        config['todo_tasks_embed_id'] = msg.id
        await self.firebase_service.update_config(guild.id, config)

    async def create_dsm(self, channel: discord.TextChannel, config: dict, is_automatic: bool = True):
        """Create a new DSM in the specified channel."""
        try:
            timezone = await self.get_guild_timezone(channel.guild.id)
            current_time = datetime.datetime.now(timezone)
            end_time = current_time + datetime.timedelta(hours=8)
            deadline_time = end_time + datetime.timedelta(hours=4)

            excluded_users = set(config.get('excluded_users', []))
            last_dsm_time = config.get('last_dsm_time')
            if last_dsm_time:
                last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
            else:
                last_dsm_time = current_time - datetime.timedelta(days=1)

            user_todos_yesterday = {}
            user_last_dsm_msg = {}
            async for message in channel.history(after=last_dsm_time, before=current_time, limit=None):
                if message.author.bot or message.author.id in excluded_users:
                    continue
                extracted = self.extract_tasks_from_message(message.content)
                if extracted:
                    user_todos_yesterday.setdefault(message.author, []).extend(extracted)
                    if message.author not in user_last_dsm_msg:
                        user_last_dsm_msg[message.author] = message
            for member in channel.guild.members:
                if not member.bot and member.id not in excluded_users:
                    user_todos_yesterday.setdefault(member, [])

            # Use todo_message_map to determine updated/pending users
            todo_message_map = config.get('todo_message_map', {})
            updated_users = [member for member in channel.guild.members if str(member.id) in todo_message_map and not member.bot and member.id not in excluded_users]
            pending_users = [member for member in channel.guild.members if str(member.id) not in todo_message_map and not member.bot and member.id not in excluded_users]

            end_time_str = end_time.strftime('%B %d, %Y %I:%M %p %Z')
            deadline_time_str = deadline_time.strftime('%B %d, %Y %I:%M %p %Z')
            dsm_date_str = current_time.strftime('%B %d, %Y')

            embed = discord.Embed(
                title=f"🍰 Daily Standup Meeting – {dsm_date_str}",
                description=(
                    "**Good morning, E-Konsulta team!**\n\n"
                    "Let's make today productive and collaborative. Please update your tasks for today by sending your TODOs below."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Timeline",
                value=f"🕒 End: {end_time_str}\n"
                      f"⚠️ Deadline: {deadline_time_str}",
                inline=False
            )
            participants_line = f"👥 Total: {len(updated_users) + len(pending_users)}  ✅ Updated: {len(updated_users)}  ⏳ Pending: {len(pending_users)}"
            embed.add_field(
                name="Participants",
                value=participants_line,
                inline=False
            )
            updated_list = "\n".join([user.mention for user in updated_users]) if updated_users else "None"
            embed.add_field(
                name="✅ Updated",
                value=updated_list,
                inline=False
            )
            pending_list = "\n".join([user.mention for user in pending_users]) if pending_users else "None"
            embed.add_field(
                name="⏳ Pending",
                value=pending_list,
                inline=False
            )
            dsm_message = await channel.send(embed=embed)

            # Message 2: Pending tasks from yesterday (as embed, always show instructions)
            pending_embed = discord.Embed(
                title='📝 Tasks Marked as "To-do" from Last Meeting',
                color=discord.Color.red()
            )
            pending_desc = "These tasks were marked as to-do in the last DSM."
            pending_embed.description = pending_desc
            any_pending = False
            for user, todos in user_todos_yesterday.items():
                if todos:
                    any_pending = True
                    msg = user_last_dsm_msg.get(user)
                    if msg:
                        user_link = f"[{user.display_name}]({msg.jump_url})"
                    else:
                        user_link = user.display_name
                    pending_embed.add_field(
                        name=user_link,
                        value="\n".join(todos),
                        inline=False
                    )
            if not any_pending:
                pending_embed.description += "\nNo tasks from previous DSM."
            await channel.send(embed=pending_embed)

            # Message 3: TODO tasks for the current day (initially empty embed)
            todo_embed = discord.Embed(
                title="🚀 Tasks To Do for Today",
                description=(
                    "Let us know what you intend to work on for today!\n"
                    "Simply send a message containing the following format:"
                    "```\nTODO\nTask1\nTask2\nTask3\n<leave last line blank to signify end>\n```"
                    "It will automatically be posted here. You can also share what you got done from yesterday, any notes, or blockers."
                ),
                color=discord.Color.orange()
            )
            # Hyperlink each user's name to their latest TODO message for today
            for user_id, messages in todo_message_map.items():
                member = channel.guild.get_member(int(user_id))
                if member:
                    # Get the latest message (by timestamp) for this user
                    latest_msg_id = max(messages, key=lambda mid: int(mid))
                    try:
                        latest_msg = await channel.fetch_message(int(latest_msg_id))
                        user_link = f"[{member.display_name}]({latest_msg.jump_url})"
                    except Exception:
                        user_link = member.display_name
                    all_tasks = []
                    for task_list in messages.values():
                        all_tasks.extend(task_list)
                    if all_tasks:
                        todo_embed.add_field(
                            name=user_link,
                            value="\n".join(all_tasks),
                            inline=False
                        )
            todo_msg = await channel.send(embed=todo_embed)
            config['todo_tasks_embed_id'] = todo_msg.id

            config['last_dsm_time'] = current_time.isoformat()
            config['current_dsm_message_id'] = dsm_message.id
            config['current_dsm_channel_id'] = channel.id
            config['todo_message_map'] = {}  # Reset for new DSM
            await self.firebase_service.update_config(channel.guild.id, config)
            logger.info(f"Created DSM in channel {channel.name}")
        except Exception as e:
            logger.error(f"Error creating DSM: {str(e)}")

    @tasks.loop(minutes=1)
    async def auto_dsm_task(self):
        """Automatically create DSM at configured time."""
        try:
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_config(guild.id)
                if not config:
                    continue

                timezone = await self.get_guild_timezone(guild.id)
                current_time = datetime.datetime.now(timezone)
                
                # Check if it's DSM time
                dsm_time = datetime.datetime.strptime(config.get('dsm_time', '09:00'), '%H:%M').time()
                if current_time.hour == dsm_time.hour and current_time.minute == dsm_time.minute:
                    channel_id = config.get('dsm_channel_id')
                    if not channel_id:
                        continue
                    
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        continue

                    # Check if DSM is skipped for today
                    skipped_dates = config.get('skipped_dates', [])
                    today_str = current_time.strftime('%Y-%m-%d')
                    if today_str in skipped_dates:
                        continue

                    await self.create_dsm(channel, config)
                    logger.info(f"Created automatic DSM in {guild.name}")

        except Exception as e:
            logger.error(f"Error in auto_dsm_task: {str(e)}")

    @app_commands.command(name="simulate_dsm", description="Manually trigger a DSM")
    @app_commands.default_permissions(administrator=True)
    async def simulate_dsm(self, interaction: discord.Interaction):
        """Manually trigger a DSM."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                await interaction.response.send_message("Please configure DSM settings first using `/configure`.", ephemeral=True)
                return

            channel_id = config.get('dsm_channel_id')
            if not channel_id:
                await interaction.response.send_message("Please set a DSM channel first using `/set_channel`.", ephemeral=True)
                return

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                await interaction.response.send_message("The configured DSM channel no longer exists.", ephemeral=True)
                return
            
            await interaction.response.send_message("Creating DSM...", ephemeral=True)
            await self.create_dsm(channel, config, is_automatic=False)
            
            # Use a new interaction to send the success message
            try:
                await interaction.edit_original_response(content="DSM created successfully!")
            except discord.NotFound:
                # If the original message is gone, send a new one
                await interaction.channel.send("DSM created successfully!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            try:
                await interaction.edit_original_response(content="Failed to create DSM. Please try again.")
            except discord.NotFound:
                # If the original message is gone, send a new one
                await interaction.channel.send("Failed to create DSM. Please try again.", ephemeral=True)

    async def get_guild_timezone(self, guild_id: int) -> pytz.timezone:
        """Get the timezone for a guild, defaulting to UTC if not set."""
        try:
            config = await self.firebase_service.get_config(guild_id)
            timezone_str = config.get('timezone', 'UTC')
            return pytz.timezone(timezone_str)
        except Exception as e:
            logger.error(f"Error getting timezone for guild {guild_id}: {str(e)}")
            return pytz.UTC

    @app_commands.command(name="configure", description="Configure DSM settings")
    @app_commands.default_permissions(administrator=True)
    async def configure(self, interaction: discord.Interaction,
                       timezone: str = None,
                       dsm_time: str = None,
                       dsm_channel: discord.TextChannel = None):
        """Configure standup settings"""
        try:
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            changes = []

            # Handle timezone
            if timezone:
                try:
                    tz = pytz.timezone(timezone)
                    config['timezone'] = timezone
                    changes.append(f"Timezone: {timezone}")
                except pytz.exceptions.UnknownTimeZoneError:
                    await interaction.response.send_message(
                        f"Invalid timezone: {timezone}. Please use a valid timezone name (e.g., 'Asia/Manila', 'UTC').",
                        ephemeral=True
                    )
                    return

            # Handle DSM time
            if dsm_time:
                try:
                    hour, minute = map(int, dsm_time.split(':'))
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError
                    config['dsm_time'] = dsm_time
                    changes.append(f"DSM Time: {dsm_time}")
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid time format. Please use HH:MM format (e.g., '09:00').",
                        ephemeral=True
                    )
                    return

            # Handle DSM channel
            if dsm_channel is not None:
                config['dsm_channel_id'] = dsm_channel.id
                changes.append(f"DSM Channel: {dsm_channel.mention}")

            # Update config
            await self.firebase_service.update_config(interaction.guild_id, config)

            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Configuration Updated",
                description="The following settings have been updated:",
                color=discord.Color.green()
            )

            if changes:
                embed.add_field(
                    name="Changes Made",
                    value="\n".join(f"• {change}" for change in changes),
                    inline=False
                )
            else:
                embed.add_field(
                    name="No Changes",
                    value="No settings were updated. Please specify at least one setting to change.",
                    inline=False
                )

            # Add current configuration
            current_config = []
            if config.get('timezone'):
                current_config.append(f"Timezone: {config['timezone']}")
            if config.get('dsm_time'):
                current_config.append(f"DSM Time: {config['dsm_time']}")
            if config.get('dsm_channel_id'):
                channel = interaction.guild.get_channel(config['dsm_channel_id'])
                if channel:
                    current_config.append(f"DSM Channel: {channel.mention}")

            if current_config:
                embed.add_field(
                    name="Current Configuration",
                    value="\n".join(f"• {setting}" for setting in current_config),
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Configuration updated for guild {interaction.guild_id}: {', '.join(changes)}")

        except Exception as e:
            logger.error(f"Error in configure: {str(e)}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while updating the configuration: {str(e)}",
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

    @app_commands.command(name="exclude_user", description="Exclude a user from DSM")
    @app_commands.default_permissions(administrator=True)
    async def exclude_user(self, interaction: discord.Interaction, user: discord.Member):
        """Exclude a user from DSM."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            excluded_users = set(config.get('excluded_users', []))
            excluded_users.add(user.id)
            
            config['excluded_users'] = list(excluded_users)
            await self.firebase_service.update_config(interaction.guild_id, config)
            
            await interaction.response.send_message(
                f"{user.mention} has been excluded from DSM.",
                ephemeral=True
            )
            logger.info(f"Excluded user {user.name} ({user.id}) from DSM")
            
        except Exception as e:
            logger.error(f"Error excluding user: {str(e)}")
            await interaction.response.send_message(
                "Failed to exclude user. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="include_user", description="Include a user in DSM")
    @app_commands.default_permissions(administrator=True)
    async def include_user(self, interaction: discord.Interaction, user: discord.Member):
        """Include a user in DSM."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            excluded_users = set(config.get('excluded_users', []))
            if user.id in excluded_users:
                excluded_users.remove(user.id)
                config['excluded_users'] = list(excluded_users)
                await self.firebase_service.update_config(interaction.guild_id, config)
                
                await interaction.response.send_message(
                    f"{user.mention} has been included in DSM.",
                    ephemeral=True
                )
                logger.info(f"Included user {user.name} ({user.id}) in DSM")
            else:
                await interaction.response.send_message(
                    f"{user.mention} is already included in DSM.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f"Error including user: {str(e)}")
            await interaction.response.send_message(
                "Failed to include user. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="list_excluded", description="List all excluded users")
    @app_commands.default_permissions(administrator=True)
    async def list_excluded(self, interaction: discord.Interaction):
        """List all excluded users."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            excluded_users = config.get('excluded_users', [])
            
            if excluded_users:
                excluded_members = []
                for user_id in excluded_users:
                    member = interaction.guild.get_member(user_id)
                    if member:
                        excluded_members.append(member.mention)
                
                embed = discord.Embed(
                    title="Excluded Users",
                    description="The following users are excluded from DSM:",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Users",
                    value="\n".join(excluded_members) if excluded_members else "None",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "No users are currently excluded from DSM.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f"Error listing excluded users: {str(e)}")
            await interaction.response.send_message(
                "Failed to list excluded users. Please try again.",
                ephemeral=True
            )

    async def send_dsm_reminder(self, channel, config):
        # Compose the reminder message
        deadline_time = datetime.datetime.fromisoformat(config['last_dsm_time']) + datetime.timedelta(hours=12)
        deadline_str = deadline_time.strftime('%B %d, %Y %I:%M %p %Z')
        # Ping all pending users
        pending_mentions = []
        excluded_users = set(config.get('excluded_users', []))
        for member in channel.guild.members:
            if not member.bot and member.id not in excluded_users:
                pending_mentions.append(member.mention)
        reminder_msg = (
            f"⏰ **DSM Reminder!**\n"
            f"The deadline for today's DSM is approaching or has just passed. Please update your tasks if you haven't yet!\n"
            f"Deadline: {deadline_str}\n"
            f"{' '.join(pending_mentions)}"
        )
        await channel.send(reminder_msg)

    @tasks.loop(minutes=1)
    async def dsm_reminder_task(self):
        # Check every minute if it's time to send a reminder
        for guild in self.bot.guilds:
            config = await self.firebase_service.get_config(guild.id)
            channel_id = config.get('current_dsm_channel_id')
            last_dsm_time = config.get('last_dsm_time')
            if not channel_id or not last_dsm_time:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            timezone = await self.get_guild_timezone(guild.id)
            dsm_time = datetime.datetime.fromisoformat(last_dsm_time).astimezone(timezone)
            deadline_time = dsm_time + datetime.timedelta(hours=12)
            now = datetime.datetime.now(timezone)
            # Reminder 1 hour before and 1 hour after deadline
            if (deadline_time - datetime.timedelta(hours=1)) <= now < (deadline_time - datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)):
                await self.send_dsm_reminder(channel, config)
            if (deadline_time + datetime.timedelta(hours=1)) <= now < (deadline_time + datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)):
                await self.send_dsm_reminder(channel, config)

    @app_commands.command(name="remind", description="Manually send a DSM reminder to everyone")
    @app_commands.default_permissions(administrator=True)
    async def remind(self, interaction: discord.Interaction):
        config = await self.firebase_service.get_config(interaction.guild_id)
        channel_id = config.get('current_dsm_channel_id')
        if not channel_id:
            await interaction.response.send_message("No DSM channel is set.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("DSM channel not found.", ephemeral=True)
            return
        await self.send_dsm_reminder(channel, config)
        await interaction.response.send_message("Reminder sent!", ephemeral=True)

# Move setup function outside of the class, at module level
async def setup(bot: commands.Bot):
    """Set up the DSM cog."""
    firebase_service = FirebaseService('firebase-credentials.json')
    await bot.add_cog(DSM(bot, firebase_service))