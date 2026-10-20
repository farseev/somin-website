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
| `data/organization.json` | Company, product and founder facts → the one Organization/SoftwareApplication node, `/about/`, `llms.txt`. |
| `data/pricing.json` | Plans, prices, features and Stripe links (from cloud.somin.ai/manuals/subscriptions.html) → `/pricing/`, Offer schema. |
| `data/content-dates.json` | Written by the build: last-changed date per URL for sitemap `lastmod` and `dateModified`. Commit it. |
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
| Marketing Mondays plugin for Claude (free) | `PI0VcVHp` | `/thank-you-plugin/` — the `.plugin` download starts automatically, plus install steps |

All three forms live in the **sominanalytics** Typeform account, use the SOMIN theme (teal `#2DBF9C` on ink `#16201F`,
Montserrat) and receive these hidden fields on every response:
`utm_source, utm_medium, utm_campaign, utm_term, utm_content, gclid, gbraid, wbraid, fbclid, li_fat_id, msclkid, ttclid,
landing_page, referrer, ga_client_id, fbp, fbc, page_url, page_path, cta_id, lead_type, case_study`.

**Claude plugin.** The home hero carries a plugin card and `/marketing-mondays-plugin/` is the landing page (skills,
the five-step loop player, install guide, FAQ, SoftwareApplication + FAQPage schema). Both open the plugin Typeform; the
thank-you page releases `https://mondays.marketing/downloads/marketing-mondays.plugin` (and the Claude Code `.zip`) only
after a submit in that browser, like the case studies. The files stay on mondays.marketing, so updates there flow through.

**Session replays.** Eleven condensed screen recordings of real SOMIN agent runs (Claude + SOMIN MCP on Grab Singapore data,
from the Marketing Mondays session of 12 Oct 2026) are in `static/assets/video/` as H.264 MP4 + VP9 WebM + WebP poster
(about 13 MB in total), listed in `data/replays.json`. Content uses `<!--mm:replay KEY-->` or `<!--mm:loop-->` (tabbed
Listen → Decode → Decide → Make → Ship player); they appear on the home page, AI agents, the plugin page, the three solution
pages and five product pages. Videos load only when scrolled into view and play muted; reduced-motion users get the poster.

