import asyncio
from datetime import datetime, timedelta, timezone
from json.decoder import JSONDecodeError

import discord
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

from userconfig import (daily_notice_hour, discord_channel, discord_token,
                        notice_margin)

# タイムゾーン
JST = timezone(timedelta(hours=+9), 'JST')


def format_datetime(dt):
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    day_of_week = weekdays[dt.weekday()]

    if dt.second == 0:
        return f'{dt.year}年{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分'
    else:
        return f'{dt.year}年{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分{dt.second}秒'


async def wait(event):
    now = datetime.now(JST)
    diff = event.time() - now
    wait_sec = int(diff.total_seconds()) - notice_margin

    if wait_sec > 600:
        wait_to = now + timedelta(seconds=600)
        print(f'{now} から {wait_to} まで、600 秒待機します')
        await asyncio.sleep(600)
        return False
    elif wait_sec <= 0:
        False
    else:
        wait_to = event.time() - timedelta(seconds=notice_margin)
        print(f'Waiting for {wait_sec} from {now} to {wait_to}.')

        await asyncio.sleep(wait_sec)
        return True


class EventInfo:
    def __init__(self, event_type, duration=None, api_url=None):
        self.name = event_type
        self.duration = duration
        self.url = api_url

    def update(self):
        if self.url is None:
            now = datetime.now(JST)
            if (now + timedelta(seconds=notice_margin)).hour < daily_notice_hour:
                dt = datetime(now.year, now.month, now.day, daily_notice_hour, 0, 0)
            else:
                tomorrow = now + timedelta(days=1)
                dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, daily_notice_hour, 0, 0)

        else:
            try:
                r = requests.get(self.url, timeout=9.0)
                data = r.json()
                dt = datetime.fromtimestamp(data['estimate'] // 1000)
            except Timeout:
                print(f'Connecting to {self.url} was timeout.')
                return True
            except ConnectionError:
                print(f'Connecting to {self.url} was failed.')
            except HTTPError:
                print(f'{self.url} response is invalid.')
            except JSONDecodeError:
                print('Failed to load json.')
                return True

        dt = dt.astimezone(JST)
        self.event_time = dt
        return False

    def time(self):
        return self.event_time

    async def notify(self, timers):
        channel = client.get_channel(discord_channel)
        if self.name == 'daily':
            timers = [event for event in timers if event.name != 'daily']
            text = '次回のイベント開始時刻をお知らせします。'

            for event in timers:
                time = self._format_datetime(event.time())
                text += f'\n{event.name}: {time}'

            prev_message = await channel.history(limit=1).flatten()
            if text == prev_message[0].content:
                print('The written massage is the same as the previous message.')
                return

        else:
            time = self._format_datetime(self.event_time)
            texts = {
                'New Year': f'New Year\'s Day が10分後から始まります\n期間: {time} から1時間',
                'Traveling Zoo': f'Traveling Zoo が10分後から始まります\n期間: {time} から1時間',
                'Spooky Festival': f'Spooky Festival が10分後から始まります\n期間: {time} から1時間',
                'Winter Event': f'Winter Event が10分後から始まります\n期間: {time} から1時間'
            }

            text = texts[self.name]

        print('----')
        print(text)
        print('----')
        print('Sending a message...')
        await channel.send(text)


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # create the background task and run it in the background
        self.bg_task = self.loop.create_task(self.timer())

    async def on_ready(self):
        print(f'Logged in as {self.user.name}.')
        print('------')

    async def timer(self):
        await self.wait_until_ready()
        await asyncio.sleep(1)
        timers = [
            EventInfo('daily'),
            EventInfo('New Year', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/newyear/estimate'),
            EventInfo('Traveling Zoo', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/zoo/estimate'),
            EventInfo('Spooky Festival', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/spookyFestival/estimate'),
            EventInfo('Winter Event', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/winter/estimate')
        ]

        while not self.is_closed():
            for event in timers:
                while event.update():
                    pass

            print('Got the events time.')

            timers = sorted(timers, key=lambda i: i.time())
            next_event = timers[0]
            print(f'The next event is {next_event.name} at {next_event.time()}.')

            if await wait(next_event):
                await next_event.notify(timers)


if __name__ == '__main__':
    print(f'Daily notification time: {daily_notice_hour}')
    print(f'Number of seconds of notification time before starting the event: {notice_margin}')
    print('------')
    client = MyClient()
    client.run(discord_token)
