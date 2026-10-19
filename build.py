#!/usr/bin/env python3
"""
Build the SOMIN website into ./_site (static, GitHub Pages ready). Python 3.9+, standard library only.

    python3 build.py            # build
    python3 build.py --serve    # build, then serve on http://localhost:8000
    python3 build.py --base-path /somin-website   # build for a sub-path (GitHub default address)

Sources
  content/pages/<slug>.html   one file per page: a JSON <!--meta ... --> header followed by the page body
  content/blog/<slug>.html    blog articles (same format, layout "post")
  site.config.json            navigation, footer, redirects, site identity
  data/case-studies.json      case-study PDFs released after the case-study form is submitted
  static/                     copied as-is (CSS, JS, images, fonts, CNAME, robots extras)
  static/assets/js/tracking.js  the ONE tracking/lead-capture script (its CONFIG block is read here too)
"""
import datetime as dt
import base64
import email.utils
import gzip
import hashlib
import html
import json
import os
import re
import shutil
import struct
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402  per-language copies of every page (see i18n.py)
OUT = ROOT / '_site'
CFG = json.loads((ROOT / 'site.config.json').read_text(encoding='utf-8'))
SITE = CFG['site']
BASE = SITE['url'].rstrip('/')
TRACKING_JS = (ROOT / 'static/assets/js/tracking.js').read_text(encoding='utf-8')
TRACK = json.loads(re.search(r'/\*CONFIG_START\*/(.*?)/\*CONFIG_END\*/', TRACKING_JS, re.S).group(1))
CASES = json.loads((ROOT / 'data/case-studies.json').read_text(encoding='utf-8'))
ORG = json.loads((ROOT / 'data/organization.json').read_text(encoding='utf-8'))
PRICING = json.loads((ROOT / 'data/pricing.json').read_text(encoding='utf-8'))
TODAY = dt.date.today().isoformat()
BUILD_ID = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M')

E = lambda s: html.escape(str(s if s is not None else ''), quote=True)


# ------------------------------------------------------------------ content loading
def read_content(path):
    text = Path(path).read_text(encoding='utf-8')
    if not text.startswith('<!--meta'):
        raise SystemExit(f'{path}: missing <!--meta ... --> header')
    end = text.index('\n-->\n')
    meta = json.loads(text[len('<!--meta'):end])
    return meta, text[end + 5:]


PLUGIN = {'file': 'https://mondays.marketing/downloads/marketing-mondays.plugin', 'zip': 'https://mondays.marketing/downloads/marketing-mondays.zip',
          'mcp': 'https://cloud.somin.ai/_mcp', 'source': 'https://mondays.marketing/plugin/'}
REPLAYS = json.loads((ROOT / 'data/replays.json').read_text(encoding='utf-8'))
ICON_PP = ('<svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>'
           '<svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>')
_DOTS = '<span class="mm-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
_TOGGLE = f'<button type="button" class="mm-toggle" aria-pressed="false" aria-label="Play replay">{ICON_PP}</button>'


def _replay_cap():
    return ('<figcaption class="mm-cap">Condensed replay of a real run: SOMIN agents in Claude on Grab Singapore data, shown live at '
            f'<a href="{REPLAYS["session_url"]}" target="_blank" rel="noopener" data-gtm-id="replay_session_link">Marketing Mondays</a> on 12 Oct 2026. No sound.</figcaption>')


def replay_figure(key):
    """<!--mm:replay KEY--> : one recorded agent run, plays muted while on screen."""
    it = REPLAYS['items'][key]
    return (f'<figure class="mm-screen mm-replay"><div class="mm-chrome">{_DOTS}<span class="mm-q">{E(it["step"])} · {E(it["q"])}</span>'
            f'<span class="mm-skill">{E(it["skill"])}</span>{_TOGGLE}</div>'
            f'<video data-replay data-src="/assets/video/{key}.mp4" poster="/assets/video/{key}.webp" muted playsinline loop preload="none" '
            f'width="1152" height="432" aria-label="{E(it["q"])}"></video>{_replay_cap()}</figure>')


def replay_loop():
    """<!--mm:loop--> : the five-step loop (Listen, Decode, Decide, Make, Ship) as a tabbed player that advances by itself."""
    tabs = ''
    for s in REPLAYS['loop']:
        it = REPLAYS['items'][s['key']]
        tabs += (f'<button type="button" class="mm-tab" role="tab" aria-controls="mm-panel" aria-selected="false" data-mm-tab data-step="{E(s["step"])}" '
                 f'data-src="/assets/video/{s["key"]}.mp4" data-poster="/assets/video/{s["key"]}.webp" data-q="{E(it["q"])}" data-skill="{E(it["skill"])}">'
                 f'<span class="mm-n">{s["n"]}</span><b>{E(s["step"])}</b><small>{E(s["label"])}</small></button>')
    k0 = REPLAYS['loop'][0]['key']
    it0 = REPLAYS['items'][k0]
    return (f'<div class="mm-player mm-replay" data-mm-player><div class="mm-tabs" role="tablist" aria-label="The five steps of the loop">{tabs}</div>'
            f'<figure class="mm-screen" id="mm-panel" role="tabpanel"><div class="mm-chrome">{_DOTS}<span class="mm-q" data-mm-q>{E(it0["q"])}</span>'
            f'<span class="mm-skill" data-mm-skill>{E(it0["skill"])}</span>{_TOGGLE}</div>'
            f'<video data-replay data-src="/assets/video/{k0}.mp4" poster="/assets/video/{k0}.webp" muted playsinline preload="none" width="1152" height="432" '
            f'aria-label="{E(it0["q"])}"></video>{_replay_cap()}</figure></div>')


REVIEWS = json.loads((ROOT / 'data/reviews.json').read_text(encoding='utf-8'))
# Founder's rule: never show reviews by anyone named Aleks or a derivative of it.
_EXCLUDED_NAME = re.compile(r'^(ale[kx]|aless|alexa|oleks|sasha|sascha|shura)', re.I)
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def _usable_reviews():
    return [r for r in REVIEWS['reviews'] if not _EXCLUDED_NAME.match(r['name'].strip()) and (r.get('rating') or 0) >= 3.5]


def stars(r, cls='rv-stars'):
    pct = max(0, min(100, round(float(r) / 5 * 100)))
    return (f'<span class="{cls}" role="img" aria-label="{r:g} out of 5 stars"><span class="rv-stars-on" style="width:{pct}%">★★★★★</span>★★★★★</span>')


def rating_badges(extra=''):
    """G2 / Capterra rating badges (real averages from data/reviews.json, linked to the profiles)."""
    out = []
    for key, pl in REVIEWS['platforms'].items():
        if pl.get('rating'):
            out.append(f'<a class="rv-badge" href="{E(pl["url"])}" target="_blank" rel="noopener" data-gtm-id="rating_badge_{key}" data-track="rating_badge_click" '
                       f'aria-label="Rated {pl["rating"]:.1f} out of 5 on {E(pl["name"])}">'
                       f'<span class="rv-src rv-src--{key}">{E(pl["name"])}</span>{stars(pl["rating"])}'
                       f'<span class="rv-score"><b>{pl["rating"]:.1f}</b></span></a>')
        else:
            out.append(f'<a class="rv-badge" href="{E(pl["url"])}" target="_blank" rel="noopener" data-gtm-id="rating_badge_{key}" data-track="rating_badge_click">'
                       f'<span class="rv-src rv-src--{key}">{E(pl["name"])}</span><span class="rv-count">Read our reviews</span></a>')
    return f'<div class="rv-badges{(" " + extra) if extra else ""}">{"".join(out)}</div>'


def _excerpt(t):
    t = t.strip()
    if t[:1].islower():
        t = '…' + t
    if t[-1:] not in '.!?':
        t = t + '…'
    return t


def review_cards(tags, limit=3):
    tags = [t.strip() for t in tags if t.strip()]
    picks = []
    for r in _usable_reviews():
        best = None
        for q in r['quotes']:
            score = sum(1 for t in tags if t in q['tags'])
            if score and (best is None or score > best[0]):
                best = (score, q)
        if best:
            picks.append((best[0], r.get('rating') or 0, r['date'], r, best[1]))
    picks.sort(key=lambda x: x[2], reverse=True)          # newest first among equals
    picks.sort(key=lambda x: (-x[0], -x[1]))
    cards = []
    for _, _, _, r, q in picks[:limit]:
        pl = REVIEWS['platforms'][r['platform']]
        y, m, _d = r['date'].split('-')
        who = ' · '.join(x for x in (r.get('role'), r.get('size')) if x)
        cards.append(f'<figure class="rv-card">{stars(r["rating"])}<blockquote>“{E(_excerpt(q["text"]))}”</blockquote>'
                     f'<figcaption><b>{E(r["name"])}</b>{f"<span>{E(who)}</span>" if who else ""}'
                     f'<a href="{E(pl["url"])}" target="_blank" rel="noopener" data-gtm-id="review_source_{r["platform"]}">{"Validated review on G2" if r["platform"] == "g2" else "Verified review on " + E(pl["name"])}'
                     f'{(" (" + E(r["source_note"]) + ")") if r.get("source_note") else ""} · {MONTHS[int(m) - 1]} {y}</a></figcaption></figure>')
    return cards


def reviews_section(attrs):
    tags = (attrs.get('tags') or 'home').split(',')
    limit = int(attrs.get('limit') or 3)
    cards = review_cards(tags, limit)
    if not cards:
        return ''
    title = attrs.get('title') or 'What users say about SOMIN.'
    native = attrs.get('native') == '1'
    cls = 'rv-section sec sec--light' if native else 'rv-section'
    pls = ' and '.join(f'<a href="{E(p["url"])}" target="_blank" rel="noopener">{E(p["name"])}</a>' for p in REVIEWS['platforms'].values())
    return (f'<section class="{cls}" aria-label="Reviews on G2 and Capterra"><div class="rv-wrap">'
            f'<div class="rv-head"><div><p class="rv-kicker">Rated by users on G2 and Capterra</p><h2>{E(title)}</h2></div>{rating_badges()}</div>'
            f'<div class="rv-grid rv-grid--{min(len(cards), 3)}">{"".join(cards)}</div>'
            f'<p class="rv-note">Short excerpts from validated reviews, quoted as written. Read every review in full on {pls}.</p>'
            f'</div></section>')


# ------------------------------------------------------------------ strategic partners powered by SOMIN
PARTNERS = json.loads((ROOT / 'data/partners.json').read_text(encoding='utf-8'))


def partner_logo(p, dark=False, scale=1.0):
    """<img> for a partner logo at its optical display height (strip_h × scale); width follows the file's aspect ratio.
    The height also goes in as the unitless --lh so CSS can scale the whole set with the viewport without distorting a logo."""
    h = round(p.get('strip_h', 22) * scale)
    w = round(h * p['logo_w'] / p['logo_h'])
    return (f'<img src="{E(p["logo_dark"] if dark else p["logo"])}" alt="{E(p["name"])} logo" width="{w}" height="{h}" '
            f'style="--lh:{h}" loading="lazy" decoding="async">')


def partners_block(attrs):
    """<!--mm:partners compact="1"--> = a two-line logo plate (home hero, under the client marquee);
    <!--mm:partners--> = the full Vision-page section with a logo card per partner and ItemList schema."""
    items = PARTNERS['items']
    if attrs.get('compact'):
        links = ''.join(
            f'<a class="se-partners-logo" href="{E(p["url"])}" target="_blank" rel="noopener" data-track="partner_click" '
            f'title="{E(p["description"])}" aria-label="{E(p["name"])}">{partner_logo(p, dark=True)}</a>' for p in items)
        return (f'<div class="se-partners" role="group" aria-label="Strategic partners powered by SOMIN"><span class="se-partners-label">'
                f'Strategic partners powered by <b>SO</b>MIN</span>{links}<a class="se-partners-all" href="/vision/#partners">All partners →</a></div>')
    def card(p):
        # spaces between the parts keep the link text (and partner_click's cta_text) readable; the flex column ignores them
        short = f' <span class="pt-short">{E(p["short"])}</span>' if p.get('short') else ''
        host = re.sub(r'^https?://(www[.])?', '', p['url']).strip('/')
        return (f'<a class="pt-card" href="{E(p["url"])}" target="_blank" rel="noopener" data-track="partner_click">'
                f'<span class="pt-logo">{partner_logo(p, scale=1.5)}</span> <strong>{E(p["name"])}</strong>{short} '
                f'<span class="pt-desc">{E(p["description"])}</span> <em>{E(host)} ↗</em></a>')
    cards = ''.join(card(p) for p in items)
    ld = {"@type": "ItemList", "@id": absu('/vision/') + '#partners', "name": "Strategic partners powered by SOMIN",
          "itemListElement": [{"@type": "ListItem", "position": i + 1,
                               "item": {"@type": "Organization", "name": p['name'], "url": p['url'], "description": p['description'],
                                        **({"logo": BASE + p['logo']} if p.get('logo') else {})}}
                              for i, p in enumerate(items)]}
    title = attrs.get('title') or 'Strategic partners powered by SOMIN'
    lede = attrs.get('lede') or ('Businesses and communities that run SOMIN for their own clients or build on our team and research. '
                                 'Each one links to its own website.')
    return (f'<section class="pt-sec" id="partners" aria-labelledby="partners-h"><p class="eyebrow eyebrow--ink">Strategic partners</p>'
            f'<h2 id="partners-h">{E(title)}</h2><p class="pt-lede">{E(lede)}</p><div class="pt-grid">{cards}</div></section>'
            f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')


# ------------------------------------------------------------------ research (peer-reviewed papers and talks)
RESEARCH = json.loads((ROOT / 'data/research.json').read_text(encoding='utf-8'))
RS_VENUES = [('AAAI', 'AAAI Conference on Artificial Intelligence'), ('ACM MM', 'ACM International Conference on Multimedia'),
             ('SIGIR', 'ACM SIGIR Conference on Research and Development in Information Retrieval'),
             ('WSDM', 'ACM International Conference on Web Search and Data Mining'), ('WWW', 'The ACM Web Conference'),
             ('ACM TOIS', 'ACM Transactions on Information Systems')]
RS_LEDE = ("SOMIN's co-founder, Prof. Aleks Farseev, publishes research on audience profiling, personality-driven content and explainable AI "
           "for advertising at AAAI, ACM Multimedia, SIGIR, WSDM and The Web Conference. Those models run inside SOMIN, next to playbooks from "
           "marketers who work with brand and agency teams every day.")


def _rs_papers(themes=None, limit=3):
    by_id = {p['id']: p for p in RESEARCH['papers']}
    order = [by_id[i] for i in RESEARCH['featured']] + [p for p in RESEARCH['papers'] if p['id'] not in RESEARCH['featured']]
    if themes:
        order = [p for p in order if p['theme'] in themes] + [p for p in order if p['theme'] not in themes]
    return [p for p in order if p['peer_reviewed']][:limit]


def _rs_venue_link(short):
    p = next((p for p in RESEARCH['papers'] if p['venue_short'] == short and p['tier'] == 'top'), None) or \
        next((p for p in RESEARCH['papers'] if p['venue_short'] == short), None)
    return p['url'] if p else '/research/'


def rs_venue_chips(cls='rs-venues'):
    return f'<div class="{cls}">' + ''.join(
        f'<a class="rs-chip" href="{E(_rs_venue_link(s))}" target="_blank" rel="noopener" title="{E(full)}" data-track="research_venue_click" data-gtm-id="research_venue">{E(s)}</a>'
        for s, full in RS_VENUES) + '</div>'


def rs_paper_card(p):
    return (f'<a class="rs-paper" href="{E(p["url"])}" target="_blank" rel="noopener" data-track="research_paper_click" data-gtm-id="research_paper">'
            f'<span class="rs-venue">{E(p["venue_short"])} · {p["year"]}</span><strong>{E(p["title"])}</strong>'
            f'<span class="rs-topic">{E(p["topic"][:1].upper() + p["topic"][1:])}</span><span class="rs-kind">{E(p["kind"])} · read the paper</span></a>')


def rs_talk_link(t):
    yr = t['date'][:4]
    return (f'<a class="rs-talk" href="{E(t["url"])}" target="_blank" rel="noopener" data-track="research_talk_click" data-gtm-id="research_talk">'
            f'<span>{E(t["kind"])} · {yr}</span>{E(t["title"])}</a>')


def research_strip(attrs):
    """'Built by seasoned marketers and an AI professor': venues, papers and talks from data/research.json (<!--mm:research-->)."""
    if attrs.get('compact') == '1':
        return (f'<div class="rs-line{(" " + E(attrs["cls"])) if attrs.get("cls") else ""}"><span class="rs-line-k">Built by seasoned marketers and an AI professor</span>'
                f'<span class="rs-line-t">Research published at</span>{rs_venue_chips("rs-venues rs-venues--line")}'
                f'<a class="rs-line-more" href="/research/" data-gtm-id="research_line_more">See the research →</a></div>')
    themes = [t.strip() for t in (attrs.get('themes') or '').split(',') if t.strip()]
    papers = ''.join(rs_paper_card(p) for p in _rs_papers(themes, int(attrs.get('limit') or 3)))
    by_id = {t['id']: t for t in RESEARCH['talks']}
    talks = ''.join(rs_talk_link(by_id[i]) for i in RESEARCH['featured_talks'][:int(attrs.get('talks') or 3)])
    title = attrs.get('title') or 'Built by seasoned marketers and an AI professor.'
    cls = 'rs-section' + (' sec sec--mist' if attrs.get('native') == 'mist' else ' sec sec--light' if attrs.get('native') == '1' else '')
    return (f'<section class="{cls}" aria-label="Research behind SOMIN"><div class="rs-wrap">'
            f'<div class="rs-head"><div><p class="rs-kicker">Peer-reviewed research</p><h2>{E(title)}</h2><p class="rs-lede">{E(attrs.get("lede") or RS_LEDE)}</p></div>'
            f'{rs_venue_chips()}</div><div class="rs-grid">{papers}</div>'
            f'<div class="rs-talks"><span class="rs-tlabel">Watch the talks</span>{talks}</div>'
            f'<p class="rs-more"><a class="rs-btn" href="/research/" data-gtm-id="research_strip_all">All papers and talks</a>'
            f'<a class="rs-ext" href="{E(RESEARCH["profiles"][0]["url"])}" target="_blank" rel="noopener" data-track="research_profile_click" data-gtm-id="research_scholar">Google Scholar profile</a></p>'
            f'</div></section>')


def research_note():
    """One-line research credit for the 'About SOMIN' block of case studies."""
    links = ', '.join(f'<a href="{E(_rs_venue_link(s))}" target="_blank" rel="noopener" data-track="research_venue_click">{E(n)}</a>'
                      for s, n in (('AAAI', 'AAAI'), ('ACM MM', 'ACM Multimedia'), ('SIGIR', 'SIGIR'), ('WSDM', 'WSDM')))
    return (f'<p class="rs-note">Built by seasoned marketers and an AI professor: the methods behind this study are peer-reviewed at {links} '
            f'and in <a href="{E(_rs_venue_link("ACM TOIS"))}" target="_blank" rel="noopener" data-track="research_venue_click">ACM TOIS</a>. '
            f'<a href="/research/" data-gtm-id="case_research_note">See the research and talks</a>.</p>')


def expand_shortcodes(body):
    body = re.sub(r'<!--\s*mm:research((?:\s+\w+="[^"]*")*)\s*-->', lambda m: research_strip(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))), body)
    body = re.sub(r'<!--\s*mm:partners((?:\s+\w+="[^"]*")*)\s*-->', lambda m: partners_block(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))), body)
    body = re.sub(r'<!--\s*mm:reviews((?:\s+\w+="[^"]*")*)\s*-->', lambda m: reviews_section(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))), body)
    body = re.sub(r'<!--\s*mm:ratings((?:\s+\w+="[^"]*")*)\s*-->', lambda m: rating_badges(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))).get('cls', '')), body)
    body = re.sub(r'<!--\s*mm:replay\s+([a-z0-9-]+)\s*-->', lambda m: replay_figure(m.group(1)), body)
    return re.sub(r'<!--\s*mm:loop\s*-->', lambda m: replay_loop(), body)


def faq_node(body, path):
    """FAQPage schema built from the visible <details><summary>Q</summary>A</details> FAQ on a page (AEO/GEO)."""
    qa = []
    for m in re.finditer(r'<details\b[^>]*>\s*<summary\b[^>]*>(.*?)</summary>(.*?)</details>', body, re.S):
        q = strip_tags(m.group(1)).strip()
        a = strip_tags(m.group(2)).strip()
        if q and a and len(a) > 20:
            qa.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    if len(qa) < 2:
        return None
    return {"@type": "FAQPage", "@id": absu(path) + "#faq", "mainEntity": qa}


def video_nodes(body, path):
    """VideoObject schema for every replay a page shows (answer engines and video search)."""
    keys = []
    for k in re.findall(r'/assets/video/([a-z0-9-]+)\.mp4', body):
        if k not in keys and k in REPLAYS['items']:
            keys.append(k)
    out = []
    for k in keys:
        it = REPLAYS['items'][k]
        out.append({"@type": "VideoObject", "@id": absu(path) + f"#video-{k}", "name": f'SOMIN agent replay — {it["step"]}: {it["q"]}',
                    "description": f'Condensed screen recording of the {it["skill"]} step run by SOMIN agents in Claude on Grab Singapore data, '
                                   f'shown at Marketing Mondays ({REPLAYS["session_title"]}, 12 October 2026).',
                    "thumbnailUrl": absu(f'/assets/video/{k}.webp'), "contentUrl": absu(f'/assets/video/{k}.mp4'),
                    "uploadDate": REPLAYS['session_date'] + 'T18:00:00+08:00', "duration": f'PT{it["dur"]}S',
                    "publisher": {"@id": f"{BASE}/#organization"}, "inLanguage": "en"})
    return out


_IMG_SIZES = {}


