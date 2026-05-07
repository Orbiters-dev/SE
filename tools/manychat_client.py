"""ManyChat API Client for GROSMIMI JP Instagram.

Usage:
    python tools/manychat_client.py page-info
    python tools/manychat_client.py find-name "みき"
    python tools/manychat_client.py get-subscriber 12345678
    python tools/manychat_client.py send-content 12345678 "メッセージ本文"
    python tools/manychat_client.py tags
    python tools/manychat_client.py fields
"""
import argparse
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except Exception:
    pass

API_BASE = 'https://api.manychat.com/fb'
API_KEY = os.environ.get('MANYCHAT_API_KEY_JP', '')


def _headers():
    return {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}


def _get(endpoint, params=None):
    resp = requests.get(f'{API_BASE}{endpoint}', headers=_headers(), params=params, timeout=15)
    return resp.json()


def _post(endpoint, data=None):
    resp = requests.post(f'{API_BASE}{endpoint}', headers=_headers(), json=data, timeout=15)
    return resp.json()


def page_info():
    return _get('/page/getInfo')


def find_by_name(name, limit=20):
    return _get('/subscriber/findByName', {'name': name, 'limit': limit})


def get_subscriber(subscriber_id):
    return _get('/subscriber/getInfo', {'subscriber_id': subscriber_id})


def get_tags():
    return _get('/page/getTags')


def get_fields():
    return _get('/page/getBotFields')


def get_widgets():
    return _get('/page/getWidgets')


def send_content(subscriber_id, text):
    return _post('/sending/sendContent', {
        'subscriber_id': int(subscriber_id),
        'data': {'version': 'v2', 'content': {'messages': [{'type': 'text', 'text': text}]}},
        'message_tag': 'ACCOUNT_UPDATE',
    })


def send_flow(subscriber_id, flow_ns):
    return _post('/sending/sendFlow', {
        'subscriber_id': int(subscriber_id),
        'flow_ns': flow_ns,
    })


def add_tag(subscriber_id, tag_id):
    return _post('/subscriber/addTag', {
        'subscriber_id': int(subscriber_id),
        'tag_id': int(tag_id),
    })


def set_custom_field(subscriber_id, field_id, value):
    return _post('/subscriber/setCustomField', {
        'subscriber_id': int(subscriber_id),
        'field_id': int(field_id),
        'field_value': value,
    })


def main():
    parser = argparse.ArgumentParser(description='ManyChat API Client — GROSMIMI JP')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('page-info', help='Get page info')
    p_find = sub.add_parser('find-name', help='Find subscriber by name')
    p_find.add_argument('name')
    p_get = sub.add_parser('get-subscriber', help='Get subscriber details')
    p_get.add_argument('subscriber_id')
    sub.add_parser('tags', help='List tags')
    sub.add_parser('fields', help='List custom fields')
    sub.add_parser('widgets', help='List widgets')
    p_send = sub.add_parser('send-content', help='Send message to subscriber')
    p_send.add_argument('subscriber_id')
    p_send.add_argument('text')
    p_flow = sub.add_parser('send-flow', help='Trigger flow for subscriber')
    p_flow.add_argument('subscriber_id')
    p_flow.add_argument('flow_ns')
    p_tag = sub.add_parser('add-tag', help='Add tag to subscriber')
    p_tag.add_argument('subscriber_id')
    p_tag.add_argument('tag_id')

    args = parser.parse_args()

    if not API_KEY:
        print('ERROR: MANYCHAT_API_KEY_JP not set in .env')
        sys.exit(1)

    commands = {
        'page-info': lambda: page_info(),
        'find-name': lambda: find_by_name(args.name),
        'get-subscriber': lambda: get_subscriber(args.subscriber_id),
        'tags': lambda: get_tags(),
        'fields': lambda: get_fields(),
        'widgets': lambda: get_widgets(),
        'send-content': lambda: send_content(args.subscriber_id, args.text),
        'send-flow': lambda: send_flow(args.subscriber_id, args.flow_ns),
        'add-tag': lambda: add_tag(args.subscriber_id, args.tag_id),
    }

    if args.command in commands:
        result = commands[args.command]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
