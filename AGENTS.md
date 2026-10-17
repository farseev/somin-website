# Working on this repo (humans and AI coding agents)

Static marketing site for somin.ai, deployed to GitHub Pages by `.github/workflows/deploy.yml`.
Read `README.md` for the layout and `docs/TRACKING.md` before touching anything analytics-related.

## Commands

```
python3 build.py --serve          # build ./_site and serve on :8000
python3 tests/check_static.py     # must report PROBLEMS (0)
python3 tests/test_tracking.py    # must report N/N checks passed (needs: pip install playwright)
```

Run all three before every commit that changes content, templates, CSS or JS.

## Rules

1. **Edit sources, never `_site/`.** `_site/` is generated and git-ignored.
2. **No tags in pages.** Never add GTM snippets, gtag, fbq, LinkedIn, Clarity or any `<script src=…>` analytics to
   content files or `build.py`. Tracking lives only in `static/assets/js/tracking.js` (IDs in its `CONFIG` block).
   New events: `window.sominTrack('event_name', {...})` in JS, or `data-track="event_name"` on a link.
   Use snake_case event names and add them to the table in `docs/TRACKING.md`.
   Lead conversions fire in GTM on the thank-you pages (Page Path triggers); keep `/thank-you-trial-somin/`,
   `/thank-you-case-study/` and `/thank-you-plugin/` at those paths and don't fire Meta/LinkedIn/`generate_lead` from code
   (double counting).
3. **Lead CTAs are links with data attributes** — `href="/try-somin/" data-lead-form="trial"`,
   `href="/get-case-study/?cs=<key>" data-lead-form="case_study" data-case-study="<key>"` or
   `href="/marketing-mondays-plugin/" data-lead-form="plugin"` (free Claude plugin). Calls are plain
   `https://calendly.com/...` links. Do not embed Typeform/Calendly code in pages; never reintroduce Leadpages
   (`leadbox`, `lp-`, `leadpages.net`, `lpusercontent`) markup.
4. **Every page needs a meta header** with `slug`, `layout`, `title` (≤ 60 chars ideally), `description` (120–160 chars),
   and `og_image` (1200×630 JPG in `static/assets/img/og/`). One `<h1>` per page — the builder renders it for
   `post`/`doc` layouts, so blog and legal bodies start at `<h2>`.
5. **URLs** are lowercase, hyphenated, with a trailing slash (`/slug/`). Internal links are root-relative.
   When a URL changes, add the old one to `redirects` in `site.config.json`.
6. **Images**: WebP for content (max 1920 px wide), `loading="lazy"` except the first visible image,
   always `alt` text. Put files under `static/assets/img/…`; never hot-link Leadpages or Drive images.
7. **Brand**: teal `#2DBF9C`, ink `#16201F`, Montserrat only (all weights); wordmark "SO" teal + "MIN" white/ink, no spacing. Use the CSS custom properties
   in `site.css` (`--teal`, `--ink`, `--display`, `--body` …) instead of hard-coded values.
8. **Structured data**: keep page-specific JSON-LD in the meta `jsonld` array; the builder adds Organization,
   WebSite, WebPage and BreadcrumbList. Use `https://somin.ai/<path>/` (apex, trailing slash) in all schema URLs.
9. **Noindex** thank-you pages, gated/lead pages and client-specific legal docs (`"robots": "noindex,follow"`).
10. Python stays standard-library only; front-end stays dependency-free vanilla JS/CSS.
11. **Case studies** live in `data/case-studies.json` (Drive IDs + hub tile text). PDFs stay on Google Drive; never commit
    them to the repo (several exceed GitHub limits). Hub tile copy must come from the case study itself, never invented.
12. **Session replays** (recorded SOMIN agent runs from Marketing Mondays) live in `static/assets/video/<key>.mp4|.webm|.webp`
    and are listed in `data/replays.json`. Put them in content with `<!--mm:replay KEY-->` or the five-step player
    `<!--mm:loop-->`; the builder adds the markup and VideoObject schema. They load and play muted only while on screen.
13. **FAQ schema**: a visible `<details><summary>Q</summary>A</details>` FAQ gets FAQPage JSON-LD automatically when the page
    has none in its meta; keep answers in the visible HTML, never in schema only.