def image_size(src):
    """(width, height) of a local JPEG/PNG/WebP under static/ (stdlib header parsing), else None."""
    if not src or src.startswith('http'):
        return None
    if src in _IMG_SIZES:
        return _IMG_SIZES[src]
    f = ROOT / 'static' / src.lstrip('/')
    size = None
    try:
        d = f.read_bytes()
        if d[:8] == b'\x89PNG\r\n\x1a\n':
            size = struct.unpack('>II', d[16:24])
        elif d[:2] == b'\xff\xd8':
            i = 2
            while i < len(d) - 9:
                if d[i] != 0xFF:
                    i += 1
                    continue
                m = d[i + 1]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack('>HH', d[i + 5:i + 9])
                    size = (w, h)
                    break
                i += 2 + struct.unpack('>H', d[i + 2:i + 4])[0]
        elif d[:4] == b'RIFF' and d[8:12] == b'WEBP':
            if d[12:16] == b'VP8X':
                size = (1 + int.from_bytes(d[24:27], 'little'), 1 + int.from_bytes(d[27:30], 'little'))
            elif d[12:16] == b'VP8 ':
                w, h = struct.unpack('<HH', d[26:30])
                size = (w & 0x3FFF, h & 0x3FFF)
            elif d[12:16] == b'VP8L':
                b = int.from_bytes(d[21:25], 'little')
                size = ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
    except OSError:
        size = None
    _IMG_SIZES[src] = tuple(size) if size else None
    return _IMG_SIZES[src]


# ------------------------------------------------------------------ content dates (sitemap lastmod, schema dateModified)
# data/content-dates.json keeps a fingerprint of every indexable page body with the date it last changed, so lastmod only
# moves when the page itself changes (not on every build). The builder updates it; commit it with your content change.
DATES_FILE = ROOT / 'data/content-dates.json'
DATES = json.loads(DATES_FILE.read_text(encoding='utf-8')) if DATES_FILE.exists() else {}
DATES.pop('_doc', None)
PAGE_DATES = {}


def content_date(path, body, meta):
    if meta.get('lastmod'):
        d = str(meta['lastmod'])[:10]
    elif meta.get('layout') == 'post':
        d = (meta.get('modified') or meta['published'])[:10]           # blog: the article header is the source of truth
    elif not meta.get('robots', 'index,follow').startswith('index'):
        return TODAY
    else:
        h = hashlib.sha1(re.sub(r'\?v=\d{12}', '', body).encode('utf-8')).hexdigest()[:16]
        rec = DATES.get(path) or {}
        if rec.get('hash') == h:
            d = rec['modified']
        else:
            d = TODAY
            DATES[path] = {'hash': h, 'modified': d, 'published': rec.get('published') or meta.get('published') or d}
        if meta.get('published'):                                        # an explicit publish date in the source wins
            DATES[path]['published'] = str(meta['published'])[:10]
    PAGE_DATES[path] = d
    return d


def content_published(path, meta):
    return str(meta.get('published') or (DATES.get(path) or {}).get('published') or TODAY)[:10]


def save_dates():
    rows = [('_doc', 'Written by build.py: body fingerprint + last-changed date per indexable URL (sitemap lastmod, schema dateModified). Commit it.')]
    rows += [(k, DATES[k]) for k in sorted(DATES)]
    text = '{\n' + ',\n'.join(f'{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in rows) + '\n}\n'
    if not DATES_FILE.exists() or DATES_FILE.read_text(encoding='utf-8') != text:
        DATES_FILE.write_text(text, encoding='utf-8')


def url_for(slug):
    return '/' if not slug else '/' + slug.strip('/') + '/'


def absu(path):
    if not path:
        return None
    if path.startswith('http'):
        return path
    return BASE + path


def strip_tags(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def initials(name):
    parts = [p for p in re.sub(r'^(Prof\.|Dr\.)\s*', '', name).split() if p[0].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper() if parts else 'S'


def fmt_date(iso):
    d = dt.datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return d.strftime('%-d %B %Y') if os.name != 'nt' else d.strftime('%d %B %Y')


# ------------------------------------------------------------------ icons
ICON = {
    'chev': '<svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    'search': '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    'check': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5L20 7" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    'download': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 21h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    'linkedin': '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05C20.6 8.65 21 11.2 21 14.5V21h-4v-5.7c0-1.36-.03-3.1-1.9-3.1-1.9 0-2.2 1.48-2.2 3v5.8H9z"/></svg>',
    'x': '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M17.8 3h3.3l-7.2 8.2L22.4 21h-6.6l-5.2-6.8L4.6 21H1.3l7.7-8.8L.9 3h6.8l4.7 6.2L17.8 3zm-1.2 16h1.8L6.5 4.9H4.6L16.6 19z"/></svg>',
    'link': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a5 5 0 007.07 0l3-3a5 5 0 00-7.07-7.07l-1.5 1.5M14 10a5 5 0 00-7.07 0l-3 3a5 5 0 007.07 7.07l1.5-1.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    'arrow': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
}

CAL_DEFAULT = TRACK['calendly']['default_url']
CAL_CASES = 'https://calendly.com/roman-vss/30min'


# ------------------------------------------------------------------ chrome
def link_attrs(item):
    a = f'href="{E(item["href"])}"'
    if item.get('gtm_id'):
        a += f' data-gtm-id="{E(item["gtm_id"])}"'
    if item.get('lead_form'):
        a += f' data-lead-form="{E(item["lead_form"])}"'
    return a


def render_header(path):
    items = []
    for n in CFG['nav']:
        current = ' is-current' if (n['href'] == path or (n['href'] != '/' and path.startswith(n['href']) and not n['href'].startswith('http'))) else ''
        if n.get('children'):
            sub = ''.join(f'<li><a {link_attrs(c)}>{E(c["label"])}</a></li>' for c in n['children'])
            sid = 'sub-' + re.sub(r'[^a-z]+', '-', n['label'].lower()).strip('-')
            items.append(
                f'<li class="nav-item has-sub{current}"><a class="nav-link" {link_attrs(n)}>{E(n["label"])}</a>'
                f'<button class="nav-sub-toggle" type="button" aria-expanded="false" aria-controls="{sid}" aria-label="Show {E(n["label"])} menu">{ICON["chev"]}</button>'
                f'<ul class="nav-sub{" nav-sub--cols" if len(n["children"]) > 12 else ""}" id="{sid}">{sub}</ul></li>')
        else:
            items.append(f'<li class="nav-item{current}"><a class="nav-link" {link_attrs(n)}>{E(n["label"])}</a></li>')
    cta = CFG['nav_cta']
    return f'''<header class="site-header">
  <div class="bar">
    <a class="site-logo" href="/" aria-label="SOMIN home"><span class="wm-logo" aria-hidden="true"><span class="so">SO</span><span class="min">MIN</span></span></a>
    <!--i18n:switch-->
    <button class="nav-toggle" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="site-nav"><span></span><span></span><span></span></button>
    <nav class="site-nav" id="site-nav" aria-label="Main">
      <ul class="nav-list">{''.join(items)}</ul>
      <div class="nav-cta"><a class="btn btn--line btn--sm" {link_attrs(cta)}>{E(cta['label'])}</a></div>
    </nav>
  </div>
</header>'''


def render_footer():
    f = CFG['footer']
    compare = ''.join(f'<li><a href="{E(c["href"])}">{E(c["label"])}</a></li>' for c in f['compare'])
    cols = ''
    for col in f['columns']:
        cols += f'<div class="f-col"><h3>{E(col["title"])}</h3><ul>' + ''.join(f'<li><a {link_attrs(l)}>{E(l["label"])}</a></li>' for l in col['links']) + '</ul></div>'
    badges = ''.join(f'<a class="f-badge" href="{E(b["href"])}" rel="noopener" target="_blank"><img src="{E(b["img"])}" alt="{E(b["alt"])}" width="64" height="64" loading="lazy"><span>{E(b["text"])}</span></a>' for b in f['badges'])
    reviews = rating_badges('rv-badges--footer') + ''.join(f'<a href="{E(r["href"])}" rel="noopener" target="_blank">{E(r["label"])}</a>' for r in f['reviews'] if r['label'] not in ('G2', 'Capterra'))
    return f'''<footer class="site-footer">
  <nav class="f-compare" aria-label="Comparisons"><ul>{compare}</ul></nav>
  <div class="f-main">
    <div class="f-brand"><a href="/" aria-label="SOMIN home" style="text-decoration:none"><span class="wm-logo" aria-hidden="true"><span class="so">SO</span><span class="min">MIN</span></span></a>
      <p>{E(SITE['tagline'][:1].upper() + SITE['tagline'][1:])}. Built in Singapore by seasoned marketers and an AI professor, used across 11+ markets. <a href="/research/" data-gtm-id="footer_research">Read the research</a>.</p>
      <a class="btn btn--line btn--sm" href="{CAL_DEFAULT}" data-gtm-id="footer_book_a_call_btn">Book a call</a></div>
    {cols}
  </div>
  <div class="f-badges">{badges}<div class="f-reviews"><span>Reviews:</span>{reviews}</div></div>
  <div class="f-bottom"><div><span>© <span data-year>{dt.date.today().year}</span> SOMIN. All rights reserved.</span><span><a href="/privacy-policy/">Privacy Policy</a> · <a href="/vision/">Our Vision</a> · <a href="/sitemap.xml">Sitemap</a></span></div></div>
</footer>'''


HEADER_CACHE = {}
FOOTER_HTML = None


ORG_ID, SOFTWARE_ID, WEBSITE_ID = f"{BASE}/#organization", f"{BASE}/#software", f"{BASE}/#website"
FOUNDER_ID = f"{BASE}/#{ORG['founder']['id']}"


def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def org_node():
    """The one Organization node (data/organization.json). Every page carries this exact node; page-level copies are replaced."""
    o = ORG['organization']
    founders = []
    for f in o['founders']:
        if f.get('ref') == ORG['founder']['id']:
            founders.append({"@id": FOUNDER_ID})
        else:
            p = {"@type": "Person", "@id": f"{BASE}/#{f['author_slug']}", "name": f['name'], "jobTitle": f['job_title'], "sameAs": f.get('same_as', [])}
            if f.get('author_slug'):
                p['url'] = absu(f'/authors/{f["author_slug"]}/')
            founders.append(p)
    return {"@type": "Organization", "@id": ORG_ID, "name": o['name'], "legalName": o['legal_name'], "alternateName": o['alternate_names'],
            "url": f"{BASE}/", "logo": {"@type": "ImageObject", "url": absu('/assets/img/brand/somin-logo-512.png'), "width": 512, "height": 512},
            "image": absu(SITE['default_og_image']), "description": o['description'], "slogan": o['slogan'], "email": o['email'],
            "foundingLocation": {"@type": "Place", "name": o['founding_location']},
            "address": {"@type": "PostalAddress", "addressLocality": o['founding_location'], "addressCountry": o['country']},
            "founder": founders, "award": o['awards'], "areaServed": [{"@type": "Country", "name": m} for m in o['markets']],
            "contactPoint": {"@type": "ContactPoint", "contactType": "sales", "email": o['email'], "url": CAL_DEFAULT, "availableLanguage": ["English"]},
            "knowsAbout": ["AI marketing intelligence", "Competitor ad monitoring", "Audience research", "Campaign planning", "Creative scoring", "Creator marketing", "Agentic AI"],
            "sameAs": _uniq(o['same_as'] + SITE['same_as']),
            "subjectOf": [{"@type": "Article", "name": s['name'], "url": s['url']} for s in o['subject_of']],
            **({"memberOf": [{"@type": "Organization", "name": m['name'], "url": m['url']} for m in o['member_of']]} if o.get('member_of') else {})}


def offers_node():
    """AggregateOffer for SOMIN's four self-serve plans (monthly list prices from data/pricing.json)."""
    pr = PRICING
    plans = pr['plans']
    return {"@type": "AggregateOffer", "priceCurrency": pr['currency'], "lowPrice": f"{min(p['price'] for p in plans):.2f}",
            "highPrice": f"{max(p['price'] for p in plans):.2f}", "offerCount": len(plans), "url": absu('/pricing/'),
            "offers": [{"@type": "Offer", "name": p['name'], "description": f"{p['tagline']}: {p['seats']}, {p['brands']} brands monitored",
                        "url": absu(f"/pricing/#plan-{p['key']}"), "price": f"{p['price']:.2f}", "priceCurrency": pr['currency'],
                        "availability": "https://schema.org/InStock", "seller": {"@id": ORG_ID},
                        "priceSpecification": {"@type": "UnitPriceSpecification", "price": f"{p['price']:.2f}", "priceCurrency": pr['currency'],
                                               "billingDuration": "P1M", "unitText": "MONTH", "valueAddedTaxIncluded": False}} for p in plans]}


def software_node():
    s = ORG['software']
    return {"@type": "SoftwareApplication", "@id": SOFTWARE_ID, "name": s['name'], "alternateName": s['alternate_names'], "url": f"{BASE}/",
            "applicationCategory": s['category'], "applicationSubCategory": s['sub_category'], "operatingSystem": s['operating_system'],
            "description": s['description'], "featureList": s['features'], "publisher": {"@id": ORG_ID}, "offers": offers_node(),
            "audience": [{"@type": "Audience", "audienceType": a['type'], "url": absu(a['url'])} for a in s['audience']],
            "citation": [{"@type": "ScholarlyArticle", "name": c['name'], "url": c['url']} for c in s['citations']]}


def founder_node():
    f = ORG['founder']
    return {"@type": "Person", "@id": FOUNDER_ID, "name": f['name'], "honorificPrefix": f['honorific_prefix'], "alternateName": f['alternate_names'],
            "jobTitle": f['job_title'], "url": absu(f'/authors/{f["id"]}/'), "description": f['description'], "worksFor": {"@id": ORG_ID},
            "affiliation": {"@type": "CollegeOrUniversity", "name": f['affiliation']}, "alumniOf": {"@type": "CollegeOrUniversity", "name": f['alumni_of']},
            "knowsAbout": f['knows_about'], "sameAs": f['same_as']}


def website_node():
    return {"@type": "WebSite", "@id": WEBSITE_ID, "url": f"{BASE}/", "name": "SOMIN", "alternateName": ORG['organization']['alternate_names'],
            "inLanguage": "en", "publisher": {"@id": ORG_ID}}


CANONICAL_NODES = {ORG_ID: org_node, SOFTWARE_ID: software_node, WEBSITE_ID: website_node, FOUNDER_ID: founder_node}


def _flatten_ld(obj):
    if isinstance(obj, list):
        return [n for o in obj for n in _flatten_ld(o)]
    if isinstance(obj, dict) and '@graph' in obj:
        return _flatten_ld(obj['@graph'])
    if isinstance(obj, dict):
        return [{k: v for k, v in obj.items() if k != '@context'}]
    return []


def schema_graph(nodes, path, lang='en'):
    """One clean @graph per page: page copies of the shared nodes (Organization, SoftwareApplication, WebSite, founder) are
    replaced by the canonical ones, duplicate @ids and second FAQPages are dropped, and a WebPage whose @id points at
    another URL is re-anchored to this page."""
    url = absu(path) if path != '/404.html' else None
    out, seen, faq = [], set(), False
    remap = {}
    for n in nodes:
        nid = n.get('@id')
        t = n.get('@type')
        if nid in CANONICAL_NODES:
            if nid in seen:
                continue
            seen.add(nid)
            out.append(CANONICAL_NODES[nid]())
            continue
        if t == 'FAQPage':
            if faq:
                continue
            faq = True
        if url and t in ('WebPage', 'CollectionPage', 'AboutPage', 'ProfilePage') and nid and nid.split('#')[0] != url:
            new = url + '#webpage'
            remap[nid] = new
            n = dict(n, **{'@id': new, 'url': url})
        if nid:
            nid = remap.get(nid, nid)
            if nid in seen:
                continue
            seen.add(nid)
        if lang != 'en' and t in ('WebPage', 'CollectionPage', 'FAQPage', 'AboutPage'):
            n = dict(n, inLanguage=lang)
        out.append(n)
    txt = json.dumps({"@context": "https://schema.org", "@graph": out}, ensure_ascii=False)
    for a, b in remap.items():
        txt = txt.replace(f'"{a}"', f'"{b}"')
    return txt


def breadcrumbs(trail):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": absu(u)} for i, (n, u) in enumerate(trail)]}


def page(meta, body, path, extra_head=''):
    """Wrap a page body in the full HTML document."""
    title = meta.get('seo_title') or meta.get('title') or 'SOMIN'
    desc = meta.get('description') or SITE['description']
    robots = meta.get('robots', 'index,follow')
    canonical = absu(meta.get('canonical') or path)
    og_img = absu(meta.get('og_image') or SITE['default_og_image'])
    og_type = 'article' if meta.get('layout') == 'post' else 'website'
    lang = meta.get('_lang', 'en')
    tags = [
        f'<meta charset="utf-8">',
        f'<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{E(title)}</title>',
        f'<meta name="description" content="{E(desc)}">',
    ]
    if meta.get('keywords'):
        tags.append(f'<meta name="keywords" content="{E(meta["keywords"])}">')
    tags += [
        f'<meta name="robots" content="{E(robots)}{",max-image-preview:large" if robots.startswith("index") else ""}">',
        f'<link rel="canonical" href="{E(canonical)}">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="SOMIN">',
        f'<meta property="og:locale" content="{E(meta.get("_og_locale") or SITE["locale"])}">',
        f'<meta property="og:url" content="{E(canonical)}">',
        f'<meta property="og:title" content="{E(meta.get("og_title") or title)}">',
        f'<meta property="og:description" content="{E(meta.get("og_description") or desc)}">',
        f'<meta property="og:image" content="{E(og_img)}">',
        f'<meta property="og:image:alt" content="{E(meta.get("og_title") or title)}">',
        f'<meta property="fb:app_id" content="{SITE["fb_app_id"]}">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{E(meta.get("twitter_title") or meta.get("og_title") or title)}">',
        f'<meta name="twitter:description" content="{E(meta.get("twitter_description") or meta.get("og_description") or desc)}">',
        f'<meta name="twitter:image" content="{E(og_img)}">',
    ]
    dims = image_size(meta.get('og_image') or SITE['default_og_image'])
    if dims:
        tags += [f'<meta property="og:image:width" content="{dims[0]}">', f'<meta property="og:image:height" content="{dims[1]}">']
    for hl, href in meta.get('_alternates', []):
        tags.append(f'<link rel="alternate" hreflang="{E(hl)}" href="{E(absu(href))}">')
    if meta.get('layout') == 'post':
        tags += [f'<meta property="article:published_time" content="{E(meta["published"])}">',
                 f'<meta property="article:modified_time" content="{E(meta.get("modified") or meta["published"])}">',
                 f'<meta property="article:author" content="{E(meta["author"])}">',
                 f'<meta name="author" content="{E(meta["author"])}">']
        tags += [f'<meta property="article:tag" content="{E(t)}">' for t in meta.get('tags', [])]
    tags += [
        f'<meta name="theme-color" content="{SITE["theme_color"]}">',
        f'<link rel="icon" href="{SITE["favicon"]}" type="image/png">',
        f'<link rel="apple-touch-icon" href="/assets/img/brand/apple-touch-icon.png">',
        f'<link rel="alternate" type="application/rss+xml" title="SOMIN Blog" href="/blog/rss.xml">',
        f'<link rel="preconnect" href="https://www.googletagmanager.com">',
        f'<link rel="preconnect" href="https://fonts.googleapis.com">',
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400&display=swap">',
        f'<link rel="stylesheet" href="/assets/css/site.css?v={BUILD_ID}">',
        f'<script src="/assets/js/tracking.js?v={BUILD_ID}"></script>',
        f'<script src="/assets/js/site.js?v={BUILD_ID}" defer></script>',
    ]
    # ---- structured data: page JSON-LD (meta + any blocks in the body) and the builder's nodes become ONE graph
    nodes = []
    for js in meta.get('jsonld', []):
        nodes += _flatten_ld(json.loads(js))
    in_body = re.findall(r'<script type="application/ld\+json">(.*?)</script>\s*', body, re.S)
    if in_body:
        body = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', '', body, flags=re.S)
        for js in in_body:
            nodes += _flatten_ld(json.loads(js))
    nodes += _flatten_ld(meta.get('_schema', []))
    if robots.startswith('index'):
        nodes += video_nodes(body, path)
        if not any(n.get('@type') == 'FAQPage' for n in nodes):
            fq = faq_node(body, path)
            if fq:
                nodes.append(fq)
    date_mod = content_date(path, body, meta)
    for n in nodes:
        if n.get('@type') in ('WebPage', 'CollectionPage', 'AboutPage', 'ProfilePage', 'Article') and not n.get('dateModified'):
            n['dateModified'] = date_mod
            if n.get('@type') == 'Article' and not n.get('datePublished'):
                n['datePublished'] = content_published(path, meta)
    if nodes:
        tags.append(f'<script type="application/ld+json">{schema_graph(nodes, path, lang)}</script>')
    layout = meta.get('layout', 'page')
    attrs = f' data-page-type="{E(meta.get("type", "page"))}" data-page-layout="{E(layout)}" data-content-group="{E(meta.get("group", meta.get("type", "page")))}"'
    if lang != 'en':
        attrs += f' data-locale="{E(meta["_locale"])}"'
    if meta.get('lead_type'):
        attrs += f' data-lead-type="{E(meta["lead_type"])}"'
    noscript = ''
    head = '\n'.join(tags) + extra_head
    return f'''<!doctype html>
<html lang="{E(lang)}"{attrs}>
<head>
{head}
</head>
<body class="page-{E(layout)}">
<a class="skip-link" href="#main">Skip to content</a>
{render_header(path)}
<main id="main">
{body}
</main>
{FOOTER_HTML}
{noscript}
</body>
</html>
'''


def write(path, html_text):
    p = OUT / path.lstrip('/')
    if path.endswith('/'):
        p = p / 'index.html'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_text, encoding='utf-8')


SITEMAP = []  # (path, lastmod, priority)
LOCALE_ALTERNATES = {}  # path -> [(hreflang, path)] for the sitemap


def add_sitemap(path, lastmod=None, priority='0.6', robots='index'):
    if robots.startswith('index'):
        SITEMAP.append((path, lastmod or TODAY, priority))


# ------------------------------------------------------------------ helpers for content
def add_heading_ids(body, levels=('h2', 'h3')):
    seen = set()

    def rep(m):
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        if 'id=' in attrs:
            return m.group(0)
        base = re.sub(r'[^a-z0-9]+', '-', strip_tags(inner).lower()).strip('-')[:60] or 'section'
        i, n = base, 2
        while i in seen:
            i, n = f'{base}-{n}', n + 1
        seen.add(i)
        return f'<{tag} id="{i}"{attrs}>{inner}</{tag}>'
    pat = r'<(' + '|'.join(levels) + r')(\b[^>]*)>(.*?)</\1>'
    return re.sub(pat, rep, body, flags=re.S)


def wrap_tables(body):
    """Wide tables scroll inside their own box on phones instead of pushing the page wider."""
    return re.sub(r'(<table\b.*?</table>)', r'<div class="table-wrap">\1</div>', body, flags=re.S)


def toc_items(body, levels=('h2', 'h3'), only_numbered=False):
    out = []
    for m in re.finditer(r'<(' + '|'.join(levels) + r')\b[^>]*id="([^"]+)"[^>]*>(.*?)</\1>', body, re.S):
        t = strip_tags(m.group(3))
        if only_numbered and not re.match(r'^\d+\.', t):
            continue
        out.append((m.group(1), m.group(2), t))
    return out


# ------------------------------------------------------------------ unified theme for imported page templates
THEME_PREFIXES = ('sc', 'se', 'sa', 'sb', 'si')
HEX_FIX = {'#2DBE9C': '#2DBF9C', '#1F8A4F': '#1F8A70', '#2A6B7E': '#1F8A70', '#A8D744': '#9CD632', '#4D8FE8': '#2DBF9C',
           '#E8B23D': '#2DBF9C', '#F4D06F': '#7FDCC4', '#82A933': '#1F8A70', '#6FB9CC': '#7FDCC4', '#1F4F5C': '#17594A',
           '#6B7891': '#2A3635', '#54607A': '#1F2A29', '#C4998F': '#D5F2EA', '#9E7A71': '#A9DCCD'}          # off-palette → SOMIN teal family
DEEP_HEX = ('#101817', '#0D1514', '#0F1816', '#101B19', '#0B1211', '#062018')      # extra-dark panels follow the surface
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


def theme_css(css):
    """Re-point a page template's stylesheet to the SOMIN palette and make it surface-aware."""
    css = re.sub(r"(--(?:sc|se|sa|sb|si)-body\s*:\s*)'Inter'", r"\1'Montserrat'", css)
    for a, b in HEX_FIX.items():
        css = re.sub(re.escape(a) + r'(?![0-9a-fA-F])', b, css, flags=re.I)
    for h in DEEP_HEX:
        css = re.sub(re.escape(h) + r'(?![0-9a-fA-F])', f'var(--u-deep,{h})', css, flags=re.I)
    css = re.sub(r'rgba\(\s*42\s*,\s*107\s*,\s*126\s*,', 'rgba(31,138,112,', css)   # old blue-teal tint
    # shadows tuned per surface (soft on white, deep on dark)
    css = re.sub(r'rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*([0-9.]+)\s*\)', lambda m: f'rgba(9,18,16,calc({m.group(1)} * var(--u-sh,1)))', css)

    def rule(m):
        sel, body = m.group(1), m.group(2)
        # image/screenshot panels painted with the "white" token are real white surfaces, not inverse text colour
        if not re.search(r'hover|btn|button|active|is-|:focus', sel) and not re.search(r'(?<![-\w])color\s*:\s*var\(--(?:sc|se|sa|sb|si)-charcoal', body):
            body = re.sub(r'(background(?:-color)?\s*:\s*)var\(--(sc|se|sa|sb|si)-white\)', r'\1#FFFFFF', body)
        return sel + '{' + body + '}'
    return re.sub(r'([^{}]+)\{([^{}]*)\}', rule, css)


def _top_children(html):
    """Start/end offsets of the direct children of the template wrapper (.somin-embed*, .somin-agency …)."""
    depth, wrap, out, i = 0, None, [], 0
    tag_re = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
    while True:
        m = tag_re.search(html, i)
        if not m:
            break
        close, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        i = m.end()
        if not close and tag in ('script', 'style'):
            e = html.lower().find(f'</{tag}', i)
            i = html.find('>', e) + 1 if e >= 0 else len(html)
            continue
        if tag in VOID or attrs.rstrip().endswith('/'):
            continue
        if close:
            if wrap is not None and depth == wrap + 1 and out and out[-1]['end'] is None:
                out[-1]['end'] = m.end()
            depth -= 1
            continue
        depth += 1
        if wrap is None and re.search(r'class="[^"]*\bsomin-(?:embed|embed-case|agency|brands|influencer)\b', attrs):
            wrap = depth
        elif wrap is not None and depth == wrap + 1:
            cls = re.search(r'class="([^"]*)"', attrs)
            out.append({'start': m.start(), 'tag_end': m.end(), 'tag': tag, 'cls': cls.group(1) if cls else '', 'end': None})
    return out


def theme_sections(body):
    """Assign every top-level section a surface so all pages share one rhythm:
    dark hero → white / mist content (alternating) → dark proof bands → dark CTA."""
    kids = _top_children(body)
    if not kids:
        return body
    plan, alt = [], 0
    for k in kids:
        c = k['cls']
        inner = body[k['tag_end']:k['end'] or k['tag_end']]
        if re.search(r'modal|lightbox', c):
            plan.append(None); continue
        if re.search(r'(^|[\s-])hero\b|-hero-', c):
            plan.append('u-hero'); alt = 0; continue
        if re.search(r'partners|trust', c) or k['tag'] == 'aside':
            plan.append('u-dark u-hero-tail'); alt = 0; continue
        if re.search(r'final', c):
            plan.append('u-dark u-cta'); continue
        if re.search(r'(^|\s)trace(\s|$)', c):
            plan.append('u-dark'); alt = 0; continue
        if re.search(r'proof|impact', c) or (re.search(r'class="[^"]*\b\w+-(?:quote|pullquote|testimonial)\b', inner) and re.search(r'-stat|-num\b', inner)):
            plan.append('u-dark'); alt = 0; continue
        plan.append('u-light' if alt % 2 == 0 else 'u-mist'); alt += 1
    # wrap each section in a full-width band that carries the surface (sections themselves are max-width boxes)
    out, last = [], 0
    for k, cls in zip(kids, plan):
        if not cls or k['end'] is None:
            continue
        out.append(body[last:k['start']])
        out.append(f'<div class="u-band {cls}">')
        out.append(body[k['start']:k['end']])
        out.append('</div>')
        last = k['end']
    out.append(body[last:])
    return ''.join(out)


def theme_fragment(body):
    body = re.sub(r'(<style[^>]*>)(.*?)(</style>)', lambda m: m.group(1) + theme_css(m.group(2)) + m.group(3), body, flags=re.S)
    return theme_sections(body)


# ------------------------------------------------------------------ layouts
# ------------------------------------------------------------------ localized home pages (/<lang>/) from the hero translations
# The home page carries its own 17-language dictionary (DICT_GZ_B64 in content/pages/index.html, keys = data-i18n attributes).
# The builder pre-renders one static, indexable page per language so search and answer engines see the translations
# (hreflang + x-default on every version); the in-page language menu links to those URLs.
LOCALES = {  # code: (path segment, hreflang, og:locale, <title>)
    'zh-Hans': ('zh-hans', 'zh-Hans', 'zh_CN', 'SOMIN：AI 营销情报与营销活动策划平台'),
    'zh-Hant': ('zh-hant', 'zh-Hant', 'zh_TW', 'SOMIN：AI 行銷情報與行銷活動企劃平台'),
    'ja': ('ja', 'ja', 'ja_JP', 'SOMIN：AIマーケティング・インテリジェンスとキャンペーン企画'),
    'ko': ('ko', 'ko', 'ko_KR', 'SOMIN: AI 마케팅 인텔리전스 및 캠페인 기획 플랫폼'),
    'th': ('th', 'th', 'th_TH', 'SOMIN: AI ข้อมูลเชิงลึกการตลาดและการวางแผนแคมเปญ'),
    'vi': ('vi', 'vi', 'vi_VN', 'SOMIN: Phân tích marketing bằng AI và lập kế hoạch chiến dịch'),
    'id': ('id', 'id', 'id_ID', 'SOMIN: Intelijen Pemasaran AI & Perencanaan Kampanye'),
    'ms': ('ms', 'ms', 'ms_MY', 'SOMIN: Risikan Pemasaran AI & Perancangan Kempen'),
    'hi': ('hi', 'hi', 'hi_IN', 'SOMIN: AI मार्केटिंग इंटेलिजेंस और कैंपेन प्लानिंग'),
    'fil': ('fil', 'tl', 'tl_PH', 'SOMIN: AI Marketing Intelligence at Pagpaplano ng Kampanya'),
    'es': ('es', 'es', 'es_ES', 'SOMIN: Inteligencia de marketing con IA y campañas'),
    'fr': ('fr', 'fr', 'fr_FR', 'SOMIN : intelligence marketing IA et planification de campagne'),
    'de': ('de', 'de', 'de_DE', 'SOMIN: KI-Marketing-Intelligence und Kampagnenplanung'),
    'pt': ('pt', 'pt', 'pt_BR', 'SOMIN: Inteligência de marketing com IA e campanhas'),
    'ar': ('ar', 'ar', 'ar_AR', 'SOMIN: ذكاء تسويقي بالذكاء الاصطناعي وتخطيط الحملات'),
    'ru': ('ru', 'ru', 'ru_RU', 'SOMIN: ИИ-аналитика маркетинга и планирование кампаний'),
}


def _home_dict(body):
    m = re.search(r'DICT_GZ_B64\s*=\s*"([A-Za-z0-9+/=]+)"', body)
    if not m:
        return None, []
    d = json.loads(gzip.decompress(base64.b64decode(m.group(1))))
    langs = json.loads(re.search(r'var LANGS = (\[.*?\]);', body, re.S).group(1))
    return d, langs


def apply_i18n(body, dct, fallback):
    """Server-side twin of the page's applyLang(): every [data-i18n] element's content becomes the translated text."""
    tag_re = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
    out, i = [], 0
    while True:
        m = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-i18n="([^"]+)"[^>]*>', body[i:])
        if not m:
            out.append(body[i:])
            break
        start, open_end, tag, key = i + m.start(), i + m.end(), m.group(1).lower(), m.group(2)
        if tag in VOID:
            out.append(body[i:open_end]); i = open_end; continue
        depth, j, close_start, close_end = 1, open_end, None, None
        while True:
            t = tag_re.search(body, j)
            if not t:
                break
            if t.group(2).lower() == tag and not t.group(3).rstrip().endswith('/'):
                depth += -1 if t.group(1) else 1
                if depth == 0:
                    close_start, close_end = t.start(), t.end()
                    break
            j = t.end()
        if close_start is None:
            out.append(body[i:open_end]); i = open_end; continue
        txt = dct.get(key, fallback.get(key))
        out.append(body[i:open_end])
        out.append(E(txt) if txt is not None else body[open_end:close_start])
        out.append(body[close_start:close_end])
        i = close_end
    return ''.join(out)