**Insight Chain game.** Visitors connect a persona to a pain point, pick the angle, watch the insight write itself and drag the TOFU/MOFU/BOFU expressions into Facebook, Instagram, LinkedIn and an SEO article (title + description in the slot, the full article draft in a popup), then press **Launch the campaign** for the results finale: an animated funnel shows where each shipped piece works (TOFU → reach, MOFU → engagement, BOFU → leads, the SEO article → search traffic; labelled as an illustration, no invented numbers), then an achievement card (time the player took, badges for first-try angle / full funnel / all 4 channels / SEO, SOMIN's "13× faster than manual research" claim), the real deliverables of that case study counting up (`delivered` in `SC`, copied from the case page), a **Book a call** button (the hero's Calendly link, `data-gtm-id="home_game_book_call"`), the next chain and the full chain recap. On a first visit on desktop the game is the first screen; "Skip to the website" / "Continue to the website" folds it into the **Play the game** button under the hero video (remembered in `localStorage` key `somin_ic_seen`). Returning visitors, phones (under 768 px), bots, automation (`navigator.webdriver`), deep links with a hash and internal navigation only get the button; the game is never shown inline under the hero. `?intro=1` forces the first-visit screen, `?intro=0` turns it off. The menu shows industries, never brand names; the first industry is picked at random on every visit ("Surprise me" picks another) and the brand is revealed when the game starts. Twelve case studies with complete insight chains are in the game (Reassured, Pepsi India, Analytic Partners, Vamp CEO Aaron Brooks, Ballroom Dance Academy, Fujifilm UK, SM Universe, Caltex Malaysia, inDrive Philippines, Thomson Medical, Tim Hortons Singapore, Nada Alkutbi; VIVA is excluded on request, and studies without a stated angle, tension or story such as Senoko, SICCI, YMCA and Heartware are left out). The page embeds only a small index (industry key, kind, chain count, faces); each case loads from `static/assets/game/cases/<id>.json` when its industry opens: personas, pain points, angles, chains, the full creative library (957 creatives in total; images reuse `static/assets/img/cases/expr/<case-slug>/` and `static/assets/img/game/<case>/`), the SEO article drafts and the SOMIN-bot tips. Every persona, pain point, angle, insight, proposition and creative line is copied from the case-study PDF on Drive, never invented; renders that show invented prices, free-trial offers or testimonials are left out of the tray, and ALL-CAPS creative copy is shown in sentence case. The **SOMIN bot** (animated from four SOMIN image-generate poses in `static/assets/img/game/bot/`) sits bottom-right and explains each step: a short explanation of the module (persona, pain point, angle, insight, propositions/expressions, results — from the SOMIN method and MCP tool descriptions) plus the case-specific reason, quoted from that case study with its page number. Its bubble opens on its own only the first time a visitor reaches each step (remembered in `localStorage` key `somin_ic_bot_seen`); on later passes the avatar only shows a new-message dot and opens when clicked, so it never covers the board. It closes on any outside click, `Hide tips` mutes it (`localStorage` key `somin_ic_bot`). **Wrong angles teach instead of just flipping:** each chain carries `why.miss.<angleId>` for every angle that is not its own (96 pairs across the 12 cases) — `s`, the one-line reason shown on the flipped card under "Not the best angle here", and `t`, the bot's explanation (what that lens explains, why it misreads this persona's pain point, and what kind of lens to look for, without naming the right one). The bot always opens for a miss (unless tips are hidden), labels it "Why this angle doesn't fit" in coral rather than as a case-study quote (it is coaching reasoned from the chain, so no page number), and adds "Where it fits in this study" with the pain point that angle was built for. Explanations use only the case data; a case without `why.miss` falls back to the old "Built for another pain point" card. **Wrong persona–pain links teach too:** each case carries `pmiss.<personaId>.<painId>` for every pair that is not a chain (84 pairs; Analytic Partners and Vamp have one persona, so none). Linking a persona to a pain point that isn't theirs shakes the card, toasts "Not a fit for this persona" and opens the bot with "Why this pain point doesn't fit" (who the persona is, what that tension is really about and whose it is, and what kind of tension to look for) plus "Whose pain point this is" with the persona it belongs to. Same rules: reasoned from the case data only, no page number; without `pmiss` the old "Not linked in this study" toast stays. The game uses a softer teal than the site's brand teal (`--ic-mint-rgb` / `--ic-hi-rgb` tokens on `.ic, .ic-play`; the SOMIN wordmark keeps the brand colour), and the generated stage background is toned with a CSS filter (`--ic-bg-tone`) rather than re-rendered. The SEO articles are drafts written from each chain (brand offers quoted from the case study, no added statistics) and are labelled as not published by the brand. Persona portraits and the stage background are SOMIN image-generate renders in `static/assets/img/game/`. UI strings are `ic_*` keys in the home dictionary (all 17 languages); events are `ic_*` in docs/TRACKING.md.

**Ratings and reviews.** G2 (4.5/5) and Capterra (5.0/5) rating plates (rating only, no review counts) sit in the home hero, the cases hub,
/try-somin/ and the footer; short verbatim excerpts from validated reviews appear as proof on the home page, AI agents, the
plugin page, the solution and product pages and the Click2View case (`data/reviews.json`, `<!--mm:reviews-->`). G2's own
star-rating widget needs a paid G2 plan, so the badges are SOMIN-styled and link to the profiles.

**Case-study heroes.** Every case-study page has its own topic background generated with SOMIN image-generate
(`static/assets/img/cases/bg/`).

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
  on the thank-you page that follows every Typeform submit (GTM version 51, Page Path triggers; the plugin thank-you page
  fires GA4 + Meta). `tracking.js` does not fire them itself, so nothing is counted twice.
* Key interactions (call clicks, form opens and submits, downloads, logins, replay plays) also reach the Meta pixel as
  custom events with `event_id` (GTM v51 tag "Facebook - somin key events (custom)").
* Debug: add `?debug_tracking=1` to any URL to log every event in the console; `?tracking=off` disables all tags.

