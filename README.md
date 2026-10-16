# somin.ai — static site (GitHub Pages)

The SOMIN marketing site, migrated off Leadpages into a plain static site:
Python-stdlib build script, one shared tracking script, Typeform for lead capture,
Calendly for calls. No framework, no npm, no Leadpages runtime.

```
python3 build.py --serve        # build into ./_site and serve on http://localhost:8000
```

---

## 1. Repo layout

| Path | What it is |
|---|---|
| `build.py` | The whole generator (Python 3.9+, standard library only). Writes `_site/`. |
| `site.config.json` | Site identity, navigation, footer, redirects. |
| `content/pages/<slug>.html` | One file per page → `/<slug>/`. `index.html` is the home page. |
| `content/blog/<slug>.html` | Blog articles → `/blog/<slug>/`. |
| `data/case-studies.json` | Case-study PDFs (Google Drive IDs) released after the case-study form. |
| `static/` | Copied as-is: `assets/css/site.css`, `assets/js/tracking.js`, `assets/js/site.js`, images, `CNAME`, favicon. |
| `tests/check_static.py` | SEO / link / asset / markup QA over `_site/`. |
| `tests/test_tracking.py` | Playwright end-to-end tracking test (GTM, GA4, Meta, LinkedIn, Clarity, Typeform, Calendly). |
| `docs/TRACKING.md` | Event dictionary and GTM wiring for conversions. |
| `.github/workflows/deploy.yml` | Builds and deploys to GitHub Pages on every push to `main`. |

Every content file starts with a JSON header, then the page body:

```html
<!--meta
{ "slug": "somin-for-brands", "layout": "fragment", "type": "solution",
  "title": "…", "description": "…", "og_image": "/assets/img/og/…jpg", "robots": "index,follow", "jsonld": [ … ] }
-->
<section>…page body…</section>
```

Layouts: `fragment` (marketing pages, self-contained HTML/CSS), `doc` (legal), `native` (vision, offer pages),
`post` (blog). The builder adds header, footer, canonical, Open Graph/Twitter, JSON-LD, breadcrumbs and the scripts —
never put `<head>` tags, GTM snippets or pixels in content files.

## 2. Deploy to GitHub Pages

This repo is the **source**. The website itself (with `index.html` at the top) is generated into `_site/` by
`python3 build.py`. Two ways to publish:

**A. Upload the ready-made site (no build step).** Use `somin-website-upload.zip` (the contents of `_site/`):
unzip it, put the files at the root of a repo's `main` branch (GitHub Desktop or `git push`; the browser uploader
takes max 100 files per commit and the site has ~430), then **Settings → Pages → Source: Deploy from a branch →
`main` / `(root)`**. Keep `.nojekyll` and `CNAME`. After any edit to the source, rebuild and upload `_site/` again.

**B. Push this source repo and let GitHub build it (recommended for ongoing edits).**

1. Create a repo (e.g. `somin-ai/somin.ai`) and push this folder to `main`.
2. **Settings → Pages → Source: GitHub Actions.** The included workflow runs `build.py` and publishes `_site/` on every push.

   Without a custom domain the site is served at `https://<user>.github.io/<repo>/`: the workflow reads that
   sub-path from GitHub (`configure-pages` → `base_path`) and builds with `--base-path`, which prefixes all internal
   links and marks every page `noindex` (it is a preview copy of somin.ai). Once `somin.ai` is set as the custom
   domain the base path is empty and the normal, indexable site is published — no file changes needed.

Then, for either way:

3. **Settings → Pages → Custom domain:** `somin.ai`, then tick **Enforce HTTPS** once the certificate is issued.
4. Verify the domain for the GitHub organisation (**Org settings → Pages → Verified domains**) to block domain takeover.
5. DNS (at the registrar), after lowering TTL a day before cut-over:

   | Host | Type | Value |
   |---|---|---|
   | `@` | A | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
   | `@` | AAAA | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
   | `www` | CNAME | `<org>.github.io` |

   GitHub then redirects `www.somin.ai` → `somin.ai` (the canonical host used everywhere in the site).
