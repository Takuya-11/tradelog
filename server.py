#!/usr/bin/env python3
"""TradeLog server — static file server + briefing auto-generation (no AI, no API key)"""
import http.server, json, os, glob, datetime, urllib.request, urllib.error, time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs

PORT = 7879
BRIEFING_DIR = os.path.expanduser('~/dev/tradesearch')
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Yahoo Finance data fetch ─────────────────────────────────────
SYMBOLS = {
    'dow':    '^DJI',
    'sp500':  '^GSPC',
    'nasdaq': '^IXIC',
    'sox':    '^SOX',
    'usdjpy': 'JPY=X',
    'nikkei': '^N225',
}

def fetch_quote(symbol):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?interval=1d&range=5d')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        result = data['chart']['result'][0]
        closes = [c for c in result['indicators']['quote'][0]['close'] if c is not None]
        meta = result['meta']
        curr = closes[-1] if closes else meta.get('regularMarketPrice', 0)
        prev = closes[-2] if len(closes) >= 2 else meta.get('previousClose', curr)
        change = curr - prev
        pct = (change / prev * 100) if prev else 0
        return {'price': curr, 'prev': prev, 'change': change, 'pct': pct, 'ok': True}
    except Exception as e:
        return {'price': 0, 'prev': 0, 'change': 0, 'pct': 0, 'ok': False, 'err': str(e)}

def fetch_all_quotes():
    result = {}
    for key, sym in SYMBOLS.items():
        result[key] = fetch_quote(sym)
        time.sleep(0.3)  # be polite
    return result

# ── RSS news fetch ───────────────────────────────────────────────
RSS_FEEDS = [
    ('NHK経済', 'https://www.nhk.or.jp/rss/news/cat4.xml'),
    ('Reuters日本語', 'https://feeds.reuters.com/reuters/JPBusinessNews'),
    ('Reuters EN', 'https://feeds.reuters.com/reuters/businessNews'),
]

def fetch_rss(url, max_items=6):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            content = r.read()
        root = ET.fromstring(content)
        titles = []
        for item in root.findall('.//item')[:max_items]:
            t = (item.findtext('title') or '').strip()
            if t:
                titles.append(t)
        if not titles:
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('.//a:entry', ns)[:max_items]:
                t = (entry.findtext('a:title', namespaces=ns) or '').strip()
                if t:
                    titles.append(t)
        return titles
    except:
        return []

def fetch_news():
    all_titles = []
    for name, url in RSS_FEEDS:
        items = fetch_rss(url)
        all_titles.extend(items)
        if len(all_titles) >= 8:
            break
    return all_titles[:8]

# ── Rule-based market analysis ───────────────────────────────────
def classify(pct):
    if pct > 2.0:  return 'strong_up'
    if pct > 0.5:  return 'up'
    if pct > -0.5: return 'flat'
    if pct > -2.0: return 'down'
    return 'strong_down'

MOOD_JP = {
    'strong_up': '急伸 (+2%超)', 'up': '上昇',
    'flat': 'ほぼ横ばい', 'down': '下落', 'strong_down': '急落 (-2%超)'
}

def leading_sector(q):
    avg = (q['dow']['pct'] + q['sp500']['pct'] + q['nasdaq']['pct']) / 3
    sox_diff  = q['sox']['pct'] - avg
    nas_diff  = q['nasdaq']['pct'] - q['dow']['pct']
    if sox_diff > 1.0:   return 'semiconductor'
    if nas_diff > 1.0:   return 'tech'
    if nas_diff < -1.0:  return 'defensive'
    return 'broad'