def build_home_locales(meta, body):
    """Write /<lang>/ for every language in the home dictionary; returns the hreflang alternates for the English page."""
    d, langs = _home_dict(body)
    if not d:
        return []
    langs = [l for l in langs if l['code'] == 'en' or (l['code'] in d and l['code'] in LOCALES)]
    alts = [('en', '/')] + [(LOCALES[l['code']][1], f'/{LOCALES[l["code"]][0]}/') for l in langs if l['code'] != 'en'] + [('x-default', '/')]
    en = d.get('en', {})
    base = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', '', body, flags=re.S)   # English FAQ/WebPage schema stays on /
    for l in langs:
        code = l['code']
        if code == 'en':
            continue
        seg, hl, ogl, title = LOCALES[code]
        path = f'/{seg}/'
        lb = apply_i18n(base, d[code], en)
        lb = lb.replace('class="se-hero" id="se-hero-root"', f'class="se-hero" id="se-hero-root" lang="{code}"' + (' dir="rtl"' if code == 'ar' else ''), 1)
        # The hero subline alone is short, so the description is headline + subline + "what SOMIN does" line.
        sub = strip_tags(d[code].get('sub') or '').strip()
        for k in ('h1a', 'wd_body'):            # add whole sentences only while the description stays within 160 chars
            extra = strip_tags(d[code].get(k) or '').strip()
            cand = f'{extra} {sub}' if k == 'h1a' else f'{sub} {extra}'
            if extra and len(cand) <= 160:
                sub = cand
        desc = sub if len(sub) <= 160 else sub[:157].rsplit(' ', 1)[0].rstrip(',;:—') + '…'
        lm = {k: v for k, v in meta.items() if k not in ('jsonld', 'keywords', 'seo_title', 'og_title', 'og_description', 'twitter_title', 'twitter_description', 'lastmod')}
        h1 = strip_tags(' '.join(d[code].get(k, '') for k in ('h1a',)) + ' ' + ''.join(d[code].get(k, '') for k in ('h1b_pre', 'h1_it', 'h1b_post')))
        lm.update({'slug': seg, 'title': title, 'seo_title': title, 'description': desc, 'og_title': f'SOMIN: {h1}', 'og_description': desc,
                   '_lang': code, '_locale': code, '_og_locale': ogl, '_alternates': alts, 'jsonld': [], 'secret_button': False})
        lm['_schema'] = [org_node(), founder_node(), software_node(), website_node(),
                         {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": title, "description": desc, "inLanguage": code,
                          "isPartOf": {"@id": WEBSITE_ID}, "about": {"@id": SOFTWARE_ID}, "publisher": {"@id": ORG_ID},
                          "translationOfWork": {"@id": f"{BASE}/#webpage"}}]
        write(path, page(lm, lb, path))
        add_sitemap(path, None, '0.8', 'index')
        LOCALE_ALTERNATES[path] = alts
    LOCALE_ALTERNATES['/'] = alts
    return alts


def build_fragment_page(meta, body):
    path = url_for(meta['slug'])
    if meta.get('secret_button'):
        body += ('\n<a class="secret-button" href="/try-somin/" data-lead-form="trial" data-gtm-id="secret_button">'
                 'You found the secret button! As a reward for your curiosity, enjoy 14 days of SOMIN on us. '
                 'Just click and drop your details in the form below.</a>')
    meta.setdefault('group', meta.get('type'))
    if meta.get('type') == 'case_study':
        body = case_fragment(meta, body, path)
    elif path != '/' and not any('BreadcrumbList' in js for js in meta.get('jsonld', [])):
        meta['_schema'] = [breadcrumbs([('Home', '/'), ((meta.get('seo_title') or meta['title']).split(' | ')[0], path)])]
    body = theme_fragment(body)
    body = hero_image(body, meta, 'u-band u-hero')
    if path == '/':
        alts = build_home_locales(meta, body)
        if alts:
            meta['_alternates'] = alts
    write(path, page(meta, body, path))
    pr = '1.0' if path == '/' else ('0.9' if meta['type'] in ('solution', 'product') else '0.8')
    add_sitemap(path, meta.get('lastmod'), pr, meta.get('robots', 'index'))


def build_doc_page(meta, body):
    path = url_for(meta['slug'])
    is_legal = meta.get('type') == 'legal'
    is_ref = meta.get('type') == 'reference'
    body = add_heading_ids(body, ('h2', 'h3'))
    body = wrap_tables(body)
    toc = toc_items(body, ('h2', 'h3'), only_numbered=is_legal) if is_legal else (toc_items(body, ('h2',)) if is_ref else [])
    toc_html = ''
    if len(toc) >= 3:
        toc_html = '<aside class="toc-dark" aria-label="On this page"><h2>On this page</h2><ol>' + ''.join(
            f'<li><a href="#{i}">{E(t)}</a></li>' for _, i, t in toc) + '</ol></aside>'
    eyebrow = 'Legal' if is_legal else ('Reference' if is_ref else 'Company')
    updated = f'<p class="updated">Last updated: {E(meta["updated"])}</p>' if meta.get('updated') else ''
    trail = [('Home', '/'), (meta.get('h1') or meta['title'].split(' | ')[0], path)]
    hero = f'''<section class="hero doc-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">{E(trail[-1][0])}</li></ol></nav>
  <p class="eyebrow">{eyebrow}</p>
  <h1>{E(meta.get('h1') or meta['title'])}</h1>{updated}
</div></section>'''
    wrap = f'<section class="doc-wrap"><div class="container"><div class="doc-layout">{toc_html or "<div></div>"}<article class="doc">{body}</article></div></div></section>'
    if not toc_html:
        wrap = f'<section class="doc-wrap"><div class="container"><div style="padding:56px 0 96px"><article class="doc" style="margin:0 auto">{body}</article></div></div></section>'
    if meta.get('variant') == 'vision':
        wrap = f'<section class="vision-wrap"><div class="container">{body}</div></section>'
    node = {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta.get('h1') or meta['title'],
            "description": meta.get('description'), "isPartOf": {"@id": f"{BASE}/#website"}, "publisher": {"@id": f"{BASE}/#organization"}, "inLanguage": "en"}
    if meta.get('updated'):
        try:
            node['dateModified'] = dt.datetime.strptime(meta['updated'], '%d %b %Y').date().isoformat()
        except ValueError:
            pass
    meta['_schema'] = [org_node(), website_node(), node, breadcrumbs(trail)]
    meta.setdefault('group', 'resources' if is_ref else 'company')
    write(path, page(meta, hero + wrap, path))
    add_sitemap(path, node.get('dateModified'), '0.3' if is_legal else ('0.7' if is_ref else '0.5'), meta.get('robots', 'index'))


def hero_image(body, meta, marker):
    """Topic background (SOMIN image-generate, static/assets/img/cases/bg/<slug>.webp) behind a case study's hero."""
    slug = meta.get('slug') or ''
    img = meta.get('hero_bg')
    if not img and meta.get('type') == 'case_study' and (ROOT / f'static/assets/img/cases/bg/{slug}.webp').exists():
        img = f'/assets/img/cases/bg/{slug}.webp'
    if not img:
        return body
    i = body.find(f'class="{marker}')
    if i < 0:
        return body
    k = body.find('"', i + len('class="'))          # end of the class attribute value
    return body[:k] + f' u-hero--img" style="--hero-img:url({img})' + body[k:]


CASE_PAGES = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted((ROOT / 'data/case-pages').glob('*.json'))}
SECTION_LABEL = {'brands': ('Brand', 'brands'), 'agencies': ('Agency', 'agencies'), 'creators': ('Creator', 'creators')}
_MANIFEST = {}


def manifest_cached():
    if not _MANIFEST:
        _MANIFEST.update(case_manifest())
    return _MANIFEST


def case_section(key):
    it = CASES['items'].get(key) or {}
    return (it.get('hub') or {}).get('section') or {'influencers': 'creators'}.get(it.get('category'), it.get('category')) or 'brands'


def related_cases(key, section, n=3):
    """Next n case pages in the same hub section (cyclic, so internal links spread evenly across all cases)."""
    man = manifest_cached()
    rows = [(k, v) for k, v in sorted(man.items(), key=lambda kv: kv[1]['order']) if v['on_hub'] and v['section'] == section and v['page']]
    keys = [k for k, _ in rows]
    if key in keys:
        i = keys.index(key)
        rows = rows[i + 1:] + rows[:i]
    return rows[:n]


def related_cards(key, section, gid):
    cards = ''
    for k, v in related_cases(key, section):
        summ = v['summary'] if len(v['summary']) <= 140 else v['summary'][:137].rsplit(' ', 1)[0] + '…'
        cards += (f'<a class="cs-rel" href="{E(v["page"])}" data-gtm-id="case_{gid}_related"><span>{E(v["category"] or "Case study")}'
                  f'{(" · " + E(v["market"])) if v.get("market") else ""}</span><strong>{E(v["title"])}</strong><em>{E(summ)}</em></a>')
    return cards


def case_schema(meta, path, h1, client, section, images):
    """One clean graph per case page: Organization, WebSite, WebPage, BreadcrumbList, Article (FAQPage is added from the visible FAQ)."""
    url = absu(path)
    bc = breadcrumbs([('Home', '/'), ('Case studies', '/cases-ai-marketing-strategy/'), (client, path)])
    bc['@id'] = url + '#breadcrumb'
    imgs = [absu(i) for i in images if i][:3] or [absu(meta.get('og_image') or SITE['default_og_image'])]
    web = {"@type": "WebPage", "@id": url + "#webpage", "url": url, "name": meta.get('seo_title') or meta['title'], "description": meta.get('description'),
           "isPartOf": {"@id": f"{BASE}/#website"}, "breadcrumb": {"@id": url + "#breadcrumb"}, "mainEntity": {"@id": url + "#article"},
           "primaryImageOfPage": {"@type": "ImageObject", "url": imgs[0]}, "inLanguage": "en"}
    art = {"@type": "Article", "@id": url + "#article", "headline": h1[:110], "description": meta.get('description'),
           "articleSection": f'{SECTION_LABEL.get(section, ("Brand",))[0]} case studies', "about": {"@type": "Organization", "name": client},
           "image": imgs, "author": {"@id": f"{BASE}/#organization"}, "publisher": {"@id": f"{BASE}/#organization"},
           "mainEntityOfPage": {"@id": url + "#webpage"}, "inLanguage": "en"}
    if meta.get('keywords'):
        art['keywords'] = meta['keywords']
    return [org_node(), website_node(), web, bc, art]


