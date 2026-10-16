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
    # --- JSON-LD
    for js in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        stats['jsonld_blocks'] += 1
        try:
            json.loads(js)
        except Exception as e:
            problems.append(f'{rel}: invalid JSON-LD ({e})')
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
