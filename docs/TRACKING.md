# Tracking on somin.ai

One file — `static/assets/js/tracking.js` — is loaded synchronously in `<head>` of every page by `build.py`.
Nothing else on the site loads a tag, pixel or gtag. All IDs live in its `CONFIG` block.

## What loads

```
tracking.js ──► dataLayer (page context + attribution)
            ──► GTM-PZG88FPZ ──► GA4 G-XXM10JVHXY (page_view, scroll, somin_event forwarder)
                              ──► Google Ads AW-16476989673
                              ──► Meta pixel 719665876016415 (PageView, cta_click)
                              ──► LinkedIn Insight 6960748 / 2907724
                              ──► Microsoft Clarity pfshy7yc19
                              ──► Calendly listener (calendly.event_scheduled → generate_lead / Lead / LinkedIn 20526828)
            ──► Typeform embed SDK (on demand) — trial + case-study forms with hidden attribution fields
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
| `lead_form_open` | A Typeform popup is opened | `form_type` (trial / case_study), `case_study`, `cta_id` |
| `lead_form_view` | An inline Typeform (on /try-somin/, /get-case-study/) is shown | `form_type` |
| `lead_form_ready` / `lead_form_start` / `lead_form_close` | Typeform SDK lifecycle | `form_type` |
| `trial_form_submit` / `case_study_form_submit` | Typeform submitted | `form_type`, `case_study`, `response_id`, `cta_id` |
| `generate_lead` | Sent by GTM (not this script) when the thank-you page loads after a submit — GA4 key event | — |
| `lead_form_fallback` | Typeform SDK blocked → visitor sent to form.typeform.com with the same hidden fields | `form_type` |
| `thank_you_view` | Thank-you page viewed | `lead_type` |
| `case_study_download` | Download / preview button on /thank-you-case-study/ | `case_study`, `cta_text`, `link_url` |
| `book_call_click` | Any calendly.com link (opens popup) | `link_url` |
| `login_click` / `platform_click` | Links to cloud.somin.ai | `link_url` |
| `email_click` / `phone_click` | mailto: / tel: | — |
| `article_read_50` / `article_read_90` | Blog article depth (page path identifies the post) | — |
| `blog_filter` / `blog_search` / `share` | Blog index and article tools | `cta_text` = topic / query / share channel |
| any `data-track="x"` | Custom link tracking | `cta_text`, `cta_id`, `link_url` |

From code: `window.sominTrack('event_name', { … })`. Calendly bookings arrive as GTM's own `calendly` events
(`push_postmessage_events: false` avoids double counting).

## Attribution

Captured on landing and stored first-touch (90 days) + last-touch: `utm_*`, `gclid`, `gbraid`, `wbraid`, `fbclid`,
`li_fat_id`, `msclkid`, `ttclid`, `landing_page`, `referrer`, plus `ga_client_id`, `_fbp`, `_fbc` cookies.
They are sent as Typeform hidden fields and appended to Calendly as UTMs, so every lead in Typeform/Calendly
can be joined back to GA4 and ad platforms. `window.sominTracking.attributionFields()` returns the current set.

## GTM wiring for lead conversions (container version 50, published 16 Oct 2026)

Lead conversions live in GTM and fire on the thank-you page view that follows every Typeform submit:

| Trigger | Condition | Tags |
|---|---|---|
| [NEO] Somonitor - Thank You Page - Free Trial | Page Path contains `/thank-you-trial-somin` | GA4 generate_lead - trial, Facebook - Main - Somonitor Lead, LinkedIn - Main - Somonitor Lead (21236668) |
| somin.ai - Thank - You - Case | Page Path contains `/thank-you-case-study` | GA4 generate_lead - case_study, Facebook - Main - Case Study Lead, LinkedIn - Main - Case Study Lead (20526508) |
| [NEO] event_scheduled - calendly | dataLayer `calendly_event` = event_scheduled | GA4 generate_lead - calendly, Meta Lead, LinkedIn 20526828 |

Before version 50 those two thank-you triggers matched `Page URL contains https://www.somin.ai/thank-you-…/`.
`www.somin.ai` 301-redirects to `somin.ai`, so they never fired on the Leadpages site. Path matching works on both
the Leadpages site and this one (with or without the trailing slash).

`tracking.js` therefore does **not** fire conversions itself (`direct_conversions.enabled: false`) and does not push
`generate_lead`; it only records `trial_form_submit` / `case_study_form_submit` and then redirects to the thank-you page.
The test suite asserts each conversion fires exactly once. Keep it that way: if you ever turn `direct_conversions`
back on, remove the GTM thank-you triggers first.

Known trade-off of page-view conversions: reloading a thank-you page, or opening `/thank-you-case-study/` directly
(it shows the locked state), fires the conversion again. Both pages are noindexed and blocked in robots.txt.

Still in the container but dead (left untouched): `[NEO] Thank You Page` (`www.somin.ai/thank-you/`, a URL that
returns 404), `[NEO] SOADS - Thank You Page - Free Trial`, the GenAI Sandbox triggers and the
`thank_you_page_view` (Mothercare) custom event, which no page pushes any more.

Optional:

1. **Clarity**: two projects existed (`pfshy7yc19` in GTM, `ikcdjzmpym` hard-coded by Leadpages). Only the GTM one
   loads now. To use `ikcdjzmpym` instead, pause the GTM Clarity tag and put the ID in `CONFIG.clarity_id`.
2. Mark `generate_lead` (and optionally `case_study_download`, `book_call_click`) as key events in GA4.

## Testing

`tests/test_tracking.py` runs Chromium with a desktop user-agent, serves `_site/` as `https://somin.ai`
(request interception, so GTM's hostname rules behave as in production), records every hit to
Google, Meta, LinkedIn and Clarity and fulfils them with empty responses (nothing reaches your accounts).
It simulates Typeform submissions with the same `postMessage` the real embed sends, and a Calendly booking.

Sections covered: base tags on load · CTA clicks and Calendly popup with UTMs · Calendly booking conversion ·
trial Typeform popup, hidden fields, submit, redirect, GA4/Meta/LinkedIn conversions · case-study form →
instant download release, and the locked state on direct visits · login, scroll-depth and blog events ·
crawl of all 97 pages for JavaScript errors and a single GTM container.

```
python3 tests/test_tracking.py                      # local build
python3 tests/test_tracking.py --live --base https://somin.ai   # production, no interception
```

In a browser: `https://somin.ai/?debug_tracking=1` logs each event; GTM Preview / Tag Assistant works as usual.
Typeform test submissions: add `?tf_sandbox=1` so test responses are not counted in Typeform insights.
