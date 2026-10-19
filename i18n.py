"""Static per-language copies of every indexable page (Python standard library only).

somin.ai is published in English plus 16 languages. Every indexable English page except the legal documents gets its own
static, indexable copy at /<lang>/<path>/ (for example /ja/somin-strategy/), with its own canonical, hreflang alternates for
all 17 versions plus x-default, translated <title>, meta description, Open Graph and JSON-LD, localized internal links and a
language switcher. There is no in-page (JavaScript) translation: one URL = one language, which is what search and answer
engines need.

How it works
- build.py renders the English site first. This module then reads each English page from _site/, splits its visible text into
  segments (a block of text with its inline markup turned into placeholders like <g1>…</g1>, <x2/> and numbers into {1}),
  looks every segment up in the translation memory and writes the translated copy.
- Translation memory: data/i18n/<lang>.json maps a segment key (sha1 of the English segment, 16 hex chars) to its
  translation. data/i18n/source.json maps the same keys to the English text, so a translator (human or AI) can see what each
  key means. A segment with no translation stays in English, so a new or edited English sentence never breaks the build;
  `python3 scripts/i18n_todo.py` lists what still needs translating per language.
- Kept in English on purpose: legal pages (privacy policy, SaaS terms), verbatim third-party reviews, code, brand wordmarks.
"""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
I18N_DIR = ROOT / 'data/i18n'

# code, path segment, hreflang, og:locale, native name, text direction (same set and order as the home page language menu)
LANGS = [
    ('zh-Hans', 'zh-hans', 'zh-Hans', 'zh_CN', '简体中文', 'ltr'),
    ('zh-Hant', 'zh-hant', 'zh-Hant', 'zh_TW', '繁體中文', 'ltr'),
    ('ja', 'ja', 'ja', 'ja_JP', '日本語', 'ltr'),
    ('ko', 'ko', 'ko', 'ko_KR', '한국어', 'ltr'),
    ('th', 'th', 'th', 'th_TH', 'ไทย', 'ltr'),
    ('vi', 'vi', 'vi', 'vi_VN', 'Tiếng Việt', 'ltr'),
    ('id', 'id', 'id', 'id_ID', 'Bahasa Indonesia', 'ltr'),
    ('ms', 'ms', 'ms', 'ms_MY', 'Bahasa Melayu', 'ltr'),
    ('hi', 'hi', 'hi', 'hi_IN', 'हिन्दी', 'ltr'),
    ('fil', 'fil', 'tl', 'tl_PH', 'Filipino', 'ltr'),
    ('es', 'es', 'es', 'es_ES', 'Español', 'ltr'),
    ('fr', 'fr', 'fr', 'fr_FR', 'Français', 'ltr'),
    ('de', 'de', 'de', 'de_DE', 'Deutsch', 'ltr'),
    ('pt', 'pt', 'pt', 'pt_BR', 'Português', 'ltr'),
    ('ar', 'ar', 'ar', 'ar_AR', 'العربية', 'rtl'),
    ('ru', 'ru', 'ru', 'ru_RU', 'Русский', 'ltr'),
]
LANG = {l[0]: l for l in LANGS}
SEGS = {l[1] for l in LANGS}
SEG_OF = {l[0]: l[1] for l in LANGS}
MIN_COVERAGE = 0.97     # share of a page's segments a language must have before that page gets a /<lang>/ copy

# ------------------------------------------------------------------ translation memory
def seg_key(src):
    return hashlib.sha1(src.encode('utf-8')).hexdigest()[:16]


def load_tm(code):
    p = I18N_DIR / f'{SEG_OF[code]}.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


