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
import email.utils
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '_site'
CFG = json.loads((ROOT / 'site.config.json').read_text(encoding='utf-8'))
SITE = CFG['site']
BASE = SITE['url'].rstrip('/')
TRACKING_JS = (ROOT / 'static/assets/js/tracking.js').read_text(encoding='utf-8')
TRACK = json.loads(re.search(r'/\*CONFIG_START\*/(.*?)/\*CONFIG_END\*/', TRACKING_JS, re.S).group(1))
CASES = json.loads((ROOT / 'data/case-studies.json').read_text(encoding='utf-8'))
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
                f'<ul class="nav-sub" id="{sid}">{sub}</ul></li>')
        else:
            items.append(f'<li class="nav-item{current}"><a class="nav-link" {link_attrs(n)}>{E(n["label"])}</a></li>')
    cta = CFG['nav_cta']
    return f'''<header class="site-header">
  <div class="bar">
    <a class="site-logo" href="/" aria-label="SOMIN home"><img src="{SITE['logo']}" alt="SOMIN" width="70" height="12"></a>
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
    reviews = ''.join(f'<a href="{E(r["href"])}" rel="noopener" target="_blank">{E(r["label"])}</a>' for r in f['reviews'])
    return f'''<footer class="site-footer">
  <nav class="f-compare" aria-label="Comparisons"><ul>{compare}</ul></nav>
  <div class="f-main">
    <div class="f-brand"><a href="/" aria-label="SOMIN home"><img src="{SITE['logo']}" alt="SOMIN" width="84" height="15" loading="lazy"></a>
      <p>{E(SITE['tagline'].capitalize())}. Built in Singapore, used across 11+ markets.</p>
      <a class="btn btn--line btn--sm" href="{CAL_DEFAULT}" data-gtm-id="footer_book_a_call_btn">Book a call</a></div>
    {cols}
  </div>
  <div class="f-badges">{badges}<div class="f-reviews"><span>Reviews:</span>{reviews}</div></div>
  <div class="f-bottom"><div><span>© <span data-year>{dt.date.today().year}</span> SOMIN. All rights reserved.</span><span><a href="/privacy-policy/">Privacy Policy</a> · <a href="/vision/">Our Vision</a> · <a href="/sitemap.xml">Sitemap</a></span></div></div>
</footer>'''


HEADER_CACHE = {}
FOOTER_HTML = None


def org_node():
    return {"@type": "Organization", "@id": f"{BASE}/#organization", "name": "SOMIN", "legalName": "Somin Pte. Ltd.", "url": f"{BASE}/",
            "logo": {"@type": "ImageObject", "url": absu('/assets/img/brand/somin-logo-512.png'), "width": 512, "height": 512},
            "sameAs": SITE['same_as']}


def website_node():
    return {"@type": "WebSite", "@id": f"{BASE}/#website", "url": f"{BASE}/", "name": "SOMIN", "inLanguage": "en", "publisher": {"@id": f"{BASE}/#organization"}}


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
        f'<meta property="og:locale" content="{SITE["locale"]}">',
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
    if og_img and '/assets/img/og/' in og_img:
        tags += ['<meta property="og:image:width" content="1200">']
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
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Montserrat:wght@500;600;700;800;900&display=swap">',
        f'<link rel="stylesheet" href="/assets/css/site.css?v={BUILD_ID}">',
        f'<script src="/assets/js/tracking.js?v={BUILD_ID}"></script>',
        f'<script src="/assets/js/site.js?v={BUILD_ID}" defer></script>',
    ]
    for js in meta.get('jsonld', []):
        tags.append(f'<script type="application/ld+json">{js.strip()}</script>')
    if meta.get('_schema'):
        tags.append('<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": meta['_schema']}, ensure_ascii=False) + '</script>')
    layout = meta.get('layout', 'page')
    attrs = f' data-page-type="{E(meta.get("type", "page"))}" data-page-layout="{E(layout)}" data-content-group="{E(meta.get("group", meta.get("type", "page")))}"'
    if meta.get('lead_type'):
        attrs += f' data-lead-type="{E(meta["lead_type"])}"'
    noscript = ''
    head = '\n'.join(tags) + extra_head
    return f'''<!doctype html>
<html lang="en"{attrs}>
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


def toc_items(body, levels=('h2', 'h3'), only_numbered=False):
    out = []
    for m in re.finditer(r'<(' + '|'.join(levels) + r')\b[^>]*id="([^"]+)"[^>]*>(.*?)</\1>', body, re.S):
        t = strip_tags(m.group(3))
        if only_numbered and not re.match(r'^\d+\.', t):
            continue
        out.append((m.group(1), m.group(2), t))
    return out


