# Tracking on somin.ai

One file — `static/assets/js/tracking.js` — is loaded in `<head>` of every page by `build.py`.
Nothing else on the site loads a tag, pixel or gtag. All IDs live in its `CONFIG` block.

**GTM starts late on purpose (Oct 2026, page speed).** tracking.js itself runs at once (dataLayer, attribution, link
handlers), but GTM and every tag in it start on the visitor's first interaction (pointer, key, touch, scroll) or
`gtm_delay_ms` (2.5 s) after the load event, whichever is first; also when the tab is hidden. Thank-you pages (lead
conversions) and `?debug_tracking=1` sessions start GTM immediately, and `?gtm=now` forces it on any page. Events
pushed before GTM starts wait in the dataLayer and are processed in order once it loads. Set `gtm_delay_ms` to 0 to go
back to loading GTM at once.

## What loads

```
tracking.js ──► dataLayer (page context + attribution)
            ──► GTM-PZG88FPZ ──► GA4 G-XXM10JVHXY (page_view, scroll, somin_event forwarder)
                              ──► Google Ads AW-16476989673
                              ──► Meta pixel 719665876016415 (PageView, cta_click)
                              ──► LinkedIn Insight 6960748 / 2907724
                              ──► Microsoft Clarity pfshy7yc19
                              ──► Calendly listener (calendly.event_scheduled → generate_lead / Lead / LinkedIn 20526828)
            ──► Typeform embed SDK (on demand) — trial, case-study and plugin forms with hidden attribution fields
            ──► Calendly popup widget (on demand) — UTMs passed through
            ──► (conversions) thank-you page view → GTM thank-you triggers → GA4 generate_lead, Meta Lead, LinkedIn 21236668 / 20526508
```

## dataLayer contract

Every page view pushes:

```js
{ page_type, page_template, content_group, somin_tracking_version }
```

Every interaction pushes one event shape (GA4 tag 142 in GTM forwards it as `event_name`):

```js
{ event: 'somin_event', event_name: 'lead_form_open', event_id: '…uuid…',
  funnel_stage: 'consideration', cta_text: 'Try SOMIN', cta_location: 'hero', … }
```

`[data-gtm-id]` clicks are additionally picked up by GTM's existing click triggers (GA4 `cta_click`,
Meta `cta_click`, LinkedIn conversion 20526804) — the builder puts `data-gtm-id` on nav and footer CTAs.

## Event dictionary

| event_name | When | Extra params |
|---|---|---|
| `lead_form_open` | A Typeform popup is opened | `form_type` (trial / case_study / plugin), `case_study`, `cta_id` |
| `lead_form_view` | An inline Typeform (on /try-somin/, /get-case-study/) is shown | `form_type` |
| `lead_form_ready` / `lead_form_start` / `lead_form_close` | Typeform SDK lifecycle | `form_type` |
| `trial_form_submit` / `case_study_form_submit` / `plugin_form_submit` | Typeform submitted (`<form_type>_form_submit`) | `form_type`, `case_study`, `response_id`, `cta_id` |
| `generate_lead` | Sent by GTM (not this script) when the thank-you page loads after a submit — GA4 key event | — |
| `lead_form_fallback` | Typeform SDK blocked → visitor sent to form.typeform.com with the same hidden fields | `form_type` |
| `thank_you_view` | Thank-you page viewed | `lead_type` |
| `case_study_download` | Download / preview button on /thank-you-case-study/ | `case_study`, `cta_text`, `link_url` |
| `case_study_auto_download` | The PDF download started automatically right after the form | `case_study`, `link_url` |
| `cases_filter` / `cases_search` | Section filter / search on /cases-ai-marketing-strategy/ | `cta_text` = section / query |
| `plugin_download` | Download buttons on /thank-you-plugin/ (.plugin file or Claude Code .zip) | `cta_text`, `link_url` |
| `plugin_auto_download` | The plugin download started automatically right after the plugin form | `link_url` |
| `rating_badge_click` | G2 / Capterra rating badge clicked (hero, footer, review sections) | `cta_id` = `rating_badge_g2` / `rating_badge_capterra` |
| `research_paper_click` / `research_pdf_click` | A peer-reviewed paper (publisher page or open-access PDF) opened from /research/, a research strip or a case study | `link_url` |
| `research_talk_click` | A talk or lecture (YouTube or event page) opened from /research/ or a research strip | `link_url` |
| `research_venue_click` / `research_profile_click` | Venue chip (AAAI, ACM MM, SIGIR…) or a research profile (Google Scholar, Semantic Scholar, ACM DL) clicked | `link_url` |
| `replay_play` | Visitor presses play on a session replay (they autoplay muted when on screen) | `cta_text` = replay question |
| `replay_step_click` | Step tab clicked in the five-step loop player (Listen … Ship) | `cta_text` = step |
| `book_call_click` | Any calendly.com link (opens popup) | `link_url` |
| `login_click` / `platform_click` | Links to cloud.somin.ai | `link_url` |
| `partner_click` | Strategic-partner logo links (home plate, Vision cards) and the Vision page's redemptive-marketing links (Forbes essay, faithdriven.sg, orthodox.sg) | `link_url`, `cta_text` (partner name on the home plate) |
| `email_click` / `phone_click` | mailto: / tel: | — |
| `article_read_50` / `article_read_90` | Blog article depth (page path identifies the post) | — |
| `blog_filter` / `blog_search` / `share` | Blog index and article tools | `cta_text` = topic / query / share channel |
| `pricing_plan_select` | "Select" under a plan in the /pricing/ table (jumps to the calculator) | `cta_id` = `pricing_select_<plan>` |
| `pricing_term_change` | Billing period switched on /pricing/ (monthly, annual, 2 or 3 years) | `term` |
| `pricing_checkout_click` | "Pay with Stripe" in the /pricing/ calculator (or the sales link for multi-year terms) | `link_url` |
| any `data-track="x"` | Custom link tracking | `cta_text`, `cta_id`, `link_url` |

