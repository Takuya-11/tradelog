#!/usr/bin/env python3
"""
TradeLog build script
  1. Generate today's briefing (Yahoo Finance + RSS, no AI)
  2. Read all .md files → briefings.json  (embedded into static site)
  3. Read latest buzz file → buzz.json
Run this before git push, or let auto_deploy.sh handle it.
"""
import sys, os, json, glob, datetime

# Reuse generation logic from server.py
sys.path.insert(0, os.path.dirname(__file__))
from server import fetch_all_quotes, fetch_news, build_md, BRIEFING_DIR

def generate_today():
    today = datetime.date.today().strftime('%Y-%m-%d')
    filename = f'{today}-morning-briefing.md'
    path = os.path.join(os.path.expanduser(BRIEFING_DIR), filename)

    if os.path.exists(path):
        print(f'[build] {filename} already exists — skipping generation')
        return filename

    print('[build] Fetching market quotes...')
    quotes = fetch_all_quotes()
    print('[build] Fetching news...')
    news = fetch_news()
    print(f'[build] Got {len(news)} news items')

    md = build_md(quotes, news)
    os.makedirs(os.path.expanduser(BRIEFING_DIR), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'[build] Generated {filename}')
    return filename

def build_briefings_json():
    briefing_dir = os.path.expanduser(BRIEFING_DIR)
    files = sorted(glob.glob(os.path.join(briefing_dir, '*.md')), reverse=True)

    result = []
    for f in files:
        name = os.path.basename(f)
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        first_line = content.splitlines()[0].lstrip('# ').strip() if content else name
        result.append({
            'file':    name,
            'title':   first_line,
            'mtime':   int(os.path.getmtime(f)),
            'content': content,
        })

    out_path = os.path.join(os.path.dirname(__file__), 'briefings.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'[build] briefings.json written ({len(result)} entries, {os.path.getsize(out_path)//1024}KB)')

BUZZ_DIR = '~/dev/x-posts/buzz'

def build_buzz_json():
    buzz_dir = os.path.expanduser(BUZZ_DIR)
    files = sorted(glob.glob(os.path.join(buzz_dir, '*.md')), reverse=True)

    result = []
    for f in files:
        name = os.path.basename(f)
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        first_line = content.splitlines()[0].lstrip('# ').strip() if content else name
        result.append({
            'file':    name,
            'title':   first_line,
            'mtime':   int(os.path.getmtime(f)),
            'content': content,
        })

    out_path = os.path.join(os.path.dirname(__file__), 'buzz.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    count = len(result)
    size = os.path.getsize(out_path) // 1024
    print(f'[build] buzz.json written ({count} entries, {size}KB)')

if __name__ == '__main__':
    generate_today()
    build_briefings_json()
    build_buzz_json()
    print('[build] Done.')
