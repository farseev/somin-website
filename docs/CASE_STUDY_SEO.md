# Case-study page standard (SEO, AEO, GEO)

Every published case study (legacy fragment pages in `content/pages/*case*.html`, `agencies-neo360.html`, `case.html`,
and the composed pages in `data/case-pages/<key>.json`) follows one outline, so search engines and answer engines
(Google AI Overviews, ChatGPT, Perplexity, Gemini) read every case the same way. `tests/check_static.py` enforces the
measurable rules below.

## Meta

| Field | Rule | Example |
|---|---|---|
| `title` / `seo_title` | 40–60 characters, pattern `<Client> Case Study: <Topic> \| SOMIN` | `Keeta HK Case Study: Food Delivery Ad Copy \| SOMIN` |
| `description` | 140–160 characters. One sentence that answers *what SOMIN did for the client and what it found*, with one real number from the page | `SOMIN benchmarked 145 Hong Kong food-delivery ads for Keeta HK and rewrote 72 bilingual ad lines around GWI audience data instead of price.` |
| `og_title`, `twitter_title` | Set by the builder from the H1. Don't hand-edit | |

## Outline

```
eyebrow   <Brand|Agency|Creator> case study · <Sector> · <Market>        (sentence case, " · " separators)
H1        names the client, states the main finding                      (45–75 characters, no full stop at the end)
lede      answer-first summary: who, what SOMIN analysed, what it found   (30–65 words)
  section tag + H2   one per content section                             (6–10 H2s per page)
    H3               items inside a section (personas, pillars, steps)
  tag "FAQ"          H2 "<Client> case study FAQ"                         (3–6 visible <details> questions)
  tag "About SOMIN"  entity paragraph (no heading needed)
  related cases      H2 "More <brand|agency|creator> case studies"       (added by the builder)
  final CTA          H2 "Get the full <Client> case study"
```

### H1

- Names the client (or the study subject when the client is unnamed, e.g. "anti-scam communications").
- 45–75 characters, sentence case, one or two clauses, no full stop at the end, no em dash.
- States the main finding with a concrete noun and, where possible, a number from the case.
- The highlighted part (legacy `<span class="sc-it">…</span>`, composed `h1_em`) is the final clause.

### H2

- 25–65 characters, sentence case, no full stop at the end, no em dash, no exclamation mark.
- Descriptive, not a slogan: a reader who sees only the H2 knows what the section contains
  ("145 ads from Keeta, Foodpanda and Deliveroo, benchmarked" rather than "One data pull.").
- At least three H2s per page name the client; numbers from the section are welcome.
- One idea per H2. Don't repeat the same H2 on two pages (the builder's standard H2s include the client name).

### Section tags (the small uppercase label above each H2)

Sentence case, 1–4 words, from this vocabulary where it fits: The client, The challenge, The approach, The data,
The competitive set, The trend, The whitespace, The audience, The persona, The pillars, The calendar, The creative,
Key findings, Results, Recommendations, The outcome, FAQ. A page-specific tag is fine when none fits.

### H3

- 60 characters or fewer where possible (quoted ad lines may run to 100), no full stop at the end.
- Never skip a level (no H4 directly under an H2).

## Schema (added by the builder)

One JSON-LD graph per case page: Organization, WebSite, WebPage, BreadcrumbList (Home › Case studies › Client),
Article (headline = H1, description, image, about = the client, author and publisher = SOMIN) and FAQPage built from
the visible FAQ. Pages carry no other JSON-LD; old inline blocks are dropped at build time.

## Content rules

All facts, numbers and names come from the case-study PDF or the existing page. Never invent or round numbers.
No reviewer or employee names, nobody called Aleks or a derivative. British or neutral spelling, plain English.