# ------------------------------------------------------------------ layouts
def build_fragment_page(meta, body):
    path = url_for(meta['slug'])
    if meta.get('secret_button'):
        body += ('\n<a class="secret-button" href="/try-somin/" data-lead-form="trial" data-gtm-id="secret_button">'
                 'You found the secret button! As a reward for your curiosity, enjoy 14 days of SOMIN on us. '
                 'Just click and drop your details in the form below.</a>')
    meta.setdefault('group', meta.get('type'))
    write(path, page(meta, body, path))
    pr = '1.0' if path == '/' else ('0.9' if meta['type'] in ('solution', 'product') else '0.8')
    add_sitemap(path, meta.get('lastmod'), pr, meta.get('robots', 'index'))


def build_doc_page(meta, body):
    path = url_for(meta['slug'])
    is_legal = meta.get('type') == 'legal'
    body = add_heading_ids(body, ('h2', 'h3'))
    toc = toc_items(body, ('h2', 'h3'), only_numbered=is_legal) if is_legal else []
    toc_html = ''
    if len(toc) >= 3:
        toc_html = '<aside class="toc-dark" aria-label="On this page"><h2>On this page</h2><ol>' + ''.join(
            f'<li><a href="#{i}">{E(t)}</a></li>' for _, i, t in toc) + '</ol></aside>'
    eyebrow = 'Legal' if is_legal else 'Company'
    updated = f'<p class="updated">Last updated: {E(meta["updated"])}</p>' if meta.get('updated') else ''
    trail = [('Home', '/'), (meta.get('h1') or meta['title'].split(' | ')[0], path)]
    hero = f'''<section class="hero doc-hero"><div class="container">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li aria-current="page">{E(trail[-1][0])}</li></ol></nav>
  <p class="eyebrow">{eyebrow}</p>
  <h1>{E(meta.get('h1') or meta['title'])}</h1>{updated}
</div></section>'''
    wrap = f'<div class="container"><div class="doc-layout">{toc_html or "<div></div>"}<article class="doc">{body}</article></div></div>'
    if not toc_html:
        wrap = f'<div class="container"><div style="padding:56px 0 96px"><article class="doc" style="margin:0 auto">{body}</article></div></div>'
    node = {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta.get('h1') or meta['title'],
            "description": meta.get('description'), "isPartOf": {"@id": f"{BASE}/#website"}, "publisher": {"@id": f"{BASE}/#organization"}, "inLanguage": "en"}
    if meta.get('updated'):
        try:
            node['dateModified'] = dt.datetime.strptime(meta['updated'], '%d %b %Y').date().isoformat()
        except ValueError:
            pass
    meta['_schema'] = [org_node(), website_node(), node, breadcrumbs(trail)]
    meta.setdefault('group', 'company')
    write(path, page(meta, hero + wrap, path))
    add_sitemap(path, node.get('dateModified'), '0.3' if is_legal else '0.5', meta.get('robots', 'index'))


def build_native_page(meta, body):
    path = url_for(meta['slug'])
    trail = [('Home', '/'), (meta['title'].split(' | ')[0], path)]
    meta['_schema'] = [org_node(), website_node(),
                       {"@type": "WebPage", "@id": absu(path) + "#webpage", "url": absu(path), "name": meta['title'], "description": meta.get('description'),
                        "isPartOf": {"@id": f"{BASE}/#website"}, "inLanguage": "en"}, breadcrumbs(trail)]
    write(path, page(meta, body, path))
    add_sitemap(path, None, '0.6', meta.get('robots', 'index'))


AUTHORS = {
    'Prof. Aleks Farseev': {"@type": "Person", "@id": f"{BASE}/#aleks-farseev", "name": "Aleks Farseev", "honorificPrefix": "Prof.",
                            "jobTitle": "Co-Founder and CEO, SOMIN", "url": "https://farseev.com/",
                            "sameAs": ["https://www.linkedin.com/in/aiprof/", "https://scholar.google.com/citations?user=ZJW7F18AAAAJ", "https://farseev.com/"]},
}
AUTHOR_ROLE = {'Prof. Aleks Farseev': 'Co-Founder & CEO, SOMIN', 'Murtaza Hyder Magsi': 'SOMIN', 'Dr. Yang Qi': 'SOMIN', 'Da-Min You': 'SOMIN', 'SOMIN Team': 'SOMIN'}


