#!/usr/bin/env python3
"""
End-to-end tracking test for the built site.

  python3 build.py && python3 -m http.server 8000 --directory _site &   # serve locally
  pip install playwright && playwright install chromium                # once
  python3 tests/test_tracking.py [--base http://localhost:8000]

Real GTM, GA4, Meta, LinkedIn, Clarity, Typeform and Calendly scripts load, but every analytics *hit*
(GA4 /g/collect, facebook.com/tr, LinkedIn px, Clarity collect, Google Ads) is intercepted, recorded and
answered locally — nothing reaches your analytics accounts. Typeform submissions are simulated through the
Typeform embed SDK's own postMessage channel, so no test responses are created in Typeform.
"""
import argparse, asyncio, json, re, sys, time, urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

ap = argparse.ArgumentParser()
ap.add_argument('--base', default='https://somin.ai', help='Origin the browser sees. https://somin.ai is served from ./_site by request interception (default), so pixels and GTM behave exactly as in production.')
ap.add_argument('--live', action='store_true', help='Do not intercept: test the real deployed site at --base')
ap.add_argument('--report', default=str(Path(__file__).with_name('tracking-report.json')))
args = ap.parse_args()
BASE = args.base.rstrip('/')

GA4 = 'G-XXM10JVHXY'
META_PIXEL = '719665876016415'
HIT_PATTERNS = {
    'ga4': re.compile(r'google-analytics\.com/g/collect|analytics\.google\.com/g/collect'),
    'meta': re.compile(r'facebook\.com/tr'),
    'linkedin': re.compile(r'px\.ads\.linkedin\.com|linkedin\.com/px|p\.adsymptotic\.com'),
    'clarity': re.compile(r'clarity\.ms/collect'),
    'gads': re.compile(r'googleads\.g\.doubleclick\.net|google\.com/pagead|google\.com/ccm|googleadservices\.com'),
}
SITE_DIR = Path(__file__).resolve().parent.parent / '_site'
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'application/javascript', '.json': 'application/json', '.xml': 'application/xml',
        '.txt': 'text/plain', '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.gif': 'image/gif',
        '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff'}


def local_file(url):
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    f = SITE_DIR / path.lstrip('/')
    if path.endswith('/') or f.is_dir():
        f = f / 'index.html'
    if f.is_file():
        return 200, f
    return 404, SITE_DIR / '404.html'


BLOCK_NAV = re.compile(r'^https://(cloud\.somin\.ai|drive\.google\.com)/')

results = []


def record(name, ok, detail=''):
    results.append({'test': name, 'ok': bool(ok), 'detail': detail})
    print(('  PASS ' if ok else '  FAIL ') + name + (f'  — {detail}' if detail else ''))


class Hits:
    def __init__(self):
        self.items = []
        self.pushed = []   # somin_event names seen in the page (survives redirects)

    def fired(self, name, since=0):
        """Event reached GA4, or was pushed as somin_event right before a redirect (GA4 batches hits and flushes them with
        a beacon on page unload; Playwright's request interception sometimes drops those unload beacons, real browsers don't)."""
        return name in [e.get('en') for e in self.ga4_events(since)] or any(n == name and ts >= since for n, ts in self.pushed)

    def add(self, kind, req):
        body = ''
        try:
            buf = req.post_data_buffer or b''
            if buf[:2] == b'\x1f\x8b':
                import gzip
                buf = gzip.decompress(buf)
            body = buf.decode('utf-8', 'replace')
        except Exception:
            body = ''
        self.items.append({'kind': kind, 'url': req.url, 'post': body, 't': time.time()})

    def ga4_events(self, since=0):
        out = []
        for h in self.items:
            if h['kind'] != 'ga4' or h['t'] < since:
                continue
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(h['url']).query))
            lines = [l for l in h['post'].split('\r\n') if l] if h['post'] else []
            if not lines:
                lines = [urllib.parse.urlsplit(h['url']).query]
            for l in lines:
                p = dict(urllib.parse.parse_qsl(l))
                merged = dict(q, **p)
                if 'en' in merged:
                    out.append(merged)
        return out

    def meta_events(self, since=0):
        out = []
        for h in self.items:
            if h['kind'] != 'meta' or h['t'] < since:
                continue
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(h['url']).query))
            body = h['post'] or ''
            if 'ev=' in body:
                q.update(dict(urllib.parse.parse_qsl(body)))
            for k, v in re.findall(r'name="([^"]+)"\r?\n\r?\n([^\r\n]*)', body):  # multipart beacons
                q.setdefault(k, v)
            out.append(q)
        return out

    def linkedin(self, since=0):
        return [h for h in self.items if h['kind'] == 'linkedin' and h['t'] >= since]

    def downloads(self, since=0):
        return [h['url'] for h in self.items if h['kind'] == 'download' and h['t'] >= since]


