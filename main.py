import asyncio
import os
from datetime import datetime, timedelta, timezone
from json.decoder import JSONDecodeError

import discord
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout


# configs: change it if you want
daily_notice_hour = 8
notice_margin = timedelta(minutes=10)
discord_token = os.environ['DISCORD_TOKEN']
discord_channel = os.environ['DISCORD_CHANNEL']
TZ = timezone(timedelta(hours=+9), 'JST')


class EventInfo:
    def __init__(self, event_type: str, duration: timedelta = None, api_url: str = None):
        self.name = event_type
        self.duration = duration
        self.url = api_url

    def update(self) -> bool:
        '''
        Update the event time.

        Returns:
            bool: Return True if update is failed, return False if update is successful.
        '''
        if self.name == 'daily':
            now = datetime.now(TZ)

            if (now + notice_margin).hour < daily_notice_hour:  # Today's daily notice time was passed.
                # set today, daily notice hour
                dt = datetime(now.year, now.month, now.day, daily_notice_hour, tzinfo=TZ)
            else:  # Today's daily notice time was not passed yet.
                # set tomorrow, daily notice hour
                tomorrow = now + timedelta(days=1)
                dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, daily_notice_hour, tzinfo=TZ)

        else:
            try:
                r = requests.get(self.url, timeout=9.0)

                if r.status_code == 200:
                    data = r.json()
                    dt = datetime.fromtimestamp(data['estimate'] // 1000, TZ)
                else:
                    print(f'{self.url} response is {r.status_code}.')
                    return True

            except Timeout:
                print(f'Connecting to {self.url} was timeout.')
                return True
            except ConnectionError:
                print(f'Connecting to {self.url} was failed.')
                return True
            except HTTPError:
                print(f'{self.url} response is invalid.')
                return True
            except JSONDecodeError:
                print('Failed to load json.')
                return True

        self.time = dt
        return False

    async def notify(self, timers: list):
        channel = client.get_channel(discord_channel)
        if self.name == 'daily':
            timers = [event for event in timers if event.name != 'daily']
            text = '次回のイベント開始時刻をお知らせします。'  # means "Notifies the time of the next event."

            for event in timers:
                time = format_datetime(event.time)
                text += f'\n{event.name}: {time}'

            prev_message = await channel.history(limit=1).flatten()
            if text == prev_message[0].content:
                print('The written massage is the same as the previous message!')
                return

        else:
            s_time = format_datetime(self.time)
            e_time = format_datetime(self.time + self.duration)
            start_in = timedelta(notice_margin).seconds / 60
            # Notify massage of each events.
            # means "(event name) will be start in (start_in) minutes."
            texts = {
                'New Year': f'New Year\'s Day が{start_in}分後から始まります\n{s_time} - {e_time}',
                'Traveling Zoo': f'Traveling Zoo が{start_in}分後から始まります\n{s_time} - {e_time}',
                'Spooky Festival': f'Spooky Festival が{start_in}分後から始まります\n期間: {s_time} - {e_time}',
                'Winter Event': f'Winter Event が{start_in}分後から始まります\n期間: {s_time} - {e_time}'
            }

            text = texts[self.name]

        print('----')
        print(text)
        print('----')
        print('Sending a message...')
        await channel.send(text)
        await print('Sent a message!')


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create the background task and run it in the background.
        self.bg_task = self.loop.create_task(self.timer())

    async def on_ready(self):
        print(f'Logged in as {self.user.name}.')
        print('------')

    async def timer(self):
        # Wait until bot is ready.
        await self.wait_until_ready()
        await asyncio.sleep(1)
        timers = [
            EventInfo('daily'),
            EventInfo('New Year', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/newyear/estimate'),
            EventInfo('Traveling Zoo', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/zoo/estimate'),
            EventInfo('Spooky Festival', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/spookyFestival/estimate'),
            EventInfo('Winter Event', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/winter/estimate')
        ]

        # Infinite loop as long as bot is running.
        while not self.is_closed():
            # Update all event timer.
            for event in timers:
                # event.update() returns True if error was occurred.
                while event.update():
                    pass

            print('Got the events time.')

            # Sort timers by event time.
            timers = sorted(timers, key=lambda i: i.time)
            next_event = timers[0]
            print(f'The next event is {next_event.name} at {next_event.time}.')

            # If event will be start in 10 minutes,
            if await wait(next_event):
                # Notify the event time.
                await next_event.notify(timers)


def format_datetime(dt: datetime) -> str:
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    day_of_week = weekdays[dt.weekday()]

    if dt.second == 0:
        return f'{dt.year}年{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分'
    else:
        return f'{dt.year}年{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分{dt.second}秒'


async def wait(event: EventInfo) -> bool:
    now = datetime.now(TZ)
    diff = event.time - now
    wait_sec = int((diff - notice_margin).total_seconds())

    if wait_sec > notice_margin.seconds + 600:
        wait_to = now + timedelta(seconds=600)
        print(f'Waiting for 600 seconds from {now} to {wait_to} for update the timers.')
        await asyncio.sleep(600)
        return False

    elif wait_sec <= 0:
        False

    else:
        wait_to = event.time - timedelta(seconds=notice_margin)
        print(f'Waiting for {wait_sec} seconds from {now} to {wait_to} for {event.name}.')

        await asyncio.sleep(wait_sec)
        return True


if __name__ == '__main__':
    print(f'Daily notification hour: {daily_notice_hour}')
    print(f'Number of seconds of notification time before starting the event: {notice_margin}')
    print('------')
    client = MyClient()
    client.run(discord_token)