def case_fragment(meta, body, path):
    """Legacy (imported) case pages: one schema graph, visible breadcrumbs, research credit and related cases."""
    key = meta['slug']
    section = case_section(key)
    client = ((CASES['items'].get(key) or {}).get('hub') or {}).get('title') or meta.get('case_study_label') or key
    body = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', '', body, flags=re.S)
    m = re.search(r'<h1\b[^>]*>(.*?)</h1>', body, re.S)
    h1 = strip_tags(m.group(1)) if m else meta['title']
    meta['h1'] = h1
    meta['og_title'] = meta['twitter_title'] = h1
    meta['og_description'] = meta['twitter_description'] = meta.get('description')
    meta['case_study_label'] = client
    imgs = re.findall(r'<figure class="cs-panel[^"]*"><img src="([^"]+)"', body) + [meta.get('og_image')]
    meta['jsonld'] = []
    meta['_schema'] = case_schema(meta, path, h1, client, section, imgs)
    crumbs = (f'<nav class="breadcrumbs cs-crumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li>'
              f'<li><a href="/cases-ai-marketing-strategy/#{section}">Case studies</a></li><li aria-current="page">{E(client)}</li></ol></nav>')
    body = re.sub(r'(<span class="sc-eyebrow)', crumbs + r'\1', body, count=1)
    i = body.find('aria-label="About SOMIN"')
    if i > 0:
        k = body.find('</p>', i)
        if k > 0:
            body = body[:k + 4] + research_note() + body[k + 4:]
    gid = re.sub(r'[^a-z0-9]+', '_', key.replace('-case-study', '').replace('-case-stud', '')).strip('_')
    cards = related_cards(key, section, gid)
    if cards:
        rel = (f'<section class="sc-section cs-related" aria-label="Related case studies"><div class="sc-section-tag" data-nosnippet="">Related case studies</div>'
               f'<h2>More {SECTION_LABEL[section][0].lower()} case studies</h2><div class="cs-rel-grid">{cards}</div>'
               f'<p class="cs-rel-all"><a href="/cases-ai-marketing-strategy/#{section}" data-gtm-id="case_{gid}_all_cases">All case studies</a></p></section>\n')
        j = body.rfind('<div class="sc-final-wrap">')
        if j > 0:
            body = body[:j] + rel + body[j:]
    return body


def case_page_meta(key, c):
    return {'slug': c['slug'], 'layout': 'native', 'type': 'case_study', 'title': c['seo_title'], 'description': c['description'],
            'og_image': f'/assets/img/og/card-case-{key}.jpg' if (ROOT / f'static/assets/img/og/card-case-{key}.jpg').exists() else SITE['default_og_image'],
            'robots': 'index,follow', 'case_study_label': c['client'], 'group': 'case_study', 'h1': c['h1'], 'published': c.get('published')}


def build_case_pages(manifest):
    """Case-study pages composed from data/case-pages/<key>.json (content taken from each case-study PDF)."""
    metas = []
    for key, c in CASE_PAGES.items():
        meta = case_page_meta(key, c)
        path = url_for(c['slug'])
        label = c['client']
        cs = c.get('client_short') or label
        h1 = E(c['h1'])
        em = c.get('h1_em') or ''
        if em and c['h1'].endswith(em) and em != c['h1']:
            h1 = E(c['h1'][:-len(em)]) + f'<em>{E(em)}</em>'
        dl = (f'href="/get-case-study/?cs={E(key)}" data-lead-form="case_study" data-case-study="{E(key)}" '
              f'data-case-study-label="{E(label)}"')
        gid = re.sub(r'[^a-z0-9]+', '_', c['slug'].replace('-case-study', '')).strip('_')
        stats = ''.join(f'<div><strong>{E(st["num"])}{f"<span>{E(st.get(chr(117)+chr(110)+chr(105)+chr(116)))}</span>" if st.get("unit") else ""}</strong>'
                        f'<small>{E(st["label"])}</small></div>' for st in c.get('stats', [])[:3])
        slides = c.get('slides') or []
        def fig(sl, cls, eager=False):
            return (f'<figure class="{cls}"><img src="{E(sl["file"])}" alt="{E(sl["alt"])}" loading="{"eager" if eager else "lazy"}" decoding="async">'
                    f'{f"<figcaption>{E(sl[chr(99)+chr(97)+chr(112)+chr(116)+chr(105)+chr(111)+chr(110)])}</figcaption>" if sl.get("caption") else ""}</figure>')
        hero_fig = fig(slides[0], 'cs-panel', True) if slides else ''
        body = f'''<section class="hero cs-hero"><div class="container hero-split">
  <div>
    <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li><a href="/cases-ai-marketing-strategy/#{SECTION_LABEL[c['section']][1]}">Case studies</a></li><li aria-current="page">{E(cs)}</li></ol></nav>
    <p class="eyebrow">{E(c['eyebrow'])}</p>
    <h1>{h1}</h1>
    <p class="lede">{E(c['lede'])}</p>
    <p class="cs-meta">{E(c.get('meta_line', ''))}</p>
    <div class="cta-row cta-row--left">
      <a class="btn btn--solid" {dl} data-gtm-id="case_{gid}_hero_download">Get the full case study</a>
      <a class="btn btn--ghost" href="{CAL_CASES}" data-gtm-id="case_{gid}_hero_call">Book a call</a>
    </div>
    <div class="cs-hero-stats">{stats}</div>
  </div>
  {hero_fig}
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head">
    <p class="eyebrow eyebrow--ink">The challenge</p>
    <h2>{E(c['challenge']['title'])}</h2>
    <p>{E(c['challenge']['body'])}</p>
  </div>
  <div class="sec-head">
    <p class="eyebrow eyebrow--ink">The approach</p>
    <h2>{E(c['approach']['title'])}</h2>
    <ul class="check-list">{''.join(f'<li>{E(x)}</li>' for x in c['approach']['points'])}</ul>
  </div>
</div></section>

<section class="sec sec--mist"><div class="container">
  <div class="sec-head sec-head--center">
    <p class="eyebrow eyebrow--ink">Key findings</p>
    <h2>{E(c.get('findings_title') or f'Three findings from the {cs} data')}</h2>
  </div>
  <div class="card-grid">{''.join(f'<div class="tile"><span class="tile-num">{i:02d}</span><h3>{E(fd["title"])}</h3><p>{E(fd["body"])}</p></div>' for i, fd in enumerate(c['findings'][:3], 1))}</div>
</div></section>

<section class="sec sec--light"><div class="container split cs-deliver">
  <div class="sec-head">
    <p class="eyebrow eyebrow--ink">What SOMIN delivered</p>
    <h2>{E(c['delivered']['title'])}</h2>
    <ul class="check-list">{''.join(f'<li>{E(x)}</li>' for x in c['delivered']['points'])}</ul>
    <div class="cta-row cta-row--left"><a class="btn btn--solid" {dl} data-gtm-id="case_{gid}_deliver_download">Get the full case study</a></div>
  </div>
  <div class="cs-gallery">{''.join(fig(sl, 'cs-shot') for sl in slides[1:3])}</div>
</div></section>
'''
        if c.get('quote') and c['quote'].get('text'):
            body += (f'<section class="sec sec--dark cs-quote"><div class="container"><blockquote>“{E(c["quote"]["text"])}”</blockquote>'
                     f'<p>{E(c["quote"].get("source") or "From the SOMIN case study")}</p></div></section>\n')
        faq = ''.join(f'<details><summary>{E(q["q"])}</summary><p>{E(q["a"])}</p></details>' for q in c.get('faq', []))
        body += f'''<section class="sec sec--mist"><div class="container">
  <div class="sec-head sec-head--center cs-outcome">
    <p class="eyebrow eyebrow--ink">The outcome</p>
    <h2>{E(c['outcome']['title'])}</h2>
    <p>{E(c['outcome']['body'])}</p>
  </div>
</div></section>
'''
        if c.get('reviews'):
            rv = c['reviews']
            body += reviews_section({'tags': rv.get('tags', ''), 'limit': str(rv.get('limit', 1)), 'title': rv.get('title') or f'What the {cs} team says on G2', 'native': '1'}) + '\n'
        body += f'''<section class="sec sec--light"><div class="container split cs-faq">
  <div class="sec-head">
    <p class="eyebrow eyebrow--ink">FAQ</p>
    <h2>{E(cs)} case study FAQ</h2>
    <div class="cs-about"><p class="eyebrow eyebrow--ink">About SOMIN</p><p>SOMIN is a Singapore-based AI marketing-intelligence platform. It turns real-time competitor and audience data into pre-scored propositions, briefs and creative concepts for brands, agencies and creator programmes across 11+ markets.</p>{research_note()}</div>
  </div>
  <div class="faq-list">{faq}</div>
</div></section>
'''
        # related case studies from the same section (pages first)
        cards = related_cards(key, c['section'], gid)
        if cards:
            body += (f'<section class="sec sec--mist cs-related"><div class="container"><div class="sec-head"><p class="eyebrow eyebrow--ink">Related case studies</p>'
                     f'<h2>More {SECTION_LABEL[c["section"]][0].lower()} case studies</h2></div><div class="cs-rel-grid">{cards}</div>'
                     f'<p class="cs-rel-all"><a href="/cases-ai-marketing-strategy/#{SECTION_LABEL[c["section"]][1]}" data-gtm-id="case_{gid}_all_cases">All case studies</a></p></div></section>\n')
        body += (f'<section class="cta-band"><div class="container"><h2>Get the full <em>{E(cs)}</em> case study</h2>'
                 f'<p>Every page of the {E(SECTION_LABEL[c["section"]][0].lower())} {"pitch" if c["section"] == "agencies" else "briefing"}: the data, the whitespace, the personas and the creative. Free, straight after a short form.</p>'
                 f'<div class="cta-row"><a class="btn btn--solid" {dl} data-gtm-id="case_{gid}_footer_download">Get the full case study</a>'
                 f'<a class="btn btn--ghost" href="{CAL_CASES}" data-gtm-id="case_{gid}_footer_call">Book a walkthrough</a></div></div></section>')
        meta['og_title'] = meta['twitter_title'] = c['h1']
        meta['jsonld'] = []
        build_native_page(meta, body, schema=case_schema(meta, path, c['h1'], label, c['section'], [sl['file'] for sl in slides]))
        metas.append(meta)
    return metas


def build_research_page():
    """/research/: Prof. Aleks Farseev's peer-reviewed papers and talks, mapped to the SOMIN features they power."""
    path = '/research/'
    R = RESEARCH
    peer = [p for p in R['papers'] if p['peer_reviewed']]
    venues = sorted({p['venue_short'] for p in peer if p['tier'] in ('top', 'strong') and not p['venue_short'].startswith(('CLEF', 'WebSci'))})
    first = min(p['year'] for p in peer)
    mt = R['metrics']
    meta = {'slug': 'research', 'layout': 'native', 'type': 'company', 'group': 'research',
            'title': 'SOMIN Research: Peer-Reviewed AI for Marketing | SOMIN',
            'description': f'The peer-reviewed research behind SOMIN: {len(peer)} papers by Prof. Aleks Farseev and the SOMIN team at AAAI, ACM Multimedia, SIGIR, WSDM and WWW, plus talks.',
            'og_image': '/assets/img/og/card-research.jpg' if (ROOT / 'static/assets/img/og/card-research.jpg').exists() else SITE['default_og_image'],
            'hero_bg': '/assets/img/brand/hero-research.webp' if (ROOT / 'static/assets/img/brand/hero-research.webp').exists() else None,
            'robots': 'index,follow', 'h1': 'The peer-reviewed AI research behind SOMIN'}
    by_theme = {}
    for p in sorted(R['papers'], key=lambda p: (-p['year'], p['id'])):
        by_theme.setdefault(p['theme'], []).append(p)
    themes = ''
    for i, t in enumerate(R['themes'], 1):
        items = ''.join(f'<li><a href="{E(p["url"])}" target="_blank" rel="noopener" data-track="research_paper_click"><b>{E(p["venue_short"])} {p["year"]}</b> {E(p["title"])}</a></li>'
                        for p in by_theme.get(t['key'], [])[:4])
        themes += (f'<div class="rs-theme"><span class="tile-num">{i:02d}</span><h3>{E(t["title"])}</h3><p>{E(t["body"])}</p><ul>{items}</ul>'
                   f'<a class="rs-uses" href="{E(t["href"])}" data-gtm-id="research_theme_product">In SOMIN today: {E(t["product"])} →</a></div>')
    def plist(rows):
        return '<ol class="rs-list">' + ''.join(
            f'<li><span class="rs-venue">{E(p["venue_short"])} · {p["year"]} · {E(p["kind"])}</span>'
            f'<a href="{E(p["url"])}" target="_blank" rel="noopener" data-track="research_paper_click" data-gtm-id="research_list_paper"><strong>{E(p["title"])}</strong></a>'
            f'<span class="rs-auth">{E(p["authors"])}. {E(p["venue"])}.</span>'
            + (f'<a class="rs-pdf" href="{E(p["pdf"])}" target="_blank" rel="noopener" data-track="research_pdf_click">Open-access PDF</a>' if p.get('pdf') else '') + '</li>'
            for p in rows) + '</ol>'
    srt = lambda rows: sorted(rows, key=lambda p: (-p['year'], p['id']))
    top = srt([p for p in R['papers'] if p['tier'] == 'top'])
    strong = srt([p for p in R['papers'] if p['tier'] == 'strong'])
    other = srt([p for p in R['papers'] if p['tier'] == 'other'])
    talks = ''.join(
        f'<a class="rs-tcard" href="{E(t["url"])}" target="_blank" rel="noopener" data-track="research_talk_click" data-gtm-id="research_talk_card">'
        f'<span class="rs-venue">{E(t["kind"])} · {E(t["date"][:4])}{" · in " + E(t["language"]) if t["language"] != "English" else ""}</span>'
        f'<strong>{E(t["title"])}</strong><em>{E(t["event"])}</em><p>{E(t["summary"])}</p></a>'
        for t in sorted(R['talks'], key=lambda t: t['date'], reverse=True))
    profiles = ''.join(f'<li><a href="{E(p["url"])}" target="_blank" rel="noopener" data-track="research_profile_click" data-gtm-id="research_profile">{E(p["label"])}</a></li>' for p in R['profiles'])
    faq = [
        ('Is SOMIN built on real AI research?', f'Yes. SOMIN was co-founded by Prof. Aleks Farseev, and the models behind its audience personas, creative scoring and competitor analytics come from research he and the SOMIN team have published since {first}, including papers at AAAI, ACM Multimedia, SIGIR, WSDM and The Web Conference and in ACM Transactions on Information Systems.'),
        ('Where has SOMIN research been published?', f'This page lists {len(peer)} peer-reviewed papers, demos and abstracts in venues including ' + ', '.join(venues) + '. Each entry links to the publisher page or DOI, and to an open-access PDF where one exists.'),
        ('Who builds SOMIN?', 'SOMIN is built by seasoned marketers and an AI professor. Prof. Aleks Farseev leads the research and the company; the SOMIN team combines machine-learning researchers, several of whom co-author the papers above, with marketers who work with brand and agency teams every day.'),
        ('How does the research show up in the product?', 'Multi-source audience profiling powers SOMIN personas, personality-driven recommendation shapes persona-matched creative, creative-performance prediction scores concepts before launch, and explainable AI with large language models explains why competitor content works. Agentic AI research keeps generated content distinctive by grounding it in real category data.'),
        ('Where can I watch talks about SOMIN?', 'Talks are listed above with links: an industry expert talk at ACM Multimedia 2025, a keynote at the Digital Marketing Conference Kuala Lumpur 2025, lectures at INSEAD and NUS, the ATxSG 2026 pitch and Marketing Mondays sessions on YouTube.'),
    ]
    faq_html = ''.join(f'<details><summary>{E(q)}</summary><p>{E(a)}</p></details>' for q, a in faq)
    cite = f'{mt["citations"]:,}'
    body = f'''<section class="hero rs-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">Research</li></ol></nav>
  <p class="eyebrow">Research · Built by seasoned marketers and an AI professor</p>
  <h1>The peer-reviewed AI research <em>behind SOMIN</em></h1>
  <p class="lede">SOMIN's audience personas, creative scoring and competitor analytics come from research by co-founder Prof. Aleks Farseev and the SOMIN team, published at AAAI, ACM Multimedia, SIGIR, WSDM and The Web Conference, and in ACM TOIS.</p>
  <div class="cta-row cta-row--left">
    <a class="btn btn--solid" href="#papers" data-gtm-id="research_hero_papers">See the papers</a>
    <a class="btn btn--ghost" href="#talks" data-gtm-id="research_hero_talks">Watch the talks</a>
  </div>
  <div class="cs-hero-stats"><div><strong>{len(peer)}</strong><small>Peer-reviewed papers, demos and abstracts</small></div><div><strong>{len(venues)}</strong><small>Top venues incl. AAAI, ACM MM, SIGIR</small></div><div><strong>{first}</strong><small>Publishing since</small></div></div>
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head">
    <p class="eyebrow eyebrow--ink">Who builds SOMIN</p>
    <h2>Seasoned marketers and an AI professor, on one product</h2>
    <p>Prof. Aleks Farseev co-founded SOMIN after a PhD at the National University of Singapore on learning user profiles from many social networks at once. He is a research professor in digital-marketing AI, and his work on audience profiling, personality-driven recommendation and explainable AI for advertising is cited {cite} times on Semantic Scholar (as of {E(mt["as_of"])}).</p>
    <p>Next to the research team, SOMIN's marketers turn those models into the playbooks brand and agency teams run every week: whitespace maps, personas and tensions, pre-scored concepts and content calendars.</p>
  </div>
  <div class="sec-head rs-profiles"><p class="eyebrow eyebrow--ink">Research profiles</p><ul>{profiles}</ul>
    <p class="rs-small">Citation figures from <a href="{E(mt["source_url"])}" target="_blank" rel="noopener">{E(mt["source"])}</a>, {E(mt["as_of"])}.</p></div>
</div></section>

<section class="sec sec--mist"><div class="container">
  <div class="sec-head sec-head--center"><p class="eyebrow eyebrow--ink">From paper to product</p><h2>Seven research lines that run inside SOMIN today</h2>
  <p>Each line of research below is a capability in the platform. Click a paper to read it on the publisher's site.</p></div>
  <div class="rs-themes">{themes}</div>
</div></section>

<section class="sec sec--light" id="papers"><div class="container">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Publications</p><h2>Top-tier conference and journal papers</h2>
  <p>Full papers and journal articles at AAAI, ACM Multimedia, SIGIR and in ACM TOIS and ACM TIST.</p></div>
  {plist(top)}
  <div class="sec-head" style="margin-top:48px"><h2>Papers, demos and abstracts at top venues</h2>
  <p>Papers, industry and demo papers, and student abstracts at ACM Multimedia, AAAI, SIGIR, WSDM, The Web Conference, ICMR, CLEF and WebSci.</p></div>
  {plist(strong)}
  <div class="sec-head" style="margin-top:48px"><h2>Journals, workshops and preprints</h2></div>
  {plist(other)}
</div></section>

<section class="sec sec--mist" id="talks"><div class="container">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Talks and lectures</p><h2>Keynotes, lectures and Marketing Mondays sessions</h2>
  <p>Prof. Aleks Farseev on AI in advertising, from ACM Multimedia and INSEAD to Marketing Mondays. Videos open on YouTube.</p></div>
  <div class="rs-tgrid">{talks}</div>
  <p style="margin-top:22px"><a class="btn btn--ghost btn--ink" href="/marketing-mondays-plugin/" data-gtm-id="research_mm_plugin">Marketing Mondays: get the free Claude plugin</a></p>
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">FAQ</p><h2>SOMIN research FAQ</h2></div>
  <div class="faq-list">{faq_html}</div>
</div></section>

<section class="cta-band"><div class="container"><h2>See the research <em>run on your category</em></h2>
<p>SOMIN reads your competitors, creators and audience, then hands you pre-scored ideas you can brief today.</p>
<div class="cta-row"><a class="btn btn--solid" href="/try-somin/" data-lead-form="trial" data-gtm-id="research_footer_trial">Try SOMIN</a><a class="btn btn--ghost" href="{CAL_DEFAULT}" data-gtm-id="research_footer_call">Book a call</a></div></div></section>'''
    person = founder_node()
    arts = [{"@type": "ListItem", "position": i + 1, "item": {"@type": "ScholarlyArticle", "name": p['title'], "headline": p['title'][:110],
             "author": [{"@type": "Person", "name": a.strip()} for a in p['authors'].replace(', et al.', '').split(',') if a.strip()],
             "datePublished": str(p['year']), "isPartOf": {"@type": "Periodical" if re.search(r'Transactions|Frontiers|Newsletter', p['venue']) else "Book", "name": p['venue']},
             "url": p['url'], **({"sameAs": p['pdf']} if p.get('pdf') else {})}} for i, p in enumerate(srt(peer))]
    graph = {"@context": "https://schema.org", "@graph": [person, {"@type": "ItemList", "@id": absu(path) + "#papers", "name": "Peer-reviewed papers by Prof. Aleks Farseev and the SOMIN team", "itemListElement": arts}]}
    meta['jsonld'] = [json.dumps(graph, ensure_ascii=False)]
    build_native_page(meta, body)
    return meta


def build_native_page(meta, body, schema=None):
    path = url_for(meta['slug'])
    body = hero_image(body, meta, 'hero')
    trail = [('Home', '/'), (meta['title'].split(' | ')[0], path)]
    meta['_schema'] = schema or [org_node(), website_node(),
                       {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta['title'], "description": meta.get('description'),
                        "isPartOf": {"@id": f"{BASE}/#website"}, "inLanguage": "en"}, breadcrumbs(trail)]
    write(path, page(meta, body, path))
    add_sitemap(path, None, '0.6', meta.get('robots', 'index'))


AUTHORS = {'Prof. Aleks Farseev': founder_node()}
# SOMIN team bylines (roles and profiles as listed on the SOMIN LinkedIn company page, Oct 2026)
TEAM = {
    'Kirill Lepikhin': ('Co-Founder and CTO, SOMIN', 'https://www.linkedin.com/in/k-lepikhin/'),
    'Dr. Yang Qi': ('Senior Data Scientist, SOMIN', 'https://www.linkedin.com/in/diuibyang/'),
    'Hsiao Yuh Tyng': ('AI Marketing Strategist and Account Manager, SOMIN', 'https://www.linkedin.com/in/hsiao-yuh-tyng/'),
    'Phil Lugovoi': ('Business Development, SOMIN', 'https://www.linkedin.com/in/filipp-lugovoi/'),
    'Joy Yu-Yi Chu': ('Data Analyst, SOMIN', 'https://www.linkedin.com/in/chuyuyi/'),
    'Egor Shevelev': ('Head of Development, SOMIN', 'https://www.linkedin.com/in/egor-shevelev-01266842/'),
    'Murtaza Hyder Magsi': ('Quality Assurance Engineer, SOMIN', 'https://www.linkedin.com/in/imurtazahyder/'),
}
def author_slug(name):
    return re.sub(r'[^a-z]+', '-', re.sub(r'^(prof|dr)\.\s*', '', name.lower())).strip('-')