async def new_context(browser, hits):
    # Meta's pixel silently drops events from 'HeadlessChrome' user agents, so present a normal desktop Chrome UA.
    ctx = await browser.new_context(viewport={'width': 1366, 'height': 900},
                                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36')

    async def route(r):
        u = r.request.url
        for kind, rx in HIT_PATTERNS.items():
            if rx.search(u):
                hits.add(kind, r.request)
                return await r.fulfill(status=204, body='')
        if not args.live and re.match(r'^https://(www\.)?somin\.ai/', u):
            status, f = local_file(u)
            return await r.fulfill(status=status, body=f.read_bytes(), headers={'content-type': MIME.get(f.suffix, 'application/octet-stream')})
        if re.match(r'^https://drive\.usercontent\.google\.com/download', u):
            hits.add('download', r.request)   # the real Drive file is never fetched
            return await r.fulfill(status=200, body=b'%PDF-1.4 test', headers={'content-type': 'application/pdf', 'content-disposition': 'attachment; filename="test.pdf"'})
        if re.match(r'^https://mondays\.marketing/downloads/', u):
            hits.add('download', r.request)   # the plugin file is never fetched in tests
            return await r.fulfill(status=200, body=b'PK test', headers={'content-type': 'application/octet-stream'})
        if BLOCK_NAV.search(u) and r.request.resource_type == 'document':
            hits.add('nav', r.request)
            return await r.fulfill(status=200, content_type='text/html', body='<html><body>blocked in test</body></html>')
        await r.continue_()
    await ctx.route('**/*', route)
    await ctx.expose_binding('__sominRec', lambda source, name: hits.pushed.append((name, time.time())))
    await ctx.add_init_script("""(() => { let seen = 0; setInterval(() => {
      const l = (window.sominTracking && window.sominTracking.log) || [];
      for (; seen < l.length; seen++) { const e = l[seen]; if (e && e.event === 'somin_event' && window.__sominRec) window.__sominRec(e.event_name); }
    }, 40); })()""")
    return ctx


async def ga4_wait(hits, names, since=0, timeout=12.0):
    """Poll until all GA4 event names have arrived (GA4 batches hits for a few seconds)."""
    end = time.time() + timeout
    while time.time() < end:
        got = [e.get('en') for e in hits.ga4_events(since)]
        if all(n in got for n in names):
            return True
        await asyncio.sleep(0.5)
    return False


async def dl(page):
    return await page.evaluate("""() => (window.dataLayer || []).filter(x => x && typeof x === 'object' && !('0' in x)).map(x => {
      const o = {}; for (const k in x) { const v = x[k]; if (v === null || ['string', 'number', 'boolean'].includes(typeof v)) o[k] = v; } return o; })""")


def somin_events(layer):
    return [x for x in layer if x.get('event') == 'somin_event']


async def wait_for(cond, timeout=8.0, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        if await cond():
            return True
        await asyncio.sleep(step)
    return False


async def simulate_typeform_submit(page, rid):
    """Fire the Typeform SDK's own 'form-submit' message for the open embed (no real response is created)."""
    return await page.evaluate('''(rid) => {
      const f = [...document.querySelectorAll('iframe')].find(i => /form\\.typeform\\.com/.test(i.src));
      if (!f) return 'no-iframe';
      const u = new URL(f.src); const embedId = u.searchParams.get('typeform-embed-id');
      window.postMessage({ type: 'form-submit', embedId, responseId: rid }, '*');
      return embedId;
    }''', rid)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--no-sandbox'])

        # ---------------------------------------------------------------- 1. page load + base tags
        print('\n[1] Base tags on page load (homepage with UTM + click IDs)')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        scripts = []; page.on('request', lambda r: scripts.append(r.url) if r.resource_type == 'script' else None)
        await page.goto(BASE + '/?utm_source=test_src&utm_medium=cpc&utm_campaign=migration_qa&gclid=TEST_GCLID&fbclid=TEST_FBCLID', wait_until='load')
        await page.wait_for_timeout(6000)
        layer = await dl(page)
        record('tracking.js loaded once', sum('/assets/js/tracking.js' in s for s in scripts) == 1)
        record('GTM container loaded once (GTM-PZG88FPZ)', sum('gtm.js?id=GTM-PZG88FPZ' in s for s in scripts) == 1)
        record('GTM booted', await page.evaluate("!!(window.google_tag_manager && window.google_tag_manager['GTM-PZG88FPZ'])"))
        record('GA4 library loaded via GTM', any(f'gtag/js?id={GA4}' in s or 'gtag/js?id=' in s for s in scripts))
        ev = hits.ga4_events()
        record('GA4 page_view hit sent to G-XXM10JVHXY', any(e.get('en') == 'page_view' and e.get('tid') == GA4 for e in ev), f"{len(ev)} GA4 events")
        record('Meta pixel loaded + PageView', any(m.get('ev') == 'PageView' and m.get('id') == META_PIXEL for m in hits.meta_events()), f"{len(hits.meta_events())} Meta hits")
        record('LinkedIn Insight loaded', any('snap.licdn.com' in s for s in scripts))
        record('LinkedIn page hit', len(hits.linkedin()) > 0, f"{len(hits.linkedin())} hits")
        record('Clarity loaded once (via GTM, pfshy7yc19)', sum('clarity.ms/tag/' in s for s in scripts) == 1, ', '.join(s.split('?')[0] for s in scripts if 'clarity.ms/tag/' in s))
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        ctxd = next((x for x in layer if 'page_type' in x), {})
        record('Page context in dataLayer', ctxd.get('page_type') == 'home', json.dumps(ctxd))
        attr = await page.evaluate('window.sominTracking.attributionFields()')
        record('Attribution captured (utm + gclid + fbclid)', attr.get('utm_source') == 'test_src' and attr.get('gclid') == 'TEST_GCLID' and attr.get('fbclid') == 'TEST_FBCLID', json.dumps(attr)[:200])

        # ---------------------------------------------------------------- 2. CTA click + Calendly popup
        print('\n[2] CTA click → Calendly popup (homepage hero "Book a call")')
        t0 = time.time()
        cta = page.locator('a[href*="calendly.com"][data-gtm-id]').first
        gid = await cta.get_attribute('data-gtm-id')
        await cta.scroll_into_view_if_needed(); await cta.click()
        ok = await wait_for(lambda: page.evaluate("!!document.querySelector('.calendly-overlay iframe, .calendly-popup iframe')"), 10)
        record('Calendly opens as popup (not new tab)', ok)
        src = await page.evaluate("(document.querySelector('.calendly-overlay iframe, .calendly-popup iframe')||{}).src||''")
        record('Calendly URL carries UTMs', 'utm_source=test_src' in src and 'utm_campaign=migration_qa' in src, src[:160])
        await page.wait_for_timeout(5000)
        names = [e.get('en') for e in hits.ga4_events(t0)]
        record(f'GA4 cta_click (cta_id={gid})', any(e.get('en') == 'cta_click' and e.get('ep.cta_id') == gid for e in hits.ga4_events(t0)), ','.join(n for n in names if n))
        record('GA4 book_call_click (somin_event)', 'book_call_click' in names)
        record('Meta custom cta_click', any(m.get('ev') == 'cta_click' for m in hits.meta_events(t0)))
        record('LinkedIn CTA conversion 20526804', any('20526804' in (h['url'] + h['post']) for h in hits.linkedin(t0)))

        print('\n[3] Calendly booking confirmed (simulated Calendly postMessage)')
        t0 = time.time()
        await page.evaluate("window.postMessage({event:'calendly.event_scheduled', payload:{}}, '*')")
        await page.wait_for_timeout(5000)
        layer = await dl(page)
        record("dataLayer 'calendly' event from GTM listener", any(x.get('event') == 'calendly' and x.get('calendly_event') == 'event_scheduled' for x in layer))
        g = hits.ga4_events(t0)
        record('GA4 generate_lead (lead_type=calendly)', any(e.get('en') == 'generate_lead' and e.get('ep.lead_type') == 'calendly' for e in g), ','.join(e.get('en', '') for e in g))
        record('Meta Lead', any(m.get('ev') == 'Lead' for m in hits.meta_events(t0)))
        record('LinkedIn conversion 20526828', any('20526828' in (h['url'] + h['post']) for h in hits.linkedin(t0)))
        await ctx.close()

        # ---------------------------------------------------------------- 4. trial Typeform
        print('\n[4] Trial lead form (Typeform popup) → submit → thank-you page')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + '/somin-for-brands/?utm_source=linkedin&utm_campaign=q4_test&li_fat_id=TEST_LI', wait_until='load')
        await page.wait_for_timeout(2500)
        t0 = time.time()
        trig = page.locator('[data-lead-form="trial"]').first
        trig_gid = await trig.get_attribute('data-gtm-id')
        await page.evaluate("document.querySelector('[data-lead-form=\"trial\"]').click()")
        ok = await wait_for(lambda: page.evaluate("!![...document.querySelectorAll('iframe')].find(i=>/form\\.typeform\\.com\\/to\\/jC5qqGJ0/.test(i.src))"), 12)
        record('Typeform popup opens with trial form jC5qqGJ0', ok)
        src = await page.evaluate("([...document.querySelectorAll('iframe')].find(i=>/typeform/.test(i.src))||{}).src||''")
        frag = urllib.parse.unquote(src)
        record('Hidden fields passed (utm_source, li_fat_id, page_path, lead_type)', all(s in frag for s in ['utm_source=linkedin', 'li_fat_id=TEST_LI', 'page_path=' + urllib.parse.urlsplit(BASE).path.rstrip('/') + '/somin-for-brands/', 'lead_type=trial']), frag[frag.find('#'):][:220])
        ready = await wait_for(lambda: page.evaluate("(window.sominTracking.log||[]).some(x=>x.event_name==='lead_form_ready')"), 15)
        record('Typeform onReady → lead_form_ready', ready)
        await simulate_typeform_submit(page, 'TEST-RID-TRIAL')
        try:
            await page.wait_for_url(re.compile(r'/thank-you-trial-somin/'), timeout=8000)
            moved = True
        except Exception:
            moved = False
        record('Redirect to /thank-you-trial-somin/ after submit', moved, page.url)
        await page.wait_for_timeout(5000)
        g = hits.ga4_events(t0)
        names = [e.get('en') for e in g]
        record('lead_form_open tracked', hits.fired('lead_form_open', t0))
        record('trial_form_submit tracked', hits.fired('trial_form_submit', t0))
        await ga4_wait(hits, ['thank_you_view'], t0)
        g = hits.ga4_events(t0); names = [e.get('en') for e in g]
        record('GA4 thank_you_view', 'thank_you_view' in names, ','.join(n for n in names if n))
        # conversions come from GTM (thank-you trigger, Page Path contains /thank-you-trial-somin) — exactly once each
        n_gl = names.count('generate_lead')
        record('GA4 generate_lead fired exactly once (GTM thank-you trigger)', n_gl == 1, f'{n_gl}x')
        n_lead = sum(1 for m in hits.meta_events(t0) if m.get('ev') == 'Lead')
        record('Meta Lead fired exactly once (GTM)', n_lead == 1, f'{n_lead}x')
        n_li = sum(1 for h in hits.linkedin(t0) if '21236668' in (h['url'] + h['post']))
        record('LinkedIn trial conversion 21236668 fired exactly once (GTM)', n_li == 1, f'{n_li}x')
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        await ctx.close()

        # ---------------------------------------------------------------- 5. case-study form + download release
        print('\n[5] Case-study form → instant download release')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + '/brands-fujifilm-case-study/', wait_until='load')
        await page.wait_for_timeout(2500)
        t0 = time.time()
        await page.evaluate("document.querySelector('[data-lead-form=\"case_study\"]').click()")
        ok = await wait_for(lambda: page.evaluate("!![...document.querySelectorAll('iframe')].find(i=>/form\\.typeform\\.com\\/to\\/lHmWeOX7/.test(i.src))"), 12)
        record('Typeform popup opens with case-study form lHmWeOX7', ok)
        src = urllib.parse.unquote(await page.evaluate("([...document.querySelectorAll('iframe')].find(i=>/typeform/.test(i.src))||{}).src||''"))
        record('Hidden field case_study=brands-fujifilm-case-study', 'case_study=brands-fujifilm-case-study' in src)
        await wait_for(lambda: page.evaluate("(window.sominTracking.log||[]).some(x=>x.event_name==='lead_form_ready')"), 15)
        await simulate_typeform_submit(page, 'TEST-RID-CASE')
        try:
            await page.wait_for_url(re.compile(r'/thank-you-case-study/\?.*cs=brands-fujifilm-case-study'), timeout=8000); moved = True
        except Exception:
            moved = False
        record('Redirect to /thank-you-case-study/?cs=…', moved, page.url)
        await page.wait_for_timeout(2500)
        auto = hits.downloads(t0)
        record('PDF download starts automatically after the form (once, page stays put)',
               len(auto) == 1 and '1Y2aQnNb-5-XCsUwHd2lKb22feZ3ZThxx' in auto[0] and '/thank-you-case-study/' in page.url, (auto[:1] or ['none'])[0][:120])
        href = await page.evaluate("(document.querySelector('[data-cs-download]')||{}).href||''")
        visible = await page.evaluate("!document.querySelector('[data-cs-state=\"ready\"]').hidden")
        record('Download released immediately with the right Drive file', visible and '1Y2aQnNb-5-XCsUwHd2lKb22feZ3ZThxx' in href, href)
        await page.click('[data-cs-download]')
        await page.wait_for_timeout(5000)
        g = hits.ga4_events(t0); names = [e.get('en') for e in g]
        record('case_study_form_submit tracked', hits.fired('case_study_form_submit', t0))
        record('GA4 case_study_download', 'case_study_download' in names, ','.join(n for n in names if n))
        n_gl = names.count('generate_lead')
        record('GA4 generate_lead fired exactly once (GTM thank-you trigger)', n_gl == 1, f'{n_gl}x')
        n_lead = sum(1 for m in hits.meta_events(t0) if m.get('ev') == 'Lead')
        record('Meta Lead fired exactly once (GTM)', n_lead == 1, f'{n_lead}x')
        n_li = sum(1 for h in hits.linkedin(t0) if '20526508' in (h['url'] + h['post']))
        record('LinkedIn case-study conversion 20526508 fired exactly once (GTM)', n_li == 1, f'{n_li}x')
        # locked state when opened without submitting
        p2 = await ctx.new_page()
        await p2.goto(BASE + '/thank-you-case-study/?cs=brands-defender-case-study', wait_until='load'); await p2.wait_for_timeout(800)
        record('Direct visit without submit stays locked', await p2.evaluate("!document.querySelector('[data-cs-state=\"locked\"]').hidden && document.querySelector('[data-cs-state=\"ready\"]').hidden"))
        p3 = await ctx.new_page()
        await p3.goto(BASE + '/thank-you-case-study/?cs=brands-pepsi-india-case-study&rid=abcdefghijklmnopqrstuvwxyz123456', wait_until='load'); await p3.wait_for_timeout(800)
        record('Direct visit with a made-up response id stays locked', await p3.evaluate("!document.querySelector('[data-cs-state=\"locked\"]').hidden"))
        # page.request bypasses the routing that serves ./_site, so read the built file locally
        src = await (await p3.request.get(BASE + '/thank-you-case-study/')).text() if args.live else (SITE_DIR / 'thank-you-case-study/index.html').read_text(encoding='utf-8')
        record('No Drive file IDs or links in the page source', 'cs-manifest' in src and '1Y2aQnNb-5-XCsUwHd2lKb22feZ3ZThxx' not in src and 'drive.google.com/file' not in src)
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        await ctx.close()

        # ---------------------------------------------------------------- 5b. case-studies hub
        print('\n[5b] Case-studies hub → PDF-only case → form → auto-download')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + '/cases-ai-marketing-strategy/', wait_until='load')
        await page.wait_for_timeout(2500)
        n_cards = await page.locator('[data-cs-card]').count()
        record('Hub lists all 45 case studies', n_cards == 45, f'{n_cards} cards')
        await page.click('[data-cs-filter="creators"]'); vis = await page.locator('[data-cs-card]:visible').count()
        await page.click('[data-cs-filter="all"]')
        record('Section filter works (creators = 6)', vis == 6, f'{vis}')
        t0 = time.time()
        await page.locator('[data-case-study="maybank"].btn').click()
        ok = await wait_for(lambda: page.evaluate("!![...document.querySelectorAll('iframe')].find(i=>/form\\.typeform\\.com\\/to\\/lHmWeOX7/.test(i.src))"), 12)
        src = urllib.parse.unquote(await page.evaluate("([...document.querySelectorAll('iframe')].find(i=>/typeform/.test(i.src))||{}).src||''"))
        record('Get the PDF opens the case-study Typeform with case_study=maybank', ok and 'case_study=maybank' in src)
        await wait_for(lambda: page.evaluate("(window.sominTracking.log||[]).some(x=>x.event_name==='lead_form_ready')"), 15)
        await simulate_typeform_submit(page, 'TEST-RID-HUB')
        try:
            await page.wait_for_url(re.compile(r'/thank-you-case-study/\?.*cs=maybank'), timeout=8000); moved = True
        except Exception:
            moved = False
        record('Redirect to /thank-you-case-study/?cs=maybank', moved, page.url)
        await page.wait_for_timeout(5000)
        auto = hits.downloads(t0)
        record('Maybank PDF downloads automatically', len(auto) == 1 and '1i7FJg49PflUdT6-Um5BQTfoyNgDPXmpq' in auto[0] and 'confirm=t' in auto[0], (auto[:1] or ['none'])[0][:120])
        await ga4_wait(hits, ['generate_lead', 'case_study_auto_download'], t0)
        g = hits.ga4_events(t0); names = [e.get('en') for e in g]
        record('case_study_form_submit + case_study_auto_download tracked', hits.fired('case_study_form_submit', t0) and 'case_study_auto_download' in names, ','.join(n for n in names if n))
        record('Lead conversions fire exactly once (GA4 / Meta / LinkedIn 20526508)',
               names.count('generate_lead') == 1 and sum(1 for m in hits.meta_events(t0) if m.get('ev') == 'Lead') == 1
               and sum(1 for h in hits.linkedin(t0) if '20526508' in (h['url'] + h['post'])) == 1)
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        await ctx.close()

        # ---------------------------------------------------------------- 5c. Claude plugin (home hero card)
        print('\n[5c] Home hero plugin card → plugin Typeform → thank-you → auto-download')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + '/?utm_source=plugin_test&utm_campaign=mm_plugin', wait_until='load')
        await page.wait_for_timeout(2500)
        t0 = time.time()
        card = page.locator('a.mm-plugin-card[data-lead-form="plugin"]')
        record('Hero shows the plugin card', await card.count() == 1)
        await card.click()
        ok = await wait_for(lambda: page.evaluate("!![...document.querySelectorAll('iframe')].find(i=>/form\\.typeform\\.com\\/to\\/PI0VcVHp/.test(i.src))"), 12)
        record('Typeform popup opens with plugin form PI0VcVHp', ok)
        src = urllib.parse.unquote(await page.evaluate("([...document.querySelectorAll('iframe')].find(i=>/typeform/.test(i.src))||{}).src||''"))
        record('Hidden fields lead_type=plugin, utm_source, cta_id', all(x in src for x in ['lead_type=plugin', 'utm_source=plugin_test', 'cta_id=home_hero_plugin']), src[src.find('#'):][:200])
        await wait_for(lambda: page.evaluate("(window.sominTracking.log||[]).some(x=>x.event_name==='lead_form_ready')"), 15)
        await simulate_typeform_submit(page, 'TEST-RID-PLUGIN')
        try:
            await page.wait_for_url(re.compile(r'/thank-you-plugin/\?.*rid=TEST-RID-PLUGIN'), timeout=8000); moved = True
        except Exception:
            moved = False
        record('Redirect to /thank-you-plugin/?rid=…', moved, page.url)
        await page.wait_for_timeout(2500)
        auto = hits.downloads(t0)
        record('Plugin download starts automatically (once, page stays put)',
               len(auto) == 1 and auto[0].endswith('/downloads/marketing-mondays.plugin') and '/thank-you-plugin/' in page.url, (auto[:1] or ['none'])[0][:120])
        record('Download buttons released (plugin + zip)', await page.evaluate("!document.querySelector('[data-plugin-state=\"ready\"]').hidden && document.querySelector('[data-plugin-main]').href.endsWith('.plugin')"))
        await ga4_wait(hits, ['generate_lead', 'plugin_auto_download'], t0)
        g = hits.ga4_events(t0); names = [e.get('en') for e in g]
        record('plugin_form_submit + plugin_auto_download tracked', hits.fired('plugin_form_submit', t0) and 'plugin_auto_download' in names, ','.join(n for n in names if n))
        n_gl = sum(1 for e in g if e.get('en') == 'generate_lead')
        record('GA4 generate_lead fired exactly once (GTM thank-you-plugin trigger)', n_gl == 1, f'{n_gl}x')
        n_lead = sum(1 for m in hits.meta_events(t0) if m.get('ev') == 'Lead')
        record('Meta Lead fired exactly once (GTM)', n_lead == 1, f'{n_lead}x')
        mev = [m.get('ev') for m in hits.meta_events(t0)]
        record('Meta key events via GTM (lead_form_open, plugin_form_submit, plugin_auto_download)',
               all(x in mev for x in ['lead_form_open', 'plugin_form_submit', 'plugin_auto_download']), ','.join(sorted(set(str(x) for x in mev))))
        p2 = await ctx.new_page()
        await p2.goto(BASE + '/thank-you-plugin/?rid=abcdefghijklmnopqrstuvwxyz123456', wait_until='load'); await p2.wait_for_timeout(800)
        # same browser already submitted → stays unlocked; a fresh browser with a made-up id must stay locked
        ctx2 = await new_context(browser, Hits()); p3 = await ctx2.new_page()
        await p3.goto(BASE + '/thank-you-plugin/?rid=abcdefghijklmnopqrstuvwxyz123456', wait_until='load'); await p3.wait_for_timeout(800)
        record('Direct visit with a made-up response id stays locked', await p3.evaluate("!document.querySelector('[data-plugin-state=\"locked\"]').hidden && document.querySelector('[data-plugin-main]').getAttribute('href') === '#'"))
        await ctx2.close()
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        await ctx.close()

        # ---------------------------------------------------------------- 5d. session replays
        print('\n[5d] Session replays (home loop player)')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + '/', wait_until='load'); await page.wait_for_timeout(1500)
        await page.locator('[data-mm-player] video').scroll_into_view_if_needed(); await page.wait_for_timeout(2500)
        st = await page.evaluate("(() => { const v = document.querySelector('[data-mm-player] video'); return {src: v.currentSrc, rs: v.readyState, t: v.currentTime}; })()")
        record('Loop replay loads and plays when scrolled into view', bool(re.search(r'/assets/video/listen-landscape-report\.(mp4|webm)$', st['src'])) and st['rs'] >= 2 and st['t'] > 0, json.dumps(st))
        t0 = time.time()
        await page.locator('[data-mm-tab][data-step="Make"]').click(); await page.wait_for_timeout(1500)
        st = await page.evaluate("(() => { const v = document.querySelector('[data-mm-player] video'); return {src: v.currentSrc, q: document.querySelector('[data-mm-q]').textContent}; })()")
        record('Step tab switches the replay (Make → Figma)', 'make-figma' in st['src'], json.dumps(st))
        await ga4_wait(hits, ['replay_step_click'], t0, timeout=8)
        record('replay_step_click tracked (GA4)', 'replay_step_click' in [e.get('en') for e in hits.ga4_events(t0)])
        n_vo = await page.evaluate("[...document.querySelectorAll('script[type=\"application/ld+json\"]')].filter(s => s.textContent.includes('VideoObject')).length")
        record('VideoObject schema on the home page', n_vo >= 1)
        record('No JavaScript errors', not errors, '; '.join(errors[:3]))
        await ctx.close()

        # ---------------------------------------------------------------- 6. login, scroll, blog
        print('\n[6] Login click, scroll depth, blog engagement')
        hits = Hits(); ctx = await new_context(browser, hits); page = await ctx.new_page()
        await page.goto(BASE + '/blog/the-end-of-seo-how-to-survive-the-rise-of-the-agentic-web/', wait_until='load')
        await page.wait_for_timeout(2500)
        t0 = time.time()
        for y in range(0, 12):
            await page.mouse.wheel(0, 700); await page.wait_for_timeout(250)
        await page.wait_for_timeout(1500)
        await page.evaluate("document.querySelector('a[href^=\"https://cloud.somin.ai/auth/signin\"]').click()")
        await page.wait_for_timeout(5000)
        g = hits.ga4_events(t0); names = [e.get('en') for e in g]
        record('GA4 scroll (GTM scroll-depth trigger)', 'scroll' in names, 'percent_scrolled=' + ','.join(sorted(set(e.get('epn.percent_scrolled') or e.get('ep.percent_scrolled', '') for e in g if e.get('en') == 'scroll'))))
        record('GA4 article_read_50', 'article_read_50' in names)
        record('GA4 login_click', 'login_click' in names, ','.join(sorted(set(n for n in names if n))))
        await ctx.close()

        # ---------------------------------------------------------------- 7. crawl every page for JS errors + single GTM
        print('\n[7] Crawl all pages (JS errors, one GTM container, tracking.js present)')
        sm = (Path(__file__).resolve().parent.parent / '_site/sitemap.xml').read_text()
        paths = [u.replace('https://somin.ai', '') for u in re.findall(r'<loc>(.*?)</loc>', sm)] + ['/try-somin/', '/get-case-study/', '/thank-you-trial-somin/', '/thank-you-plugin/', '/c5584ab5-007d-4499-b460-978130fe387b/']
        hits = Hits(); ctx = await new_context(browser, hits)
        bad = []
        sem = asyncio.Semaphore(6)

        async def visit(path):
            async with sem:
                pg = await ctx.new_page(); errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
                try:
                    r = await pg.goto(BASE + path, wait_until='load', timeout=45000)
                    await pg.wait_for_timeout(1800)
                    n = await pg.evaluate("Object.keys(window.google_tag_manager||{}).filter(k=>k.startsWith('GTM-')).length")
                    if not r or r.status != 200 or errs or n != 1:
                        bad.append({'path': path, 'status': r.status if r else None, 'gtm_containers': n, 'errors': errs[:2]})
                except Exception as e:
                    bad.append({'path': path, 'error': str(e)[:160]})
                await pg.close()
        await asyncio.gather(*(visit(pth) for pth in paths))
        record(f'All {len(paths)} pages load with no JS errors and exactly one GTM container', not bad, json.dumps(bad)[:600])
        await ctx.close()
        await browser.close()

    passed = sum(r['ok'] for r in results)
    print(f'\n{passed}/{len(results)} checks passed')
    Path(args.report).write_text(json.dumps({'base': BASE, 'passed': passed, 'total': len(results), 'results': results}, indent=1))
    sys.exit(0 if passed == len(results) else 1)

if __name__ == '__main__':
    asyncio.run(main())
