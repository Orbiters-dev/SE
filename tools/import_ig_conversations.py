"""Import all IG DM participants from @grosmimi_japan into Django CRM.

Modes:
  --check         : verify token + capability + IG-Page link (read-only, no fetch)
  --dry-run       : fetch all conversations, extract handles, compare with Django CRM,
                    print counts (NEW vs EXISTING). No POST.
  --commit        : same as --dry-run + actually POST new creators to Django CRM.

Source tag: 'ig_conversations_import'
Status for new: 'Not Started'

Requires:
  META_ACCESS_TOKEN (.env) — must have instagram_business_manage_messages capability
  Django CRM API: https://orbitools.orbiters.co.kr/api/onzenna/pipeline/creators/
                  Auth: Basic admin:admin (env ORBITOOLS_USER/PASS)
"""
import os
import sys
import json
import time
import argparse
import urllib.parse
import urllib.request
import urllib.error
from base64 import b64encode
from typing import Iterable
from dotenv import load_dotenv

load_dotenv('.env')

GRAPH = 'https://graph.facebook.com/v21.0'
GROSIMI_PAGE_ID = '633086096548958'  # FB Page "Grosimimi Japan"
DJANGO_BASE = 'https://orbitools.orbiters.co.kr'
SOURCE_TAG = 'ig_conversations_import'