From code: `window.sominTrack('event_name', { … })`. Calendly bookings arrive as GTM's own `calendly` events
(`push_postmessage_events: false` avoids double counting).

## Attribution

Captured on landing and stored first-touch (90 days) + last-touch: `utm_*`, `gclid`, `gbraid`, `wbraid`, `fbclid`,
`li_fat_id`, `msclkid`, `ttclid`, `landing_page`, `referrer`, plus `ga_client_id`, `_fbp`, `_fbc` cookies.
They are sent as Typeform hidden fields and appended to Calendly as UTMs, so every lead in Typeform/Calendly
can be joined back to GA4 and ad platforms. `window.sominTracking.attributionFields()` returns the current set.

## Lead routing: Typeform → Pipedrive → Slack (set up 18 Oct 2026)

Nothing in this repo sends leads anywhere; routing lives in Typeform and Pipedrive. The three forms are trial `jC5qqGJ0`,
case study `lHmWeOX7` and plugin `PI0VcVHp` (Typeform account "sominanalytics").

1. **Typeform → Pipedrive** (Typeform's "Pipedrive Classic" integration on each form, authorised as sominanalytics@gmail.com)
   creates a person, an organisation and a deal in **[SALES] MAIN → Qualified Leads**. Deal title = Company. Mapped fields:
   person name/email/phone, organisation name, and the deal fields `Website: Work Email`, `Website: Company`,
   `Website: Position`, `Website: Last Name`, `Website: Ad Budget`, `Website: Subject of Inquiry` (needs / enquiry),
   `Website: Lead Form` (`lead_type`), `Website: Case Study`, `Website: CTA` (`cta_id`), `Website: Landing Page`,
   `Website: Referrer` and `Website: UTM Source/Medium/Campaign/Term/Content` (hidden fields). The `Website: …` fields
   from Last Name onwards were added for this on 18 Oct 2026. The integration has no edit mode: to change a mapping,
   delete the form's Pipedrive integration and connect it again.
2. **Pipedrive automation** "[AUTO] Website lead (Typeform): owner Filipp, Booked date, post to #sales_main" (active for all
   users): when a deal is created in Qualified Leads with `Website: Work Email` filled, it sets owner = Filipp and
   Deal source = Inbound, sets the person's name to first + last name, owner = Filipp, Lead Source = Website Form and
   Booked = the lead's date, then posts to Slack **#sales_main** with `@channel`: form, company, name, email, phone, position,
   budget, needs, case study, CTA, landing page, referrer, UTMs and the deal link.
3. Typeform's own Slack integration on each form also posts to #sales_main (all fields, but no `@channel`). Once the
   Pipedrive post is confirmed with a test lead, switch it off in Typeform → Connect → Slack so each lead is posted once.

## GTM wiring for lead conversions (container version 52, published 17 Oct 2026)

The container (GTM-PZG88FPZ, renamed **somin.ai main website**) tracks the somin.ai main website only. The Google tags are
named **somin.ai main website** (Google Ads AW-16476989673 / GT-NNZ3QKBW) and **somin.ai main website (GA4)** (G-XXM10JVHXY / GT-TQDCQ46);
the GTM tag that loads GA4 is **Google tag - somin.ai main website (GA4)**.

Lead conversions live in GTM and fire on the thank-you page view that follows every Typeform submit:

| Trigger | Condition | Tags |
|---|---|---|
| somin.ai - Thank You - Trial | Page Path contains `/thank-you-trial-somin` | GA4 generate_lead - trial, Facebook - Main - Somonitor Lead, LinkedIn - Main - Somonitor Lead (21236668) |
| somin.ai - Thank - You - Case | Page Path contains `/thank-you-case-study` | GA4 generate_lead - case_study, Facebook - Main - Case Study Lead, LinkedIn - Main - Case Study Lead (20526508) |
| somin.ai - Thank You - Plugin | Page Path contains `/thank-you-plugin` | GA4 generate_lead - plugin, Facebook - Main - Plugin Lead (no LinkedIn conversion ID exists for the plugin yet) |
| Calendly - event_scheduled (somin.ai) | Custom Event `calendly`, `DLV - calendly_event` = event_scheduled (pushed by the tag **cHTML - Calendly listener (somin.ai)**) | GA4 generate_lead - calendly, Meta Lead, LinkedIn 20526828 |

Key interactions also reach the Meta pixel (version 51): trigger **CE - somin_event - key events** (Custom Event `somin_event`,
`DLV - event_name` matches `^(book_call_click|lead_form_open|trial_form_submit|case_study_form_submit|plugin_form_submit|case_study_download|case_study_auto_download|plugin_download|plugin_auto_download|login_click|replay_play)$`)
fires **Facebook - somin key events (custom)**, which sends the event under its own name with `event_id` (dedup) and
`content_name` / `content_category` = `cta_text` / `cta_location`. Use them in Meta for custom audiences and custom conversions.
GA4 already receives every `somin_event` through **GA4 - Router - somin_event**; LinkedIn gets CTA clicks through the
`[data-gtm-id]` click trigger (conversion 20526804).

Before version 50 the trial and case-study thank-you triggers matched `Page URL contains https://www.somin.ai/thank-you-…/`.
`www.somin.ai` 301-redirects to `somin.ai`, so they never fired on the Leadpages site. Path matching works on both
the Leadpages site and this one (with or without the trailing slash).

`tracking.js` therefore does **not** fire conversions itself (`direct_conversions.enabled: false`) and does not push
`generate_lead`; it only records `<form_type>_form_submit` and then redirects to the thank-you page.
The test suite asserts each conversion fires exactly once. Keep it that way: if you ever turn `direct_conversions`
back on, remove the GTM thank-you triggers first.

Known trade-off of page-view conversions: reloading a thank-you page, or opening `/thank-you-case-study/` directly
(it shows the locked state), fires the conversion again. Both pages are noindexed and blocked in robots.txt.

Version 52 cleanup (nothing deleted; everything can be unpaused from its folder):

- **Archive - cloud.somin.ai (paused, not tracked)**: the 13 Meta, Google Ads, GA4 and LinkedIn tags that fired on
  cloud.somin.ai registration, verification and welcome pages. The app is no longer tracked from this container.
  The GA4 stream "cloud.somin.ai Platform" (G-J0ZV27346P) was detached from the somin.ai Google tag and now sits on its
  own Google tag, "cloud.somin.ai (not tracked, detached from somin.ai)", which is installed nowhere.
- **Archive - [NEO] (paused, not used)**: the 15 agency-era `[NEO]` GA4 tags.
- Kept because live lead tags depend on them, renamed without the `[NEO]` prefix: the Calendly listener, the scroll-depth
  tag (`GA4 - scroll depth (somin.ai)` on trigger `Scroll depth 25/50/75/90 (somin.ai)`), the trial and Calendly triggers
  and `DLV - calendly_event`.
- Still present but harmless: the old `[NEO]` click-text triggers used by a few Meta/LinkedIn tags, the GenAI Sandbox
  triggers and the cloud.somin.ai triggers (their tags are paused). They only match the old Leadpages markup.

`login_click` / `platform_click` remain: they are clicks on somin.ai links that point to the app, measured on somin.ai.

Version 53 (go-live on GitHub Pages, 18 Oct 2026; nothing deleted, unpause from the folder to restore):

- **Archive - Leadpages site & duplicates (paused, not used)**, 46 tags:
  - `LinkedIn - cta_click (Unified)` sent conversion 20526804 a second time on every CTA click, next to `LinkedIn - cta_click`.
    Each CTA click now sends it once (checked on the live site).
  - `Test HTML` only wrote `console.log('test')` on every page.
  - 44 Leadpages-era Meta, Google Ads, GA4 and LinkedIn tags. Their triggers only matched the old site: `www.somonitor.ai`
    or `www.somin.ai/thank-you…` URLs, `lp-button-react` classes, and click texts that no longer exist on any page.
- Still live: the thank-you, plugin and Calendly lead tags, `GA4 - Router - somin_event`, `GA4 - cta_click`, scroll depth,
  Meta Pageview and key events, `LinkedIn - cta_click`, Google Ads remarketing, Conversion Linker and Clarity.

Version 54 (18 Oct 2026): `LinkedIn Insight Tags` (All Pages) is paused and in the same archive folder. It sent page views to
partner 2907724, which isn't in either SOMIN ad account (SoMin.ai 512925300 uses 6960748; Boost SOMIN 517674190 has no Insight
Tag). All SOMIN LinkedIn conversions (6960748: 20526804, 21236668, 20526508, 20526828) still fire.

