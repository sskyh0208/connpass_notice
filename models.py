from abc import ABCMeta, abstractmethod
from datetime import datetime, timezone
import os

import boto3
import requests
from twitter import Twitter, OAuth

today = datetime.now(timezone.utc)

TABLE_NAME = os.environ.get('TABLE_NAME')

# LINE Notify
LINE_TOKEN = os.environ.get('LINE_TOKEN')
LINE_API_URL = os.environ.get('LINE_API_URL')

# Twitter API
TWITTER_ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
TWITTER_API_KEY = os.environ.get('TWITTER_API_KEY')
TWITTER_API_SECRET = os.environ.get('TWITTER_API_SECRET')

class Connpass:
    def __init__(self):
        self.url = 'https://connpass.com/api/v1/event?{}'

    def get_event_data(self, params: dict) -> dict:
        url = self.generate_request_url(params)
        # リクエスト
        res = requests.get(url).json()

        # key:イベントID value:イベント情報 の辞書を作成
        events_dict = {}
        events_dict = {str(event['event_id']):event for event in res['events']}

        return self.delete_past_event_ids(events_dict)

    def generate_request_url(self, params: dict) -> str:
        params_text = ''
        for k, v in params.items():
            # パラメータ=値&　の形でつなげる
            params_text += f'{k}={v}&'
        # 最後の&を削除して戻す
        return self.url.format(params_text)
    
    def delete_past_event_ids(self, events: dict) -> dict:
        new_events = {}
        for id, event in events.items():
            event_dt = datetime.strptime(event['started_at'], '%Y-%m-%dT%H:%M:%S%z')
            if today <= event_dt:
                new_events[id] = event
        return new_events


class NoticeTable:
    def __init__(self):
        dynamo_db = boto3.resource('dynamodb')
        table = dynamo_db.Table(TABLE_NAME)
        self.table = table
        self.items = table.scan()['Items']

    def get_event_ids(self):
        return [item['Id'] for item in self.items]
 
    def save_items(self, events: dict):
        with self.table.batch_writer() as batch:
            for id, event in events.items():
                batch.put_item(
                    Item={
                        'Id': str(id),
                        'Start': event['started_at']
                    }
                )

    def delete_items(self):
        delete_ids = []
        for item in self.items:
            item_dt = datetime.strptime(item['Start'], '%Y-%m-%dT%H:%M:%S%z')
            if item_dt <= today:
                delete_ids.append(item['Id'])

        for id in delete_ids:
            response = table.delete_item(Key={'Id': id}
            )
            print(id, response['ResponseMetadata']['HTTPStatusCode'])


class Notice(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def send(self):
        pass

    def generate_message(self, event: dict) -> str:
        # 文字列をdatetime型へ変換
        start = datetime.strptime(event['started_at'], '%Y-%m-%dT%H:%M:%S%z')
        end = datetime.strptime(event['ended_at'], '%Y-%m-%dT%H:%M:%S%z')

        # 曜日を表示用文字列へ変換
        week_day = {0: '月', 1: '火', 2: '水', 3: '木', 4: '金', 5: '土', 6: '日'}
        start_weekday = week_day[start.weekday()]
        end_weekday = week_day[end.weekday()]

        # 日付を表示用文字列へ変換
        start_date = f'{start.year}年{start.month}月{start.day}日({start_weekday})'
        end_date = f'{end.year}年{end.month}月{end.day}日({end_weekday})'

        # 時間を表示用文字列へ変換
        end_time = format(end, '%H:%M')
        start_time = format(start, '%H:%M')

        # 開催日時の表示文字列をイベントの日程で変更
        if start.day == end.day:
            # 終了日が開催日と同じ日の場合
            dt = f'{start_date} {start_time} ~ {end_time}'
        else:
            # 終了日が開催日翌日以降の場合
            dt = (
                f'{start_date} {start_time} ~ \n'
                f'    {end_date} {end_time}\n'
            )

        return (
            '\n'
            '【タイトル】\n'
            f'{event["title"]}\n'
            '\n'
            '【日時】\n'
            f'{dt}\n'
            '\n'
            '【場所】\n'
            f'{event["address"]}\n'
            '\n'
            '【会場】\n'
            f'{event["place"]}\n'
            '\n'
            '【定員】\n'
            f'{event["limit"]}\n'
            '\n'
            '【ハッシュタグ】\n'
            f'#{event["hash_tag"]}'
            '\n'
            f'{event["event_url"]}'
        )


class LineNotice(Notice):
    def __init__(self):
        self.token = LINE_TOKEN
        self.url = LINE_API_URL

    def send(self, events: dict):
        results = {}
        if events:
            # イベントの数だけ内容を送信
            for id, event in events.items():
                send_contents = self.generate_message(event)
                token_dict = {'Authorization': 'Bearer' + ' ' + self.token}
                send_dict = {'message': send_contents}

                res = requests.post(self.url, headers=token_dict, data=send_dict)

                if res.status_code == 200:
                    results[id] = event
                else:
                    print(res.status_code, id)
        else:
            # イベント情報なしとだけ送信
            send_contents = '\n新着イベント情報なし'
            token_dict = {'Authorization': 'Bearer' + ' ' + self.token}
            send_dict = {'message': send_contents}

            res = requests.post(self.url, headers=token_dict, data=send_dict)
        return results


class TwitterNotice(Notice):
    def __init__(self):
        self.api_key = TWITTER_API_KEY
        self.api_secret = TWITTER_API_SECRET
        self.access_token = TWITTER_ACCESS_TOKEN
        self.access_token_secret = TWITTER_ACCESS_TOKEN_SECRET
    
    def send(self, events):
        twitter = Twitter(
            auth=OAuth(
                self.access_token,
                self.access_token_secret,
                self.api_key,
                self.api_secret
            )
        )

        if events:
            # イベントの数だけ内容を送信
            for id, event in events.items():
                send_contents = self.generate_message(event)
                status_update = twitter.statuses.update(status=send_contents)
        else:
            # イベント情報なしとだけ送信
            send_contents = (
                '\n'
                '新着イベント情報なし'
            )
            status_update = twitter.statuses.update(status=send_contents)