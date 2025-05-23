import asyncio
import datetime
import pytz
import logging
from discord.ext import tasks

class AutoDSMService:
    def __init__(self, bot, firebase_service, create_dsm_callback):
        self.bot = bot
        self.firebase_service = firebase_service
        self.create_dsm_callback = create_dsm_callback  # Should be an async function: (channel, config, is_automatic)
        self.logger = logging.getLogger("auto_dsm_service")
        self.task = None

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run())
            self.logger.info("AutoDSMService started.")

    async def run(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.logger.info(f"[{current_time}] AutoDSMService running...")
                for guild in self.bot.guilds:
                    config = await self.firebase_service.get_config(guild.id)
                    if not config:
                        self.logger.debug(f"No config found for guild {guild.id}")
                        continue
                    dsm_time = config.get('dsm_time')
                    if not dsm_time:
                        self.logger.debug(f"No DSM time configured for guild {guild.id}")
                        continue
                    tz_str = config.get('timezone', 'UTC')
                    try:
                        tz = pytz.timezone(tz_str)
                    except pytz.exceptions.UnknownTimeZoneError:
                        self.logger.error(f"Invalid timezone {tz_str} for guild {guild.id}, defaulting to UTC")
                        tz = pytz.UTC
                    now = datetime.datetime.now(tz)
                    try:
                        hour, minute = map(int, dsm_time.split(':'))
                        dsm_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except ValueError:
                        self.logger.error(f"Invalid DSM time format {dsm_time} for guild {guild.id}")
                        continue
                    self.logger.info(
                        f"[{current_time}] DSM Check for guild {guild.id}:\n"
                        f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                        f"DSM time: {dsm_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                        f"Timezone: {tz_str}\n"
                        f"Time difference: {abs((now - dsm_datetime).total_seconds())} seconds"
                    )
                    time_diff = abs((now - dsm_datetime).total_seconds())
                    if time_diff <= 60:
                        self.logger.info(f"Time check passed for guild {guild.id} (difference: {time_diff} seconds)")
                        latest_dsm = config.get('latest_dsm_thread', {})
                        if isinstance(latest_dsm, dict):
                            latest_date = latest_dsm.get('date')
                            if latest_date == now.strftime('%Y-%m-%d'):
                                self.logger.info(f"DSM already created today for guild {guild.id} at {latest_date}")
                                continue
                        channel_id = config.get('dsm_channel_id')
                        if not channel_id:
                            self.logger.warning(f"No DSM channel configured for guild {guild.id}")
                            continue
                        channel = guild.get_channel(int(channel_id))
                        if not channel:
                            self.logger.warning(f"DSM channel {channel_id} not found in guild {guild.id}")
                            continue
                        self.logger.info(
                            f"Creating automatic DSM for guild {guild.id}\n"
                            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                            f"Channel: {channel.name} ({channel.id})"
                        )
                        await self.create_dsm_callback(channel, config, True)
                        self.logger.info(f"Automatic DSM created in guild {guild.id}")
                    else:
                        self.logger.debug(
                            f"Time check not passed for guild {guild.id}\n"
                            f"Current time: {now.strftime('%H:%M:%S')}\n"
                            f"Target time: {dsm_datetime.strftime('%H:%M:%S')}\n"
                            f"Difference: {time_diff} seconds"
                        )
            except Exception as e:
                self.logger.error(f"Error in AutoDSMService: {str(e)}", exc_info=True)
            await asyncio.sleep(60) 