Version 55 (18 Oct 2026): new tag **LinkedIn Insight - page view (SOMIN 6960748)** on All Pages, so SOMIN's own ad account gets
page views for retargeting and website demographics. Every page load now sends one page view to partner 6960748 and nothing to
2907724; `tests/test_tracking.py` checks "LinkedIn Insight loaded" and "LinkedIn page hit" pass again.

Optional:

1. **Clarity**: two projects existed (`pfshy7yc19` in GTM, `ikcdjzmpym` hard-coded by Leadpages). Only the GTM one
   loads now. To use `ikcdjzmpym` instead, pause the GTM Clarity tag and put the ID in `CONFIG.clarity_id`.
2. Mark `generate_lead` (and optionally `case_study_download`, `plugin_download`, `book_call_click`) as key events in GA4.
3. LinkedIn: create a URL-based conversion for `/thank-you-plugin/` in Campaign Manager (the Insight tag already records the page view),
   or add a conversion ID and a LinkedIn tag on the plugin trigger in GTM.

## Testing

`tests/test_tracking.py` runs Chromium with a desktop user-agent, serves `_site/` as `https://somin.ai`
(request interception, so GTM's hostname rules behave as in production), records every hit to
Google, Meta, LinkedIn and Clarity and fulfils them with empty responses (nothing reaches your accounts).
It simulates Typeform submissions with the same `postMessage` the real embed sends, and a Calendly booking.

Sections covered: base tags on load · CTA clicks and Calendly popup with UTMs · Calendly booking conversion ·
trial Typeform popup, hidden fields, submit, redirect, GA4/Meta/LinkedIn conversions · case-study form →
instant download release, and the locked state on direct visits · cases hub · home-hero plugin card → plugin form →
auto-download + GA4/Meta conversions + Meta key events · session replays (load, tab switch, VideoObject) ·
login, scroll-depth and blog events · crawl of all 100 pages for JavaScript errors and a single GTM container.

```
python3 tests/test_tracking.py                      # local build
python3 tests/test_tracking.py --live --base https://somin.ai   # production, no interception
```

In a browser: `https://somin.ai/?debug_tracking=1` logs each event; GTM Preview / Tag Assistant works as usual.
Typeform test submissions: add `?tf_sandbox=1` so test responses are not counted in Typeform insights.
