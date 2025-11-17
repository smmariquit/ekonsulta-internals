"""Daily Standup Meeting cog."""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import re
from typing import Dict, Any, Optional, List
from services.firebase_service import FirebaseService
from utils.logging_util import get_logger
from config.default_config import DEFAULT_CONFIG
from utils.philippine_holidays import PhilippineHolidays
import pytz
import logging

logger = logging.getLogger(__name__)
logging.getLogger(__name__).info('dsm.py module imported')

def admin_required():
    """Decorator to check if user is an admin."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild_id:
            return False
        # Get the bot from the client - Discord.py bots always have get_cog
        try:
            # Type assertion: interaction.client is actually a Bot instance
            cog = interaction.client.get_cog('DSM')  # type: ignore
        except AttributeError:
            # Fallback in case of unusual client setup
            return False
        if not cog:
            return False
        return await cog.is_admin(interaction.user.id, interaction.guild_id)
    return app_commands.check(predicate)

class DSM(commands.Cog):
    """Daily Standup Meeting cog."""
    
    def __init__(self, bot: commands.Bot, firebase_service: FirebaseService):
        self.bot = bot
        self.firebase_service = firebase_service
        self.last_reminder_sent = {}  # Track when reminders were sent per guild
        self.auto_dsm_task.start()
        self.dsm_reminder_task.start()
        self.log_config_task.start()
        logger.info("DSM cog initialized")

    @tasks.loop(minutes=5)
    async def log_config_task(self):
        """Log configuration to test channel for debugging."""
        try:
            for guild in self.bot.guilds:
                config = await self.firebase_service.get_config(guild.id)
                if not config:
                    continue
                    
                channel_id = config.get('test_channel_id')
                if not channel_id:
                    continue
                    
                channel = guild.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"Config: {config}")
                else:
                    logger.warning(f"Channel not found for guild {guild.id}")
        except Exception as e:
            logger.error(f"Error in log_config_task: {e}")

    def is_valid_dsm_participation(self, content: str) -> bool:
        """Check if message is valid DSM participation (any non-empty message)."""
        return len(content.strip()) > 0

    def extract_tasks_from_message(self, content: str) -> List[str]:
        """Extract tasks from message content. For simplified DSM, just return the whole message as a task."""
        if content.strip():
            return [content.strip()]
        return []

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
        
        # Calculate the lookback time (2 hours before DSM by default)
        lookback_hours = config.get('dsm_lookback_hours', 2)
        lookback_time = last_dsm_time - datetime.timedelta(hours=lookback_hours)
        
        # Calculate the DSM deadline (12 hours 15 minutes after DSM creation - 9:15 PM)
        dsm_deadline = last_dsm_time + datetime.timedelta(hours=12, minutes=15)
        
        logger.info(f"[get_user_tasks] Looking for messages from {lookback_time} to {dsm_deadline} for user {user.display_name}")
        logger.info(f"[get_user_tasks] Lookback period: {lookback_time} to {last_dsm_time}")
        logger.info(f"[get_user_tasks] DSM period: {last_dsm_time} to {dsm_deadline}")
        
        # Get messages from both lookback period and DSM period
        async for message in channel.history(after=lookback_time, before=dsm_deadline + datetime.timedelta(seconds=1), limit=None):
            if message.author.id == user.id:
                # Check if message is within acceptable time windows
                in_lookback_period = lookback_time <= message.created_at < last_dsm_time
                in_dsm_period = last_dsm_time <= message.created_at <= dsm_deadline
                
                if in_lookback_period or in_dsm_period:
                    message_tasks = self.extract_tasks_from_message(message.content)
                    tasks.extend(message_tasks)
                    logger.info(f"[get_user_tasks] Found {len(message_tasks)} tasks in message {message.id} (lookback: {in_lookback_period}, DSM: {in_dsm_period})")
        
        return list(set(tasks))  # Remove duplicates

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        logger.info(f"[on_message] Received message from {message.author} in channel {getattr(message.channel, 'name', None)}: {repr(message.content)}")
        if message.author.bot or not message.guild:
            logger.info("[on_message] Ignored bot or non-guild message.")
            return
        config = await self.firebase_service.get_config(message.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id:
            try:
                dsm_channel_id = int(dsm_channel_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid DSM channel ID format: {dsm_channel_id}")
                return
                
        if dsm_channel_id and message.channel.id != dsm_channel_id:
            logger.info(f"[on_message] Ignored message not in DSM channel (expected {dsm_channel_id}).")
            return

        # Update DSM participation tracking
        print(f"[on_message] Processing message in DSM channel. Author: {message.author}")
        logger.info(f"[on_message] Processing message in DSM channel. Author: {message.author}")

        # Update participation tracking
        await self.update_dsm_participation(message.guild, message.channel, message)
        
        # Get the latest config after update_todo_tasks_for_today
        config = await self.firebase_service.get_config(message.guild.id)
        todo_message_map = config.get('todo_message_map', {})

        # Update DSM embed if there's an active DSM
        current_dsm_message_id = config.get('current_dsm_message_id')
        if current_dsm_message_id:
            try:
                # Convert string message ID to int
                current_dsm_message_id = int(current_dsm_message_id)
                dsm_message = await message.channel.fetch_message(current_dsm_message_id)
                print(f"[on_message] Found current DSM message: {current_dsm_message_id}")
                logger.info(f"[on_message] Found current DSM message: {current_dsm_message_id}")

                # Get the last DSM time
                last_dsm_time = config.get('last_dsm_time')
                if last_dsm_time:
                    last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
                else:
                    last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)
                print(f"[on_message] Last DSM time: {last_dsm_time}")
                logger.info(f"[on_message] Last DSM time: {last_dsm_time}")

                # Process the todo_message_map directly
                updated_users = set()
                for user_id, messages in todo_message_map.items():
                    member = message.guild.get_member(int(user_id))
                    if member and not member.bot and member.id not in config.get('excluded_users', []):
                        # If user has any messages in the map, they've updated
                        updated_users.add(member)
                        print(f"[on_message] Added {member.display_name} to updated users (has messages in todo_message_map)")
                        logger.info(f"[on_message] Added {member.display_name} to updated users (has messages in todo_message_map)")

                # Update the DSM embed
                embed = dsm_message.embeds[0]
                updated_users_list = list(updated_users)
                pending_users = [member for member in message.guild.members 
                               if not member.bot 
                               and member.id not in config.get('excluded_users', [])
                               and member not in updated_users_list]

                # Update the participants field
                participants_line = f"👥 Total: {len(updated_users_list) + len(pending_users)}  ✅ Updated: {len(updated_users_list)}  ⏳ Pending: {len(pending_users)}"
                for i, field in enumerate(embed.fields):
                    if field.name == "Participants":
                        embed.set_field_at(i, name="Participants", value=participants_line, inline=False)
                        break

                # Update the Updated and Pending fields
                updated_list = "\n".join([user.mention for user in updated_users_list]) if updated_users_list else "None"
                pending_list = "\n".join([user.mention for user in pending_users]) if pending_users else "None"

                for i, field in enumerate(embed.fields):
                    if field.name == "✅ Updated":
                        embed.set_field_at(i, name="✅ Updated", value=updated_list, inline=False)
                    elif field.name == "⏳ Pending":
                        embed.set_field_at(i, name="⏳ Pending", value=pending_list, inline=False)

                print(f"[on_message] Updating DSM embed with {len(updated_users_list)} updated users and {len(pending_users)} pending users")
                logger.info(f"[on_message] Updating DSM embed with {len(updated_users_list)} updated users and {len(pending_users)} pending users")
                await dsm_message.edit(embed=embed)

            except (ValueError, TypeError) as e:
                print(f"[on_message] Invalid DSM message ID format: {current_dsm_message_id}")
                logger.error(f"[on_message] Invalid DSM message ID format: {current_dsm_message_id}")
            except Exception as e:
                print(f"[on_message] Error updating DSM embed: {e}")
                logger.error(f"[on_message] Error updating DSM embed: {e}")

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        logger.info(f"[on_message_edit] Message edited by {after.author} in channel {getattr(after.channel, 'name', None)}: {repr(after.content)}")
        if after.author.bot or not after.guild:
            logger.info("[on_message_edit] Ignored bot or non-guild message.")
            return
        config = await self.firebase_service.get_config(after.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id:
            try:
                dsm_channel_id = int(dsm_channel_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid DSM channel ID format: {dsm_channel_id}")
                return
                
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
        await self.update_dsm_participation(after.guild, after.channel, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        logger.info(f"[on_message_delete] Message deleted by {message.author if message.author else 'Unknown'} in channel {getattr(message.channel, 'name', None)}: {repr(message.content) if hasattr(message, 'content') else 'No content'}")
        if not message.guild or message.author is None or message.author.bot:
            return
        config = await self.firebase_service.get_config(message.guild.id)
        dsm_channel_id = config.get('dsm_channel_id')
        if dsm_channel_id:
            try:
                dsm_channel_id = int(dsm_channel_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid DSM channel ID format: {dsm_channel_id}")
                return
                
        if dsm_channel_id and message.channel.id != dsm_channel_id:
            return
        # Only update the TODO TASKS for Today embed
        await self.update_dsm_participation(message.guild, message.channel, message, deleted=True)

    async def update_dsm_participation(self, guild, channel, message, deleted=False):
        """Track DSM participation and weekly attendance."""
        config = await self.firebase_service.get_config(guild.id)
        last_dsm_time = config.get('last_dsm_time')
        if last_dsm_time:
            last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
        else:
            last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)
        
        # Calculate the DSM deadline
        dsm_deadline = last_dsm_time + datetime.timedelta(hours=12, minutes=15)
        
        user_id = str(message.author.id)
        message_time = message.created_at
        
        # Only track participation within DSM period
        if not (last_dsm_time <= message_time <= dsm_deadline):
            return
            
        # Get or initialize participation tracking
        dsm_participants = config.get('dsm_participants', {})
        weekly_attendance = config.get('weekly_attendance', {})
        
        # Convert message time to guild timezone for proper date calculation
        timezone = await self.get_guild_timezone(guild.id)
        participation_datetime = message_time.astimezone(timezone)
        participation_date = participation_datetime.date()
        user_weekly_key = f"{user_id}_{participation_date.strftime('%Y-%W')}"
        
        if deleted:
            # Remove participation
            dsm_participants.pop(user_id, None)
            # Also remove from weekly attendance if needed
            if user_weekly_key in weekly_attendance:
                day_abbrev = ['M', 'T', 'W', 'Th', 'F'][participation_date.weekday()]
                weekly_attendance[user_weekly_key][day_abbrev] = False
        else:
            # Mark as participated if valid message
            if self.is_valid_dsm_participation(message.content):
                dsm_participants[user_id] = {
                    'message_id': str(message.id),
                    'participated_at': message_time.isoformat()
                }
                
                # Update weekly attendance
                if user_weekly_key not in weekly_attendance:
                    weekly_attendance[user_weekly_key] = {'M': False, 'T': False, 'W': False, 'Th': False, 'F': False}
                
                # Mark the actual participation day's attendance
                day_abbrev = ['M', 'T', 'W', 'Th', 'F'][participation_date.weekday()]
                weekly_attendance[user_weekly_key][day_abbrev] = True
        
        config['dsm_participants'] = dsm_participants
        config['weekly_attendance'] = weekly_attendance
        await self.firebase_service.update_config(guild.id, config)
        await self.update_dsm_embed(guild, channel, config)

    # Removed update_todo_tasks_embed function as it's no longer needed with simplified DSM

    async def create_dsm(self, channel: discord.TextChannel, config: dict, is_automatic: bool = True):
        """Create a new DSM in the specified channel."""
        try:
            timezone = await self.get_guild_timezone(channel.guild.id)
            current_time = datetime.datetime.now(timezone)
            end_time = current_time + datetime.timedelta(hours=8)
            deadline_time = current_time + datetime.timedelta(hours=12, minutes=15)  # 9:15 PM for 9:00 AM start

            excluded_users = set(self.ensure_str_ids(config.get('excluded_users', [])))
            logger.info(f"[DEBUG] Creating DSM with excluded users: {excluded_users}")
            last_dsm_time = config.get('last_dsm_time')
            if last_dsm_time:
                last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
            else:
                last_dsm_time = current_time - datetime.timedelta(days=1)

            # Calculate the lookback time (2 hours before last DSM by default)
            lookback_hours = config.get('dsm_lookback_hours', 2)
            lookback_time = last_dsm_time - datetime.timedelta(hours=lookback_hours)
            
            logger.info(f"[create_dsm] Gathering TODOs from {lookback_time} to {current_time}")

            # No need to gather yesterday's tasks since we simplified the DSM

            end_time_str = end_time.strftime('%B %d, %Y %I:%M %p %Z')
            deadline_time_str = deadline_time.strftime('%B %d, %Y %I:%M %p %Z')
            dsm_date_str = current_time.strftime('%B %d, %Y')

            # Create simplified DSM embed with weekly attendance
            embed = discord.Embed(
                title=f"🍰 Daily Standup Meeting – {dsm_date_str}",
                description=(
                    "**Good morning, E-Konsulta team!**\n\n"
                    "Please share:\n"
                    "• **Tasks to do for today**\n"
                    "• **Tasks you got done from yesterday**\n"
                    "• **Any blockers or notes**\n\n"
                    "Simply send any message to participate!"
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Timeline",
                value=f"🕒 End: {end_time_str}\n"
                      f"⚠️ Deadline: {deadline_time_str}",
                inline=False
            )
            
            # Send DSM embed and update last_dsm_time in config immediately
            dsm_message = await channel.send(embed=embed)
            config['last_dsm_time'] = dsm_message.created_at.isoformat()
            
            # Initialize participation tracking
            all_members = [member for member in channel.guild.members 
                          if not member.bot and member.id not in excluded_users]
            updated_users = []
            pending_users = all_members.copy()
            
            # Add participants section
            participants_line = f"👥 Total: {len(all_members)}  ✅ Participated: 0  ⏳ Pending: {len(all_members)}"
            embed.add_field(
                name="Participants",
                value=participants_line,
                inline=False
            )
            embed.add_field(
                name="✅ Participated",
                value="None",
                inline=False
            )
            embed.add_field(
                name="⏳ Pending",
                value="\n".join([user.mention for user in pending_users]) if pending_users else "None",
                inline=False
            )
            
            # Add weekly attendance section
            weekly_attendance_text = self.get_weekly_attendance_display(config, all_members, current_time.date(), current_time)
            if weekly_attendance_text:
                embed.add_field(
                    name="📅 Weekly Attendance (M T W Th F)",
                    value=weekly_attendance_text,
                    inline=False
                )
            
            # Edit the DSM embed to add all fields
            await dsm_message.edit(embed=embed)

            config['current_dsm_message_id'] = str(dsm_message.id)
            config['current_dsm_channel_id'] = str(channel.id)
            config['dsm_participants'] = {}  # Reset for new DSM
            
            # Initialize weekly attendance for today
            today = current_time.date()
            for member in all_members:
                user_weekly_key = f"{member.id}_{today.strftime('%Y-%W')}"
                if 'weekly_attendance' not in config:
                    config['weekly_attendance'] = {}
                if user_weekly_key not in config['weekly_attendance']:
                    config['weekly_attendance'][user_weekly_key] = {'M': False, 'T': False, 'W': False, 'Th': False, 'F': False}
            await self.firebase_service.update_config(channel.guild.id, config)
            logger.info(f"Created DSM in channel {channel.name}")
        except Exception as e:
            logger.error(f"Error creating DSM: {str(e)}")

    @tasks.loop(minutes=1)
    async def dsm_reminder_task(self):
        # Check every minute if it's time to send a reminder (at 8:45AM) and update DSM embed (after deadline at 9:15AM)
        for guild in self.bot.guilds:
            try:
                config = await self.firebase_service.get_config(guild.id)
                if not config:
                    continue
                    
                timezone = await self.get_guild_timezone(guild.id)
                now = datetime.datetime.now(timezone)
                
                # Get configured DSM time (default 09:00)
                dsm_time_str = config.get('dsm_time', '09:00')
                try:
                    dsm_hour, dsm_minute = map(int, dsm_time_str.split(':'))
                except ValueError:
                    logger.error(f"Invalid DSM time format: {dsm_time_str}")
                    continue
                    
                # Calculate reminder time (15 minutes before DSM)
                reminder_hour = dsm_hour
                reminder_minute = dsm_minute - 15
                if reminder_minute < 0:
                    reminder_hour -= 1
                    reminder_minute += 60
                if reminder_hour < 0:
                    reminder_hour += 24
                    
                # Check if it's reminder time (8:45AM for default 9:00AM DSM)
                if now.hour == reminder_hour and now.minute == reminder_minute:
                    # Check if we've already sent a reminder today
                    today_key = f"{guild.id}_{now.date()}"
                    if today_key in self.last_reminder_sent:
                        continue  # Already sent reminder today
                    
                    channel_id = config.get('dsm_channel_id')
                    if channel_id:
                        try:
                            channel_id = int(channel_id)
                            channel = guild.get_channel(channel_id)
                            if channel and isinstance(channel, discord.TextChannel):
                                logger.info(f"Sending DSM reminder for guild {guild.name} at {now.strftime('%H:%M')}")
                                await self.send_dsm_reminder(channel, config)
                                # Mark that we've sent the reminder today
                                self.last_reminder_sent[today_key] = now
                        except (ValueError, TypeError):
                            logger.error(f"Invalid channel ID format: {channel_id}")
                            continue
                            
            except Exception as e:
                logger.error(f"Error in dsm_reminder_task for guild {guild.name}: {str(e)}")
            
            # Check if DSM was created today and if it's past deadline (15 minutes after DSM time)
            current_dsm_channel_id = config.get('current_dsm_channel_id')
            if current_dsm_channel_id:
                try:
                    current_dsm_channel_id = int(current_dsm_channel_id)
                    channel = guild.get_channel(current_dsm_channel_id)
                    if channel:
                        last_dsm_time = config.get('last_dsm_time')
                        if last_dsm_time:
                            dsm_time = datetime.datetime.fromisoformat(last_dsm_time).astimezone(timezone)
                            dsm_deadline = dsm_time + datetime.timedelta(hours=12, minutes=15)
                            
                            # Update DSM embed 1 minute after deadline
                            if (dsm_deadline + datetime.timedelta(minutes=1)) <= now < (dsm_deadline + datetime.timedelta(minutes=2)):
                                await self.update_dsm_embed(guild, channel, config)
                except (ValueError, TypeError):
                    logger.error(f"Invalid current DSM channel ID format: {current_dsm_channel_id}")
                    continue

    def should_skip_dsm_today(self, date, config):
        """Check if DSM should be skipped for the given date."""
        # Check if it's a weekend
        if PhilippineHolidays.is_weekend(date):
            return True
        
        # Check if it's a Philippine holiday
        if PhilippineHolidays.is_holiday(date):
            return True
        
        # Check manual skip dates
        skipped_dates = config.get('skipped_dates', [])
        date_str = date.strftime('%Y-%m-%d')
        if date_str in skipped_dates:
            return True
        
        return False
    
    def get_weekly_attendance_display(self, config, members, today, current_datetime=None):
        """Generate weekly attendance display string with proper date alignment."""
        weekly_attendance = config.get('weekly_attendance', {})
        week_key = today.strftime('%Y-%W')
        
        # Get the Monday of the current week
        days_since_monday = today.weekday()
        monday_of_week = today - datetime.timedelta(days=days_since_monday)
        
        # Create header with dates
        header_dates = []
        header_days = []
        for i, day_abbrev in enumerate(['M', 'T', 'W', 'Th', 'F']):
            current_day_date = monday_of_week + datetime.timedelta(days=i)
            date_str = current_day_date.strftime('%m/%d')
            header_dates.append(f"{date_str:>5}")
            header_days.append(f"{day_abbrev:>5}")
        
        # Create table
        table_lines = []
        table_lines.append(f"{'Name':<12} {' '.join(header_days)}")
        table_lines.append(f"{'':>12} {' '.join(header_dates)}")
        table_lines.append(f"{'-' * 12} {'-' * 29}")
        
        for member in members[:10]:  # Limit to first 10 members to avoid embed length issues
            user_weekly_key = f"{member.id}_{week_key}"
            attendance = weekly_attendance.get(user_weekly_key, {'M': False, 'T': False, 'W': False, 'Th': False, 'F': False})
            
            status_symbols = []
            for i, day in enumerate(['M', 'T', 'W', 'Th', 'F']):
                current_day_date = monday_of_week + datetime.timedelta(days=i)
                
                # Check if this day should have had a DSM (not weekend/holiday and has passed)
                if self.should_skip_dsm_today(current_day_date, config):
                    # Day was skipped (weekend/holiday) - show as pending
                    status_symbols.append('⭕')
                elif attendance.get(day, False):
                    # User participated on this day
                    status_symbols.append('✅')
                elif current_day_date > today:
                    # Future workday - show as pending
                    status_symbols.append('⭕')
                else:
                    # Past or current workday without participation
                    status_symbols.append('❌')
            
            # Format status symbols with proper spacing
            formatted_symbols = [f"{symbol:>5}" for symbol in status_symbols]
            table_lines.append(f"{member.display_name[:12]:<12} {' '.join(formatted_symbols)}")
        
        if len(members) > 10:
            table_lines.append(f"... and {len(members) - 10} more")
        
        return "```\n" + "\n".join(table_lines) + "\n```" if table_lines else ""

    async def update_dsm_embed(self, guild, channel, config=None):
        """Update the DSM embed with current participation and weekly attendance."""
        if config is None:
            config = await self.firebase_service.get_config(guild.id)
        current_dsm_message_id = config.get('current_dsm_message_id')
        if not current_dsm_message_id:
            return
        try:
            # Convert string message ID to int
            current_dsm_message_id = int(current_dsm_message_id)
            dsm_message = await channel.fetch_message(current_dsm_message_id)
            last_dsm_time = config.get('last_dsm_time')
            if last_dsm_time:
                last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
            else:
                last_dsm_time = datetime.datetime.now() - datetime.timedelta(days=1)

            # Get current excluded users
            excluded_users = set(self.ensure_str_ids(config.get('excluded_users', [])))
            
            # Get participation data
            dsm_participants = config.get('dsm_participants', {})
            
            # Get all eligible members
            all_members = [member for member in guild.members 
                          if not member.bot and str(member.id) not in excluded_users]
            
            # Separate participated and pending users
            participated_users = []
            participated_user_ids = set()
            
            logger.info(f"[DEBUG] Processing {len(dsm_participants)} participants from config")
            
            for user_id in dsm_participants:
                try:
                    # Handle both string and int user IDs
                    member_id = int(user_id)
                    member = guild.get_member(member_id)
                    if member and member in all_members:
                        participated_users.append(member)
                        participated_user_ids.add(member_id)
                        logger.info(f"[DEBUG] Added participant: {member.display_name} (ID: {member_id})")
                    else:
                        logger.warning(f"[DEBUG] Member not found or excluded: {member_id}")
                except (ValueError, TypeError):
                    logger.warning(f"Invalid user ID in dsm_participants: {user_id}")
                    continue
            
            # Remove participated users from all_members to get pending users
            pending_users = [member for member in all_members if member.id not in participated_user_ids]
            
            logger.info(f"[DEBUG] Final counts - Participated: {len(participated_users)}, Pending: {len(pending_users)}, Total: {len(all_members)}")

            # Update the embed
            embed = dsm_message.embeds[0]
            participants_line = f"👥 Total: {len(all_members)}  ✅ Participated: {len(participated_users)}  ⏳ Pending: {len(pending_users)}"
            
            # Update the Participants field
            for i, field in enumerate(embed.fields):
                if field.name == "Participants":
                    embed.set_field_at(i, name="Participants", value=participants_line, inline=False)
                    break

            # Update the Participated and Pending fields
            participated_list = "\n".join([user.mention for user in participated_users]) if participated_users else "None"
            pending_list = "\n".join([user.mention for user in pending_users]) if pending_users else "None"

            for i, field in enumerate(embed.fields):
                if field.name == "✅ Participated":
                    embed.set_field_at(i, name="✅ Participated", value=participated_list, inline=False)
                elif field.name == "⏳ Pending":
                    embed.set_field_at(i, name="⏳ Pending", value=pending_list, inline=False)
                elif field.name == "📅 Weekly Attendance (M T W Th F)":
                    # Update weekly attendance display with proper timezone
                    timezone = await self.get_guild_timezone(guild.id)
                    timezone_aware_dsm_time = last_dsm_time.astimezone(timezone)
                    weekly_attendance_text = self.get_weekly_attendance_display(config, all_members, timezone_aware_dsm_time.date(), timezone_aware_dsm_time)
                    if weekly_attendance_text:
                        embed.set_field_at(i, name="📅 Weekly Attendance (M T W Th F)", value=weekly_attendance_text, inline=False)

            await dsm_message.edit(embed=embed)
            logger.info(f"[DEBUG] Updated DSM embed with {len(participated_users)} participated users and {len(pending_users)} pending users")

        except (ValueError, TypeError) as e:
            print(f"[update_dsm_embed] Invalid DSM message ID format: {current_dsm_message_id}")
            logger.error(f"[update_dsm_embed] Invalid DSM message ID format: {current_dsm_message_id}")
        except Exception as e:
            print(f"[update_dsm_embed] Error updating DSM embed: {e}")
            logger.error(f"[update_dsm_embed] Error updating DSM embed: {e}")

    @app_commands.command(name="remind", description="Manually send a DSM reminder to everyone")
    async def remind(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        config = await self.firebase_service.get_config(interaction.guild_id)
        current_dsm_channel_id = config.get('current_dsm_channel_id')
        if not current_dsm_channel_id:
            await interaction.response.send_message("No DSM channel is set.", ephemeral=True)
            return
            
        try:
            current_dsm_channel_id = int(current_dsm_channel_id)
        except (ValueError, TypeError):
            await interaction.response.send_message("Invalid DSM channel ID format.", ephemeral=True)
            return
            
        channel = interaction.guild.get_channel(current_dsm_channel_id)
        if not channel:
            await interaction.response.send_message("DSM channel not found.", ephemeral=True)
            return
        await self.send_dsm_reminder(channel, config)
        await interaction.response.send_message("Reminder sent!", ephemeral=True)

    @app_commands.command(name="add_admin", description="Add an admin user to the bot")
    async def add_admin(self, interaction: discord.Interaction, user: discord.Member):
        """Add an admin user to the bot."""
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            admin_users = set(config.get('admin_users', []))
            admin_users.add(user.id)
            
            config['admin_users'] = list(admin_users)
            await self.firebase_service.update_config(interaction.guild_id, config)
            
            await interaction.response.send_message(
                f"{user.mention} has been added as an admin.",
                ephemeral=True
            )
            logger.info(f"Added admin user {user.name} ({user.id})")
            
        except Exception as e:
            logger.error(f"Error adding admin user: {str(e)}")
            await interaction.response.send_message(
                "Failed to add admin user. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="remove_admin", description="Remove an admin user from the bot")
    async def remove_admin(self, interaction: discord.Interaction, user: discord.Member):
        """Remove an admin user from the bot."""
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            admin_users = set(config.get('admin_users', []))
            if user.id in admin_users:
                admin_users.remove(user.id)
                config['admin_users'] = list(admin_users)
                await self.firebase_service.update_config(interaction.guild_id, config)
                
                await interaction.response.send_message(
                    f"{user.mention} has been removed as an admin.",
                    ephemeral=True
                )
                logger.info(f"Removed admin user {user.name} ({user.id})")
            else:
                await interaction.response.send_message(
                    f"{user.mention} is not an admin.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f"Error removing admin user: {str(e)}")
            await interaction.response.send_message(
                "Failed to remove admin user. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="list_admins", description="List all admin users")
    async def list_admins(self, interaction: discord.Interaction):
        """List all admin users."""
        try:
            if not interaction.guild_id or not interaction.guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return
            config = await self.firebase_service.get_config(interaction.guild_id)
            admin_users = config.get('admin_users', [])
            
            if admin_users:
                admin_members = []
                for user_id in admin_users:
                    member = interaction.guild.get_member(user_id)
                    if member:
                        admin_members.append(member.mention)
                
                embed = discord.Embed(
                    title="Admin Users",
                    description="The following users are admins:",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Users",
                    value="\n".join(admin_members) if admin_members else "None",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "No users are currently set as admins.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f"Error listing admin users: {str(e)}")
            await interaction.response.send_message(
                "Failed to list admin users. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="show_lookback", description="Show current DSM lookback configuration")
    async def show_lookback(self, interaction: discord.Interaction):  # type: ignore
        """Show the current DSM lookback configuration."""
        try:
            # Defer the response to prevent timeout
            await interaction.response.defer(ephemeral=True)
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}
            
            lookback_hours = config.get('dsm_lookback_hours', 2)
            last_dsm_time = config.get('last_dsm_time')
            
            embed = discord.Embed(
                title="🔍 DSM Time Window Configuration",
                description="Current settings for message collection periods",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Lookback Hours",
                value=f"**{lookback_hours} hours** before DSM creation",
                inline=False
            )
            
            if last_dsm_time:
                last_dsm_dt = datetime.datetime.fromisoformat(last_dsm_time)
                lookback_time = last_dsm_dt - datetime.timedelta(hours=lookback_hours)
                dsm_deadline = last_dsm_dt + datetime.timedelta(hours=12)
                
                embed.add_field(
                    name="Last DSM Time",
                    value=f"**{last_dsm_dt.strftime('%Y-%m-%d %H:%M:%S')}**",
                    inline=True
                )
                
                embed.add_field(
                    name="Lookback Period",
                    value=f"**{lookback_time.strftime('%Y-%m-%d %H:%M:%S')}** to **{last_dsm_dt.strftime('%Y-%m-%d %H:%M:%S')}**\n(Early submissions)",
                    inline=True
                )
                
                embed.add_field(
                    name="DSM Period",
                    value=f"**{last_dsm_dt.strftime('%Y-%m-%d %H:%M:%S')}** to **{dsm_deadline.strftime('%Y-%m-%d %H:%M:%S')}**\n(During DSM)",
                    inline=True
                )
                
                embed.add_field(
                    name="Total Collection Window",
                    value=f"Messages are collected from **{lookback_hours} hours before** DSM creation until **12 hours after** DSM creation",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Last DSM",
                    value="No previous DSM found",
                    inline=False
                )
            
            embed.add_field(
                name="How to Change",
                value="Use `/configure dsm_lookback_hours:<hours>` to modify the lookback period",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in show_lookback: {str(e)}")
            await interaction.followup.send(
                f"Failed to show lookback configuration: {str(e)}",
                ephemeral=True
            )

    async def send_dsm_reminder(self, channel, config):
        # Compose the pre-DSM reminder message
        timezone = await self.get_guild_timezone(channel.guild.id)
        
        # Get configured DSM time (default 09:00)
        dsm_time_str = config.get('dsm_time', '09:00')
        try:
            dsm_hour, dsm_minute = map(int, dsm_time_str.split(':'))
        except ValueError:
            logger.error(f"Invalid DSM time format: {dsm_time_str}")
            return
            
        # Create today's DSM time
        now = datetime.datetime.now(timezone)
        dsm_start_time = now.replace(hour=dsm_hour, minute=dsm_minute, second=0, microsecond=0)
        deadline_time = dsm_start_time + datetime.timedelta(hours=12, minutes=15)
        
        dsm_start_str = dsm_start_time.strftime('%I:%M %p')
        deadline_str = deadline_time.strftime('%I:%M %p')

        # Get all non-bot, non-excluded users
        excluded_users = set(self.ensure_str_ids(config.get('excluded_users', [])))
        all_mentions = []
        for member in channel.guild.members:
            if not member.bot and str(member.id) not in excluded_users:
                all_mentions.append(member.mention)

        reminder_msg = (
            f"Good morning, team!\n\n"
            f"DSM starts in 15 minutes at {dsm_start_str}**"
            f"Deadline is at {deadline_str}!\n\n"
            f"{' '.join(all_mentions)}"
        )
        await channel.send(reminder_msg)

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
                    
                    try:
                        channel_id = int(channel_id)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid channel ID format: {channel_id}")
                        continue
                    
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        continue

                    # Check if DSM should be skipped for today (weekends, holidays, or manual skip)
                    if self.should_skip_dsm_today(current_time.date(), config):
                        continue

                    if isinstance(channel, discord.TextChannel):
                        await self.create_dsm(channel, config)
                    logger.info(f"Created automatic DSM in {guild.name}")

        except Exception as e:
            logger.error(f"Error in auto_dsm_task: {str(e)}")

    @app_commands.command(name="simulate_dsm", description="Manually trigger a DSM")
    async def simulate_dsm(self, interaction: discord.Interaction):  # type: ignore
        """Manually trigger a DSM."""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                await interaction.followup.send("Please configure DSM settings first using `/configure`.", ephemeral=True)
                return

            channel_id = config.get('dsm_channel_id')
            if not channel_id:
                await interaction.followup.send("Please set a DSM channel first using `/set_channel`.", ephemeral=True)
                return

            try:
                channel_id = int(channel_id)
            except (ValueError, TypeError):
                await interaction.followup.send("Invalid DSM channel ID format.", ephemeral=True)
                return

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                await interaction.followup.send("The configured DSM channel no longer exists.", ephemeral=True)
                return
            
            await interaction.followup.send("Creating DSM...", ephemeral=True)
            await self.create_dsm(channel, config, is_automatic=False)
            
            # Send success message
            await interaction.followup.send("DSM created successfully!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in simulate_dsm: {str(e)}")
            await interaction.followup.send("Failed to create DSM. Please try again.", ephemeral=True)

    async def get_guild_timezone(self, guild_id: int) -> pytz.BaseTzInfo:
        """Get the timezone for a guild, defaulting to UTC if not set."""
        try:
            config = await self.firebase_service.get_config(guild_id)
            timezone_str = config.get('timezone', 'UTC')
            return pytz.timezone(timezone_str)
        except Exception as e:
            logger.error(f"Error getting timezone for guild {guild_id}: {str(e)}")
            return pytz.UTC

    @app_commands.command(name="configure", description="Configure DSM settings")  # type: ignore
    async def configure(self, interaction: discord.Interaction,
                       timezone: Optional[str] = None,
                       dsm_time: Optional[str] = None,
                       dsm_channel: Optional[discord.TextChannel] = None,
                       dsm_lookback_hours: Optional[int] = None):
        """Configure standup settings"""
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
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
                    await interaction.followup.send(
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
                    await interaction.followup.send(
                        "Invalid time format. Please use HH:MM format (e.g., '09:00').",
                        ephemeral=True
                    )
                    return

            # Handle DSM channel
            if dsm_channel is not None:
                config['dsm_channel_id'] = str(dsm_channel.id)
                changes.append(f"DSM Channel: {dsm_channel.mention}")

            # Handle DSM lookback hours
            if dsm_lookback_hours is not None:
                if not (0 <= dsm_lookback_hours <= 24):
                    await interaction.followup.send(
                        "Invalid lookback hours. Please use a value between 0 and 24 hours.",
                        ephemeral=True
                    )
                    return
                config['dsm_lookback_hours'] = dsm_lookback_hours
                changes.append(f"DSM Lookback Hours: {dsm_lookback_hours}")

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
                try:
                    channel_id = int(config['dsm_channel_id'])
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        current_config.append(f"DSM Channel: {channel.mention}")
                except (ValueError, TypeError):
                    current_config.append(f"DSM Channel: Invalid ID format")
            if config.get('dsm_lookback_hours'):
                current_config.append(f"DSM Lookback Hours: {config['dsm_lookback_hours']}")

            if current_config:
                embed.add_field(
                    name="Current Configuration",
                    value="\n".join(f"• {setting}" for setting in current_config),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Configuration updated for guild {interaction.guild_id}: {', '.join(changes)}")

        except Exception as e:
            logger.error(f"Error in configure: {str(e)}")
            await interaction.followup.send(
                f"An error occurred while updating the configuration: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="set_channel", description="Set the channel where DSMs will be posted")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel where DSMs will be posted."""
        try:
            # Update the config with the new channel ID
            await self.firebase_service.update_config(interaction.guild_id, {'dsm_channel_id': str(channel.id)})
            
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
    async def skip_dsm(self, interaction: discord.Interaction, date: str):
        """Skip DSM on a specific date."""
        try:
            # Validate date format
            datetime.datetime.strptime(date, '%Y-%m-%d')
            
            # Defer the response to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Add date to skipped dates if not already present
            if date not in config.get('skipped_dates', []):
                skipped_dates = config.get('skipped_dates', []) + [date]
                await self.firebase_service.update_config(interaction.guild_id, {'skipped_dates': skipped_dates})
                await interaction.followup.send(f"DSM will be skipped on {date}", ephemeral=True)
                logger.info(f"Added {date} to skipped dates")
            else:
                await interaction.followup.send(f"DSM is already scheduled to be skipped on {date}", ephemeral=True)
                
        except ValueError:
            await interaction.followup.send(
                "Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-21)",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in skip_dsm: {str(e)}")
            await interaction.followup.send(
                f"Failed to skip DSM: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="unskip_dsm", description="Remove a date from the skipped DSM list")
    async def unskip_dsm(self, interaction: discord.Interaction, date: str):
        """Remove a date from the skipped DSM list."""
        try:
            # Validate date format
            datetime.datetime.strptime(date, '%Y-%m-%d')
            
            # Defer the response to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            # Get current config
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Remove date from skipped dates if present
            skipped_dates = config.get('skipped_dates', [])
            if date in skipped_dates:
                skipped_dates.remove(date)
                await self.firebase_service.update_config(interaction.guild_id, {'skipped_dates': skipped_dates})
                await interaction.followup.send(f"DSM will no longer be skipped on {date}", ephemeral=True)
                logger.info(f"Removed {date} from skipped dates")
            else:
                await interaction.followup.send(f"DSM was not scheduled to be skipped on {date}", ephemeral=True)
                
        except ValueError:
            await interaction.followup.send(
                "Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-21)",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in unskip_dsm: {str(e)}")
            await interaction.followup.send(
                f"Failed to unskip DSM: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="list_skipped_dsm", description="List all dates where DSM is skipped")
    async def list_skipped_dsm(self, interaction: discord.Interaction):
        """List all dates where DSM is skipped."""
        try:
            # Defer the response to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
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
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("No dates are currently scheduled to skip DSM.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in list_skipped_dsm: {str(e)}")
            await interaction.followup.send(
                f"Failed to list skipped dates: {str(e)}",
                ephemeral=True
            )

    async def is_admin(self, user_id: int, guild_id: int) -> bool:
        """Check if a user is an admin in the guild."""
        try:
            config = await self.firebase_service.get_config(guild_id)
            admin_users = config.get('admin_users', [])
            return user_id in admin_users
        except Exception as e:
            logger.error(f"Error checking admin status: {str(e)}")
            return False

    def ensure_int_ids(self, id_list: List) -> List[int]:
        """Convert all IDs in a list to integers."""
        return [int(id) for id in id_list]

    def ensure_str_ids(self, id_list: List) -> List[str]:
        """Convert all IDs in a list to strings."""
        return [str(id) for id in id_list]

    async def get_excluded_users(self, guild_id: int) -> List[int]:
        """Get list of excluded user IDs, ensuring they are integers."""
        config = await self.firebase_service.get_config(guild_id)
        excluded_users = config.get('excluded_users', [])
        return self.ensure_int_ids(excluded_users)

    @app_commands.command(name="exclude_user", description="Exclude a user from DSM")
    async def exclude_user(self, interaction: discord.Interaction, user: discord.Member):
        """Exclude a user from DSM."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            logger.info(f"[DEBUG] Current config for guild {interaction.guild_id}: {config}")
            
            if not config:
                config = {}

            excluded_users = set(self.ensure_str_ids(config.get('excluded_users', [])))
            logger.info(f"[DEBUG] Current excluded users: {excluded_users}")
            
            excluded_users.add(str(user.id))
            logger.info(f"[DEBUG] Adding user {user.id} to excluded users. New set: {excluded_users}")
            
            config['excluded_users'] = list(excluded_users)
            await self.firebase_service.update_config(interaction.guild_id, config)
            logger.info(f"[DEBUG] Updated config with excluded users: {config}")
            
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
    async def include_user(self, interaction: discord.Interaction, user: discord.Member):
        """Include a user in DSM."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            if not config:
                config = {}

            excluded_users = set(self.ensure_str_ids(config.get('excluded_users', [])))
            if str(user.id) in excluded_users:
                excluded_users.remove(str(user.id))
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
    async def list_excluded(self, interaction: discord.Interaction):
        """List all excluded users."""
        try:
            config = await self.firebase_service.get_config(interaction.guild_id)
            logger.info(f"[DEBUG] Config for list_excluded: {config}")
            
            excluded_users = config.get('excluded_users', [])
            logger.info(f"[DEBUG] Raw excluded users from config: {excluded_users}")
            
            if excluded_users:
                excluded_members = []
                for user_id in excluded_users:
                    logger.info(f"[DEBUG] Processing user_id: {user_id} (type: {type(user_id)})")
                    try:
                        member = interaction.guild.get_member(int(user_id))
                        if member:
                            excluded_members.append(member.mention)
                            logger.info(f"[DEBUG] Found member: {member.name} ({member.id})")
                        else:
                            logger.info(f"[DEBUG] No member found for ID: {user_id}")
                    except ValueError as e:
                        logger.error(f"[DEBUG] Error converting user_id to int: {e}")
                        continue
                
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

    @app_commands.command(name="debug_todo", description="Debug TODO message processing")
    async def debug_todo(self, interaction: discord.Interaction, test_message: Optional[str] = None):
        """Debug TODO message processing to help identify issues."""
        try:
            # Defer the response to prevent timeout
            await interaction.response.defer(ephemeral=True)
            config = await self.firebase_service.get_config(interaction.guild_id)
            
            # Test the extract_tasks_from_message function
            if test_message:
                tasks = self.extract_tasks_from_message(test_message)
                embed = discord.Embed(
                    title="🔍 TODO Debug Results",
                    description=f"Testing message: `{test_message}`",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Extracted Tasks",
                    value="\n".join(tasks) if tasks else "No tasks found",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Show current configuration
            embed = discord.Embed(
                title="🔍 TODO Debug Information",
                color=discord.Color.blue()
            )
            
            # DSM Channel
            dsm_channel_id = config.get('dsm_channel_id')
            dsm_channel = interaction.guild.get_channel(int(dsm_channel_id)) if dsm_channel_id else None
            embed.add_field(
                name="DSM Channel",
                value=f"ID: {dsm_channel_id}\nChannel: {dsm_channel.mention if dsm_channel else 'Not found'}",
                inline=False
            )
            
            # Current channel
            embed.add_field(
                name="Current Channel",
                value=f"ID: {interaction.channel_id}\nChannel: {interaction.channel.mention}",
                inline=False
            )
            
            # Last DSM time and lookback
            last_dsm_time = config.get('last_dsm_time')
            if last_dsm_time:
                last_dsm_time = datetime.datetime.fromisoformat(last_dsm_time)
                lookback_hours = config.get('dsm_lookback_hours', 2)
                lookback_time = last_dsm_time - datetime.timedelta(hours=lookback_hours)
                dsm_deadline = last_dsm_time + datetime.timedelta(hours=12)
                embed.add_field(
                    name="Time Windows",
                    value=f"Last DSM: {last_dsm_time}\nLookback: {lookback_hours} hours\nLookback Period: {lookback_time} to {last_dsm_time}\nDSM Period: {last_dsm_time} to {dsm_deadline}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Time Windows",
                    value="No last DSM time found",
                    inline=False
                )
            
            # TODO message map
            todo_message_map = config.get('todo_message_map', {})
            embed.add_field(
                name="TODO Message Map",
                value=f"Users with TODOs: {len(todo_message_map)}\nTotal messages: {sum(len(messages) for messages in todo_message_map.values())}",
                inline=False
            )
            
            # Excluded users
            excluded_users = config.get('excluded_users', [])
            excluded_mentions = []
            for user_id in excluded_users:
                member = interaction.guild.get_member(int(user_id))
                excluded_mentions.append(member.mention if member else f"<@{user_id}>")
            embed.add_field(
                name="Excluded Users",
                value="\n".join(excluded_mentions) if excluded_mentions else "None",
                inline=False
            )
            
            # Test message processing
            test_content = """TODO
Task 1: Test task
Task 2: Another test task

Regular message content"""
            
            tasks = self.extract_tasks_from_message(test_content)
            embed.add_field(
                name="Test Message Processing",
                value=f"Test content:\n```\n{test_content}\n```\nExtracted tasks:\n" + "\n".join([f"• {task}" for task in tasks]),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in debug_todo: {e}")
            await interaction.response.send_message(f"Error during debug: {e}", ephemeral=True)

# Move setup function outside of the class, at module level
async def setup(bot: commands.Bot):
    """Setup function for the DSM cog."""
    from services.firebase_service import FirebaseService
    
    # Firebase service now uses environment variables exclusively
    firebase_service = FirebaseService()
    await bot.add_cog(DSM(bot, firebase_service))