for _n, (_role, _li) in TEAM.items():
    AUTHORS[_n] = {"@type": "Person", "@id": f"{BASE}/#{re.sub(r'[^a-z]+', '-', _n.lower()).strip('-')}", "name": _n, "jobTitle": _role,
                   "url": absu(f'/authors/{author_slug(_n)}/'), "worksFor": {"@id": f"{BASE}/#organization"}, "sameAs": [_li]}
AUTHOR_ROLE = {'Prof. Aleks Farseev': 'Co-Founder & CEO, SOMIN', 'Da-Min You': 'SOMIN', 'SOMIN Team': 'SOMIN', **{n: r for n, (r, _) in TEAM.items()}}


def author_node(name):
    if name == 'SOMIN Team':
        return {"@id": f"{BASE}/#organization"}
    return AUTHORS.get(name) or {"@type": "Person", "@id": f"{BASE}/#{author_slug(name)}", "name": name, "url": absu(f'/authors/{author_slug(name)}/'),
                                 "worksFor": {"@id": f"{BASE}/#organization"}}


def author_link(name, cls=''):
    """Byline name linked to the author's profile page (not for the 'SOMIN Team' byline)."""
    if name == 'SOMIN Team':
        return E(name)
    return f'<a{(" class=" + chr(34) + cls + chr(34)) if cls else ""} href="/authors/{author_slug(name)}/" rel="author">{E(name)}</a>'


def post_card(p, cls='card', feature=False):
    tag = p['tags'][0] if p['tags'] else 'Insights'
    data = f' data-post data-tags="{E("|".join(p["tags"]))}" data-search="{E((p["title"] + " " + p["description"] + " " + " ".join(p["tags"]) + " " + p["author"]).lower())}"'
    img = p['image'] if feature else p['image_card']
    meta = (f'<div class="meta byline"><span class="avatar" aria-hidden="true">{initials(p["author"])}</span><span class="who"><b>{E(p["author"])}</b>'
            f'<small><time datetime="{p["published"][:10]}">{fmt_date(p["published"])}</time> · {p["reading_minutes"]} min read</small></span></div>')
    if feature:
        return (f'<a class="feature" href="{url_for(p["slug"])}"><div class="feature-media"><img src="{img}" alt="{E(p['title'])}" width="1600" height="1067" fetchpriority="high"></div>'
                f'<div class="feature-body"><span class="eyebrow">Latest · {E(tag)}</span><h2>{E(p["title"])}</h2><p>{E(p["description"])}</p>{meta}</div></a>')
    return (f'<a class="{cls}" href="{url_for(p["slug"])}"{data}><div class="card-media"><img src="{img}" alt="{E(p['title'])}" width="720" height="480" loading="lazy" decoding="async"></div>'
            f'<div class="card-body"><span class="card-tag">{E(tag)}</span><h3>{E(p["title"])}</h3><p>{E(p["description"])}</p>{meta}</div></a>')


def xref_pools():
    """Audience heroes, agent/product heroes, and case studies a blog post can point at."""
    pools = {'brand': [], 'agency': [], 'creator': []}
    for key, item in CASES['items'].items():
        page = item.get('page')
        if not page:
            continue
        title = ((item.get('hub') or {}).get('title') or key).strip()
        if page.startswith('/agencies'):
            pools['agency'].append((page, title))
        elif page.startswith('/influencers'):
            pools['creator'].append((page, title))
        elif page.startswith('/brands'):
            pools['brand'].append((page, title))
    for rows in pools.values():
        rows.sort()
    return pools


def post_xrefs(meta):
    """Three links to different SOMIN pages: an audience hero, an agent or product hero, and a case study."""
    text = ' '.join([meta.get('slug', ''), meta.get('title', ''), ' '.join(meta.get('tags') or [])]).lower()
    if any(w in text for w in ('agency', 'agencies', 'retainer', 'pitch')):
        family = 'agency'
    elif any(w in text for w in ('creator', 'influencer', 'kol', 'ugc')):
        family = 'creator'
    else:
        family = 'brand'
    audience = {
        'brand': ('/somin-for-brands/', 'For brands'),
        'agency': ('/somin-for-agencies/', 'For agencies'),
        'creator': ('/somin-for-creators/', 'For creators'),
    }[family]
    heroes = [
        ('/ai-agents/', 'AI agents'),
        ('/somin-strategy/', 'Strategy'),
        ('/somin-paid-media/', 'Paid Media'),
        ('/somin-crm/', 'CRM'),
        ('/somin-reporting/', 'Reporting'),
        ('/', 'Home'),
    ]
    if family == 'creator':
        heroes = [('/somin-influencer-gmv/', 'Creators')] + heroes
    n = int(hashlib.sha1(meta['slug'].encode()).hexdigest()[:8], 16)
    hero = heroes[n % len(heroes)]
    cases = xref_pools()[family] or xref_pools()['brand']
    case = cases[n % len(cases)]
    links = [audience, hero, case]
    # keep three different URLs even if a rotation collides
    seen, out = set(), []
    for href, label in links:
        if href in seen:
            continue
        seen.add(href)
        out.append((href, label))
    return out


def post_xref_html(meta):
    items = ''.join(f'<li><a href="{E(href)}">{E(label)}</a></li>' for href, label in post_xrefs(meta))
    return f'<nav class="post-xref" aria-label="See it on SOMIN"><h2>See it on SOMIN</h2><ul>{items}</ul></nav>'


def build_post(meta, body, posts):
    path = url_for(meta['slug'])
    body = add_heading_ids(body, ('h2', 'h3'))
    body = wrap_tables(body)
    toc = toc_items(body, ('h2', 'h3'))
    # in-article CTA after ~45% of the paragraphs
    paras = [m.end() for m in re.finditer(r'</p>', body)]
    cta = (f'<aside class="inline-cta"><div><h3>See what SOMIN finds in <em style="font-style:normal;color:var(--teal)">your</em> category</h3>'
           f'<p>A 30-minute walkthrough on your brand, your competitors and the moment you are about to buy media against.</p></div>'
           f'<a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="blog_inline_book_call">Book a demo</a></aside>')
    if len(paras) > 6:
        cut = paras[int(len(paras) * 0.45)]
        body = body[:cut] + cta + body[cut:]
    else:
        body = body + cta
    tags_html = ''.join(f'<a class="tag" href="/blog/#topic={urllib.parse.quote(t)}">{E(t)}</a>' for t in meta['tags'])
    share_url = urllib.parse.quote(absu(path), safe='')
    share = (f'<div class="share" aria-label="Share">'
             f'<a href="https://www.linkedin.com/sharing/share-offsite/?url={share_url}" target="_blank" rel="noopener" data-share="linkedin" aria-label="Share on LinkedIn">{ICON["linkedin"]}</a>'
             f'<a href="https://twitter.com/intent/tweet?url={share_url}&text={urllib.parse.quote(meta["title"])}" target="_blank" rel="noopener" data-share="x" aria-label="Share on X">{ICON["x"]}</a>'
             f'<button type="button" data-copy-link aria-label="Copy link">{ICON["link"]}</button></div>')
    toc_html = ''
    if len(toc) >= 2:
        toc_html = '<nav class="toc" aria-label="In this article"><h2>In this article</h2><ol>' + ''.join(
            f'<li><a class="lvl-{lv[1]}" href="#{i}">{E(t)}</a></li>' for lv, i, t in toc) + '</ol></nav>'
    aside = (f'<aside class="post-aside">{toc_html}{share}<div class="aside-cta"><h3>Try SOMIN on your category</h3>'
             f'<p>Pre-scored campaign concepts from live competitor and audience data.</p>'
             f'<a class="btn btn--solid btn--sm btn--block" href="/try-somin/" data-lead-form="trial" data-gtm-id="blog_aside_try">Try SOMIN</a></div></aside>')
    related = [p for p in posts if p['slug'] != meta['slug'] and set(p['tags']) & set(meta['tags'])]
    related = (related + [p for p in posts if p['slug'] != meta['slug'] and p not in related])[:3]
    rel_html = ''.join(post_card(p) for p in related)
    a = meta['author']
    hero = f'''<div class="read-progress" aria-hidden="true"><span></span></div>
<section class="hero post-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li><a href="/blog/">Blog</a></li><li aria-current="page">{E(meta['title'] if len(meta['title']) <= 48 else meta['title'][:46].rsplit(' ', 1)[0] + '…')}</li></ol></nav>
  <h1>{E(meta['title'])}</h1>
  <p class="lede">{E(meta['description'])}</p>
  <div class="meta"><span class="avatar" aria-hidden="true">{initials(a)}</span><span>{author_link(a)}</span><span class="dot"></span><time datetime="{meta['published'][:10]}">{fmt_date(meta['published'])}</time><span class="dot"></span><span>{meta['reading_minutes']} min read</span></div>
</div></section>
<div class="container post-cover"><img src="{meta['image']}" alt="{E('Illustration: ' + meta['title'])}" width="1600" height="1067" fetchpriority="high"></div>'''
    main = f'''<div class="post-wrap"><div class="container"><div class="post-grid-layout">
  <div><article class="prose" data-article>{body}</article>
    <div class="post-tags">{tags_html}</div>
    {post_xref_html(meta)}
    <div class="author-box"><span class="avatar" aria-hidden="true">{initials(a)}</span><div><strong>{author_link(a)}</strong><span>{E(AUTHOR_ROLE.get(a, 'SOMIN'))}</span>{'' if a == 'SOMIN Team' else f'<a class="author-more" href="/authors/{author_slug(a)}/">More from {E(re.sub(r"^(Prof|Dr)[.] *", "", a).split()[0])} →</a>'}</div></div>
    {research_strip({'compact': '1', 'cls': 'rs-line--light'})}
  </div>
  {aside}
</div></div></div>
<section class="related"><div class="container"><h2>Keep reading</h2><div class="post-grid">{rel_html}</div></div></section>'''
    posting = {"@type": "BlogPosting", "@id": absu(path) + "#article", "headline": meta['title'][:110], "description": meta['description'],
               "image": [absu(meta['og_image']), absu(meta['image'])], "datePublished": meta['published'], "dateModified": meta.get('modified') or meta['published'],
               "author": author_node(a), "publisher": {"@id": f"{BASE}/#organization"}, "mainEntityOfPage": absu(path),
               "keywords": ', '.join(meta['tags']), "articleSection": meta['tags'][0] if meta['tags'] else 'Insights',
               "wordCount": meta['words'], "timeRequired": f"PT{meta['reading_minutes']}M", "inLanguage": "en", "isPartOf": {"@id": f"{BASE}/blog/#blog"}}
    meta['_schema'] = [org_node(), website_node(), posting, breadcrumbs([('Home', '/'), ('Blog', '/blog/'), (meta['title'], path)])]
    meta['group'] = 'blog'
    meta['seo_title'] = meta.get('seo_title') or (f"{meta['title']} | SOMIN Blog" if len(meta['title']) <= 52 else meta['title'])
    meta['og_title'] = meta['title']
    write(path, page(meta, hero + main, path))
    add_sitemap(path, meta['published'][:10], '0.7')


def build_blog_index(posts):
    path = '/blog/'
    topics = {}
    for p in posts:
        for t in p['tags']:
            topics[t] = topics.get(t, 0) + 1
    top = [t for t, n in sorted(topics.items(), key=lambda x: (-x[1], x[0])) if n >= 2 and t not in ('Community',)][:12]
    chips = '<button class="chip" type="button" data-topic="all" aria-pressed="true">All topics</button>' + ''.join(
        f'<button class="chip" type="button" data-topic="{E(t)}" aria-pressed="false">{E(t)}</button>' for t in top)
    feat = post_card(posts[0], feature=True)
    cards = ''.join(post_card(p) for p in posts)
    body = f'''<section class="hero blog-hero"><div class="container">
  <p class="eyebrow">SOMIN Blog</p>
  <h1>Marketing intelligence for the <em>agentic</em> era.</h1>
  <p class="lede">Field notes from the SOMIN team on AI agents, competitor and audience intelligence, paid media and creative strategy — written for marketers and agencies across APAC and beyond.</p>
  {research_strip({'compact': '1'})}
  <div class="blog-tools"><div class="chips" role="group" aria-label="Filter by topic">{chips}</div>
    <label class="search"><span class="visually-hidden">Search articles</span>{ICON['search']}<input type="search" placeholder="Search articles" data-post-search></label></div>
  {feat}
</div></section>
<section class="blog-list"><div class="container">
  <div class="blog-list-head"><h2>All articles</h2><p><span data-post-count>{len(posts)}</span> articles</p></div>
  <div class="post-grid" data-post-grid>{cards}</div>
  <p class="empty" data-post-empty hidden>No articles match that filter yet.</p>
</div></section>
<section class="cta-band"><div class="container"><h2>See it run on <em>your</em> category.</h2><p>A 30-minute walkthrough on your brand, your competitors and the moment you are about to buy media against.</p>
<div class="cta-row"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="blog_index_book_call">Book a demo</a><a class="btn btn--ghost" href="/try-somin/" data-lead-form="trial" data-gtm-id="blog_index_try">Try SOMIN</a></div></div></section>'''
    blog_node = {"@type": "Blog", "@id": f"{BASE}/blog/#blog", "url": f"{BASE}/blog/", "name": "SOMIN Blog", "description": "AI marketing intelligence, competitor research, paid media and creative strategy from the SOMIN team.",
                 "publisher": {"@id": f"{BASE}/#organization"}, "inLanguage": "en",
                 "blogPost": [{"@type": "BlogPosting", "headline": p['title'][:110], "url": absu(url_for(p['slug'])), "datePublished": p['published'], "image": absu(p['og_image']), "author": {"@type": "Person", "name": p['author']} if p['author'] != 'SOMIN Team' else {"@id": f"{BASE}/#organization"}} for p in posts]}
    meta = {'title': 'SOMIN Blog — AI Marketing Intelligence, Agents & Strategy', 'description': 'Insights from the SOMIN team on AI marketing agents, competitor and audience intelligence, paid media, creator marketing and campaign strategy.',
            'type': 'blog_index', 'layout': 'blog', 'og_image': posts[0]['og_image'], 'group': 'blog',
            '_schema': [org_node(), website_node(), blog_node, breadcrumbs([('Home', '/'), ('Blog', '/blog/')])]}
    write(path, page(meta, hero_image(body, dict(meta, hero_bg='/assets/img/brand/hero-blog.webp'), 'hero'), path))
    add_sitemap(path, posts[0]['published'][:10], '0.8')


def build_rss(posts):
    items = ''
    for p in posts[:50]:
        u = absu(url_for(p['slug']))
        pub = email.utils.format_datetime(dt.datetime.fromisoformat(p['published'].replace('Z', '+00:00')))
        cats = ''.join(f'<category>{E(t)}</category>' for t in p['tags'])
        items += (f'<item><title>{E(p["title"])}</title><link>{u}</link><guid isPermaLink="true">{u}</guid><pubDate>{pub}</pubDate>'
                  f'<dc:creator>{E(p["author"])}</dc:creator>{cats}<description>{E(p["description"])}</description>'
                  f'<enclosure url="{absu(p["og_image"])}" type="image/jpeg" length="0"/></item>')
    rss = (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f'<title>SOMIN Blog</title><link>{BASE}/blog/</link><atom:link href="{BASE}/blog/rss.xml" rel="self" type="application/rss+xml"/>'
           f'<description>AI marketing intelligence from the SOMIN team.</description><language>en</language><lastBuildDate>{email.utils.format_datetime(dt.datetime.now(dt.timezone.utc))}</lastBuildDate>{items}</channel></rss>')
    (OUT / 'blog').mkdir(parents=True, exist_ok=True)
    (OUT / 'blog/rss.xml').write_text(rss, encoding='utf-8')


# ------------------------------------------------------------------ lead + thank-you pages
def drive_download(drive_id):
    # drive.usercontent serves the file as an attachment (no HTML interstitial, even for the 140 MB deck)
    return f'https://drive.usercontent.google.com/download?id={drive_id}&export=download&confirm=t'


def case_manifest():
    """All case-study PDFs keyed like data/case-studies.json, enriched with titles, covers and links."""
    out = {}
    pages = {}
    for f in sorted((ROOT / 'content/pages').glob('*.html')):
        m, _ = read_content(f)
        pages[m['slug']] = m
    # fallback labels from the navigation ("Consumer Electronics: Fujifilm UK" -> "Fujifilm UK")
    nav_labels = {}
    for n in CFG['nav']:
        for c in n.get('children', []):
            nav_labels[c['href'].strip('/')] = (c['label'].split(':', 1)[-1].strip(), c['label'].split(':', 1)[0].strip() if ':' in c['label'] else '')
    for key, it in CASES['items'].items():
        pm = pages.get(key, {})
        hub = it.get('hub') or {}
        label, sector = nav_labels.get(key) or (None, '')
        title = hub.get('title') or label or re.sub(r'\.pdf$', '', it['file'], flags=re.I).replace('_', ' ').title()
        out[key] = {'title': title, 'download': drive_download(it['drive_id']), 'drive_id': it['drive_id'],
                    'view': f'https://drive.google.com/file/d/{it["drive_id"]}/view', 'size_mb': it['size_mb'],
                    'page': it.get('page') or (url_for(CASE_PAGES[key]['slug']) if key in CASE_PAGES else None), 'cover': hub.get('cover') or pm.get('og_image'),
                    'category': hub.get('sector') or sector or it.get('category'), 'market': hub.get('market', ''),
                    'section': hub.get('section') or {'influencers': 'creators'}.get(it.get('category'), it.get('category')),
                    'summary': hub.get('summary', ''), 'order': hub.get('order', 999), 'on_hub': bool(hub)}
    return out


def _obf(drive_id):
    # keeps raw Drive IDs out of the page source (soft gate); site.js reverses it after the form is submitted
    import base64
    return base64.b64encode(drive_id.encode()).decode()[::-1]


