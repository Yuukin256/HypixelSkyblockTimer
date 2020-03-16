import asyncio
import os
from time import sleep
from datetime import time, datetime, timedelta, timezone
from json.decoder import JSONDecodeError

import discord
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout


# 設定: 必要に応じて変更
TZ = timezone(timedelta(hours=+9), 'JST')
notify_margin = timedelta(minutes=10)
update_interval = timedelta(minutes=10)
discord_token = os.environ['DISCORD_TOKEN']
discord_channel = int(os.environ['DISCORD_CHANNEL'])


class BaseEvent:
    def __init__(self, name: str):
        self.name = name

    async def wait(self) -> bool:
        '''
        イベントをお知らせする時刻が来るか、update_interval で指定した時間が経つまで待機する

        Returns:
            [bool]: イベントをお知らせする時刻が来たら True 、それ以外なら False

        '''

        now = datetime.now(TZ)
        diff = self.notify_time - now
        wait_sec = diff.total_seconds()

        if wait_sec > update_interval.seconds:  # 次のイベントの時間が update_interval より先の場合
            wait_to = now + update_interval
            print(f'イベント時刻再取得のため {now} から {wait_to} まで {update_interval.seconds} 秒待機します')
            await asyncio.sleep(update_interval.seconds)
            return False

        elif wait_sec <= 0:  # 次のイベントのお知らせ時刻を過ぎている場合
            print(f'{self.name} の時間が過ぎています！300 秒経過後、イベント時刻を再取得します。')
            await asyncio.sleep(300)
            return False

        else:
            wait_to = self.notify_time
            print(f'{self.name} のため {now} から {wait_to} まで {wait_sec} 秒待機します')

            await asyncio.sleep(wait_sec)
            return True

    def _format_datetime(self, dt: datetime) -> str:
        weekdays = ['月', '火', '水', '木', '金', '土', '日']
        day_of_week = weekdays[dt.weekday()]

        if dt.second == 0:
            return f'{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分'
        else:
            return f'{dt.month}月{dt.day}日 ({day_of_week}) {dt.hour}時{dt.minute}分{dt.second}秒'

    async def _send_message(self, text: str):
        channel = client.get_channel(discord_channel)

        if channel is None:
            print('送信先のチャンネルが見つかりませんでした')

        else:
            print('メッセージを送信します')
            prev_message = await channel.history(limit=1).flatten()
            if text == prev_message[0].content:
                print('前回のメッセージと同じ内容です！送信を中止します')

            else:
                print('------')
                print(text)
                print('------')
                print('送信中...')
                await channel.send(text)
                print('完了！')


class DailyEvent(BaseEvent):
    def __init__(self, name: str, set_time: time):
        super().__init__(name)
        self.set_time = set_time

    def update(self):
        now = datetime.now(TZ)
        now_ymd = (now.year, now.month, now.day)
        set_time_hms = (self.set_time.hour, self.set_time.minute, self.set_time.second)

        if now < datetime(*now_ymd, *set_time_hms, tzinfo=TZ):  # その日のお知らせ時刻をまだ過ぎていない場合
            self.time = datetime(*now_ymd, *set_time_hms, tzinfo=TZ)

        else:  # その日のお知らせ時刻を過ぎている場合
            tomorrow = now + timedelta(days=1)
            self.time = datetime(tomorrow.year, tomorrow.month, tomorrow.day, *set_time_hms, tzinfo=TZ)

        self.notify_time = self.time

    async def notify(self, timers: list):
        text = '次回のイベント開始時刻をお知らせします。'

        for event in [timer for timer in timers if timer.name != 'daily']:
            time = self._format_datetime(event.time)
            text += f'\n{event.name}: {time}'

        await self._send_message(text)


class GameEvent(BaseEvent):
    def __init__(self, name: str, duration: timedelta, api_url: str):
        super().__init__(name)
        self.duration = duration
        self.url = api_url

    def update(self):
        def _update_core(self):
            try:
                r = requests.get(self.url, timeout=1.0)

                if r.status_code == 200:
                    data = r.json()
                    dt = datetime.fromtimestamp(data['estimate'] // 1000, TZ)
                    self.time = dt
                    self.notify_time = dt - notify_margin
                    return True

                else:
                    print(f'{self.url} response is {r.status_code}.')
                    return False

            except Timeout:
                print(f'Connecting to {self.url} was timeout.')
                return False
            except ConnectionError:
                print(f'Connecting to {self.url} was failed.')
                return False
            except HTTPError:
                print(f'{self.url} response is invalid.')
                return False
            except JSONDecodeError:
                print('Failed to load json.')
                return False

        while not _update_core(self):
            sleep(1)

    async def notify(self):
        s_time = self._format_datetime(self.time)
        e_time = self._format_datetime(self.time + self.duration)
        start_in = int(notify_margin.total_seconds() / 60)

        texts = {
            'New Year': f'New Year\'s Day が{start_in}分後から始まります\n{s_time}～{e_time}',
            'Traveling Zoo': f'Traveling Zoo が{start_in}分後から始まります\n{s_time}～{e_time}',
            'Spooky Festival': f'Spooky Festival が{start_in}分後から始まります\n{s_time}～{e_time}',
            'Winter Event': f'Winter Event が{start_in}分後から始まります\n{s_time}～{e_time}'
        }
        text = texts[self.name]

        await self._send_message(text)


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # バックグラウンドタスクを作成、実行
        self.bg_task = self.loop.create_task(self.timer())

    async def on_ready(self):
        print(f'{self.user.name} でログインしました')
        print('------')

        # アクティビティを指定
        await self.change_presence(activity=discord.Activity(name='HypixelSkyblockTimer', type=discord.ActivityType.playing))

    async def timer(self):
        # Bot が起動 + 1 秒経過するまで待機
        await self.wait_until_ready()
        await asyncio.sleep(1)

        # Bot 起動中は無限ループ
        while not self.is_closed():
            timers = [
                DailyEvent('daily', time(hour=8, tzinfo=TZ)),
                GameEvent('New Year', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/newyear/estimate'),
                GameEvent('Traveling Zoo', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/zoo/estimate'),
                GameEvent('Spooky Festival', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/spookyFestival/estimate'),
                GameEvent('Winter Event', timedelta(hours=1), 'https://hypixel-api.inventivetalent.org/api/skyblock/winter/estimate')
            ]

            # 全タイマーを再取得
            for timer in timers:
                timer.update()

            print('イベント時刻を取得しました')

            # タイマーを時間順で並び替え
            timers = sorted(timers, key=lambda i: i.notify_time)
            next_event = timers[0]
            print(f'次のイベントは {next_event.name} {next_event.time} です')

            if await next_event.wait():
                if isinstance(next_event, DailyEvent):
                    await next_event.notify(timers)
                else:
                    await next_event.notify()

            print('------')


if __name__ == '__main__':
    print('Discord にログイン中...')
    client = MyClient()
    client.run(discord_token)