def author_node(name):
    return AUTHORS.get(name) or {"@type": "Person", "name": name, "worksFor": {"@id": f"{BASE}/#organization"}} if name != 'SOMIN Team' else {"@id": f"{BASE}/#organization"}


def post_card(p, cls='card', feature=False):
    tag = p['tags'][0] if p['tags'] else 'Insights'
    data = f' data-post data-tags="{E("|".join(p["tags"]))}" data-search="{E((p["title"] + " " + p["description"] + " " + " ".join(p["tags"]) + " " + p["author"]).lower())}"'
    img = p['image'] if feature else p['image_card']
    meta = (f'<div class="meta byline"><span class="avatar" aria-hidden="true">{initials(p["author"])}</span><span class="who"><b>{E(p["author"])}</b>'
            f'<small><time datetime="{p["published"][:10]}">{fmt_date(p["published"])}</time> · {p["reading_minutes"]} min read</small></span></div>')
    if feature:
        return (f'<a class="feature" href="{url_for(p["slug"])}"><div class="feature-media"><img src="{img}" alt="" width="1600" height="1067" fetchpriority="high"></div>'
                f'<div class="feature-body"><span class="eyebrow">Latest · {E(tag)}</span><h2>{E(p["title"])}</h2><p>{E(p["description"])}</p>{meta}</div></a>')
    return (f'<a class="{cls}" href="{url_for(p["slug"])}"{data}><div class="card-media"><img src="{img}" alt="" width="720" height="480" loading="lazy" decoding="async"></div>'
            f'<div class="card-body"><span class="card-tag">{E(tag)}</span><h3>{E(p["title"])}</h3><p>{E(p["description"])}</p>{meta}</div></a>')


def build_post(meta, body, posts):
    path = url_for(meta['slug'])
    body = add_heading_ids(body, ('h2', 'h3'))
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
  <div class="meta"><span class="avatar" aria-hidden="true">{initials(a)}</span><span>{E(a)}</span><span class="dot"></span><time datetime="{meta['published'][:10]}">{fmt_date(meta['published'])}</time><span class="dot"></span><span>{meta['reading_minutes']} min read</span></div>
</div></section>
<div class="container post-cover"><img src="{meta['image']}" alt="{E('Illustration: ' + meta['title'])}" width="1600" height="1067" fetchpriority="high"></div>'''
    main = f'''<div class="post-wrap"><div class="container"><div class="post-grid-layout">
  <div><article class="prose" data-article>{body}</article>
    <div class="post-tags">{tags_html}</div>
    <div class="author-box"><span class="avatar" aria-hidden="true">{initials(a)}</span><div><strong>{E(a)}</strong><span>{E(AUTHOR_ROLE.get(a, 'SOMIN'))}</span></div></div>
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
    meta['seo_title'] = f"{meta['title']} | SOMIN Blog" if len(meta['title']) <= 52 else meta['title']
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
    write(path, page(meta, body, path))
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
def case_manifest():
    out = {}
    pages = {}
    for f in sorted((ROOT / 'content/pages').glob('*.html')):
        m, _ = read_content(f)
        pages[m['slug']] = m
    # human labels for case studies come from the navigation ("Consumer Electronics: Fujifilm UK" -> "Fujifilm UK")
    nav_labels = {}
    for n in CFG['nav']:
        for c in n.get('children', []):
            nav_labels[c['href'].strip('/')] = (c['label'].split(':', 1)[-1].strip(), c['label'].split(':', 1)[0].strip() if ':' in c['label'] else '')
    extra = {'case': ('Miraflora Wagyu × GWI', 'eCommerce')}
    for key, it in CASES['items'].items():
        pm = pages.get(key, {})
        label, sector = nav_labels.get(key) or extra.get(key) or (None, '')
        title = label or re.sub(r'\.pdf$', '', it['file'], flags=re.I).replace('_', ' ').title()
        if sector:
            it = dict(it, category=sector)
        out[key] = {'title': title, 'download': f'https://drive.google.com/uc?export=download&id={it["drive_id"]}',
                    'view': f'https://drive.google.com/file/d/{it["drive_id"]}/view', 'size_mb': it['size_mb'],
                    'page': it.get('page'), 'cover': pm.get('og_image'), 'category': it.get('category')}
    return out


