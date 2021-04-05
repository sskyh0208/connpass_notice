from datetime import datetime, timezone
import os

import boto3
import requests

from models import Connpass, NoticeTable, LineNotice, TwitterNotice

KEYWORD = os.environ.get('KEYWORD')

PARAMS = {
    # イベント開催年月
    'ym': format(datetime.now(timezone.utc), "%Y%m"),
    # 検索結果の表示順 1:更新日時準 2:開催日時準 3:新着順
    'oder': '2',
    # 取得件数
    'count': '100',
    # 検索キーワード
    'keyword': KEYWORD
}

def lambda_handler(event, context):
    connpass = Connpass()
    # イベント情報取得
    events = connpass.get_event_data(PARAMS)

    # イベント情報用テーブル
    table = NoticeTable()

    # 既に通知済みのイベントを削除する
    event_ids = table.get_event_ids()
    for id in event_ids:
        if events.get(id):
            del events[id]

    # LINE通知
    line_notice = LineNotice()
    results = line_notice.send(events)

    # Twitterツイート
    twitter_notice = TwitterNotice()
    twitter_notice.send(events)

    # 通知結果保存
    table.save_items(results)

    # 現在時以前の通知結果を削除
    table.delete_items()
