#!/usr/bin/env python3
"""Static QA for the built site (_site): broken internal links, missing assets, SEO metadata, JSON-LD validity.
Run after `python3 build.py`:   python3 tests/check_static.py
"""
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / '_site'
BASE = 'https://somin.ai'
NOT_MIGRATED = {'/cases-ai-marketing-strategy/'}  # regenerated separately — allowed to be missing

problems, warnings = [], []
pages = sorted(p for p in SITE.rglob('*.html'))


def exists(path):
    path = urllib.parse.unquote(path.split('#')[0].split('?')[0])
    if path in NOT_MIGRATED:
        return True
    p = SITE / path.lstrip('/')
    if path.endswith('/'):
        return (p / 'index.html').exists()
    return p.exists() or (p / 'index.html').exists()


stats = {'pages': 0, 'internal_links': 0, 'assets': 0, 'jsonld_blocks': 0}
for f in pages:
    rel = '/' + str(f.relative_to(SITE)).replace('index.html', '')
    t = f.read_text(encoding='utf-8')
    if 'http-equiv="refresh"' in t:
        continue  # redirect stub
    stats['pages'] += 1
    head = t[:t.find('</head>')]
    body = t[t.find('<body'):]
    # --- metadata
    title = re.search(r'<title>(.*?)</title>', head, re.S)
    if not title or not title.group(1).strip():
        problems.append(f'{rel}: missing <title>')
    elif len(html.unescape(title.group(1))) > 70:
        warnings.append(f'{rel}: title {len(html.unescape(title.group(1)))} chars')
    if not re.search(r'<meta name="description" content="[^"]{20,}"', head):
        problems.append(f'{rel}: missing/short meta description')
    robots = re.search(r'<meta name="robots" content="([^"]+)"', head)
    if rel != '/404.html' and not re.search(r'<link rel="canonical" href="https://somin\.ai/[^"]*"', head):
        problems.append(f'{rel}: missing canonical')
    if not re.search(r'<meta property="og:image" content="https://somin\.ai/', head):
        problems.append(f'{rel}: og:image not absolute/self-hosted')
    h1 = len(re.findall(r'<h1\b', re.sub(r'<script\b.*?</script>', '', body, flags=re.S)))
    if h1 != 1:
        (warnings if rel.startswith('/c5584') else problems).append(f'{rel}: {h1} <h1> elements')
    if t.count('googletagmanager.com/gtm.js') > 0:
        problems.append(f'{rel}: inline GTM snippet found (should only come from tracking.js)')
    if t.count('/assets/js/tracking.js') != 1:
        problems.append(f'{rel}: tracking.js included {t.count("/assets/js/tracking.js")} times')
    for bad in ('leadpages', 'lpcontent', 'htmlpub', 'data-leadbox', 'center.io', 'lp-button-react'):
        if bad in t.lower():
            problems.append(f'{rel}: Leadpages leftover "{bad}"')
    # --- JSON-LD (one graph per page: no duplicate @id, one Organization, at most one FAQPage)
    ld_nodes = []
    for js in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        stats['jsonld_blocks'] += 1
        try:
            d = json.loads(js)
            ld_nodes += d.get('@graph', [d]) if isinstance(d, dict) else d
        except Exception as e:
            problems.append(f'{rel}: invalid JSON-LD ({e})')
    ids = [n.get('@id') for n in ld_nodes if isinstance(n, dict) and n.get('@id')]
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f'{rel}: JSON-LD @id {i} defined {ids.count(i)} times')
    kinds = [n.get('@type') for n in ld_nodes if isinstance(n, dict)]
    if kinds.count('FAQPage') > 1 or kinds.count('Organization') > 1:
        problems.append(f'{rel}: JSON-LD has {kinds.count("FAQPage")} FAQPage / {kinds.count("Organization")} Organization nodes (max 1)')
    # --- hreflang: every alternate exists and lists this page back
    for hl, href in re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', head):
        if not href.startswith(BASE + '/') or not exists(href[len(BASE):]):
            problems.append(f'{rel}: hreflang {hl} points at missing {href}')
            continue
        other = (SITE / href[len(BASE) + 1:] / 'index.html') if href.endswith('/') else SITE / href[len(BASE) + 1:]
        if other.exists() and f'href="{BASE}{rel}"' not in other.read_text(encoding='utf-8')[:20000]:
            problems.append(f'{rel}: hreflang {hl} target {href} does not link back')
    # --- case-study standard (docs/CASE_STUDY_SEO.md)
    if 'data-page-type="case_study"' in t and robots and robots.group(1).startswith('index'):
        tt = html.unescape(title.group(1)) if title else ''
        dsc = html.unescape((re.search(r'<meta name="description" content="([^"]*)"', head) or [None, ''])[1])
        if not (40 <= len(tt) <= 60) or not tt.endswith('| SOMIN') or 'Case Study' not in tt:
            problems.append(f'{rel}: case title must be 40-60 chars, "<Client> Case Study: <Topic> | SOMIN" ({len(tt)}: {tt})')
        if not (140 <= len(dsc) <= 160):
            problems.append(f'{rel}: case description {len(dsc)} chars (140-160)')
        mp = body[body.find('<main'):body.find('</main>')] if '<main' in body else body
        clean = re.sub(r'<script\b.*?</script>|<style\b.*?</style>', '', mp, flags=re.S)
        hs = [(lv, re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', x))).strip()) for lv, x in re.findall(r'<h([1-6])\b[^>]*>(.*?)</h\1>', clean, re.S)]
        hs = [(lv, x) for lv, x in hs if x]
        main_h = hs
        h1s = [x for lv, x in main_h if lv == '1']
        if h1s and not (45 <= len(h1s[0]) <= 75 and not h1s[0].endswith('.')):
            problems.append(f'{rel}: case H1 must be 45-75 chars without a full stop ({len(h1s[0])}: {h1s[0]})')
        h2s = [x for lv, x in main_h if lv == '2']
        for x in h2s:
            if x.endswith('.') or '—' in x or len(x) > 70:
                problems.append(f'{rel}: case H2 "{x}" (no full stop, no em dash, <= 70 chars)')
        if not any(x.endswith(' case study FAQ') for x in h2s):
            problems.append(f'{rel}: case page has no "<Client> case study FAQ" H2')
        lv = [int(a) for a, _ in main_h]
        for a, b in zip(lv, lv[1:]):
            if b > a + 1:
                problems.append(f'{rel}: heading level skips h{a}->h{b}')
                break
        graph = []
        for js in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
            try:
                d = json.loads(js)
                graph += d.get('@graph', [d])
            except Exception:
                pass
        kinds = [n.get('@type') for n in graph]
        if kinds.count('Article') != 1 or kinds.count('FAQPage') != 1:
            problems.append(f'{rel}: case schema needs exactly one Article and one FAQPage (has {kinds.count("Article")}/{kinds.count("FAQPage")})')
        if 'somin.ai/case-studies/' in t:
            problems.append(f'{rel}: schema points at a non-existent /case-studies/ URL')
    # --- links + assets
    for m in re.finditer(r'\b(href|src)="([^"]+)"', body + head):
        attr, url = m.group(1), html.unescape(m.group(2))
        if url.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', '#', 'data:', 'javascript:')):
            if url.startswith(BASE + '/') and attr == 'href' and 'canonical' not in m.group(0):
                pass
            continue
        if not url.startswith('/'):
            problems.append(f'{rel}: relative URL {url}')
            continue
        if attr == 'href':
            stats['internal_links'] += 1
        else:
            stats['assets'] += 1
        if not exists(url):
            problems.append(f'{rel}: broken {attr} {url}')
    # CSS url() assets inside inline styles
    for m in re.finditer(r'url\((["\']?)(/assets/[^)"\']+)\1\)', t):
        stats['assets'] += 1
        if not exists(m.group(2)):
            problems.append(f'{rel}: missing css asset {m.group(2)}')

# sitemap / robots / llms
sm = (SITE / 'sitemap.xml').read_text()
locs = re.findall(r'<loc>(.*?)</loc>', sm)
for u in locs:
    if not exists(u.replace(BASE, '')):
        problems.append(f'sitemap: {u} does not exist')
for f in ('robots.txt', 'llms.txt', 'llms-full.txt', 'CNAME', '.nojekyll', '404.html', 'blog/rss.xml', 'favicon.ico'):
    if not (SITE / f).exists():
        problems.append(f'missing {f}')

print(json.dumps(stats))
print(f'sitemap URLs: {len(locs)}')
print(f'\nPROBLEMS ({len(problems)}):')
for p in problems[:200]:
    print('  -', p)
print(f'\nWARNINGS ({len(warnings)}):')
for w in warnings[:60]:
    print('  -', w)
sys.exit(1 if problems else 0)