def build_lead_pages():
    manifest = case_manifest()
    # remove internals the browser does not need
    public = {k: {kk: v[kk] for kk in ('title', 'size_mb', 'page', 'cover', 'category')} for k, v in manifest.items()}
    trial_id = TRACK['lead_forms']['trial']['typeform_id']
    cs_id = TRACK['lead_forms']['case_study']['typeform_id']

    # ---- /try-somin/
    body = f'''<section class="hero"><div class="container lead-layout">
  <div>
    <p class="eyebrow">Free trial</p>
    <h1>Try <em>SOMIN</em> on your own category.</h1>
    <p class="lede">Tell us a little about you and what you need. We set up your workspace with your brand and competitors so the first run is already relevant.</p>
    <ul class="lead-points">
      <li><span><strong>Live competitor &amp; audience data</strong> — ads, posts and creators across your market, read in real time.</span></li>
      <li><span><strong>Pre-scored campaign concepts</strong> — propositions and creative directions ranked before you spend.</span></li>
      <li><span><strong>Agents that run the loop</strong> — strategy, paid media, creators, social, CRM and reporting.</span></li>
    </ul>
    <div class="trust"><span>Trusted by teams at <b>P&amp;G</b>, <b>Audi</b>, <b>Dentsu</b> and <b>Havas</b></span><span>Gartner Cool Vendor in Marketing AI</span></div>
    {rating_badges("rv-badges--hero")}
    {research_strip({'compact': '1'})}
    <p style="margin-top:28px"><a class="btn btn--ghost" href="{CAL_DEFAULT}" data-gtm-id="try_page_book_call">Prefer to talk? Book a call</a></p>
  </div>
  <div class="form-card"><div data-lead-form-inline="trial" data-height="640" data-gtm-id="try_page_inline_form">
    <div class="form-fallback"><p>Loading the form… If it does not appear, <a data-fallback href="https://form.typeform.com/to/{trial_id}" target="_blank" rel="noopener">open it in a new tab</a>.</p></div>
  </div></div>
</div></section>'''
    meta = {'title': 'Try SOMIN — Request Trial Access', 'description': 'Request trial access to SOMIN: AI marketing intelligence that turns live competitor and audience data into pre-scored campaign concepts.',
            'type': 'lead', 'layout': 'lead', 'robots': 'noindex,follow', 'group': 'lead'}
    write('/try-somin/', page(meta, body, '/try-somin/'))

    # ---- /get-case-study/
    body = f'''<section class="hero" data-cs-request-page><div class="container lead-layout">
  <div>
    <p class="eyebrow">Case study</p>
    <h1>Get the full case study: <em data-cs-title>SOMIN case study</em></h1>
    <p class="lede">Leave your details and the download unlocks straight away — no waiting for an email.</p>
    <ul class="lead-points">
      <li><span><strong>The full PDF</strong> — every chart, finding and creative from the engagement.</span></li>
      <li><span><strong>Instant access</strong> — the download link appears the moment you submit.</span></li>
      <li><span><strong>Optional walkthrough</strong> — book 30 minutes with the analyst who ran it.</span></li>
    </ul>
    <p style="margin-top:28px"><a class="btn btn--ghost" href="{CAL_CASES}" data-gtm-id="get_case_study_book_call">Book a walkthrough</a></p>
  </div>
  <div class="form-card"><div data-lead-form-inline="case_study" data-height="640" data-gtm-id="get_case_study_inline_form">
    <div class="form-fallback"><p>Loading the form… If it does not appear, <a data-fallback href="https://form.typeform.com/to/{cs_id}" target="_blank" rel="noopener">open it in a new tab</a>.</p></div>
  </div></div>
</div></section>
<script type="application/json" id="cs-manifest">{json.dumps({k: {'title': v['title']} for k, v in public.items()}, ensure_ascii=False)}</script>'''
    meta = {'title': 'Get the SOMIN Case Study', 'description': 'Request a SOMIN case study and download the full PDF instantly.',
            'type': 'lead', 'layout': 'lead', 'robots': 'noindex,follow', 'group': 'lead'}
    write('/get-case-study/', page(meta, body, '/get-case-study/'))

    # ---- /thank-you-case-study/  (download release)
    hub_items = sorted([(k, v) for k, v in manifest.items() if v['on_hub']], key=lambda kv: kv[1]['order'])
    by_sec = {s: [kv for kv in hub_items if kv[1]['section'] == s] for s in ('brands', 'agencies', 'creators')}
    picks, i = [], 0
    while len(picks) < 9 and any(by_sec.values()):
        s = ('brands', 'agencies', 'creators', 'brands')[i % 4]; i += 1
        if by_sec[s]:
            picks.append(by_sec[s].pop(0))

    def mini(k, v):
        if v['page']:
            return f'<a class="mini" href="{E(v["page"])}" data-cs-more data-cs-key="{E(k)}"><span>{E(v["category"] or "Case study")}</span><strong>{E(v["title"])}</strong></a>'
        return (f'<a class="mini" href="/get-case-study/?cs={E(k)}" data-lead-form="case_study" data-case-study="{E(k)}" data-case-study-label="{E(v["title"])}" '
                f'data-cs-more data-cs-key="{E(k)}"><span>{E(v["category"] or "Case study")}</span><strong>{E(v["title"])}</strong></a>')
    cards = ''.join(mini(k, v) for k, v in picks)
    body = f'''<section class="hero"><div class="container" style="max-width:980px" data-cs-release>
  <div class="ty-card" data-cs-state="ready" hidden>
    <div class="ty-check">{ICON['check']}</div>
    <p class="eyebrow">Your case study is ready</p>
    <div class="dl-card" style="margin-top:22px">
      <div class="dl-cover"><img data-cs-cover hidden alt=""><span class="pdf">PDF</span></div>
      <div>
        <h1 class="dl-title" data-cs-title>Case study</h1>
        <p class="dl-meta" data-cs-meta>PDF</p>
        <div class="dl-actions">
          <a class="btn btn--solid" data-cs-download href="#" rel="noopener" data-gtm-id="case_study_download_pdf">{ICON['download']} Download PDF</a>
          <a class="btn btn--ghost" data-cs-view href="#" target="_blank" rel="noopener" data-gtm-id="case_study_view_pdf">Open in browser</a>
        </div>
        <p class="dl-note" data-cs-auto-note hidden><strong>Your download has started.</strong> Check your browser's downloads; if nothing appears in a few seconds, use the Download PDF button.</p>
        <p class="dl-note">Large decks can take a few seconds to start. The PDF stays available on this page in this browser.</p>
      </div>
    </div>
  </div>
  <div class="ty-card" data-cs-state="locked" hidden>
    <p class="eyebrow">One step left</p>
    <h2 class="dl-title" style="margin-top:12px">Unlock <span data-cs-title>this case study</span></h2>
    <p class="dl-meta">Tell us where you work and the download link appears instantly.</p>
    <a class="btn btn--solid" href="/get-case-study/" data-lead-form="case_study" data-cs-request data-gtm-id="thank_you_unlock_case_study">Get the case study</a>
  </div>
  <div class="ty-card" data-cs-state="unknown">
    <div class="ty-check">{ICON['check']}</div>
    <p class="eyebrow">Thank you</p>
    <h2 class="dl-title" style="margin-top:12px">Thanks — we have your request.</h2>
    <p class="dl-meta">The SOMIN team will send the case study you asked for. Meanwhile, browse more results below or book a walkthrough.</p>
  </div>
  <div class="ty-card" style="margin-top:20px">
    <ol class="steps">
      <li><span><strong>Read the case</strong>See exactly how SOMIN turned live category data into propositions and creatives.</span></li>
      <li><span><strong>Walk through it with the analyst</strong>30 minutes on how the same approach would read your category.</span></li>
      <li><span><strong>Run it on your brand</strong>Your competitors, your audience, your next brief.</span></li>
    </ol>
    <div class="cta-row" style="justify-content:flex-start;margin-top:26px">
      <a class="btn btn--solid" href="{CAL_CASES}" data-gtm-id="thank_you_case_book_walkthrough">Book a walkthrough</a>
      <a class="btn btn--ghost" data-cs-page hidden href="/">Back to the case</a>
    </div>
  </div>
</div></section>
<section class="section" style="padding-top:0"><div class="container" style="max-width:980px"><h2 class="section-title">More SOMIN case studies</h2><div class="mini-grid">{cards}</div>
<p style="margin-top:22px"><a class="btn btn--ghost" href="/cases-ai-marketing-strategy/" data-gtm-id="thank_you_case_all_cases">Browse all {sum(1 for v in manifest.values() if v['on_hub'])} case studies</a></p></div></section>
<script type="application/json" id="cs-manifest">{json.dumps({k: dict(public[k], f=_obf(v['drive_id'])) for k, v in manifest.items()}, ensure_ascii=False)}</script>'''
    meta = {'title': 'Your SOMIN Case Study Download', 'description': 'Download your SOMIN case study.', 'type': 'thank_you', 'lead_type': 'case_study',
            'layout': 'thank-you', 'robots': 'noindex,nofollow', 'group': 'thank_you'}
    write('/thank-you-case-study/', page(meta, body, '/thank-you-case-study/'))

    # ---- /thank-you-trial-somin/
    body = f'''<section class="hero"><div class="container" style="max-width:980px">
  <div class="ty-card">
    <div class="ty-check">{ICON['check']}</div>
    <p class="eyebrow">Request received</p>
    <h1 class="dl-title" style="font-size:clamp(30px,4vw,46px);margin-top:12px">Thank you for reaching out!</h1>
    <p class="lede" style="margin-top:14px">We've successfully received your details. A member of the SOMIN team will contact you shortly to discuss how our AI-powered platform can seamlessly fit into your workflow.</p>
    <p class="lede" style="margin-top:14px">Whether your goal is to defend every campaign with live data or pitch with unfair speed, we'll walk you through exactly how SOMIN surfaces audience tensions and cuts research time by 75%.</p>
    <ol class="steps">
      <li><span><strong>We set up your workspace</strong>Your brand and competitors, loaded before the first session.</span></li>
      <li><span><strong>Guided demo</strong>We run the whitespace read live on the competitor set you name.</span></li>
      <li><span><strong>Your first brief</strong>Pre-scored concepts you can take straight to the team.</span></li>
    </ol>
  </div>
</div></section>
<section class="cta-band"><div class="container"><h2>Want us to guide you through the <em>demo</em>?</h2>
<div class="cta-row"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="thank_you_trial_book_call">Book a discovery call with the SOMIN team</a><a class="btn btn--ghost" href="/blog/">Read the blog</a></div></div></section>'''
    meta = {'title': 'Thank You — SOMIN', 'description': 'Thanks for requesting SOMIN trial access.', 'type': 'thank_you', 'lead_type': 'trial',
            'layout': 'thank-you', 'robots': 'noindex,nofollow', 'group': 'thank_you'}
    write('/thank-you-trial-somin/', page(meta, body, '/thank-you-trial-somin/'))

    # ---- /thank-you-plugin/  (Marketing Mondays plugin download release)
    body = f'''<section class="hero"><div class="container" style="max-width:980px" data-plugin-release>
  <div class="ty-card" data-plugin-state="ready" hidden>
    <div class="ty-check">{ICON['check']}</div>
    <p class="eyebrow">Your plugin is ready</p>
    <h1 class="dl-title" style="font-size:clamp(28px,3.6vw,42px);margin-top:12px">The Marketing Mondays plugin for Claude</h1>
    <p class="dl-meta">marketing-mondays.plugin · 664 KB · 26 skills and the SOMIN connector in one file</p>
    <div class="dl-actions">
      <a class="btn btn--solid" href="#" data-plugin-dl="{PLUGIN['file']}" data-plugin-main rel="noopener" data-gtm-id="plugin_download_file">{ICON['download']} Download the plugin</a>
      <a class="btn btn--ghost" href="#" data-plugin-dl="{PLUGIN['zip']}" rel="noopener" data-gtm-id="plugin_download_zip">Using Claude Code? Get the .zip</a>
    </div>
    <p class="dl-note" data-plugin-auto-note hidden><strong>Your download has started.</strong> Look for marketing-mondays.plugin in your downloads folder; if nothing appears, use the button above.</p>
  </div>
  <div class="ty-card" data-plugin-state="locked" hidden>
    <p class="eyebrow">One step left</p>
    <h2 class="dl-title" style="font-size:clamp(28px,3.6vw,42px);margin-top:12px">Get the free Marketing Mondays plugin</h2>
    <p class="dl-meta">Tell us who you are and the download starts straight away.</p>
    <a class="btn btn--solid" href="/marketing-mondays-plugin/" data-lead-form="plugin" data-gtm-id="thank_you_plugin_unlock">Get the plugin</a>
  </div>
  <div class="ty-card" style="margin-top:20px">
    <p class="eyebrow">Add it to Claude · about three minutes</p>
    <ol class="steps">
      <li><span><strong>Sign in to SOMIN first, then Claude</strong>Sign in at <a href="https://cloud.somin.ai/auth/signin" target="_blank" rel="noopener" data-gtm-id="thank_you_plugin_somin_signin">cloud.somin.ai</a>, then open <a href="https://claude.ai/" target="_blank" rel="noopener">claude.ai</a> or the Claude desktop app. Claude links to whichever SOMIN account is signed in when you click Connect.</span></li>
      <li><span><strong>Upload the plugin</strong>In Claude open <a href="https://claude.ai/customize/plugins" target="_blank" rel="noopener">Customize › Plugins</a>, click Add › Upload plugin and choose marketing-mondays.plugin.</span></li>
      <li><span><strong>Connect SOMIN</strong>Open Marketing Mondays in Customize › Plugins, go to its Connectors tab and click Connect (Add first, if asked).</span></li>
      <li><span><strong>Test it</strong>Ask Claude which SOMIN workspaces it can see. A list within seconds means you are connected; then ask for a brand deck.</span></li>
    </ol>
    <p class="dl-note">No Connectors tab? Add SOMIN as a custom connector instead: Customize › Connectors › Add custom connector, name <b>SOMIN</b>, server URL <b>{PLUGIN['mcp']}</b> (keep the underscore). Full guide: <a href="/marketing-mondays-plugin/#install" data-gtm-id="thank_you_plugin_guide">install steps</a>.</p>
    <div class="cta-row" style="justify-content:flex-start;margin-top:22px">
      <a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="thank_you_plugin_book_call">Book a 30-minute setup call</a>
      <a class="btn btn--ghost" href="https://cloud.somin.ai/auth/signin" data-gtm-id="thank_you_plugin_login">Sign in to SOMIN</a>
    </div>
  </div>
</div></section>'''
    meta = {'title': 'Your Marketing Mondays Plugin — SOMIN', 'description': 'Download the free Marketing Mondays plugin for Claude and connect it to SOMIN.',
            'type': 'thank_you', 'lead_type': 'plugin', 'layout': 'thank-you', 'robots': 'noindex,nofollow', 'group': 'thank_you'}
    write('/thank-you-plugin/', page(meta, body, '/thank-you-plugin/'))
    return manifest


def build_cases_hub(manifest):
    """/cases-ai-marketing-strategy/ — every case study as a tile; 'Get the PDF' opens the case-study Typeform."""
    path = '/cases-ai-marketing-strategy/'
    # within each section: case studies with a full story page first, then PDF-only ones (both in the original hub order)
    items = sorted([(k, v) for k, v in manifest.items() if v['on_hub']], key=lambda kv: (not kv[1]['page'], kv[1]['order']))
    sections = [('brands', 'For brands', 'brand'), ('agencies', 'For agencies', 'agency'), ('creators', 'For creators', 'creator')]
    count = {s: sum(1 for _, v in items if v['section'] == s) for s, _, _ in sections}
    total = len(items)

    def card(k, v):
        kicker = ' · '.join(x for x in (v['category'], v['market']) if x)
        lead = (f'href="/get-case-study/?cs={E(k)}" data-lead-form="case_study" data-case-study="{E(k)}" '
                f'data-case-study-label="{E(v["title"])}"')
        media_href = f'href="{E(v["page"])}"' if v['page'] else lead
        q = ' '.join([v['title'], v['category'] or '', v['market'], v['summary'], v['section']]).lower()
        read = (f'<a class="cs-read" href="{E(v["page"])}" data-gtm-id="cases_hub_read_{E(k[:40])}">Read the story {ICON["arrow"]}</a>'
                if v['page'] else '')
        return f"""<article class="cs-card" data-cs-card data-q="{E(q)}">
  <a class="cs-media" {media_href} tabindex="-1" aria-hidden="true"><img src="{E(v['cover'])}" alt="{E(v['title'])} case study cover" width="800" height="420" loading="lazy" decoding="async"></a>
  <div class="cs-body">
    <p class="cs-kicker">{E(kicker)}</p>
    <h3>{E(v['title'])}</h3>
    <p class="cs-sum">{E(v['summary'])}</p>
    <div class="cs-actions"><a class="btn btn--solid btn--sm" {lead} data-gtm-id="cases_hub_pdf_{E(k[:40])}">{ICON['download']} Get the PDF</a>{read}</div>
  </div>
</article>"""

    groups = ''
    for s, label, word in sections:
        cards = ''.join(card(k, v) for k, v in items if v['section'] == s)
        groups += (f'<div class="cs-group" data-cs-group="{s}" id="{s}"><div class="blog-list-head"><h2>{label}</h2>'
                   f'<p><span data-cs-count>{count[s]}</span> case studies</p></div><div class="cs-grid">{cards}</div></div>')
    chips = (f'<button class="chip" type="button" data-cs-filter="all" aria-pressed="true">All ({total})</button>' +
             ''.join(f'<button class="chip" type="button" data-cs-filter="{s}" aria-pressed="false">{label} ({count[s]})</button>' for s, label, _ in sections))
    # measured results quoted from the case-study tiles themselves
    proof = [('12x', 'faster planning', 'agencies-samy-case-study'), ('75%', 'lower pitch cost', 'agencies-kpi-media-case-study'),
             ('9h → 1h', 'monthly reporting', 'agencies-click2view-asia-case-study'), ('80%', 'less research time', 'brands-mothercare-sg-case-study')]
    proof_html = ''.join(f'<a href="{E(manifest[k]["page"])}" data-gtm-id="cases_hub_proof_{E(k[:40])}"><strong>{E(n)}</strong><span>{E(txt)} · <em>{E(manifest[k]["title"])}</em></span></a>'
                         for n, txt, k in proof if k in manifest and manifest[k]['page'])
    body = f"""<section class="hero cases-hero"><div class="container">
  <p class="eyebrow">Case studies</p>
  <h1>What SOMIN finds in <em>real</em> categories.</h1>
  <p class="lede">{total} case studies from brands, agencies and creators across Asia-Pacific, the Middle East, Europe and the Americas: competitor reads, whitespace maps, content calendars and the time and cost savings agencies measured. Every full PDF is free: fill in a short form and the download starts straight away.</p>
  {rating_badges("rv-badges--hero")}
  {research_strip({'compact': '1'})}
  <div class="cases-stats"><div><strong>{count['brands']}</strong><span>brand studies</span></div><div><strong>{count['agencies']}</strong><span>agency stories</span></div><div><strong>{count['creators']}</strong><span>creator strategies</span></div></div>
  <div class="cs-proof" aria-label="Measured results">{proof_html}</div>
  <div class="blog-tools"><div class="chips" role="group" aria-label="Filter case studies">{chips}</div>
    <label class="search"><span class="visually-hidden">Search case studies</span>{ICON['search']}<input type="search" placeholder="Search brand, sector or market" data-cs-search></label></div>
</div></section>
<section class="blog-list cases-list" data-cs-hub><div class="container">
  {groups}
  <p class="empty" data-cs-empty hidden>No case studies match that search. Try a brand, a sector (e.g. “banking”) or a market (e.g. “Singapore”).</p>
</div></section>
<section class="cta-band"><div class="container"><h2>Thinking about giving it a shot for <em>your business</em>?</h2><p>Book a session with our team to walk through the platform and discover insights relevant to you or your clients.</p>
<div class="cta-row"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="cases_hub_book_call">Book a call with the team</a><a class="btn btn--ghost" href="/try-somin/" data-lead-form="trial" data-gtm-id="cases_hub_try">Try SOMIN</a></div></div></section>"""

    def item_url(k, v):
        return absu(v['page']) if v['page'] else absu(f'/get-case-study/?cs={k}')
    desc = (f'{total} SOMIN case studies for brands, agencies and creators: competitor intelligence, whitespace, '
            'content calendars and ROI. Every full PDF is free.')
    coll = {"@type": "CollectionPage", "@id": f"{BASE}{path}#webpage", "url": f"{BASE}{path}", "name": "SOMIN Case Studies",
            "description": desc, "inLanguage": "en", "isPartOf": {"@id": f"{BASE}/#website"}, "about": {"@id": f"{BASE}/#organization"},
            "primaryImageOfPage": absu('/assets/img/og/cases-hub.jpg'),
            "mainEntity": {"@type": "ItemList", "numberOfItems": total, "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": item_url(k, v), "name": v['title'], "description": v['summary']}
                for i, (k, v) in enumerate(items)]}}
    meta = {'title': 'AI Marketing Case Studies for Brands & Agencies | SOMIN', 'description': desc, 'hero_bg': '/assets/img/brand/hero-cases.webp',
            'og_title': 'SOMIN Case Studies: what AI marketing intelligence finds in real categories',
            'type': 'cases_hub', 'layout': 'hub', 'og_image': '/assets/img/og/cases-hub.jpg', 'group': 'case_study',
            'keywords': 'AI marketing case studies, competitor intelligence case study, agency pitch case study, creator strategy, SOMIN, SOMONITOR',
            '_schema': [org_node(), website_node(), coll, breadcrumbs([('Home', '/'), ('Case studies', path)])]}
    write(path, page(meta, hero_image(body, meta, 'hero'), path))
    add_sitemap(path, TODAY, '0.8')


# ------------------------------------------------------------------ pricing, about and author pages
PRICING_JS = r'''<script>
(function () {
  var root = document.querySelector('[data-pricing]'), calc = document.querySelector('[data-pricing-calc]');
  var D = JSON.parse(document.getElementById('pricing-data').textContent);
  var term = 'y1', ccy = 'USD', fxDate = null, fxLoaded = false;
  Object.keys(D.terms).forEach(function (k) { if (D.terms[k].default) term = k; });
  function fmt(v) { return v.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function money(usd) { return ccy + ' ' + fmt(usd * D.fx[ccy]); }
  function q(sel, el) { return (el || document).querySelector(sel); }
  function opts(sel, max) {
    var v = Math.min(parseInt(sel.value || '0', 10) || 0, max), h = '';
    for (var i = 0; i <= max; i++) h += '<option' + (i === v ? ' selected' : '') + '>' + i + '</option>';
    sel.innerHTML = h;
  }
  function render() {
    var t = D.terms[term];
    root.querySelectorAll('[data-plan-price]').forEach(function (el) { el.textContent = money(D.plans[el.getAttribute('data-plan-price')].price * (1 - t.d)); });
    root.querySelectorAll('[data-term-cap]').forEach(function (el) { el.textContent = t.cap; });
    var n = q('[data-fx-note]');
    if (n) n.textContent = 'Prices are set and billed in USD; other currencies are indicative' + (ccy === 'USD' ? '' : (fxDate ? ' (ECB rates of ' + fxDate + ')' : ' (reference rates)') + ': 1 USD = ' + D.fx[ccy] + ' ' + ccy) + '. Prices exclude applicable taxes.';
    calcRender();
  }
  function calcRender() {
    if (!calc) return;
    var plan = q('[data-calc="plan"]', calc).value, P = D.plans[plan], t = D.terms[term];
    var an = +q('[data-calc="an"]', calc).value, sp = +q('[data-calc="sp"]', calc).value, hb = +q('[data-calc="hb"]', calc).value;
    var base = P.price * (1 - t.d), seats = an * D.addons.analyst_seat + sp * D.addons.specialist_seat, blocks = hb * P.block, m = base + seats + blocks;
    q('[data-calc-breakdown]', calc).innerHTML = 'Plan after term saving: <b>' + money(base) + '</b> / mo' + (seats ? ' · Extra seats: <b>' + money(seats) + '</b> / mo' : '') + (blocks ? ' · +' + (hb * 10) + ' brands: <b>' + money(blocks) + '</b> / mo' : '');
    q('[data-calc-month]', calc).textContent = money(m);
    q('[data-calc-billed-label]', calc).textContent = 'Billed in advance · ' + (t.m === 1 ? '1 month' : (t.m / 12) + (t.m === 12 ? ' year' : ' years'));
    q('[data-calc-billed]', calc).textContent = money(m * t.m);
    var pay = q('[data-calc-pay]', calc), note = q('[data-calc-note]', calc), al = q('[data-calc-alert]', calc);
    var links = D.pay[plan] && D.pay[plan][term];
    al.hidden = true;
    if (!links) {
      pay.textContent = 'Multi-year terms: talk to sales'; pay.href = pay.getAttribute('data-sales') || pay.href;
      note.textContent = 'Two- and three-year prepays are issued as private offers or order forms, not card checkout.';
      return;
    }
    pay.textContent = 'Pay with Stripe →';
    pay.href = links[((an ? 'a' : '') + (sp ? 's' : '') + (hb ? 'h' : '')) || '0'];
    note.textContent = 'Secure Stripe checkout, billed in USD.';
    if (an > 1 || sp > 1 || hb > 1) { al.hidden = false; al.textContent = 'The payment link opens with one of each selected add-on: raise the quantities on the Stripe page after you click Pay.'; }
  }
  function caps() {
    var P = D.plans[q('[data-calc="plan"]', calc).value];
    opts(q('[data-calc="an"]', calc), P.seats); opts(q('[data-calc="sp"]', calc), P.seats); opts(q('[data-calc="hb"]', calc), P.blocks);
  }
  function press(group, btn) { group.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'); }); }
  root.querySelectorAll('[data-term]').forEach(function (b) { b.addEventListener('click', function () { term = b.getAttribute('data-term'); press(b.parentNode, b); render(); if (window.sominTrack) window.sominTrack('pricing_term_change', { term: term }); }); });
  root.querySelectorAll('[data-ccy]').forEach(function (b) { b.addEventListener('click', function () {
    ccy = b.getAttribute('data-ccy'); press(b.parentNode, b); render();
    if (!fxLoaded && ccy !== 'USD' && window.fetch) { fxLoaded = true;
      fetch('https://api.frankfurter.app/latest?from=USD&to=GBP,EUR,SGD').then(function (r) { return r.json(); })
        .then(function (d) { if (d && d.rates) { ['GBP', 'EUR', 'SGD'].forEach(function (c) { if (d.rates[c]) D.fx[c] = d.rates[c]; }); fxDate = d.date; render(); } }).catch(function () {});
    }
  }); });
  root.querySelectorAll('[data-plan-select]').forEach(function (a) { a.addEventListener('click', function () { q('[data-calc="plan"]', calc).value = a.getAttribute('data-plan-select'); caps(); calcRender(); }); });
  if (calc) {
    q('[data-calc-pay]', calc).setAttribute('data-sales', q('[data-calc-pay]', calc).href);
    q('[data-calc="plan"]', calc).addEventListener('change', function () { caps(); calcRender(); });
    ['an', 'sp', 'hb'].forEach(function (k) { q('[data-calc="' + k + '"]', calc).addEventListener('change', calcRender); });
    caps();
  }
  render();
})();
</script>'''