6. Remove the domain from Leadpages only after the GitHub site answers on `somin.ai`.
7. Keep these hosts as they are — they are not part of this site: `cloud.somin.ai` (platform login), `share.somin.ai`.

The preview build is served at `https://<user>.github.io/<repo>/` (all pages `noindex`); see section B above.

> The site uses root-relative URLs, so preview it locally (`python3 build.py --serve`) rather than on a
> `<user>.github.io/<repo>/` project URL.

## 3. Everyday edits

| Task | Where |
|---|---|
| Edit a page | `content/pages/<slug>.html` (body) and its meta header (title, description, OG). |
| New page | Copy an existing page file, change `slug`, `title`, `description`. It lands in the sitemap and `llms.txt` automatically. |
| New blog post | `content/blog/<slug>.html` with `layout: "post"`, `date`, `author`, `topic`, `image` (1600×900 WebP in `static/assets/img/blog/`). |
| Menu / footer | `site.config.json` → `nav`, `nav_cta`, `footer`. |
| Redirect an old URL | `site.config.json` → `redirects` (`"/old/": "/new/"`). Generates a noindexed stub with canonical + instant redirect. |
| Hide a page from search | meta `"robots": "noindex,follow"` (also drops it from the sitemap and `llms.txt`). |
| Add a case-study PDF | Upload it to the Drive folder, add an entry in `data/case-studies.json` (key = page slug or a short id) with a `hub` block (section, title, sector, market, summary, cover in `static/assets/img/cases/`). It appears on the hub, in the thank-you picks and in `llms.txt`. |
| Change form / pixel IDs | `static/assets/js/tracking.js` → `CONFIG` block (the builder reads it too). |

Run the checks before pushing:

```
python3 build.py
python3 tests/check_static.py             # 0 problems expected (long-title warnings are informational)
pip install -r requirements-dev.txt && python3 -m playwright install chromium
python3 tests/test_tracking.py            # serves ./_site as https://somin.ai and checks every tag fires
python3 tests/test_tracking.py --live --base https://somin.ai   # same checks against production after deploy
```

## 4. Lead capture

All CTAs use plain links with a data attribute, so they work without JavaScript and are tracked with no extra code:

```html
<a href="/try-somin/" data-lead-form="trial">Try SOMIN</a>
<a href="/get-case-study/?cs=brands-fujifilm-case-study" data-lead-form="case_study"
   data-case-study="brands-fujifilm-case-study">Get the case study</a>
<a href="https://calendly.com/filipp-lugovoi/30min">Book a call</a>     <!-- auto Calendly popup with UTMs -->
```

| Flow | Typeform | After submit |
|---|---|---|
| Try SOMIN (free trial) | `jC5qqGJ0` | `/thank-you-trial-somin/` |
| Case-study request | `lHmWeOX7` | `/thank-you-case-study/?cs=<key>` — the PDF download unlocks immediately |

Both forms live in the **sominanalytics** Typeform account, use the SOMIN theme (teal `#2DBF9C` on ink `#16201F`,
Montserrat/Inter) and receive these hidden fields on every response:
`utm_source, utm_medium, utm_campaign, utm_term, utm_content, gclid, gbraid, wbraid, fbclid, li_fat_id, msclkid, ttclid,
landing_page, referrer, ga_client_id, fbp, fbc, page_url, page_path, cta_id, lead_type, case_study`.

**Case-study hub.** `/cases-ai-marketing-strategy/` lists all 45 case studies (27 brands, 12 agencies, 6 creators) with
section filters and search, built from `data/case-studies.json` (`hub` blocks carry the tile title, sector, market and
summary from the Leadpages hub). Every tile's **Get the PDF** opens the case-study Typeform; tiles with a full story page
also link to it.

**Case-study release.** Submitting the case-study form redirects to `/thank-you-case-study/?cs=<key>&rid=<responseId>`,
which **starts the PDF download automatically** and shows Download / Open-in-browser buttons plus six more case studies.
The page only unlocks after the form was submitted in that browser (or when arriving straight from the form with a real
Typeform response id); a direct visit, or a made-up `rid`, shows a locked card that reopens the form. Drive file IDs are
not in the page source in plain text.