def http_get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def http_post(url: str, body: dict, headers: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    h = {'Content-Type': 'application/json', **headers}
    req = urllib.request.Request(url, data=data, headers=h, method='POST')
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def get_page_access_token(user_token: str) -> tuple[str, str]:
    """Return (page_access_token, ig_user_id) for Grosimimi Japan FB Page."""
    url = (
        f'{GRAPH}/me/accounts'
        f'?fields=name,id,instagram_business_account{{id,username}},access_token'
        f'&access_token={urllib.parse.quote(user_token)}'
    )
    d = http_get(url)
    for p in d.get('data', []):
        if p.get('id') == GROSIMI_PAGE_ID:
            igb = p.get('instagram_business_account') or {}
            return p.get('access_token', ''), igb.get('id', '')
    raise RuntimeError(f'Grosimimi Japan page (id={GROSIMI_PAGE_ID}) not found in /me/accounts')


def fetch_all_conversations(page_token: str, ig_user_id: str) -> list[dict]:
    """Paginate /me/conversations and return all entries with participant info."""
    convos = []
    next_url = (
        f'{GRAPH}/me/conversations'
        f'?platform=instagram'
        f'&fields=id,updated_time,participants'
        f'&limit=100'
        f'&access_token={urllib.parse.quote(page_token)}'
    )
    while next_url:
        d = http_get(next_url)
        convos.extend(d.get('data', []))
        next_url = (d.get('paging') or {}).get('next', '')
        if next_url:
            time.sleep(0.3)  # gentle pagination
    return convos


def extract_handles(conversations: list[dict], own_ig_id: str) -> list[dict]:
    """Return list of {ig_handle, igsid} for the *other* participant in each conversation."""
    out = []
    seen = set()
    for c in conversations:
        parts = ((c.get('participants') or {}).get('data')) or []
        for p in parts:
            pid = str(p.get('id', ''))
            if pid == str(own_ig_id):
                continue
            handle = (p.get('username') or '').strip().lower()
            if not handle or handle in seen:
                continue
            seen.add(handle)
            out.append({
                'ig_handle': handle,
                'igsid': pid,
                'name': p.get('name', ''),
                'updated_time': c.get('updated_time', ''),
                'conversation_id': c.get('id', ''),
            })
    return out


def fetch_existing_handles_django(auth_header: str) -> set[str]:
    """Fetch all existing JP creators from Django CRM, return set of lowercased ig_handles."""
    handles = set()
    page = 1
    while True:
        url = f'{DJANGO_BASE}/api/onzenna/pipeline/creators/?region=jp&page={page}&page_size=200'
        try:
            d = http_get(url, headers={'Authorization': auth_header})
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            raise
        results = d.get('results') or d.get('creators') or d.get('data') or []
        if not results:
            break
        for c in results:
            h = (c.get('ig_handle') or '').strip().lower()
            if h:
                handles.add(h)
        if not d.get('next'):
            break
        page += 1
    return handles


def post_new_creator(auth_header: str, handle: str, igsid: str, name: str) -> tuple[int, dict]:
    body = {
        'ig_handle': handle,
        'platform': 'instagram',
        'region': 'jp',
        'pipeline_status': 'Not Started',
        'source': SOURCE_TAG,
        'sources': [SOURCE_TAG],
        'full_name': name or '',
        'manychat_id': igsid or '',
    }
    return http_post(
        f'{DJANGO_BASE}/api/onzenna/pipeline/creators/',
        body,
        {'Authorization': auth_header},
    )


def cmd_check(user_token: str) -> int:
    print('=== Token user ===')
    me = http_get(f'{GRAPH}/me?fields=id,name&access_token={urllib.parse.quote(user_token)}')
    print(f'  {me}')
    print()
    print('=== Grosimimi Japan FB Page IG link ===')
    page_url = (
        f'{GRAPH}/{GROSIMI_PAGE_ID}'
        f'?fields=name,instagram_business_account{{id,username}}'
        f'&access_token={urllib.parse.quote(user_token)}'
    )
    p = http_get(page_url)
    print(f'  {p}')
    igb = p.get('instagram_business_account')
    if not igb:
        print('  ERROR: IG biz account not linked yet (cache or permission). Cannot proceed.')
        return 1
    print()
    print('=== Conversations capability test (1 call, limit=1) ===')
    page_tok, ig_id = get_page_access_token(user_token)
    test_url = (
        f'{GRAPH}/me/conversations?platform=instagram&limit=1'
        f'&access_token={urllib.parse.quote(page_tok)}'
    )
    try:
        r = http_get(test_url)
        cnt = len(r.get('data', []))
        print(f'  OK. Returned {cnt} conversation. Has next page: {bool((r.get("paging") or {}).get("next"))}')
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  HTTP {e.code}: {body[:300]}')
        if '#3' in body or 'capability' in body:
            print('  -> App still missing "Instagram Messaging" use case. wjcho action needed.')
        return 2


def cmd_run(user_token: str, commit: bool) -> int:
    user = os.environ.get('ORBITOOLS_USER', 'admin')
    pwd = os.environ.get('ORBITOOLS_PASS', 'admin')
    auth = 'Basic ' + b64encode(f'{user}:{pwd}'.encode()).decode()

    print('Step 1: get page access token + IG user id')
    page_tok, ig_id = get_page_access_token(user_token)
    if not ig_id:
        print('  ERROR: IG biz account id missing')
        return 1
    print(f'  ig_user_id={ig_id}, page_token_len={len(page_tok)}')

    print('Step 2: fetch all conversations (paginating)')
    convos = fetch_all_conversations(page_tok, ig_id)
    print(f'  conversations: {len(convos)}')

    print('Step 3: extract unique IG handles')
    handles = extract_handles(convos, ig_id)
    print(f'  unique handles: {len(handles)}')

    print('Step 4: fetch existing Django CRM handles (region=jp)')
    existing = fetch_existing_handles_django(auth)
    print(f'  existing: {len(existing)}')

    print('Step 5: classify')
    new_ones = [h for h in handles if h['ig_handle'] not in existing]
    dup_ones = [h for h in handles if h['ig_handle'] in existing]
    print(f'  NEW (will INSERT): {len(new_ones)}')
    print(f'  EXISTING (skip):   {len(dup_ones)}')

    # save artifact for review
    out_path = f'.tmp/ig_conversations_extract_{int(time.time())}.json'
    os.makedirs('.tmp', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_conversations': len(convos),
            'unique_handles': len(handles),
            'new': new_ones,
            'existing_count': len(dup_ones),
        }, f, ensure_ascii=False, indent=2)
    print(f'  saved: {out_path}')

    if not commit:
        print()
        print('DRY RUN finished. No POST. Sample of NEW (up to 10):')
        for h in new_ones[:10]:
            print(f'  - @{h["ig_handle"]:<25} igsid={h["igsid"]} name={h["name"][:20]}')
        return 0

    print()
    print(f'Step 6: COMMIT — POST {len(new_ones)} new creators to Django CRM')
    ok = err = 0
    for i, h in enumerate(new_ones, 1):
        status, body = post_new_creator(auth, h['ig_handle'], h['igsid'], h['name'])
        if status in (200, 201):
            ok += 1
        else:
            err += 1
            print(f'  [{i}] @{h["ig_handle"]} FAIL {status}: {str(body)[:200]}')
        if i % 50 == 0:
            print(f'  progress: {i}/{len(new_ones)} (ok={ok} err={err})')
    print(f'  done. ok={ok} err={err}')
    return 0 if err == 0 else 3


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--commit', action='store_true')
    args = ap.parse_args()

    tok = os.environ.get('META_ACCESS_TOKEN', '')
    if not tok:
        print('ERROR: META_ACCESS_TOKEN missing in .env')
        return 1

    if args.check:
        return cmd_check(tok)
    return cmd_run(tok, commit=args.commit)


if __name__ == '__main__':
    sys.exit(main())