def _money(v):
    return f'{v:,.2f}'


def pricing_rows_html(pr):
    rows = ''
    n = len(pr['plans']) + 2
    for g in pr['groups']:
        rows += f'<tr class="pr-grp"><th colspan="{n}" scope="colgroup">{E(g["title"])}</th></tr>'
        for r in g['rows']:
            cells = ''
            for i, v in enumerate(r['values']):
                ent = ' pr-ent' if i == len(r['values']) - 1 else ''
                if isinstance(v, dict):
                    cells += (f'<td class="pr-c{ent}"><details class="pr-fx pr-val"><summary>{E(v["v"])}</summary>'
                              f'<p class="pr-exp">{E(v["note"])}</p></details></td>')
                else:
                    cls = ' pr-yes' if v in ('Yes', '✓', 'Included') else ' pr-no' if v == 'No' else ''
                    label = {'Yes': 'Included', 'No': 'Not included', '✓': 'Included'}.get(v)
                    shown = '✓' if v == 'Yes' else ('—' if v == 'No' else v)
                    cells += f'<td class="pr-c{cls}{ent}"' + (f' aria-label="{label}"' if label else '') + f'>{E(shown)}</td>'
            rows += (f'<tr><th scope="row" class="pr-feat"><details class="pr-fx"><summary>{E(r["name"])}</summary>'
                     f'<p class="pr-exp">{E(r["detail"])}</p></details></th>{cells}</tr>')
    return rows


def build_pricing_page():
    """/pricing/: SOMIN plans and prices from data/pricing.json (the cloud.somin.ai pricing sheet), rendered server-side so
    search and answer engines read the real numbers; the inline script only switches term, currency and the calculator."""
    path = '/pricing/'
    pr = PRICING
    plans = pr['plans']
    term = next(t for t in pr['terms'] if t.get('default'))
    low = min(p['price'] for p in plans)
    low_y = low * (1 - term['discount'])
    terms_html = ''.join(
        f'<button type="button" data-term="{t["key"]}" aria-pressed="{"true" if t.get("default") else "false"}">{E(t["label"])}'
        + (f' <span class="pr-badge">{E(t["badge"])}</span>' if t.get('badge') else '') + (f' <small>· {E(t["note"])}</small>' if t.get('note') else '') + '</button>'
        for t in pr['terms'])
    ccy_html = ''.join(f'<button type="button" data-ccy="{c}" aria-pressed="{"true" if c == "USD" else "false"}">{c}</button>' for c in pr['fx_fallback'])
    head = '<th scope="col" class="pr-feat"><span class="visually-hidden">Feature</span></th>' + ''.join(
        f'<th scope="col" class="pr-tier" id="plan-{p["key"]}">{E(p["name"])}<span>{E(p["tagline"])}</span></th>' for p in plans) + \
        f'<th scope="col" class="pr-tier pr-tier--ent">{E(pr["enterprise"]["name"])}<span>{E(pr["enterprise"]["tagline"])}</span></th>'
    price_cells = '<td class="pr-feat"></td>' + ''.join(
        f'<td class="pr-head"><div class="pr-price" data-plan-price="{p["key"]}">USD {_money(p["price"] * (1 - term["discount"]))}</div>'
        f'<div class="pr-per" data-term-cap>{E(term["cap"])}</div>'
        f'<a class="pr-sel" href="#pr-calc" data-plan-select="{p["key"]}" data-track="pricing_plan_select" data-gtm-id="pricing_select_{p["key"]}">Select</a></td>'
        for p in plans) + (f'<td class="pr-head pr-ent"><div class="pr-price">{E(pr["enterprise"]["price_label"])}</div><div class="pr-per">{E(pr["enterprise"]["note"])}</div>'
                           f'<a class="pr-sel" href="{CAL_DEFAULT}" data-gtm-id="pricing_enterprise_call">Talk to sales</a></td>')
    glance = ''.join(
        f'<li><strong>{E(p["name"].title().replace("Somin", "SOMIN"))}</strong>: US${p["price"]:,} a month, or US${_money(p["price"] * 0.9)} a month billed annually. '
        f'{E(p["seats"])}, {p["brands"]} brands monitored, {p["swaps"]} handle swaps a month.</li>' for p in plans) + \
        f'<li><strong>SOMIN Enterprise</strong>: custom multi-market private offers with handle pools (100+ brands) and a customer success manager.</li>'
    plan_opts = ''.join(f'<option value="{p["key"]}">{E(p["name"])}</option>' for p in plans)
    js_data = {'plans': {p['key']: {'price': p['price'], 'seats': p['seat_cap'], 'blocks': p['handle_blocks_cap'], 'block': p['handle_block_price']} for p in plans},
               'terms': {t['key']: {'d': t['discount'], 'm': t['months'], 'cap': t['cap'], 'checkout': t['checkout'], 'default': bool(t.get('default'))} for t in pr['terms']},
               'addons': pr['addons'], 'fx': pr['fx_fallback'], 'pay': pr['paylinks']}
    a = pr['addons']
    faq = [
        ('How much does SOMIN cost?', f'SOMIN has four self-serve plans: SOMIN Light at US${plans[0]["price"]:,} a month, SOMIN Pro at US${plans[1]["price"]:,}, SOMIN Agency Light at US${plans[2]["price"]:,} and SOMIN Agency Pro at US${plans[3]["price"]:,}. Annual billing saves 10%, two-year terms 16% and three-year terms 22% (multi-year through sales). Enterprise plans are custom. Prices are in US dollars and exclude taxes.'),
        ('What is a seat?', f'Every seat is one named user with full dashboard access and the agentic MCP connector for Claude, Manus or Codex. An Analyst seat carries {pr["seat_types"]["Analyst"]}; a Specialist seat carries {pr["seat_types"]["Specialist"]}. Extra seats cost US${a["analyst_seat"]} (Analyst) or US${a["specialist_seat"]} (Specialist) a month, up to each plan\'s cap.'),
        ('Are there overage fees?', 'No. Quotas pause and resume automatically, so nothing ever bills past your plan. If a seat reaches its 5-hour window cap mid-build it waits for the next window; weekly ceilings reset on Monday at 00:00 UTC.'),
        ('Can I monitor more brands?', f'Yes. Each plan includes a set number of monitored brand handles and can grow in blocks of 10 (US${plans[0]["handle_block_price"]} a month on Light plans, US${plans[1]["handle_block_price"]} on Pro plans), up to 2 blocks on brand plans and 3 on agency plans. Larger portfolios move up a tier or to Enterprise.'),
        ('Can I try SOMIN before I buy?', 'Yes. Request trial access and the team sets up a workspace with your brand and competitors, or book a 30-minute walkthrough on your own category.'),
        ('Is grant support available in Singapore?', 'SMEs are eligible for up to 50% business grant support for the adoption of SOMIN, a Pre-Approved Solution under the IMDA SMEs Go Digital programme. Check eligibility at share.somin.ai/psg.'),
    ]
    faq_html = ''.join(f'<details><summary>{E(q)}</summary><p>{E(ans)}</p></details>' for q, ans in faq)
    body = f'''<section class="hero pr-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">Pricing</li></ol></nav>
  <p class="eyebrow">Plans &amp; pricing</p>
  <h1>SOMIN pricing: plans for <em>brands and agencies</em></h1>
  <p class="lede">Four self-serve plans from US${low:,} a month (US${_money(low_y)} billed annually). Every seat ships with the SOMIN dashboard and agentic MCP access, so complete pitch builds run inside the AI assistant your team already uses. No overage fees.</p>
  <div class="cta-row cta-row--left">
    <a class="btn btn--solid" href="#pr-plans" data-gtm-id="pricing_hero_plans">Compare plans</a>
    <a class="btn btn--ghost" href="{CAL_DEFAULT}" data-gtm-id="pricing_hero_call">Talk to sales</a>
  </div>
</div></section>

<section class="sec sec--light"><div class="container">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">At a glance</p><h2>SOMIN plans and prices</h2>
  <p>Monthly list prices in US dollars, excluding taxes. Annual billing saves 10%; two- and three-year terms (16% and 22% off) are arranged through sales.</p></div>
  <ul class="check-list pr-glance">{glance}</ul>
</div></section>

<section class="sec sec--mist" id="pr-plans"><div class="container pr-sheet" data-pricing>
  <div class="pr-bar">
    <div class="pr-toggle" role="group" aria-label="Billing period">{terms_html}</div>
    <div class="pr-toggle pr-toggle--ccy" role="group" aria-label="Currency">{ccy_html}</div>
  </div>
  <div class="table-scroll pr-scroll"><table class="pr-table">
    <caption class="visually-hidden">SOMIN plans compared: price, seats, monitored brands and features</caption>
    <thead><tr>{head}</tr></thead>
    <tbody><tr class="pr-prices">{price_cells}</tr>{pricing_rows_html(pr)}</tbody>
  </table></div>
  <p class="pr-note" data-fx-note>Prices are set and billed in USD; other currencies are indicative. {E(pr["taxes"])}</p>
  <p class="pr-note"><strong>Custom reports.</strong> {E(pr["custom_reports"])}</p>
</div></section>

<section class="sec sec--light" id="pr-calc"><div class="container">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Price calculator</p><h2>Build your plan and check out</h2>
  <p>Pick a plan and add seats or brand blocks. The billing period and currency follow the switches above the table; term savings apply to the plan base and add-ons bill at list.</p></div>
  <div class="pr-calc" data-pricing-calc>
    <div class="pr-calc-grid">
      <label>Plan<select data-calc="plan">{plan_opts}</select></label>
      <label>+ Analyst seats<select data-calc="an"><option>0</option></select></label>
      <label>+ Specialist seats<select data-calc="sp"><option>0</option></select></label>
      <label>+10-brand blocks<select data-calc="hb"><option>0</option></select></label>
    </div>
    <p class="pr-brk" data-calc-breakdown></p>
    <div class="pr-tot"><div><small>Monthly total</small><strong data-calc-month>—</strong></div><div><small data-calc-billed-label>Billed in advance</small><strong data-calc-billed>—</strong></div>
      <div><a class="btn btn--solid pr-pay" data-calc-pay href="{CAL_DEFAULT}" target="_blank" rel="noopener" data-track="pricing_checkout_click" data-gtm-id="pricing_pay_stripe">Pay with Stripe →</a>
      <p class="pr-small" data-calc-note></p></div></div>
    <p class="pr-alert" data-calc-alert hidden></p>
    <p class="pr-small">Add-ons: Analyst seat US${a["analyst_seat"]} · Specialist seat US${a["specialist_seat"]} · +10 brands US${plans[0]["handle_block_price"]} on Light plans, US${plans[1]["handle_block_price"]} on Pro plans a month, capped per plan (seats {"/".join(str(p["seat_cap"]) for p in plans)}, blocks {"/".join(str(p["handle_blocks_cap"]) for p in plans)}). The payment link carries one of each selected add-on; raise quantities on the Stripe page. Billed in USD.</p>
  </div>
</div></section>

<section class="sec sec--mist"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Billing</p><h2>Cancellation and change policy</h2>
    <ul class="check-list">{"".join(f"<li>{E(x)}</li>" for x in pr["policy"])}</ul></div>
  <div class="sec-head" id="quote"><p class="eyebrow eyebrow--ink">Enterprise</p><h2>Get a custom quote</h2><p>{E(pr["custom_quote"])}</p>
    <div class="cta-row cta-row--left"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="pricing_quote_call">Book a call with sales</a>
    <a class="btn btn--ghost btn--ink" href="/try-somin/" data-lead-form="trial" data-gtm-id="pricing_quote_trial">Try SOMIN</a></div></div>
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">FAQ</p><h2>SOMIN pricing FAQ</h2></div>
  <div class="faq-list">{faq_html}</div>
</div></section>

<section class="cta-band"><div class="container"><h2>See SOMIN on <em>your</em> category first</h2>
<p>A 30-minute walkthrough on your brand, your competitors and the brief on your desk this week.</p>
<div class="cta-row"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="pricing_footer_call">Book a call</a><a class="btn btn--ghost" href="/try-somin/" data-lead-form="trial" data-gtm-id="pricing_footer_trial">Try SOMIN</a></div></div></section>
<script type="application/json" id="pricing-data">{json.dumps(js_data, ensure_ascii=False)}</script>''' + PRICING_JS
    meta = {'slug': 'pricing', 'layout': 'native', 'type': 'pricing', 'group': 'pricing', 'robots': 'index,follow',
            'title': 'SOMIN Pricing: Plans for Brands & Agencies | SOMIN',
            'seo_title': 'SOMIN Pricing: Plans for Brands and Agencies',
            'description': f'SOMIN pricing: four plans from US${low:,} a month for brands and agencies, with agentic seats, monitored brands and no overage fees. Annual billing saves 10%.',
            'og_image': '/assets/img/og/card-default.jpg'}
    web = {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta['seo_title'], "description": meta['description'],
           "isPartOf": {"@id": WEBSITE_ID}, "about": {"@id": SOFTWARE_ID}, "mainEntity": {"@id": SOFTWARE_ID}, "inLanguage": "en"}
    build_native_page(meta, body, schema=[org_node(), website_node(), software_node(), web, breadcrumbs([('Home', '/'), ('Pricing', path)])])
    return meta


def build_about_page(post_metas):
    """/about/: who SOMIN is, in one place (entity page for search and answer engines), from data/organization.json."""
    path = '/about/'
    o, s, f = ORG['organization'], ORG['software'], ORG['founder']
    low = min(p['price'] for p in PRICING['plans'])
    team = [('Prof. Aleks Farseev', 'Co-Founder and CEO, SOMIN')] + [(n, r) for n, (r, _) in TEAM.items()]
    team_html = ''.join(f'<a class="mini mini--light" href="/authors/{author_slug(n)}/"><span>{E(r.replace(", SOMIN", ""))}</span><strong>{E(n)}</strong></a>' for n, r in team)
    facts = [('Company', f'{o["name"]} ({o["legal_name"]})'), ('Headquarters', o['founding_location']),
             ('Founders', 'Prof. Aleks Farseev (CEO) and Kirill Lepikhin (CTO)'), ('Platform', 'SOMIN, with the SOMONITOR intelligence engine'),
             ('Markets', ', '.join(o['markets'][:-1]) + ' and ' + o['markets'][-1]), ('Pricing', f'From US${low:,} a month; see the plans'),
             ('Contact', o['email'])]
    facts_html = ''.join(f'<div><dt>{E(k)}</dt><dd>' + (f'<a href="/pricing/">{E(v)}</a>' if k == 'Pricing' else f'<a href="mailto:{E(v)}">{E(v)}</a>' if k == 'Contact' else E(v)) + '</dd></div>' for k, v in facts)
    awards = [('Gartner Cool Vendor in Marketing AI', 'https://ddistenfield.medium.com/gsd-labs-company-somin-is-a-gartner-cool-ai-vendor-78da8fcd41ff'),
              ('Google for Startups AI First Programme', 'https://startup.google.com/programs/accelerator/singapore/'),
              ('IMDA SMEs Go Digital Pre-Approved Solution', 'https://smesgodigital.gov.sg/web/solution/20240259/somonitor'),
              ('Zapier Silver Agentic AI Partner', 'https://zapier.com/partnerdirectory/somin'),
              ('Google Cloud customer story', 'https://cloud.google.com/customers/somin-ai')]
    awards_html = ''.join(f'<li><a href="{E(u)}" target="_blank" rel="noopener">{E(n)}</a></li>' for n, u in awards)
    labels = {'linkedin': 'LinkedIn', 'crunchbase': 'Crunchbase', 'cbinsights': 'CB Insights', 'g2.com': 'G2 reviews', 'capterra': 'Capterra reviews',
              'sourceforge': 'SourceForge', 'zapier': 'Zapier partner directory', 'smesgodigital': 'IMDA SMEs Go Digital listing'}
    prof = ''.join(f'<li><a href="{E(u)}" target="_blank" rel="noopener">{E(next((v for k, v in labels.items() if k in u), u))}</a></li>' for u in o['same_as'])
    faq = [
        ('What is SOMIN?', o['description']),
        ('Who founded SOMIN?', 'SOMIN was co-founded by Prof. Aleks Farseev, its CEO and a research professor in digital-marketing AI, and Kirill Lepikhin, its CTO.'),
        ('Where is SOMIN based?', f'SOMIN ({o["legal_name"]}) is based in Singapore and works with brand, agency and creator teams across 11+ markets in APAC, MENA and Europe.'),
        ('Is SOMIN the same as SOMONITOR?', 'SOMONITOR is the name of the intelligence engine inside the SOMIN platform (it is also how SOMIN is listed under the IMDA SMEs Go Digital programme). SOMIN is the company and the product.'),
        ('How much does SOMIN cost?', f'Self-serve plans start at US${low:,} a month, with 10% off for annual billing; enterprise plans are custom. See the pricing page for every plan.'),
        ('How do I contact SOMIN?', f'Book a call with the team through the website, request trial access, or email {o["email"]}.'),
    ]
    faq_html = ''.join(f'<details><summary>{E(q)}</summary><p>{E(ans)}</p></details>' for q, ans in faq)
    body = f'''<section class="hero ab-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">About</li></ol></nav>
  <p class="eyebrow">About SOMIN</p>
  <h1>About SOMIN: AI marketing intelligence <em>built in Singapore</em></h1>
  <p class="lede">{E(o["description"])}</p>
  <div class="cta-row cta-row--left"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="about_hero_call">Book a call</a><a class="btn btn--ghost" href="/pricing/" data-gtm-id="about_hero_pricing">See pricing</a></div>
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">What SOMIN does</p><h2>Verified category data in, defensible ideas out</h2>
    <p>{E(s["description"])}</p>
    <p>Agencies use SOMIN to <a href="/somin-for-agencies/">pitch, report and plan strategy</a>, brands use it to <a href="/somin-for-brands/">watch competitors and brief their teams</a>, and creator programs use it to <a href="/somin-for-creators/">choose creators and brief them to sell</a>. Six <a href="/ai-agents/">AI agents</a> run the work, and the free <a href="/marketing-mondays-plugin/">Marketing Mondays plugin</a> brings them into Claude.</p></div>
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Key facts</p><dl class="ab-facts">{facts_html}</dl></div>
</div></section>

<section class="sec sec--mist"><div class="container">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Who builds SOMIN</p><h2>Seasoned marketers and an AI professor</h2>
  <p>{E(f["description"])} Next to the research team, SOMIN's marketers turn those models into the playbooks brand and agency teams run every week. <a href="/research/">Read the research</a> or <a href="/vision/">our vision</a>.</p></div>
  <div class="mini-grid ab-team">{team_html}</div>
</div></section>

<section class="sec sec--light"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Recognition</p><h2>Awards, programmes and partners</h2><ul class="check-list ab-links">{awards_html}</ul></div>
  <div class="sec-head"><p class="eyebrow eyebrow--ink">Find SOMIN elsewhere</p><h2>Profiles and reviews</h2><ul class="check-list ab-links">{prof}</ul></div>
</div></section>

<section class="sec sec--mist"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">FAQ</p><h2>About SOMIN FAQ</h2></div>
  <div class="faq-list">{faq_html}</div>
</div></section>

<section class="cta-band"><div class="container"><h2>See what SOMIN finds in <em>your</em> category</h2>
<p>A 30-minute walkthrough on your brand, your competitors and the work on your desk this week.</p>
<div class="cta-row"><a class="btn btn--solid" href="{CAL_DEFAULT}" data-gtm-id="about_footer_call">Book a call</a><a class="btn btn--ghost" href="/try-somin/" data-lead-form="trial" data-gtm-id="about_footer_trial">Try SOMIN</a></div></div></section>'''
    meta = {'slug': 'about', 'layout': 'native', 'type': 'company', 'group': 'company', 'robots': 'index,follow',
            'title': 'About SOMIN: AI Marketing Intelligence from Singapore | SOMIN', 'seo_title': 'About SOMIN: AI Marketing Intelligence from Singapore',
            'description': 'About SOMIN (Somin Pte. Ltd.): the Singapore AI marketing-intelligence company behind SOMONITOR, its founders, team, research, awards and markets.',
            'og_image': '/assets/img/og/card-default.jpg'}
    web = {"@type": "AboutPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta['seo_title'], "description": meta['description'],
           "isPartOf": {"@id": WEBSITE_ID}, "about": {"@id": ORG_ID}, "mainEntity": {"@id": ORG_ID}, "inLanguage": "en"}
    build_native_page(meta, body, schema=[org_node(), founder_node(), website_node(), software_node(), web, breadcrumbs([('Home', '/'), ('About', path)])])
    return meta