Test result at hand-over: **76 / 76 checks passed** locally (GTM container v51; each lead conversion fires exactly once;
case-study PDFs and the Claude plugin download automatically after their forms; replays load and switch). Report:
`tests/tracking-report.json`.

## 6. SEO / AEO / GEO built in

* Canonical (apex, trailing slash), unique titles/descriptions, Open Graph + Twitter cards with absolute 1200×630 images.
* JSON-LD on every page: `Organization`, `WebSite`, `WebPage`, `BreadcrumbList`; `BlogPosting` + `Blog` on the blog;
  the original page-specific schema (FAQ, SoftwareApplication, etc.) is kept and normalised to `https://somin.ai/…/`.
* `sitemap.xml` with `lastmod`, `robots.txt` (AI answer engines explicitly allowed), `llms.txt` and `llms-full.txt`
  for LLM/answer-engine discovery, RSS at `/blog/rss.xml`.
* Clean URLs (`/slug/`), real 404 page, redirect stubs for retired Leadpages URLs, noindex on thank-you, lead and
  client-specific legal pages.
* Images converted to WebP and lazy-loaded; total site ~22 MB (was ~150 MB of Leadpages assets).
* Hygiene pass (Oct 2026): every indexable title ≤ 60 characters (`seo_title` in the meta header when the H1 is longer),
  every description 120–160 characters, one H1 per page, descriptive alt text on content and card images, FAQPage
  schema generated from visible FAQs where a page had none, BreadcrumbList on every page, VideoObject for each replay,
  and `llms.txt` now explains the five-step loop, the four questions and the free Claude plugin.
* Case studies (Oct 2026): all 45 case pages follow one outline (`docs/CASE_STUDY_SEO.md`): `<Client> Case Study: <Topic> | SOMIN`
  titles, 45–75 character H1s that name the client, descriptive H2s, a `<Client> case study FAQ`, visible breadcrumbs, related
  cases and a single Organization/WebPage/BreadcrumbList/Article/FAQPage graph (the old inline blocks pointed at non-existent
  `/case-studies/…` URLs). The Click2View and Nikki Taylor pages, which showed copies of other cases, and the thin Miraflora
  Wagyu × GWI page (now `/brands-miraflora-wagyu-gwi-case-study/`, redirected from `/case/`) were rebuilt from their PDFs.
* Research credibility: `/research/` lists Prof. Aleks Farseev's peer-reviewed papers (AAAI, ACM Multimedia, SIGIR, WSDM,
  The Web Conference, ACM TOIS…) and talks from `data/research.json`, with ScholarlyArticle and Person schema; research strips
  sit on the home, agents, product, solution, comparison and plugin pages, and a one-line credit on case studies, blog posts,
  the cases hub, /try-somin/, /vision/ and in the footer.

* SEO/AEO/GEO pass 2 (17 Oct 2026):
  * One JSON-LD graph per page; Organization, SoftwareApplication, WebSite and founder come from `data/organization.json`
    (15 pages had two FAQPage blocks and 14 had two conflicting Organization nodes). The home Organization now has a logo,
    `alternateName`, contact point, markets and the merged `sameAs` list.
  * `/pricing/` from `data/pricing.json` (the cloud.somin.ai plans sheet) with Offer schema, `/about/` (AboutPage entity page)
    and `/authors/` + one profile page per blog author; bylines link to them. All three are in the nav/footer and `llms.txt`.
  * 16 static translations of the home page (`/zh-hans/` … `/ru/`) with hreflang + x-default, translated title, description and
    FAQ schema; the hero language menu links to them and `<html lang>` follows the chosen language.
  * GTM starts on the first interaction or 2.5 s after load (see `docs/TRACKING.md`), cutting main-thread work on first paint.
  * `og:image:width/height` read from the actual image; sitemap `lastmod` from `data/content-dates.json` (+ hreflang links,
    no ignored `priority`); robots.txt repeats the Disallow lines for every named AI crawler (and lists more of them);
    case-study Articles carry `datePublished`/`dateModified`; three home H2s name SOMIN / the topic; ` -- ` became `—` in copy.

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