# ------------------------------------------------------------------ tokenizer
TAG_RE = re.compile(r'<!--.*?-->|<![^>]*>|<(/?)([a-zA-Z][a-zA-Z0-9:-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>', re.S)
RAW_ELEMENTS = {'script', 'style', 'svg', 'textarea', 'noscript', 'template', 'math'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
INLINE = {'a', 'abbr', 'b', 'bdi', 'bdo', 'br', 'cite', 'del', 'dfn', 'em', 'i', 'img', 'ins', 'mark', 'q', 's', 'small',
          'span', 'strong', 'sub', 'sup', 'u', 'wbr', 'time', 'code', 'kbd', 'samp', 'var', 'data', 'abbr'}
OPAQUE = {'time', 'code', 'kbd', 'samp', 'var'}          # kept as one unit, never translated inside a sentence
NOTRANSLATE_TAGS = {'pre', 'code', 'kbd', 'samp'}
NOTRANSLATE_CLASSES = ('notranslate', 'rv-card', 'rv-badge', 'rv-badges', 'wm-logo', 'locale-nav', 'lang-switch', 'wm ', 'se-lang')
TRANSLATABLE_ATTRS = ('alt', 'title', 'aria-label', 'placeholder')
LETTER = re.compile(r'[^\W\d_]', re.U)
NUM_RE = re.compile(r'\d+(?:[.,:]\d+)*')
PH_RE = re.compile(r'</?g\d+>|<x\d+/>|\{\d+\}')
DONT = {'somin', 'somonitor', 'g2', 'capterra', 'claude', 'mcp', 'linkedin', 'x', 'meta', 'google', 'tiktok', 'instagram',
        'facebook', 'youtube', 'threads', 'mindfuse', 'chatgpt', 'gemini', 'perplexity', 'figma', 'canva', 'zapier', 'gwi',
        'nielsen', 'euromonitor', 'milieu', 'hubspot', 'salesforce', 'typeform', 'calendly', 'ok', 'faq', 'apac', 'mena',
        'sea', 'ai', 'seo', 'aeo', 'geo', 'roas', 'ctr', 'cpm', 'kpi', 'kpis', 'b2b', 'b2c', 'sg', 'en'}


def tokenize(s):
    """[(kind, raw, name, closing, attrs)] with kind in text/tag/raw. Raw elements (script, style, svg…) are one token."""
    out, i, n = [], 0, len(s)
    while i < n:
        m = TAG_RE.search(s, i)
        if not m:
            out.append(('text', s[i:], None, False, ''))
            break
        if m.start() > i:
            out.append(('text', s[i:m.start()], None, False, ''))
        if m.group(2) is None:                     # comment / doctype
            out.append(('raw', m.group(0), None, False, ''))
            i = m.end()
            continue
        name = m.group(2).lower()
        closing = bool(m.group(1))
        if not closing and name in RAW_ELEMENTS:
            end = re.compile(r'</' + name + r'\s*>', re.I).search(s, m.end())
            j = end.end() if end else n
            out.append(('raw', s[m.start():j], name, False, ''))
            i = j
            continue
        out.append(('tag', m.group(0), name, closing, m.group(3) or ''))
        i = m.end()
    return out


def _attr(attrs, name):
    m = re.search(r'(?:^|\s)' + re.escape(name) + r'\s*=\s*("([^"]*)"|\'([^\']*)\')', attrs)
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(3)


def _is_notranslate(name, attrs):
    if name in NOTRANSLATE_TAGS:
        return True
    if _attr(attrs, 'translate') == 'no' or _attr(attrs, 'data-i18n') is not None:
        return True
    cls = _attr(attrs, 'class')
    if cls:
        c = ' ' + cls + ' '
        return any(f' {x.strip()} ' in c for x in NOTRANSLATE_CLASSES)
    return False


# ------------------------------------------------------------------ segments
def _norm(text):
    return ' '.join(text.split())


def mask_numbers(s):
    nums = []

    def rep(m):
        nums.append(m.group(0))
        return '{' + str(len(nums)) + '}'
    # only outside placeholders
    parts = re.split(r'(</?g\d+>|<x\d+/>)', s)
    out = [p if PH_RE.fullmatch(p or '') else NUM_RE.sub(rep, p) for p in parts]
    return ''.join(out), nums


def worth_translating(src):
    plain = PH_RE.sub(' ', src)
    if not LETTER.search(plain):
        return False
    words = plain.strip().lower()
    if words in DONT:
        return False
    if re.fullmatch(r'(https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+', plain.strip()):
        return False
    return True


class Segmenter:
    """Walks one HTML document. mode 'extract' collects segments; mode 'apply' returns the translated document."""

    def __init__(self, tm=None, collect=None, stats=None):
        self.tm = tm or {}
        self.collect = collect          # dict key -> source  (extract mode)
        self.stats = stats if stats is not None else {'seg': 0, 'hit': 0}

    # ---- one segment
    def translate(self, src):
        """src: normalized text with <gN>/<xN/> placeholders (already unescaped). Returns translated text with numbers restored or None."""
        if not worth_translating(src):
            return None
        masked, nums = mask_numbers(src)
        k = seg_key(masked)
        self.stats['seg'] += 1
        if self.collect is not None:
            self.collect.setdefault(k, masked)
            return None
        tr = self.tm.get(k)
        if not tr or not valid(masked, tr):
            return None
        self.stats['hit'] += 1
        return re.sub(r'\{(\d+)\}', lambda m: nums[int(m.group(1)) - 1] if 0 < int(m.group(1)) <= len(nums) else m.group(0), tr)

    def plain(self, text):
        """Translate a plain-text value (attribute, meta). Returns new text or original."""
        t = _norm(html.unescape(text))
        if not t:
            return text
        tr = self.translate(t)
        return tr if tr is not None else None

    # ---- document
    def run(self, doc):
        toks = tokenize(doc)
        out, stack, run = [], [], []
        nt_depth = None      # stack depth at which a notranslate container opened

        def flush():
            if run:
                out.append(self._flush(run))
                run.clear()

        def swallow(i, name):
            """Collect an element from its opening tag to the matching close as one opaque inline unit."""
            j, depth, buf = i + 1, 1, [toks[i][1]]
            while j < len(toks) and depth:
                k2, r2, n2, c2, a2 = toks[j]
                buf.append(r2)
                if k2 == 'tag' and n2 == name and not (n2 in VOID or r2.endswith('/>')):
                    depth += -1 if c2 else 1
                j += 1
            return j, ''.join(buf)

        i = 0
        while i < len(toks):
            kind, raw, name, closing, attrs = toks[i]
            if nt_depth is not None:                     # inside a notranslate container: copy as is
                out.append(raw)
                if kind == 'tag':
                    if closing:
                        self._pop(stack, name)
                        if len(stack) < nt_depth:
                            nt_depth = None
                    elif name not in VOID and not raw.endswith('/>'):
                        stack.append(name)
                i += 1
                continue
            if kind == 'raw':
                flush(); out.append(raw); i += 1; continue
            if kind == 'text':
                run.append(toks[i]); i += 1; continue
            if not closing:
                raw = self._attrs(raw, attrs)
                toks[i] = (kind, raw, name, closing, attrs)
            is_void = name in VOID or raw.endswith('/>')
            if name in INLINE:
                if not closing and not is_void and (name in OPAQUE or _is_notranslate(name, attrs)):
                    j, whole = swallow(i, name)
                    run.append(('opaque', whole, name, False, attrs))
                    i = j
                    continue
                run.append(toks[i]); i += 1; continue
            # block-level tag
            flush()
            out.append(raw)
            if closing:
                self._pop(stack, name)
            elif not is_void:
                stack.append(name)
                if _is_notranslate(name, attrs):
                    nt_depth = len(stack)
            i += 1
        flush()
        return ''.join(out)

    @staticmethod
    def _pop(stack, name):
        for k in range(len(stack) - 1, -1, -1):
            if stack[k] == name:
                del stack[k:]
                return

    def _attrs(self, raw, attrs):
        if not any(a + '=' in attrs or a + ' =' in attrs for a in TRANSLATABLE_ATTRS):
            return raw
        for a in TRANSLATABLE_ATTRS:
            v = _attr(attrs, a)
            if not v:
                continue
            tr = self.plain(v)
            if tr is not None and tr != v:
                raw = re.sub(r'(\s' + re.escape(a) + r'\s*=\s*)("[^"]*"|\'[^\']*\')', lambda m: m.group(1) + '"' + html.escape(tr, quote=True) + '"', raw, count=1)
        return raw

    def _flush(self, run):
        raws = ''.join(t[1] for t in run)
        if not any(t[0] == 'text' and LETTER.search(html.unescape(t[1])) for t in run):
            return raws
        # balanced inline markup?
        st, ok = [], True
        for t in run:
            if t[0] == 'tag' and t[2] not in VOID and not t[1].endswith('/>'):
                if t[3]:
                    if st and st[-1] == t[2]:
                        st.pop()
                    else:
                        ok = False
                        break
                else:
                    st.append(t[2])
        if st:
            ok = False
        if not ok:   # fall back: translate each text node on its own
            return ''.join(self._text_only(t) if t[0] == 'text' else t[1] for t in run)
        # leading / trailing whitespace stays outside the segment
        lead = re.match(r'\s*', html.unescape(run[0][1])).group(0) if run[0][0] == 'text' else ''
        trail = re.search(r'\s*$', html.unescape(run[-1][1])).group(0) if run[-1][0] == 'text' else ''
        parts, ph, n, open_ids = [], {}, 0, []
        for t in run:
            if t[0] == 'text':
                parts.append(html.unescape(t[1]))
            elif t[0] == 'opaque' or t[2] in VOID or t[1].endswith('/>'):
                n += 1
                ph[f'<x{n}/>'] = t[1]
                parts.append(f'<x{n}/>')
            elif not t[3]:
                n += 1
                open_ids.append(n)
                ph[f'<g{n}>'] = t[1]
                parts.append(f'<g{n}>')
            else:
                gid = open_ids.pop()
                ph[f'</g{gid}>'] = t[1]
                parts.append(f'</g{gid}>')
        src = _norm(''.join(parts))
        # a segment wrapped whole in one inline element ("<g1>Read more</g1>") is translated without the wrapper,
        # so the same words share one translation wherever they appear
        wrap_l, wrap_r = '', ''
        while True:
            m = re.fullmatch(r'<g(\d+)>(.*)</g\1>', src, re.S)
            if not m or f'<g{m.group(1)}>' in m.group(2):
                break
            wrap_l, wrap_r = wrap_l + f'<g{m.group(1)}>', f'</g{m.group(1)}>' + wrap_r
            src = m.group(2).strip()
        tr = self.translate(src)
        if tr is None:
            return raws
        tr = wrap_l + tr + wrap_r
        rebuilt = []
        for piece in re.split(r'(</?g\d+>|<x\d+/>)', tr):
            if piece in ph:
                rebuilt.append(ph[piece])
            elif piece:
                rebuilt.append(html.escape(piece, quote=False))
        return lead + ''.join(rebuilt) + trail

    def _text_only(self, t):
        raw = t[1]
        txt = html.unescape(raw)
        core = _norm(txt)
        if not core:
            return raw
        tr = self.translate(core)
        if tr is None:
            return raw
        lead = re.match(r'\s*', txt).group(0)
        trail = re.search(r'\s*$', txt).group(0)
        return lead + html.escape(tr, quote=False) + trail


def valid(src, tr):
    """A translation is usable when it keeps exactly the same placeholders as its source."""
    a = sorted(PH_RE.findall(src))
    b = sorted(PH_RE.findall(tr))
    if a != b:
        return False
    # every opened group must close after it opens
    for g in set(re.findall(r'<g(\d+)>', tr)):
        if tr.find(f'<g{g}>') > tr.find(f'</g{g}>'):
            return False
    return True


# ------------------------------------------------------------------ dates
MONTHS = {
    'zh-Hans': None, 'zh-Hant': None, 'ja': None, 'ko': None,
    'th': 'มกราคม กุมภาพันธ์ มีนาคม เมษายน พฤษภาคม มิถุนายน กรกฎาคม สิงหาคม กันยายน ตุลาคม พฤศจิกายน ธันวาคม',
    'vi': None,
    'id': 'Januari Februari Maret April Mei Juni Juli Agustus September Oktober November Desember',
    'ms': 'Januari Februari Mac April Mei Jun Julai Ogos September Oktober November Disember',
    'hi': 'जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर',
    'fil': 'Enero Pebrero Marso Abril Mayo Hunyo Hulyo Agosto Setyembre Oktubre Nobyembre Disyembre',
    'es': 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre',
    'fr': 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre',
    'de': 'Januar Februar März April Mai Juni Juli August September Oktober November Dezember',
    'pt': 'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro',
    'ar': 'يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر',
    'ru': 'января февраля марта апреля мая июня июля августа сентября октября ноября декабря',
}


def fmt_date(code, y, m, d):
    if code in ('zh-Hans', 'zh-Hant', 'ja'):
        return f'{y}年{m}月{d}日'
    if code == 'ko':
        return f'{y}년 {m}월 {d}일'
    if code == 'vi':
        return f'{d} tháng {m}, {y}'
    names = MONTHS[code].split()
    mn = names[m - 1]
    if code in ('es', 'pt'):
        return f'{d} de {mn} de {y}'
    if code == 'de':
        return f'{d}. {mn} {y}'
    if code == 'ru':
        return f'{d} {mn} {y} г.'
    if code == 'fil':
        return f'{mn} {d}, {y}'
    return f'{d} {mn} {y}'


def localize_dates(doc, code):
    def rep(m):
        y, mo, d = (int(x) for x in m.group(2).split('-'))
        return f'{m.group(1)}{fmt_date(code, y, mo, d)}</time>'
    return re.sub(r'(<time\b[^>]*\bdatetime="(\d{4}-\d{2}-\d{2})[^"]*"[^>]*>)[^<]*</time>', rep, doc)


# ------------------------------------------------------------------ links, head, schema
def localize_links(doc, seg, url_map):
    """Root-relative hrefs to pages that have a copy in this language point at that copy."""
    def rep(m):
        url = m.group(2)
        path, sep, rest = url.partition('#')
        path, qsep, q = path.partition('?')
        if not path.startswith('/') or path.startswith('//'):
            return m.group(0)
        first = path.strip('/').split('/')[0]
        if first in SEGS:
            return m.group(0)
        if path in url_map:
            new = url_map[path] + (qsep + q if qsep else '') + (sep + rest if sep else '')
            return f'{m.group(1)}{new}"'
        return m.group(0)
    return re.sub(r'(\bhref=")([^"]*)"', rep, doc)


def faq_from_body(body, page_url):
    qa = []
    strip = lambda s: html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()
    for m in re.finditer(r'<details\b[^>]*>\s*<summary\b[^>]*>(.*?)</summary>(.*?)</details>', body, re.S):
        q, a = strip(m.group(1)), strip(m.group(2))
        if q and a and len(a) > 20:
            qa.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    if len(qa) < 2:
        return None
    return {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": qa}


CANON_TYPES = {'Organization', 'WebSite', 'SoftwareApplication', 'Person', 'Brand', 'Corporation'}
KEEP_FRAGS = {'blog', 'person'}
LANG_TYPES = {'WebPage', 'CollectionPage', 'AboutPage', 'ProfilePage', 'FAQPage', 'Article', 'BlogPosting', 'ItemList',
              'DefinedTermSet', 'Dataset', 'HowTo', 'ContactPage'}
TEXT_KEYS = ('name', 'headline', 'description', 'alternativeName', 'caption', 'articleSection', 'text')


def localize_jsonld(txt, base, en_path, loc_path, code, url_map, seg, body):
    data = json.loads(txt)
    graph = data.get('@graph', [data]) if isinstance(data, dict) else data

    def u(s):
        if not isinstance(s, str) or not s.startswith(base + '/'):
            return s
        rest = s[len(base):]
        path, _, frag = rest.partition('#')
        if path == '/':
            return base + url_map['/'] if (not frag and '/' in url_map) else s
        if frag in KEEP_FRAGS:
            return s
        if path in url_map:
            return base + url_map[path] + ('#' + frag if frag else '')
        return s

    def walk(v, translate=True):
        if isinstance(v, dict):
            if v.get('@type') in CANON_TYPES and len(v) > 1:
                return v
            out = {}
            for k, x in v.items():
                if k in TEXT_KEYS and isinstance(x, str) and translate:
                    tr = seg.plain(x)
                    out[k] = tr if tr else x
                else:
                    out[k] = walk(x, translate)
            return out
        if isinstance(v, list):
            return [walk(x, translate) for x in v]
        return u(v)

    out = []
    page_url = base + loc_path
    for n in graph:
        t = n.get('@type')
        if t in CANON_TYPES:
            out.append(n)
            continue
        if t == 'FAQPage':
            fq = faq_from_body(body, page_url)
            if fq:
                fq['inLanguage'] = code
                out.append(fq)
            continue
        en_id = n.get('@id')
        m = walk(n)
        if t in LANG_TYPES:
            m['inLanguage'] = code
            if en_id and isinstance(en_id, str) and en_id.startswith(base + en_path + '#'):
                m['translationOfWork'] = {'@id': en_id}
        out.append(m)
    return json.dumps({"@context": "https://schema.org", "@graph": out}, ensure_ascii=False)


def head_meta(doc, seg):
    """Translate <title> and the description / Open Graph / Twitter text in <head>."""
    def t_title(m):
        tr = seg.plain(m.group(2))
        return m.group(1) + (html.escape(tr, quote=False) if tr else m.group(2)) + m.group(3)
    doc = re.sub(r'(<title>)(.*?)(</title>)', t_title, doc, count=1, flags=re.S)

    def t_meta(m):
        tr = seg.plain(m.group(2))
        return m.group(1) + (html.escape(tr, quote=True) if tr else m.group(2)) + m.group(3)
    doc = re.sub(r'(<meta (?:name|property)="(?:description|og:title|og:description|og:image:alt|twitter:title|twitter:description)" content=")([^"]*)(")', t_meta, doc)
    return doc


def alternates_html(group, base):
    return ''.join(f'<link rel="alternate" hreflang="{hl}" href="{base}{p}">' for hl, p in group)


def switcher_html(current_code, group_links):
    """Header language menu: a <details> list of plain links (works without JavaScript, crawlable)."""
    names = [('en', 'English')] + [(l[0], l[4]) for l in LANGS]
    cur = dict(names).get(current_code, 'English')
    short = 'EN' if current_code == 'en' else LANG[current_code][1].split('-')[0].upper()
    items = []
    for code, native in names:
        href = group_links.get(code)
        if not href:
            continue
        hl = 'en' if code == 'en' else LANG[code][2]
        attr = ' aria-current="true"' if code == current_code else ''
        items.append(f'<li><a href="{href}" hreflang="{hl}" lang="{code}"{attr}>{html.escape(native)}</a></li>')
    globe = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9" fill="none" '
             'stroke="currentColor" stroke-width="1.6"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" '
             'fill="none" stroke="currentColor" stroke-width="1.6"/></svg>')
    return (f'<details class="lang-switch notranslate" translate="no"><summary aria-label="Language: {html.escape(cur)}">{globe}<span>{short}</span></summary>'
            f'<ul class="lang-menu">{"".join(items)}</ul></details>')


# ------------------------------------------------------------------ in-page dictionaries (home + four solution pages)
def page_dictionary(doc, code):
    """The home page and four solution pages carry gzip+base64 dictionaries keyed by data-i18n (written for an older in-page
    switcher). The builder now uses them only to pre-render each language's own page; returns {key: text} or None."""
    import base64, gzip
    for m in re.finditer(r'"([A-Za-z0-9+/=]{400,})"', doc):
        try:
            d = json.loads(gzip.decompress(base64.b64decode(m.group(1))))
        except Exception:
            continue
        if isinstance(d, dict) and 'k' in d and 'v' in d and code in d['v']:
            return dict(zip(d['k'], d['v'][code]))
        if isinstance(d, dict) and code in d and isinstance(d[code], dict):
            return d[code]
    return None


def apply_dictionary(doc, dct):
    """Server-side twin of the old applyLang(): each [data-i18n] element's content becomes the translated text."""
    tag_re = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
    out, i = [], 0
    while True:
        m = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-i18n="([^"]+)"[^>]*>', doc[i:])
        if not m:
            out.append(doc[i:])
            break
        start, open_end, tag, key = i + m.start(), i + m.end(), m.group(1).lower(), m.group(2)
        if tag in VOID:
            out.append(doc[i:open_end]); i = open_end; continue
        depth, j, cs, ce = 1, open_end, None, None
        while True:
            t = tag_re.search(doc, j)
            if not t:
                break
            if t.group(2).lower() == tag and not t.group(3).rstrip().endswith('/'):
                depth += -1 if t.group(1) else 1
                if depth == 0:
                    cs, ce = t.start(), t.end()
                    break
            j = t.end()
        if cs is None:
            out.append(doc[i:open_end]); i = open_end; continue
        txt = dct.get(key)
        out.append(doc[i:open_end])
        out.append(html.escape(txt, quote=False) if txt is not None else doc[open_end:cs])
        out.append(doc[cs:ce])
        i = ce
    return ''.join(out)