def make_points(q, overall, leader, news):
    """Return list of 3 analysis strings"""
    pts = []
    up   = overall in ('strong_up', 'up')
    down = overall in ('strong_down', 'down')

    # ── Point 1: main driver ──────────────────────────────────────
    if up:
        if leader == 'semiconductor':
            pts.append(
                f"**主因：半導体株が相場を牽引**\n"
                f"   SOX指数が{q['sox']['pct']:+.2f}%と突出して上昇。"
                f" 半導体セクターへの強気見通しが継続し、Nasdaqを押し上げた。"
            )
        elif leader == 'tech':
            pts.append(
                f"**主因：テック・AI関連株がリード**\n"
                f"   Nasdaqが{q['nasdaq']['pct']:+.2f}%とDow（{q['dow']['pct']:+.2f}%）を大きくアウトパフォーム。"
                f" AI・クラウド関連銘柄に資金が集中した。"
            )
        elif leader == 'defensive':
            pts.append(
                f"**主因：バリュー・ディフェンシブ株主導**\n"
                f"   Dow（{q['dow']['pct']:+.2f}%）がNasdaq（{q['nasdaq']['pct']:+.2f}%）を上回り、"
                f" 金融・素材・エネルギーへの資金シフトが見られた。"
            )
        else:
            pts.append(
                f"**主因：全面的な買いが優勢**\n"
                f"   主要3指数が揃って上昇（Dow {q['dow']['pct']:+.2f}% / S&P {q['sp500']['pct']:+.2f}% / Nasdaq {q['nasdaq']['pct']:+.2f}%）。"
                f" 幅広いセクターに買いが入る強い地合い。"
            )
    elif down:
        if leader == 'semiconductor':
            pts.append(
                f"**主因：半導体株の急落が相場を圧迫**\n"
                f"   SOX指数が{q['sox']['pct']:+.2f}%と大幅下落。"
                f" 利益確定売りや需給懸念が半導体セクター全体に波及した。"
            )
        elif leader == 'tech':
            pts.append(
                f"**主因：テック株の調整が重石**\n"
                f"   Nasdaqが{q['nasdaq']['pct']:+.2f}%下落。"
                f" 高バリュエーションへの警戒から利益確定売りが加速した。"
            )
        else:
            pts.append(
                f"**主因：リスクオフの動きが優勢**\n"
                f"   主要3指数が揃って下落（Dow {q['dow']['pct']:+.2f}% / Nasdaq {q['nasdaq']['pct']:+.2f}%）。"
                f" 景気・金融政策への警戒感から幅広い売りが出た。"
            )
    else:
        pts.append(
            f"**主因：方向感のない様子見相場**\n"
            f"   Dow {q['dow']['pct']:+.2f}% / Nasdaq {q['nasdaq']['pct']:+.2f}% と小幅な動き。"
            f" 次の材料待ちで積極的な売買は限定的。"
        )

    # ── Point 2: SOX or news ─────────────────────────────────────
    sox_cls = classify(q['sox']['pct'])
    if sox_cls in ('strong_up', 'strong_down') and leader != 'semiconductor':
        direction = '急騰' if q['sox']['pct'] > 0 else '急落'
        pts.append(
            f"**注目：半導体指数（SOX）が{direction}**\n"
            f"   SOX {q['sox']['pct']:+.2f}%。"
            f" 日本の半導体株（東エレク 8035・アドバンテスト 6857）への影響に要注意。"
        )
    elif news:
        pts.append(f"**ニュース材料**\n   {news[0]}")
    else:
        move = '円安' if q['usdjpy']['pct'] > 0 else '円高'
        effect = '輸出株に追い風' if q['usdjpy']['pct'] > 0 else 'ディフェンシブ・輸入コスト改善に有利'
        pts.append(
            f"**為替：ドル円 {q['usdjpy']['price']:.1f}円（{move}）**\n"
            f"   前日比 {q['usdjpy']['change']:+.2f}円。{effect}。"
        )

    # ── Point 3: additional news or FX ───────────────────────────
    if len(news) >= 2:
        pts.append(f"**その他の材料**\n   {news[1]}")
    elif news:
        move = '円安' if q['usdjpy']['pct'] > 0 else '円高'
        pts.append(
            f"**為替：ドル円 {q['usdjpy']['price']:.1f}円（{move}）**\n"
            f"   前日比 {q['usdjpy']['change']:+.2f}円。"
            f" {'輸出株の追い風' if q['usdjpy']['pct'] > 0 else '円高は輸出株の重石'}。"
        )
    else:
        pts.append(
            f"**セクター補足**\n"
            f"   SOX {q['sox']['pct']:+.2f}% ／ ドル円 {q['usdjpy']['price']:.1f}円。"
            f" 引き続き半導体・AI セクターの動向と為替が日本株のカギ。"
        )

    return pts