def build_lead_pages():
    manifest = case_manifest()
    # remove internals the browser does not need
    public = {k: {kk: v[kk] for kk in ('title', 'size_mb', 'page', 'cover')} for k, v in manifest.items()}
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
    picks = [v for k, v in manifest.items() if v['page'] and k != 'case'][:7]
    cards = ''.join(f'<a class="mini" href="{E(v["page"])}" data-cs-more><span>{E(v["category"] or "Case study")}</span><strong>{E(v["title"])}</strong></a>' for v in picks)
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
        <p class="dl-note">The link stays on this page for this browser session. Large decks can take a few seconds to start downloading.</p>
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
<section class="section" style="padding-top:0"><div class="container" style="max-width:980px"><h2 class="section-title">More SOMIN case studies</h2><div class="mini-grid">{cards}</div></div></section>
<script type="application/json" id="cs-manifest">{json.dumps({k: dict(public[k], download=v['download'], view=v['view']) for k, v in manifest.items()}, ensure_ascii=False)}</script>'''
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
    return manifest


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
        rows.append(f'<url><loc>{absu(path)}</loc><lastmod>{(lastmod or TODAY)[:10]}</lastmod><priority>{pr}</priority></url>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(rows) + '\n</urlset>\n'
    (OUT / 'sitemap.xml').write_text(xml, encoding='utf-8')
    return len(rows)


def build_robots():
    txt = f'''# SOMIN — {BASE}
User-agent: *
Allow: /
Disallow: /thank-you-trial-somin/
Disallow: /thank-you-case-study/

# AI assistants and answer engines are welcome to read and cite this site.
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Applebot-Extended
Allow: /

Sitemap: {BASE}/sitemap.xml
'''
    (OUT / 'robots.txt').write_text(txt, encoding='utf-8')


def build_llms(pages, posts):
    by = lambda t: [m for m in pages if m.get('type') == t and m.get('robots', 'index').startswith('index')]
    def line(m):
        return f'- [{m["title"].split(" | ")[0]}]({absu(url_for(m["slug"]))}): {m.get("description") or ""}'
    home = next((m for m in pages if m['slug'] == ''), None)
    parts = [f'# SOMIN', '', f'> {SITE["description"]}', '',
             'SOMIN (somin.ai, legal name Somin Pte. Ltd., Singapore) is an agentic AI marketing-intelligence platform. Its SOMONITOR engine reads competitor ads, posts and creators plus live audience conversation, finds category whitespace, and produces pre-scored propositions, briefs and on-brand creative concepts for brands, agencies and creator programmes across 11+ markets in APAC, MENA and Europe. Recognised as a Gartner Cool Vendor in Marketing AI and a Zapier agentic-AI partner.', '',
             '## Key pages']
    if home:
        parts.append(f'- [Home]({BASE}/): {home.get("description")}')
    parts += [line(m) for m in by('solution')]
    parts += ['', '## AI agents and products'] + [line(m) for m in by('product')]
    parts += ['', '## Comparisons'] + [line(m) for m in by('comparison')]
    parts += ['', '## Case studies'] + [line(m) for m in by('case_study')]
    parts += ['', '## Blog (latest first)'] + [f'- [{p["title"]}]({absu(url_for(p["slug"]))}): {p["description"]}' for p in posts]
    parts += ['', '## Company & legal', f'- [Our Vision]({BASE}/vision/)', f'- [Privacy Policy]({BASE}/privacy-policy/)', f'- [SaaS Agreement]({BASE}/saas-terms-general/)',
              '', '## Contact', f'- Book a call: {CAL_DEFAULT}', f'- Try SOMIN: {BASE}/try-somin/', '- Platform login: https://cloud.somin.ai/auth/signin', '']
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
    for f in sorted((ROOT / 'content/pages').glob('*.html')):
        meta, body = read_content(f)
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
    for f in (ROOT / 'content/blog').glob('*.html'):
        meta, body = read_content(f)
        posts.append((meta, body))
    posts.sort(key=lambda x: x[0]['published'], reverse=True)
    post_metas = [m for m, _ in posts]
    for meta, body in posts:
        build_post(dict(meta), body, post_metas)
    build_blog_index(post_metas)
    build_rss(post_metas)

    build_lead_pages()
    build_404()
    build_redirects()
    n = build_sitemap()
    build_robots()
    build_llms(pages, post_metas)
    (OUT / '.nojekyll').write_text('', encoding='utf-8')
    print(f'Built {len(pages)} pages + {len(posts)} posts → {OUT} (sitemap: {n} URLs)')


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