**Where the PDFs live: Google Drive, not the repo.** The 46 PDFs are 434 MB in total, five are over 25 MB and one
(HEA Energy) is 140 MB, above GitHub's 100 MB file limit. Drive's direct endpoint
(`drive.usercontent.google.com/download?id=…&export=download&confirm=t`) serves every file, including the 140 MB one,
as an attachment without an interstitial, and replacing a PDF in Drive needs no redeploy. Keep the folder shared as
**Anyone with the link → Viewer**. It is still a soft gate: anyone who has a Drive link can open it, as on Leadpages.

**Calls.** Every `calendly.com` link opens the Calendly popup with the visitor's UTMs passed through. The
**BOOK A CALL** button uses `calendly.com/filipp-lugovoi/30min`; the case-study pages keep `calendly.com/roman-vss/30min`.

## 5. Tracking (summary — details in `docs/TRACKING.md`)

* Exactly **one** script handles tracking on every page: `/assets/js/tracking.js`. It boots GTM `GTM-PZG88FPZ`,
  which loads GA4 `G-XXM10JVHXY`, Google Ads `AW-16476989673`, Meta pixel `719665876016415`,
  LinkedIn Insight `6960748`/`2907724`, Microsoft Clarity `pfshy7yc19` and the Calendly listener.
* Clean events go to the dataLayer as `{event: 'somin_event', event_name, event_id, funnel_stage, cta_text, cta_location…}`;
  the existing GA4 event tag forwards them. Custom events from anywhere: `window.sominTrack('my_event', {…})`
  or `<a data-track="my_event">`.
* Lead conversions (GA4 `generate_lead`, Meta `Lead`, LinkedIn `21236668` trial / `20526508` case study) fire in GTM
  on the thank-you page that follows every Typeform submit (GTM version 50, Page Path triggers). `tracking.js` does
  not fire them itself, so nothing is counted twice.
* Debug: add `?debug_tracking=1` to any URL to log every event in the console; `?tracking=off` disables all tags.

Test result at hand-over, against the live GTM container v50: **48 / 48 checks passed**, each lead conversion fires
exactly once (`tests/tracking-report.json`).

## 6. SEO / AEO / GEO built in

* Canonical (apex, trailing slash), unique titles/descriptions, Open Graph + Twitter cards with absolute 1200×630 images.
* JSON-LD on every page: `Organization`, `WebSite`, `WebPage`, `BreadcrumbList`; `BlogPosting` + `Blog` on the blog;
  the original page-specific schema (FAQ, SoftwareApplication, etc.) is kept and normalised to `https://somin.ai/…/`.
* `sitemap.xml` with `lastmod`, `robots.txt` (AI answer engines explicitly allowed), `llms.txt` and `llms-full.txt`
  for LLM/answer-engine discovery, RSS at `/blog/rss.xml`.
* Clean URLs (`/slug/`), real 404 page, redirect stubs for retired Leadpages URLs, noindex on thank-you, lead and
  client-specific legal pages.
* Images converted to WebP and lazy-loaded; total site ~22 MB (was ~150 MB of Leadpages assets).

## 7. Things fixed during the migration (were broken on the Leadpages site)

* GTM thank-you triggers matched `www.somin.ai/…/`, which always redirects to `somin.ai`, so trial and case-study
  leads never reached GA4, Meta or LinkedIn → triggers changed to Page Path in GTM (version 50, live on the current
  Leadpages site too).
* Two Clarity projects loaded on the same page and crashed each other (`reading 'unshift'`) → only GTM's Clarity loads.
* `/somin-strategy` showed a copy of `/ai-agents`; the real Strategy page sat at `/somin-comparisons` → swapped + redirect.
* `/somin-reporting` and `/somin-social-media-manager` reused the comparison pages' titles/descriptions → fixed.
* JavaScript syntax error in the Chinese translations on `/somin-for-creators` → fixed.
* Privacy-policy title, dead blog links, duplicate "-copy" blog post, empty `/forms` and `/pixel` pages → fixed/redirected.
* Mobile menu, blog layout, article pages, thank-you and case-study pages redesigned; every blog post has a SOMIN-styled cover.