# ------------------------------------------------------------------ the build stage
def _read(p):
    return p.read_text(encoding='utf-8')


def page_file(out_dir, path):
    return out_dir / path.lstrip('/') / 'index.html' if path.endswith('/') else out_dir / path.lstrip('/')


def localizable(doc):
    if 'http-equiv="refresh"' in doc:
        return False
    if 'data-page-type="legal"' in doc:
        return False
    m = re.search(r'<meta name="robots" content="([^"]+)"', doc)
    return not (m and m.group(1).startswith('noindex'))


def set_html_attrs(doc, code):
    l = LANG.get(code)
    def rep(m):
        attrs = re.sub(r'\s(lang|dir|data-locale)="[^"]*"', '', m.group(1))
        extra = f' lang="{code}"'
        if l and l[5] == 'rtl':
            extra += ' dir="rtl"'
        if code != 'en':
            extra += f' data-locale="{code}"'
        return f'<html{extra}{attrs}>'
    return re.sub(r'<html\b([^>]*)>', rep, doc, count=1)


def localize_head(doc, base, en_path, loc_path, code, group, seg, url_map):
    head_end = doc.find('</head>')
    head, rest = doc[:head_end], doc[head_end:]
    head = head_meta(head, seg)
    head = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{base}{loc_path}">', head, count=1)
    head = re.sub(r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{base}{loc_path}">', head, count=1)
    ogl = LANG[code][3]
    alts = ''.join(f'<meta property="og:locale:alternate" content="{l[3]}">' for l in LANGS if l[0] != code) + '<meta property="og:locale:alternate" content="en_US">'
    head = re.sub(r'<meta property="og:locale" content="[^"]*">', f'<meta property="og:locale" content="{ogl}">{alts}', head, count=1)
    head = re.sub(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">', '', head)
    head = head.replace('<meta name="theme-color"', alternates_html(group, base) + '<meta name="theme-color"', 1)
    body = rest

    def ld(m):
        try:
            return m.group(1) + localize_jsonld(m.group(2), base, en_path, loc_path, code, url_map, seg, body) + m.group(3)
        except Exception:
            return m.group(0)
    head = re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)', ld, head, flags=re.S)
    return head + rest


def build(out_dir, base, entries, log=print):
    """entries: [(path, lastmod, priority)] for every indexable English URL in build order (home locale copies included).
    Writes all language copies, inserts hreflang + language switchers, and returns the sitemap rows
    [(path, lastmod, priority, lang, group)] for every language."""
    out_dir = Path(out_dir)
    seen, en_rows = set(), []
    for path, lastmod, pr in entries:
        if path in seen:
            continue
        seen.add(path)
        if path.strip('/').split('/')[0] in SEGS:
            continue                                   # /ja/ … home copies written by build.py; handled below
        en_rows.append((path, lastmod, pr))
    loc_paths, skip = [], []
    for path, lastmod, pr in en_rows:
        f = page_file(out_dir, path)
        if f.exists() and localizable(_read(f)):
            loc_paths.append(path)
        else:
            skip.append(path)
    tms = {code: load_tm(code) for code, *_ in LANGS}
    # A page gets a language copy only when that language's translation memory covers the page (MIN_COVERAGE of its
    # segments). Pages still being translated stay English-only — no half-English /<lang>/ copies, no hreflang to them.
    avail, partial = {}, []
    for path in loc_paths:
        if path == '/':
            avail[path] = {l[0] for l in LANGS}       # /<lang>/ home copies always exist (hero dictionary)
            continue
        keys = extract(out_dir, [path])
        langs = set()
        for code, *_ in LANGS:
            tm = tms[code]
            hit = sum(1 for k, s in keys.items() if k in tm and valid(s, tm[k]))
            if not keys or hit / len(keys) >= MIN_COVERAGE:
                langs.add(code)
        avail[path] = langs
    for path in [p for p in loc_paths if not avail[p]]:
        loc_paths.remove(path)
        skip.append(path)
        partial.append(path)
    url_map = {code: {p: f'/{seg}{p}' for p in loc_paths if code in avail[p]} for code, seg, *_ in LANGS}
    groups = {p: [('en', p)] + [(l[2], f'/{l[1]}{p}') for l in LANGS if l[0] in avail[p]] + [('x-default', p)] for p in loc_paths}
    links_for = lambda p: {'en': p, **{l[0]: f'/{l[1]}{p}' for l in LANGS if l[0] in avail[p]}}
    home_links = {'en': '/', **{l[0]: f'/{l[1]}/' for l in LANGS}}
    rows = []
    report = {}
    meta = {p: (lm, pr) for p, lm, pr in en_rows}
    for path in loc_paths:
        f = page_file(out_dir, path)
        en_doc = _read(f)
        group = groups[path]
        for code, seg_name, hl, ogl, native, direction in LANGS:
            if code not in avail[path]:
                continue
            loc = f'/{seg_name}{path}'
            seg = Segmenter(tms[code], stats=report.setdefault(code, {'seg': 0, 'hit': 0}))
            if path == '/':
                src = _read(page_file(out_dir, loc))     # build.py already rendered the hero dictionary into /<lang>/
                doc = src
            else:
                dct = page_dictionary(en_doc, code)
                doc = apply_dictionary(en_doc, dct) if dct else en_doc
            head_end = doc.find('</head>')
            body = seg.run(doc[head_end:])
            body = localize_dates(body, code)
            body = localize_links(body, seg_name, url_map[code])
            body = body.replace('<!--i18n:switch-->', switcher_html(code, links_for(path)), 1)
            doc = doc[:head_end] + body
            if path != '/':                              # /<lang>/ home copies already carry their own head from build.py
                doc = localize_head(doc, base, path, loc, code, group, seg, url_map[code])
            doc = set_html_attrs(doc, code)
            page_file(out_dir, loc).parent.mkdir(parents=True, exist_ok=True)
            page_file(out_dir, loc).write_text(doc, encoding='utf-8')
            rows.append((loc, meta[path][0], meta[path][1], code, group))
        # the English page: alternates, switcher, language bar
        head_end = en_doc.find('</head>')
        head = re.sub(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">', '', en_doc[:head_end])
        head = head.replace('<meta name="theme-color"', alternates_html(group, base) + '<meta name="theme-color"', 1)
        body = en_doc[head_end:].replace('<!--i18n:switch-->', switcher_html('en', links_for(path)), 1)
        f.write_text(head + body, encoding='utf-8')
        rows.append((path, meta[path][0], meta[path][1], 'en', group))
    for path in skip:
        rows.append((path, meta[path][0], meta[path][1], 'en', None))
    # every other HTML file (legal, lead, thank-you, 404 …): the switcher points at the language home pages
    for f in out_dir.rglob('index.html'):
        t = _read(f)
        if '<!--i18n:switch-->' in t:
            f.write_text(t.replace('<!--i18n:switch-->', switcher_html('en', home_links), 1), encoding='utf-8')
    nf = out_dir / '404.html'
    if nf.exists() and '<!--i18n:switch-->' in _read(nf):
        nf.write_text(_read(nf).replace('<!--i18n:switch-->', switcher_html('en', home_links), 1), encoding='utf-8')
    for code, st in report.items():
        pct = 100.0 * st['hit'] / st['seg'] if st['seg'] else 100.0
        n = sum(1 for p in loc_paths if code in avail[p])
        log(f'  i18n {code:8s} {n} pages · {st["hit"]}/{st["seg"]} segments translated ({pct:.1f}%)')
    if partial:
        log(f'  i18n {len(partial)} pages kept English-only until translated (below {MIN_COVERAGE:.0%} coverage); run scripts/i18n_todo.py')
    return rows, loc_paths


def write_sitemaps(out_dir, base, rows, dates=None):
    """sitemap.xml is a sitemap index; one sitemap per language, every URL with its hreflang alternates."""
    out_dir = Path(out_dir)
    by_lang = {}
    for path, lastmod, pr, code, group in rows:
        by_lang.setdefault(code, []).append((path, lastmod, pr, group))
    files = []
    order = ['en'] + [l[0] for l in LANGS]
    for code in order:
        if code not in by_lang:
            continue
        name = 'sitemap-en.xml' if code == 'en' else f'sitemap-{SEG_OF[code]}.xml'
        lines = []
        last = '1970-01-01'
        for path, lastmod, pr, group in by_lang[code]:
            lm = ((dates or {}).get(path) or lastmod or '')[:10]
            last = max(last, lm or last)
            alt = ''.join(f'<xhtml:link rel="alternate" hreflang="{hl}" href="{base}{p}"/>' for hl, p in (group or []))
            lines.append(f'<url><loc>{base}{path}</loc>' + (f'<lastmod>{lm}</lastmod>' if lm else '') + f'{alt}</url>')
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
               'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + '\n'.join(lines) + '\n</urlset>\n')
        (out_dir / name).write_text(xml, encoding='utf-8')
        files.append((name, last))
    idx = ('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + '\n'.join(f'<sitemap><loc>{base}/{n}</loc><lastmod>{lm}</lastmod></sitemap>' for n, lm in files) + '\n</sitemapindex>\n')
    (out_dir / 'sitemap.xml').write_text(idx, encoding='utf-8')
    return sum(len(v) for v in by_lang.values()), [n for n, _ in files]


# ------------------------------------------------------------------ extraction (used by scripts/i18n_todo.py)
def extract(out_dir, paths):
    """All translatable segments of the given English pages: {key: masked English source}, in first-seen order."""
    out_dir = Path(out_dir)
    found = {}
    for path in paths:
        doc = _read(page_file(out_dir, path))
        seg = Segmenter(collect=found)
        head_end = doc.find('</head>')
        head = doc[:head_end]
        # head texts first (title, description, social), then JSON-LD strings, then the body
        for m in re.finditer(r'<title>(.*?)</title>', head, re.S):
            seg.plain(m.group(1))
        for m in re.finditer(r'<meta (?:name|property)="(?:description|og:title|og:description|og:image:alt|twitter:title|twitter:description)" content="([^"]*)"', head):
            seg.plain(m.group(1))
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', head, re.S):
            try:
                g = json.loads(m.group(1))
            except Exception:
                continue
            def walk(v):
                if isinstance(v, dict):
                    if v.get('@type') in CANON_TYPES and len(v) > 1:
                        return
                    if v.get('@type') == 'FAQPage':
                        return
                    for k, x in v.items():
                        if k in TEXT_KEYS and isinstance(x, str):
                            seg.plain(x)
                        else:
                            walk(x)
                elif isinstance(v, list):
                    for x in v:
                        walk(x)
            walk(g)
        seg.run(doc[head_end:])
    return found
