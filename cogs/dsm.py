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
        logger.info("DSM cog initialized")

    def extract_tasks_from_message(self, content: str) -> List[str]:
        """Extract tasks from a message content."""
        # Look for task indicators
        task_indicators = ['to do', 'todo', 'tasks', 'task list']
        content_lower = content.lower()
        
        # Find the task section
        task_section = None
        for indicator in task_indicators:
            if indicator in content_lower:
                # Split by the indicator and take everything after it
                parts = content.split(indicator, 1)
                if len(parts) > 1:
                    task_section = parts[1]
                    break
        
        if not task_section:
            return []
        
        # Split by newlines and filter out empty lines
        lines = [line.strip() for line in task_section.split('\n') if line.strip()]
        
        # Find where the task list ends (empty line)
        end_index = len(lines)
        for i, line in enumerate(lines):
            if not line:
                end_index = i
                break
        
        # Extract tasks (lines between start and end)
        tasks = []
        for line in lines[:end_index]:
            # Remove common bullet points and numbering
            line = re.sub(r'^[-•*]\s*', '', line)
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            if line.strip():
                tasks.append(line.strip())
        
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

    async def create_dsm(self, channel: discord.TextChannel, config: dict, is_automatic: bool = True):
        """Create a new DSM in the specified channel."""
        try:
            # Get current time and calculate end time (8 hours from now)
            timezone = await self.get_guild_timezone(channel.guild.id)
            current_time = datetime.datetime.now(timezone)
            end_time = current_time + datetime.timedelta(hours=8)
            deadline_time = end_time + datetime.timedelta(hours=4)  # 4 hours after end time

            # Initialize task tracking
            total_tasks = 0
            completed_tasks = 0
            pending_tasks = 0
            updated_users = set()
            pending_users = set()

            # Get tasks for each user
            for member in channel.members:
                if not member.bot:
                    tasks = await self.get_user_tasks(channel, member)
                    if tasks:
                        total_tasks += len(tasks)
                        # Check if user has any TODO messages
                        async for message in channel.history(after=current_time - datetime.timedelta(hours=24), limit=None):
                            if message.author.id == member.id and any(indicator in message.content.lower() for indicator in ['todo', 'to do', 'tasks']):
                                updated_users.add(member)
                                completed_tasks += len(tasks)
                                break
                        else:
                            pending_users.add(member)
                            pending_tasks += len(tasks)

            # Create DSM message
            embed = discord.Embed(
                title="Daily Standup Meeting",
                description="A new daily standup meeting has been initiated.",
                color=discord.Color.blue()
            )
            
            # Add timeline
            embed.add_field(
                name="Timeline:",
                value=f"🕒 End Time: {end_time.strftime('%I:%M %p %Z')}\n"
                      f"⚠️ Deadline: {deadline_time.strftime('%Y-%m-%d %I:%M %p %Z')}",
                inline=False
            )

            # Add meeting title
            embed.add_field(
                name=f"Daily Standup Meeting for {current_time.strftime('%B %d, %Y')}",
                value="",
                inline=False
            )

            # Add task statistics
            embed.add_field(
                name="Task Statistics",
                value=f"Total Tasks: {total_tasks}\n"
                      f"Completed: {completed_tasks}\n"
                      f"Pending: {pending_tasks}",
                inline=False
            )

            # Add participant statistics
            embed.add_field(
                name="Participants",
                value=f"Total: {len(updated_users) + len(pending_users)}\n"
                      f"Updated: {len(updated_users)}\n"
                      f"Pending: {len(pending_users)}",
                inline=False
            )

            # Add updated users
            updated_list = "\n".join([user.mention for user in updated_users]) if updated_users else "None"
            embed.add_field(
                name="Updated:",
                value=updated_list,
                inline=False
            )

            # Add pending users
            pending_list = "\n".join([user.mention for user in pending_users]) if pending_users else "None"
            embed.add_field(
                name="Pending:",
                value=pending_list,
                inline=False
            )
            
            # Send the message
            message = await channel.send(embed=embed)
            
            # Update last DSM time
            config['last_dsm_time'] = current_time.isoformat()
            await self.firebase_service.update_config(channel.guild.id, config)
            
            logger.info(f"Created DSM in channel {channel.name}")
            
        except Exception as e:
            logger.error(f"Error creating DSM: {str(e)}")

    @tasks.loop(minutes=1)
    async def auto_dsm_task(self):
        """Automatically create DSM at configured time."""
        try:
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_guild_config(guild.id)
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
            config = await self.firebase_service.get_guild_config(interaction.guild_id)
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
            await interaction.followup.send("DSM created successfully!", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            await interaction.followup.send("Failed to create DSM. Please try again.", ephemeral=True)

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

# Move setup function outside of the class, at module level
async def setup(bot: commands.Bot):
    """Set up the DSM cog."""
    firebase_service = FirebaseService('firebase-credentials.json')
    await bot.add_cog(DSM(bot, firebase_service))