def build_author_pages(post_metas):
    """/authors/ and /authors/<slug>/: a profile page per blog author (E-E-A-T), listing their articles."""
    by = {}
    for p in post_metas:
        if p['author'] != 'SOMIN Team':
            by.setdefault(p['author'], []).append(p)
    for n in TEAM:
        by.setdefault(n, [])
    order = sorted(by, key=lambda n: (n != 'Prof. Aleks Farseev', -len(by[n]), n))
    cards = ''
    metas = []
    for name in order:
        posts = by[name]
        slug = author_slug(name)
        path = f'/authors/{slug}/'
        node = dict(author_node(name))
        role = (ORG['founder']['job_title'] if name == 'Prof. Aleks Farseev' else AUTHOR_ROLE.get(name) or 'SOMIN')
        role_short = role.replace(', SOMIN', '') if role != 'SOMIN' else 'SOMIN team'
        topics = []
        for p in posts:
            for t in p['tags']:
                if t not in topics and t != 'Community':
                    topics.append(t)
        first = re.sub(r'^(Prof|Dr)[.] *', '', name).split()[0]
        if name == 'Prof. Aleks Farseev':
            bio = (f'<p>{E(ORG["founder"]["description"])}</p><p>He leads SOMIN\'s research on audience profiling, personality-driven content and '
                   f'explainable AI for advertising; the papers and talks are on the <a href="/research/">research page</a>.</p>')
        else:
            bio = f'<p>{E(name)} is {E(role_short)} at SOMIN, the Singapore AI marketing-intelligence company.' + (
                f' {E(first)} writes on the SOMIN blog about {E(", ".join(topics[:3]).lower())}.</p>' if topics else '</p>')
        links = ''.join(f'<li><a href="{E(u)}" target="_blank" rel="noopener me">{E("LinkedIn" if "linkedin" in u else "Google Scholar" if "scholar.google" in u else "Semantic Scholar" if "semanticscholar" in u else "ACM Digital Library" if "acm.org" in u else "Forbes Technology Council" if "forbes" in u else "Crunchbase" if "crunchbase" in u else re.sub(r"^https?://(www[.])?", "", u).strip("/"))}</a></li>'
                        for u in node.get('sameAs', [])[:8])
        grid = ''.join(post_card(p) for p in posts)
        body = f'''<section class="hero au-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li><a href="/authors/">Authors</a></li><li aria-current="page">{E(name)}</li></ol></nav>
  <p class="eyebrow">Author · {E(role_short)}</p>
  <h1>{E(name)}</h1>
  <p class="lede">{E(role)}{f" · {len(posts)} article{'s' if len(posts) != 1 else ''} on the SOMIN blog" if posts else ""}</p>
</div></section>
<section class="sec sec--light"><div class="container split">
  <div class="sec-head"><p class="eyebrow eyebrow--ink">About {E(first)}</p>{bio}</div>
  <div class="sec-head">{"<p class='eyebrow eyebrow--ink'>Profiles</p><ul class='check-list ab-links'>" + links + "</ul>" if links else ""}</div>
</div></section>
''' + (f'''<section class="blog-list au-posts"><div class="container"><div class="blog-list-head"><h2>Articles by {E(name)}</h2><p>{len(posts)} articles</p></div>
<div class="post-grid">{grid}</div></div></section>''' if posts else '')
        desc = (f'{name}, {role_short} at SOMIN. ' + (f'Read {len(posts)} article{"s" if len(posts) != 1 else ""} by {first} on '
                + (', '.join(topics[:2]).lower() if topics else 'AI marketing') + ' and more on the SOMIN blog.' if posts else 'Profile and links.'))
        if len(desc) < 120:
            desc += ' SOMIN turns live competitor and audience data into pre-scored campaign ideas.'
        desc = desc if len(desc) <= 160 else desc[:157].rsplit(' ', 1)[0] + '…'
        title = f'{name}, {role_short} | SOMIN'
        meta = {'slug': f'authors/{slug}', 'layout': 'native', 'type': 'author', 'group': 'blog', 'robots': 'index,follow',
                'title': title if len(title) <= 60 else (f'{name}, SOMIN author | SOMIN' if len(name) <= 32 else f'{name} | SOMIN'),
                'description': desc, 'og_image': '/assets/img/og/card-default.jpg'}
        node['mainEntityOfPage'] = absu(path)
        prof = {"@type": "ProfilePage", "@id": absu(path) + "#webpage", "url": absu(path), "name": f'{name}, {role_short}', "isPartOf": {"@id": WEBSITE_ID},
                "mainEntity": {"@id": node.get('@id')}, "inLanguage": "en"}
        if posts:
            prof['hasPart'] = [{"@type": "BlogPosting", "headline": p['title'][:110], "url": absu(url_for(p['slug'])), "datePublished": p['published']} for p in posts[:20]]
        build_native_page(meta, body, schema=[org_node(), website_node(), node, prof, breadcrumbs([('Home', '/'), ('Authors', '/authors/'), (name, path)])])
        metas.append(meta)
        cards += f'<a class="mini mini--light" href="{path}"><span>{E(role_short)}</span><strong>{E(name)}</strong><em>{len(posts)} article{"s" if len(posts) != 1 else ""}</em></a>'
    path = '/authors/'
    body = f'''<section class="hero au-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">Authors</li></ol></nav>
  <p class="eyebrow">SOMIN Blog</p><h1>The people behind the <em>SOMIN blog</em></h1>
  <p class="lede">Researchers, strategists, data scientists and engineers from the SOMIN team, writing on AI marketing agents, competitor and audience intelligence, paid media and creative strategy.</p>
</div></section>
<section class="sec sec--light"><div class="container"><div class="mini-grid ab-team">{cards}</div>
<p style="margin-top:28px"><a class="btn btn--ghost btn--ink" href="/blog/" data-gtm-id="authors_blog">Read the blog</a></p></div></section>'''
    meta = {'slug': 'authors', 'layout': 'native', 'type': 'author_index', 'group': 'blog', 'robots': 'index,follow',
            'title': 'SOMIN Blog Authors: Researchers and Strategists | SOMIN',
            'description': 'Meet the SOMIN blog authors: researchers, strategists, data scientists and engineers writing on AI marketing agents, competitor intelligence and strategy.',
            'og_image': '/assets/img/og/card-default.jpg'}
    coll = {"@type": "CollectionPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": "SOMIN Blog Authors", "isPartOf": {"@id": WEBSITE_ID}, "inLanguage": "en"}
    build_native_page(meta, body, schema=[org_node(), website_node(), coll, breadcrumbs([('Home', '/'), ('Authors', path)])])
    return metas + [meta]


def build_404():
    links = [('Solutions', 'SOMIN for Brands', '/somin-for-brands/'), ('Solutions', 'SOMIN for Agencies', '/somin-for-agencies/'),
             ('Solutions', 'SOMIN for Creators', '/somin-for-creators/'), ('Platform', 'AI Agents', '/ai-agents/'),
             ('Insights', 'Blog', '/blog/'), ('Company', 'Our Vision', '/vision/')]
    cards = ''.join(f'<a class="mini" href="{u}"><span>{E(c)}</span><strong>{E(t)}</strong></a>' for c, t, u in links)
    body = f'''<section class="hero nf"><div class="container" style="max-width:980px">
  <p class="code">404</p><h1>Oops, page not found</h1>
  <p class="lede">But that doesn't mean we can't help you find what you're looking for!</p>
  <div class="cta-row" style="margin-top:28px"><a class="btn btn--solid" href="/">Go to the homepage</a><a class="btn btn--ghost" href="{CAL_DEFAULT}" data-gtm-id="404_book_call">Book a call</a></div>
  <div class="mini-grid">{cards}</div>
</div></section>'''
    meta = {'title': 'Page not found — SOMIN', 'description': 'The page you were looking for could not be found.', 'type': '404', 'layout': '404', 'robots': 'noindex,follow'}
    html_text = page(meta, body, '/404.html')
    # 404 is served from any depth: make relative-safe (all our URLs are root-relative already)
    (OUT / '404.html').write_text(html_text.replace(f'<link rel="canonical" href="{BASE}/404.html">', ''), encoding='utf-8')


def build_redirects():
    for src, dst in CFG['redirects'].items():
        target = dst
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Redirecting…</title>'
                f'<meta name="robots" content="noindex,follow"><link rel="canonical" href="{absu(target)}">'
                f'<meta http-equiv="refresh" content="0; url={E(target)}">'
                f'<script>location.replace({json.dumps(target)} + location.search + location.hash);</script></head>'
                f'<body><p>This page has moved to <a href="{E(target)}">{E(absu(target))}</a>.</p></body></html>')
        write(src, body)


# ------------------------------------------------------------------ SEO / AEO / GEO files
def build_sitemap():
    seen, rows = set(), []
    for path, lastmod, pr in SITEMAP:
        if path in seen:
            continue
        seen.add(path)
        alt = ''.join(f'<xhtml:link rel="alternate" hreflang="{E(hl)}" href="{E(absu(h))}"/>' for hl, h in LOCALE_ALTERNATES.get(path, []))
        rows.append(f'<url><loc>{absu(path)}</loc><lastmod>{(PAGE_DATES.get(path) or lastmod or TODAY)[:10]}</lastmod>{alt}</url>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
           + '\n'.join(rows) + '\n</urlset>\n')
    (OUT / 'sitemap.xml').write_text(xml, encoding='utf-8')
    return len(rows)


AI_CRAWLERS = ['GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'ClaudeBot', 'Claude-SearchBot', 'Claude-User', 'PerplexityBot', 'Perplexity-User',
               'Google-Extended', 'Applebot-Extended', 'Meta-ExternalAgent', 'Amazonbot', 'DuckAssistBot', 'MistralAI-User', 'CCBot']
ROBOTS_DISALLOW = ['/thank-you-trial-somin/', '/thank-you-case-study/', '/thank-you-plugin/']


def build_robots():
    # A crawler obeys only the most specific group that names it, so every named AI group repeats the Disallow lines.
    rules = 'Allow: /\n' + ''.join(f'Disallow: {p}\n' for p in ROBOTS_DISALLOW)
    ai = ''.join(f'User-agent: {ua}\n' for ua in AI_CRAWLERS)
    txt = (f'# SOMIN — {BASE}\nUser-agent: *\n{rules}\n'
           f'# AI assistants and answer engines are welcome to read and cite this site.\n{ai}{rules}\n'
           f'Sitemap: {BASE}/sitemap.xml\n')
    (OUT / 'robots.txt').write_text(txt, encoding='utf-8')


def build_llms(pages, posts, manifest=None, localized=()):
    by = lambda t: [m for m in pages if m.get('type') == t and m.get('robots', 'index').startswith('index')]
    def line(m):
        return f'- [{m["title"].split(" | ")[0]}]({absu(url_for(m["slug"]))}): {m.get("description") or ""}'
    home = next((m for m in pages if m['slug'] == ''), None)
    parts = [f'# SOMIN', '', f'> {SITE["description"]}', '',
             'SOMIN (somin.ai, legal name Somin Pte. Ltd., Singapore) is an agentic AI marketing-intelligence platform. Its SOMONITOR engine reads competitor ads, posts and creators plus live audience conversation, finds category whitespace, and produces pre-scored propositions, briefs and on-brand creative concepts for brands, agencies and creator programmes across 11+ markets in APAC, MENA and Europe. Recognised as a Gartner Cool Vendor in Marketing AI and a Zapier agentic-AI partner.', '',
             'How SOMIN works: one loop in five steps, run by AI agents on verified category data. Listen (what happened?), Decode (who is winning, and how?), Decide (what do we say?), Make (what does it look like?) and Ship (when does it go out?). Every idea answers four questions: who are we talking to (persona), what is bugging them (tension), why does that happen (angle) and what is the one line that says it (story). Every number traces back to a SOMIN post, study or ID.', '',
             'Third-party ratings: ' + '; '.join(f'{p["rating"]:.1f}/5 on {p["name"]} ({p["url"]})' for p in REVIEWS['platforms'].values() if p.get('rating')) + '.', '',
             f'Free tool: the Marketing Mondays plugin for Claude ({BASE}/marketing-mondays-plugin/) packs 8 main skills (26 in all) and the SOMIN connector (MCP server {PLUGIN["mcp"]}) so Claude can run that loop on a team\'s own SOMIN data.', '',
             'Pricing (US$, monthly list, excl. taxes; annual billing saves 10%): ' + '; '.join(f'{pl["name"]} US${pl["price"]:,}/month ({pl["seats"]}, {pl["brands"]} brands)' for pl in PRICING['plans'])
             + f'; {PRICING["enterprise"]["name"]} custom. Details: {BASE}/pricing/', '',
             '## Key pages']
    if home:
        parts.append(f'- [Home]({BASE}/): {home.get("description")}')
    for m in pages:
        if m.get('slug') in ('pricing', 'about'):
            parts.append(line(m))
    parts += [line(m) for m in by('solution')]
    parts += ['', '## AI agents and products'] + [line(m) for m in by('product')]
    parts += ['', '## Comparisons'] + [line(m) for m in by('comparison')]
    parts += ['', '## Case studies', f'- [All SOMIN case studies]({BASE}/cases-ai-marketing-strategy/): every case study with a summary; the full PDFs are free after a short form.']
    parts += [line(m) for m in by('case_study')]
    if manifest:
        more = sorted([v for v in manifest.values() if v['on_hub'] and not v['page']], key=lambda v: v['order'])
        parts += ['', '### More case studies (PDF on the case-studies page)'] + [f'- {v["title"]} ({", ".join(x for x in (v["category"], v["market"]) if x)}): {v["summary"]}' for v in more]
    peer = [p for p in RESEARCH['papers'] if p['peer_reviewed']]
    parts += ['', '## Research behind SOMIN', f'- [SOMIN research: papers and talks]({BASE}/research/): SOMIN is built by seasoned marketers and an AI professor. Co-founder Prof. Aleks Farseev and the SOMIN team have published {len(peer)} peer-reviewed papers, demos and abstracts since {min(p["year"] for p in peer)}, at venues including AAAI, ACM Multimedia, SIGIR, WSDM and The Web Conference, and in ACM TOIS and ACM TIST.']
    parts += [f'- {p["venue_short"]} {p["year"]}: [{p["title"]}]({p["url"]}) ({p["authors"]})' for p in sorted(peer, key=lambda p: (p['tier'] != 'top', -p['year']))[:14]]
    parts += ['', '### Talks'] + [f'- {t["kind"]}, {t["event"]} ({t["date"][:4]}): [{t["title"]}]({t["url"]})' for t in sorted(RESEARCH['talks'], key=lambda t: t['date'], reverse=True) if t['language'] == 'English'][:10]
    parts += ['', '## Blog (latest first)'] + [f'- [{p["title"]}]({absu(url_for(p["slug"]))}): {p["description"]}' for p in posts]
    parts += ['', '## Pricing'] + [f'- {pl["name"]} ({pl["tagline"]}): US${pl["price"]:,} a month, US${pl["price"] * 0.9:,.2f} a month billed annually; {pl["seats"]}, {pl["brands"]} brands monitored, {pl["swaps"]} handle swaps a month.' for pl in PRICING['plans']]
    parts += [f'- {PRICING["enterprise"]["name"]}: custom multi-market private offers, handle pools (100+ brands), customer success manager.',
              f'- Add-ons: Analyst seat US${PRICING["addons"]["analyst_seat"]}/month, Specialist seat US${PRICING["addons"]["specialist_seat"]}/month, +10 brands US$190 (Light plans) or US$390 (Pro plans) a month. No overage fees. Full table: {BASE}/pricing/']
    authors = [m for m in pages if m.get('type') == 'author']
    if authors:
        parts += ['', '## Authors'] + [f'- [{m["title"].split(" | ")[0]}]({absu(url_for(m["slug"]))})' for m in authors]
    if localized:
        parts += ['', '## Languages',
                  f'{len(localized)} of the pages above also exist in {len(i18n.LANGS)} other languages at /<language>/<path>/ '
                  f'(for example {BASE}/ja/somin-strategy/), linked with hreflang; the language sitemaps list them. '
                  f'Legal documents are English only. Language home pages and sitemaps:']
        parts += [f'- {native} ({code}): {BASE}/{seg}/ · sitemap {BASE}/sitemap-{seg}.xml' for code, seg, hl, ogl, native, d in i18n.LANGS]
    parts += ['', '## Company & legal', f'- [About SOMIN]({BASE}/about/)', f'- [Our Vision]({BASE}/vision/)', f'- [Privacy Policy]({BASE}/privacy-policy/)', f'- [SaaS Agreement]({BASE}/saas-terms-general/)',
              '', '## Contact', f'- Book a call: {CAL_DEFAULT}', f'- Try SOMIN: {BASE}/try-somin/', f'- Free Claude plugin: {BASE}/marketing-mondays-plugin/', '- Platform login: https://cloud.somin.ai/auth/signin', '']
    (OUT / 'llms.txt').write_text('\n'.join(parts), encoding='utf-8')
    # llms-full.txt: plain-text bodies of the blog for answer engines
    full = ['# SOMIN — full text of articles', '']
    for p in posts:
        _, body = read_content(ROOT / 'content/blog' / (p['slug'].split('/')[-1] + '.html'))
        full += [f'## {p["title"]}', f'URL: {absu(url_for(p["slug"]))}', f'Author: {p["author"]} · Published: {p["published"][:10]}', '', strip_tags(body), '']
    (OUT / 'llms-full.txt').write_text('\n'.join(full), encoding='utf-8')


# ------------------------------------------------------------------ main
def main():
    global FOOTER_HTML
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / 'static', OUT)
    FOOTER_HTML = render_footer()

    pages = []
    superseded = {url_for(c['slug']) for c in CASE_PAGES.values()} | set(CFG.get('redirects', {}))
    for f in sorted((ROOT / 'content/pages').glob('*.html')):
        meta, body = read_content(f)
        if url_for(meta['slug']) in superseded:
            print(f'  skip {f.name}: {url_for(meta["slug"])} is now a composed case page or a redirect')
            continue
        body = expand_shortcodes(body)
        pages.append(meta)
        layout = meta.get('layout')
        if layout == 'fragment':
            build_fragment_page(meta, body)
        elif layout == 'doc':
            build_doc_page(meta, body)
        elif layout == 'native':
            build_native_page(meta, body)
        else:
            raise SystemExit(f'{f}: unknown layout {layout}')

    posts = []
    for f in sorted((ROOT / 'content/blog').glob('*.html')):
        meta, body = read_content(f)
        posts.append((meta, body))
    posts.sort(key=lambda x: x[0]['published'], reverse=True)
    post_metas = [m for m, _ in posts]
    for meta, body in posts:
        build_post(dict(meta), body, post_metas)
    build_blog_index(post_metas)
    build_rss(post_metas)

    manifest = build_lead_pages()
    pages += build_case_pages(manifest)
    pages.append(build_research_page())
    pages.append(build_pricing_page())
    pages.append(build_about_page(post_metas))
    pages += build_author_pages(post_metas)
    build_cases_hub(manifest)
    build_404()
    build_redirects()
    save_dates()
    # every indexable page (legal pages excepted) gets its own static copy in 16 languages, with hreflang everywhere
    rows, localized = i18n.build(OUT, BASE, [(p, PAGE_DATES.get(p) or lm, pr) for p, lm, pr in SITEMAP])
    n, maps = i18n.write_sitemaps(OUT, BASE, rows, PAGE_DATES)
    build_robots()
    build_llms(pages, post_metas, manifest, localized)
    (OUT / '.nojekyll').write_text('', encoding='utf-8')
    print(f'Built {len(pages)} pages + {len(posts)} posts → {OUT} (sitemaps: {n} URLs in {len(maps)} files, {len(localized)} pages × {len(i18n.LANGS)} languages)')


def apply_base_path(base):
    """Serve the site from a sub-path (e.g. GitHub's default https://<user>.github.io/<repo>/).

    Prefixes every root-relative URL that points at a file or folder of this site with `base`
    (HTML attributes, inline scripts/JSON, CSS url(), JS string literals) and marks every page noindex,
    because the preview duplicates somin.ai. Absolute URLs (canonical, Open Graph, JSON-LD, sitemap) stay on
    https://somin.ai. With a custom domain the base path is empty and nothing changes.
    """
    base = '/' + base.strip('/')
    names = {p.name for p in OUT.iterdir() if not p.name.startswith('.')}
    names |= {k.strip('/').split('/')[0] for k in CFG.get('not_migrated', {})}  # pages added later (e.g. the cases hub)
    names = sorted(names, key=len, reverse=True)
    alt = '|'.join(re.escape(n) for n in names)
    local = re.compile(r'(?<=["\'`(=,\s])/(?=(?:' + alt + r')(?:[/"\'`?#)\s,]|$))')
    root_attr = re.compile(r'\b((?:href|src|action|content)=")/(?=["?#])')
    robots = re.compile(r'<meta name="robots" content="[^"]*">')
    n = 0
    for f in OUT.rglob('*'):
        if not f.is_file() or f.suffix not in ('.html', '.css', '.js'):
            continue
        t = f.read_text(encoding='utf-8')
        new = local.sub(base + '/', t)
        if f.suffix == '.html':
            new = root_attr.sub(lambda m: m.group(1) + base + '/', new)
            new = new.replace('content="0; url=/"', f'content="0; url={base}/"')
            if robots.search(new):
                new = robots.sub('<meta name="robots" content="noindex,follow">', new)
            elif '<head>' in new:
                new = new.replace('<head>', '<head><meta name="robots" content="noindex,follow">', 1)
        if new != t:
            f.write_text(new, encoding='utf-8')
            n += 1
    print(f'Base path {base}/ applied to {n} files (preview build: all pages noindex)')


if __name__ == '__main__':
    main()
    _bp = os.environ.get('BASE_PATH', '')
    if '--base-path' in sys.argv:
        _i = sys.argv.index('--base-path')
        _bp = sys.argv[_i + 1] if _i + 1 < len(sys.argv) else ''
    if _bp.strip('/'):
        apply_base_path(_bp)
    if '--serve' in sys.argv:
        import http.server, functools, socketserver
        port = 8000
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        with socketserver.TCPServer(('', port), handler) as httpd:
            print(f'Serving http://localhost:{port}')
            httpd.serve_forever()