def japan_outlook(overall, leader, q):
    up   = overall in ('strong_up', 'up')
    down = overall in ('strong_down', 'down')
    lines = []

    if up:
        lines.append('米国株の上昇を受けて日本株にも買いが波及しやすい地合い。')
    elif down:
        lines.append('米国株安を受けて日本株にも下押し圧力がかかりやすい。')
    else:
        lines.append('米国株が横ばいのため、日本株も方向感の乏しい展開となりそう。')

    sox_cls = classify(q['sox']['pct'])
    if sox_cls in ('strong_up', 'up'):
        lines.append('SOX高から東京エレクトロン（8035）・アドバンテスト（6857）に追い風。')
    elif sox_cls in ('strong_down', 'down'):
        lines.append('SOX安から半導体関連（東エレク・アドバンテスト）に売り圧力の可能性。')

    if q['usdjpy']['pct'] > 0.3:
        lines.append(f"ドル円 {q['usdjpy']['price']:.1f}円の円安で輸出株（自動車・電機）に有利。")
    elif q['usdjpy']['pct'] < -0.3:
        lines.append(f"ドル円 {q['usdjpy']['price']:.1f}円の円高は輸出株の重石となる可能性。")

    return '\n\n'.join(lines)

def sector_summary(overall, leader):
    up = overall in ('strong_up', 'up')
    if leader == 'semiconductor':
        return ('半導体・テック', '金融・ディフェンシブ（相対的）') if up else ('ディフェンシブ・金融', '半導体・テック')
    if leader == 'tech':
        return ('テック・AI・グロース', 'バリュー・エネルギー') if up else ('バリュー・ディフェンシブ', 'テック・AI')
    if leader == 'defensive':
        return ('金融・素材・エネルギー', 'テック・グロース') if up else ('公益・生活必需品', '金融・素材')
    return ('全般（幅広く）', '特になし') if up else ('特になし（全面安）', '全般')

# ── Markdown builder ─────────────────────────────────────────────
WD_JP = ['月', '火', '水', '木', '金', '土', '日']

def prev_business_day(d):
    d -= datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d

def build_md(q, news):
    today = datetime.date.today()
    yest  = prev_business_day(today)
    td = f"{today.strftime('%Y-%m-%d')}（{WD_JP[today.weekday()]}）"
    yd = f"{yest.strftime('%Y-%m-%d')}（{WD_JP[yest.weekday()]}）"

    overall = classify((q['dow']['pct'] + q['sp500']['pct'] + q['nasdaq']['pct']) / 3)
    leader  = leading_sector(q)
    pts     = make_points(q, overall, leader, news)
    strong, weak = sector_summary(overall, leader)
    outlook = japan_outlook(overall, leader, q)
    mood_jp = {'strong_up': '強気（リスクオン）', 'up': 'やや強気',
               'flat': '中立・様子見', 'down': 'やや弱気', 'strong_down': '弱気（リスクオフ）'}[overall]

    def n(v, dec=0): return f"{v:,.{dec}f}" if v else '─'
    def s(v): return f"**{v:+.2f}%**"

    nikkei_str = n(q['nikkei']['price'], 0) + '円' if q['nikkei']['ok'] else '─（取得失敗）'

    news_md = '\n'.join(f'- {t}' for t in news[:6]) if news else '（取得できませんでした）'

    return f"""# 朝の市場ブリーフィング {td}
*自動生成 / TradeLog ／ データ: Yahoo Finance + RSS*

---

## ① 前日（{yd}・米国）市場

| 指数 | 終値 | 前日比 | 変動率 | 一言 |
|------|------|--------|--------|------|
| Dow | {n(q['dow']['price'],0)} | {q['dow']['change']:+,.0f} | {s(q['dow']['pct'])} | {'上昇' if q['dow']['pct']>0 else '下落'} |
| S&P500 | {n(q['sp500']['price'],0)} | {q['sp500']['change']:+,.0f} | {s(q['sp500']['pct'])} | {'上昇' if q['sp500']['pct']>0 else '下落'} |
| Nasdaq | {n(q['nasdaq']['price'],0)} | {q['nasdaq']['change']:+,.0f} | {s(q['nasdaq']['pct'])} | {'上昇' if q['nasdaq']['pct']>0 else '下落'} |
| SOX | {n(q['sox']['price'],0)} | {q['sox']['change']:+,.0f} | {s(q['sox']['pct'])} | {'上昇' if q['sox']['pct']>0 else '下落'} |

**ドル円:** {n(q['usdjpy']['price'],1)}円（前日比 {q['usdjpy']['change']:+.2f}円）

**なぜ動いたか（3ポイント）**

1. {pts[0]}

2. {pts[1]}

3. {pts[2]}

**セクター別:**
- 強い：{strong}
- 弱い：{weak}

---

## ② 今日（{td}・日本株）の動き

**日経平均（前日終値）**: {nikkei_str}

**見立て**

{outlook}

> 🔑 **教訓**：*（取引後に記入）*

---

## ③ 今日の企業行動カレンダー

| 内容 | 詳細 |
|------|------|
| *（手動記入）* | ─ |

---

## ④ 今日注目する銘柄

*（手動記入）*

---

## ⑤ 今日の戦略サマリー

**相場ムード**: {mood_jp}

**やること**
1. *（手動記入）*

**避けること**
- *（手動記入）*

---

## ⑥ ニュース見出し（自動取得）

{news_md}

---

*自動生成: TradeLog ／ {today.strftime('%Y-%m-%d %H:%M')} JST*
"""

# ── HTTP Handler ─────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP_DIR, **kw)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == '/api/briefings':
            self._list_briefings()
        elif p.path == '/api/briefing':
            qs = parse_qs(p.query)
            self._get_briefing(qs.get('file', [None])[0])
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path)
        if p.path == '/api/generate':
            self._generate()
        else:
            self.send_error(404)

    def _list_briefings(self):
        try:
            files = sorted(
                glob.glob(os.path.join(os.path.expanduser(BRIEFING_DIR), '*.md')),
                reverse=True
            )
            result = []
            for f in files:
                name = os.path.basename(f)
                with open(f, 'r', encoding='utf-8') as fh:
                    first = fh.readline().strip().lstrip('# ')
                result.append({'file': name, 'title': first, 'mtime': int(os.path.getmtime(f))})
            self._json(result)
        except Exception as e:
            self._json({'error': str(e)}, 500)

    def _get_briefing(self, filename):
        if not filename or '..' in filename or not filename.endswith('.md'):
            self.send_error(400); return
        path = os.path.join(os.path.expanduser(BRIEFING_DIR), filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._json({'content': f.read(), 'file': filename})
        except FileNotFoundError:
            self.send_error(404)
        except Exception as e:
            self._json({'error': str(e)}, 500)

    def _generate(self):
        try:
            self._json({'status': 'fetching', 'msg': 'マーケットデータ取得中...'})
        except: pass

        try:
            print('[generate] Fetching market quotes...')
            quotes = fetch_all_quotes()
            print('[generate] Fetching news...')
            news   = fetch_news()
            print(f'[generate] Got {len(news)} news items')

            md = build_md(quotes, news)

            today    = datetime.date.today().strftime('%Y-%m-%d')
            filename = f'{today}-morning-briefing.md'
            path     = os.path.join(os.path.expanduser(BRIEFING_DIR), filename)
            os.makedirs(os.path.expanduser(BRIEFING_DIR), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(md)

            print(f'[generate] Saved {filename}')
            self._json({'status': 'ok', 'file': filename,
                        'quotes': {k: {'price': v['price'], 'pct': v['pct'], 'ok': v['ok']}
                                   for k, v in quotes.items()}})
        except Exception as e:
            import traceback
            print('[generate] ERROR:', traceback.format_exc())
            self._json({'status': 'error', 'msg': str(e)}, 500)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, *_): pass

if __name__ == '__main__':
    os.makedirs(os.path.expanduser(BRIEFING_DIR), exist_ok=True)
    print(f'TradeLog  →  http://localhost:{PORT}')
    with http.server.HTTPServer(('', PORT), Handler) as s:
        s.serve_forever()
