/*!
 * SOMIN — shared tracking & lead-capture script (one file for every page).
 *
 * What it does
 *   1. Loads Google Tag Manager once (GTM holds GA4, Google Ads, Meta pixel, LinkedIn Insight, Clarity #2).
 *   2. Loads Microsoft Clarity (direct project) once.
 *   3. Captures attribution (UTMs + click IDs, first & last touch) and passes it to Typeform/Calendly.
 *   4. Opens Typeform lead forms (popup or inline) and Calendly booking popups from plain links.
 *   5. Pushes clean, named events to the dataLayer as `somin_event` (GA4 tag "somin_event" in GTM
 *      forwards them using `event_name`). Lead conversions (GA4 generate_lead, Meta Lead, LinkedIn) fire in GTM
 *      on the thank-you page view, so this script redirects there after every Typeform submit.
 *
 * How to use in HTML (no inline JS needed)
 *   <a href="/try-somin/" data-lead-form="trial" data-gtm-id="hero_try">Try SOMIN</a>
 *   <a href="/get-case-study/?cs=brands-fujifilm-case-study" data-lead-form="case_study"
 *      data-case-study="brands-fujifilm-case-study">Download the case study</a>
 *   <a href="https://calendly.com/filipp-lugovoi/30min">Book a call</a>   (auto popup)
 *   <div data-lead-form-inline="trial"></div>                              (inline form)
 *   JS:  window.sominTrack('my_event', {cta_text: '...'})
 *
 * Debug: add ?debug_tracking=1 to any URL (remembered for the session) to log every event to the console.
 * Disable on a page view: ?tracking=off
 */
(function (w, d) {
  'use strict';

  /* ===================== CONFIG — edit here (single source of truth) ===================== */
  var CONFIG = /*CONFIG_START*/{
    "gtm_id": "GTM-PZG88FPZ",
    "clarity_id": "",
    "_clarity_doc": "GTM already loads Microsoft Clarity project pfshy7yc19 on every page. Leadpages ALSO loaded project ikcdjzmpym directly, and two Clarity projects on one page collide (JS error 'reading unshift' on the live site). Put 'ikcdjzmpym' here only after pausing the Clarity tag in GTM.",
    "ga4_measurement_id": "G-XXM10JVHXY",
    "meta_pixel_id": "719665876016415",
    "linkedin_partner_ids": ["6960748", "2907724"],
    "direct_conversions": {
      "_doc": "OFF: since GTM version 50 the lead conversions (GA4 generate_lead, Meta Lead, LinkedIn 21236668 / 20526508) fire in GTM on the thank-you page view (Page Path contains /thank-you-trial-somin or /thank-you-case-study). Only set enabled=true if those GTM triggers are removed, otherwise Meta/LinkedIn leads are counted twice.",
      "enabled": false,
      "meta_event": "Lead",
      "linkedin_conversion_ids": { "trial": 21236668, "case_study": 20526508 }
    },
    "lead_forms": {
      "trial":      { "typeform_id": "jC5qqGJ0", "label": "Try SOMIN", "thank_you": "/thank-you-trial-somin/" },
      "case_study": { "typeform_id": "lHmWeOX7", "label": "Case study request", "thank_you": "/thank-you-case-study/" }
    },
    "typeform": {
      "embed_js": "https://embed.typeform.com/next/embed.js",
      "embed_css": ["https://embed.typeform.com/next/css/popup.css", "https://embed.typeform.com/next/css/widget.css"],
      "redirect_delay_ms": 1200,
      "sandbox_param": "tf_sandbox"
    },
    "calendly": {
      "default_url": "https://calendly.com/filipp-lugovoi/30min",
      "widget_js": "https://assets.calendly.com/assets/external/widget.js",
      "widget_css": "https://assets.calendly.com/assets/external/widget.css",
      "popup": true,
      "push_postmessage_events": false,
      "_doc": "GTM (Custom HTML tag 'calendly listener') already turns Calendly postMessages into dataLayer 'calendly' events, so push_postmessage_events stays false to avoid double counting."
    },
    "attribution": {
      "params": ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "gbraid", "wbraid", "fbclid", "li_fat_id", "msclkid", "ttclid"],
      "first_touch_days": 90
    },
    "consent": { "respect_gpc": false, "default": null },
    "debug_param": "debug_tracking"
  }/*CONFIG_END*/;
  /* ======================================================================================= */

  var VERSION = '1.0.0';
  var loc = w.location;
  var qs = new URLSearchParams(loc.search);
  var api = w.sominTracking = w.sominTracking || {};
  api.version = VERSION;
  api.config = CONFIG;
  api.log = api.log || [];

  var store = {
    get: function (k, s) { try { return JSON.parse((s ? w.sessionStorage : w.localStorage).getItem(k)); } catch (e) { return null; } },
    set: function (k, v, s) { try { (s ? w.sessionStorage : w.localStorage).setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  if (qs.get(CONFIG.debug_param) === '1') store.set('somin_debug', true, true);
  if (qs.get(CONFIG.debug_param) === '0') store.set('somin_debug', false, true);
  var DEBUG = !!store.get('somin_debug', true);
  var DISABLED = qs.get('tracking') === 'off';

  w.dataLayer = w.dataLayer || [];
  function gtag() { w.dataLayer.push(arguments); }

  function dl(obj) {
    w.dataLayer.push(obj);
    api.log.push(obj);
    if (DEBUG && w.console) console.log('%c[somin-tracking]', 'color:#2DBF9C;font-weight:700', obj.event || '(data)', obj);
  }

  function uuid() {
    if (w.crypto && w.crypto.randomUUID) return w.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
    });
  }

  function cookie(name) {
    var m = d.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  }

  function loadScript(src, attrs) {
    return new Promise(function (resolve, reject) {
      var existing = d.querySelector('script[src="' + src + '"]');
      if (existing) { if (existing.dataset.loaded) return resolve(); existing.addEventListener('load', function () { resolve(); }); existing.addEventListener('error', reject); return; }
      var s = d.createElement('script'); s.src = src; s.async = true;
      if (attrs) for (var k in attrs) s.setAttribute(k, attrs[k]);
      s.onload = function () { s.dataset.loaded = '1'; resolve(); };
      s.onerror = reject;
      d.head.appendChild(s);
    });
  }
  function loadCss(href) {
    if (d.querySelector('link[href="' + href + '"]')) return;
    var l = d.createElement('link'); l.rel = 'stylesheet'; l.href = href; d.head.appendChild(l);
  }

  /* ---------------- page context (available to GTM as dataLayer variables) ---------------- */
  var html = d.documentElement;
  var page = {
    page_type: html.getAttribute('data-page-type') || 'page',
    page_template: html.getAttribute('data-page-layout') || '',
    content_group: html.getAttribute('data-content-group') || '',
    page_path: loc.pathname
  };

  /* ---------------- attribution ---------------- */
  function captureAttribution() {
    var found = {}, any = false;
    CONFIG.attribution.params.forEach(function (p) { var v = qs.get(p); if (v) { found[p] = v.slice(0, 200); any = true; } });
    var ref = d.referrer && d.referrer.indexOf(loc.host) === -1 ? d.referrer : '';
    var now = Date.now();
    var ft = store.get('somin_attr_ft');
    if (!ft || (now - ft.ts) > CONFIG.attribution.first_touch_days * 864e5) {
      ft = { ts: now, landing_page: loc.pathname, referrer: ref };
      for (var k in found) ft[k] = found[k];
      store.set('somin_attr_ft', ft);
    }
    var lt = store.get('somin_attr_lt', true);
    if (any || !lt) {
      lt = { ts: now, landing_page: loc.pathname, referrer: ref };
      for (var k2 in found) lt[k2] = found[k2];
      store.set('somin_attr_lt', lt, true);
    }
    return { first: ft, last: lt };
  }
  var attribution = captureAttribution();
  api.attribution = attribution;

  function attributionFields() {
    var lt = attribution.last || {}, ft = attribution.first || {}, out = {};
    CONFIG.attribution.params.forEach(function (p) { var v = lt[p] || ft[p]; if (v) out[p] = v; });
    out.landing_page = ft.landing_page || lt.landing_page || '';
    out.referrer = lt.referrer || ft.referrer || '';
    var ga = cookie('_ga'); if (ga) out.ga_client_id = ga.split('.').slice(-2).join('.');
    var fbp = cookie('_fbp'); if (fbp) out.fbp = fbp;
    var fbc = cookie('_fbc'); if (fbc) out.fbc = fbc;
    return out;
  }
  api.attributionFields = attributionFields;

  /* ---------------- consent (optional) ---------------- */
  if (CONFIG.consent && CONFIG.consent.default) gtag('consent', 'default', CONFIG.consent.default);
  if (CONFIG.consent && CONFIG.consent.respect_gpc && navigator.globalPrivacyControl) {
    gtag('consent', 'default', { ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });
  }

  /* ---------------- boot tags ---------------- */
  dl({ page_type: page.page_type, page_template: page.page_template, content_group: page.content_group, somin_tracking_version: VERSION });

  if (!DISABLED) {
    if (CONFIG.gtm_id) {
      dl({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
      var g = d.createElement('script'); g.async = true; g.src = 'https://www.googletagmanager.com/gtm.js?id=' + CONFIG.gtm_id;
      (d.head || d.documentElement).appendChild(g);
    }
    if (CONFIG.clarity_id) {
      w.clarity = w.clarity || function () { (w.clarity.q = w.clarity.q || []).push(arguments); };
      var c = d.createElement('script'); c.async = true; c.src = 'https://www.clarity.ms/tag/' + CONFIG.clarity_id;
      (d.head || d.documentElement).appendChild(c);
      w.clarity('set', 'page_type', page.page_type);
    }
  }

  /* ---------------- event API ---------------- */
  // Every custom event goes out as `somin_event` so the existing GA4 tag (event name = {{event_name}},
  // params event_id / funnel_stage / cta_text / cta_location) forwards it without GTM changes.
  function track(name, params) {
    params = params || {};
    var o = {
      event: 'somin_event',
      event_name: name,
      event_id: params.event_id || uuid(),
      funnel_stage: params.funnel_stage || '',
      cta_text: params.cta_text || '',
      cta_location: params.cta_location || loc.pathname
    };
    for (var k in params) if (!(k in o)) o[k] = params[k];
    if (params.eventCallback) { o.eventCallback = params.eventCallback; o.eventTimeout = params.eventTimeout || 1500; }
    dl(o);
    return o.event_id;
  }
  w.sominTrack = track;
  api.track = track;

  function ctaInfo(el) {
    var gid = el.closest('[data-gtm-id]');
    return {
      cta_text: (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 100),
      cta_id: gid ? gid.getAttribute('data-gtm-id') : '',
      cta_location: loc.pathname
    };
  }

  /* ---------------- direct pixel conversions ---------------- */
  function fireConversions(formType, eventId, extra) {
    var dc = CONFIG.direct_conversions || {};
    if (!dc.enabled || DISABLED) return;
    try {
      if (w.fbq && dc.meta_event) {
        w.fbq('track', dc.meta_event, { content_name: formType, content_category: (extra && extra.case_study) || '' }, { eventID: eventId });
      }
    } catch (e) {}
    try {
      var id = dc.linkedin_conversion_ids && dc.linkedin_conversion_ids[formType];
      if (w.lintrk && id) w.lintrk('track', { conversion_id: id });
    } catch (e) {}
  }
  api.fireConversions = fireConversions;

  /* ---------------- Typeform ---------------- */
  var tfReady = null;
  function loadTypeform() {
    if (tfReady) return tfReady;
    CONFIG.typeform.embed_css.forEach(loadCss);
    tfReady = loadScript(CONFIG.typeform.embed_js).then(function () {
      if (!w.tf) throw new Error('typeform sdk missing');
      return w.tf;
    });
    return tfReady;
  }

  function leadContext(formType, el) {
    var ctx = ctaInfo(el || d.body);
    ctx.form_type = formType;
    ctx.case_study = el ? (el.getAttribute('data-case-study') || '') : '';
    ctx.case_study_label = el ? (el.getAttribute('data-case-study-label') || '') : '';
    if (!ctx.case_study && formType === 'case_study') ctx.case_study = qs.get('cs') || '';
    return ctx;
  }

  function hiddenFields(ctx) {
    var h = attributionFields();
    h.page_url = loc.origin + loc.pathname;
    h.page_path = loc.pathname;
    h.cta_id = ctx.cta_id || '';
    h.lead_type = ctx.form_type;
    if (ctx.case_study) h.case_study = ctx.case_study;
    for (var k in h) { if (h[k] === '' || h[k] == null) delete h[k]; else h[k] = String(h[k]).slice(0, 250); }
    return h;
  }

  function typeformOptions(formType, ctx, onDone) {
    var started = false, submitted = false;
    var opts = {
      hidden: hiddenFields(ctx),
      medium: 'somin-site',
      autoClose: false,
      enableSandbox: qs.get(CONFIG.typeform.sandbox_param) === '1',
      onReady: function () { track('lead_form_ready', { funnel_stage: 'consideration', form_type: formType, case_study: ctx.case_study, cta_text: ctx.cta_text }); },
      onStarted: function (e) {
        if (started) return; started = true;
        track('lead_form_start', { funnel_stage: 'consideration', form_type: formType, case_study: ctx.case_study, cta_text: ctx.cta_text, response_id: e && e.responseId });
      },
      onSubmit: function (e) {
        if (submitted) return; submitted = true;
        var rid = (e && e.responseId) || uuid();
        onLeadSubmitted(formType, ctx, rid, onDone);
      },
      onClose: function () {
        if (!submitted) track('lead_form_close', { funnel_stage: 'consideration', form_type: formType, case_study: ctx.case_study, started: started });
      }
    };
    return opts;
  }

  function onLeadSubmitted(formType, ctx, rid, onDone) {
    var form = CONFIG.lead_forms[formType] || {};
    if (formType === 'case_study' && ctx.case_study) {
      // unlocks /thank-you-case-study/?cs=<key> in this browser (local + session, in case one of them is blocked)
      store.set('somin_cs_unlocked_' + ctx.case_study, { rid: rid, ts: Date.now() });
      store.set('somin_cs_unlocked_' + ctx.case_study, { rid: rid, ts: Date.now() }, true);
    }
    store.set('somin_lead_' + formType, { rid: rid, ts: Date.now() }, true);
    fireConversions(formType, rid, ctx);
    var redirected = false;
    function go() {
      if (redirected) return; redirected = true;
      if (onDone) return onDone(rid);
      if (!form.thank_you) return;
      var u = new URL(form.thank_you, loc.origin);
      u.searchParams.set('rid', rid);
      if (ctx.case_study) u.searchParams.set('cs', ctx.case_study);
      u.searchParams.set('from', loc.pathname);
      loc.assign(u.toString());
    }
    // The conversion itself (GA4 generate_lead, Meta Lead, LinkedIn) fires in GTM on the thank-you page view.
    // This event only records the submit; the redirect waits for GTM to flush it.
    track(formType === 'trial' ? 'trial_form_submit' : 'case_study_form_submit', {
      event_id: rid, funnel_stage: 'conversion', form_type: formType, lead_type: formType, case_study: ctx.case_study,
      cta_text: ctx.cta_text, cta_id: ctx.cta_id, response_id: rid,
      eventCallback: function () { setTimeout(go, 150); }, eventTimeout: CONFIG.typeform.redirect_delay_ms
    });
    setTimeout(go, CONFIG.typeform.redirect_delay_ms + 600); // safety net if GTM is blocked
  }
  api._onLeadSubmitted = onLeadSubmitted;

  function fallbackUrl(formType, ctx) {
    var form = CONFIG.lead_forms[formType];
    var h = hiddenFields(ctx), parts = [];
    for (var k in h) parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(h[k]));
    return 'https://form.typeform.com/to/' + form.typeform_id + '#' + parts.join('&');
  }

  function openLeadForm(formType, el) {
    var form = CONFIG.lead_forms[formType];
    if (!form) return false;
    var ctx = leadContext(formType, el);
    track('lead_form_open', { funnel_stage: 'consideration', form_type: formType, case_study: ctx.case_study, cta_text: ctx.cta_text, cta_id: ctx.cta_id });
    loadTypeform().then(function (tf) {
      var popup = tf.createPopup(form.typeform_id, typeformOptions(formType, ctx));
      popup.open();
      api._popup = popup;
    }).catch(function () {
      track('lead_form_fallback', { form_type: formType, case_study: ctx.case_study });
      w.open(fallbackUrl(formType, ctx), '_blank', 'noopener');
    });
    return true;
  }
  api.openLeadForm = openLeadForm;
  w.sominOpenLeadForm = openLeadForm;

  function mountInlineForms() {
    var nodes = d.querySelectorAll('[data-lead-form-inline]');
    if (!nodes.length) return;
    loadTypeform().then(function (tf) {
      Array.prototype.forEach.call(nodes, function (node) {
        if (node.dataset.mounted) return; node.dataset.mounted = '1';
        var formType = node.getAttribute('data-lead-form-inline');
        var form = CONFIG.lead_forms[formType]; if (!form) return;
        var ctx = leadContext(formType, node);
        ctx.cta_text = ctx.cta_text || (form.label + ' (inline)');
        var opts = typeformOptions(formType, ctx);
        opts.container = node;
        opts.inlineOnMobile = true;
        opts.height = parseInt(node.getAttribute('data-height') || '620', 10);
        node.innerHTML = '';
        tf.createWidget(form.typeform_id, opts);
        track('lead_form_view', { funnel_stage: 'consideration', form_type: formType, case_study: ctx.case_study });
      });
    }).catch(function () {
      Array.prototype.forEach.call(nodes, function (node) {
        var formType = node.getAttribute('data-lead-form-inline');
        var a = node.querySelector('a[data-fallback]');
        if (a) a.href = fallbackUrl(formType, leadContext(formType, node));
      });
    });
  }

  /* ---------------- Calendly ---------------- */
  var calReady = null;
  function loadCalendly() {
    if (calReady) return calReady;
    loadCss(CONFIG.calendly.widget_css);
    calReady = loadScript(CONFIG.calendly.widget_js).then(function () {
      if (!w.Calendly) throw new Error('calendly missing');
      // Some page sections ship their own Calendly hook; ignore a second popup request in the same click.
      if (!w.Calendly.__sominGuard) {
        var orig = w.Calendly.initPopupWidget, last = 0;
        w.Calendly.initPopupWidget = function () {
          var now = Date.now(); if (now - last < 800) return; last = now;
          return orig.apply(this, arguments);
        };
        w.Calendly.__sominGuard = true;
      }
      return w.Calendly;
    });
    return calReady;
  }
  function calendlyUrl(href) {
    var u = new URL(href, loc.origin);
    var a = attributionFields();
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'].forEach(function (k) { if (a[k] && !u.searchParams.get(k)) u.searchParams.set(k, a[k]); });
    if (!u.searchParams.get('utm_source')) u.searchParams.set('utm_source', 'somin.ai');
    if (!u.searchParams.get('utm_content')) u.searchParams.set('utm_content', loc.pathname.slice(0, 100));
    return u.toString();
  }
  function openCalendly(href, el) {
    var info = ctaInfo(el || d.body);
    track('book_call_click', { funnel_stage: 'intent', cta_text: info.cta_text, cta_id: info.cta_id, link_url: href.split('?')[0] });
    if (!CONFIG.calendly.popup) { w.open(calendlyUrl(href), '_blank', 'noopener'); return; }
    loadCalendly().then(function (Cal) { Cal.initPopupWidget({ url: calendlyUrl(href) }); })
      .catch(function () { w.open(calendlyUrl(href), '_blank', 'noopener'); });
  }
  api.openCalendly = openCalendly;

  if (CONFIG.calendly.push_postmessage_events) {
    w.addEventListener('message', function (e) {
      if (e.origin.indexOf('calendly.com') === -1 || !e.data || !e.data.event || e.data.event.indexOf('calendly.') !== 0) return;
      dl({ event: 'calendly', calendly_event: e.data.event.split('.')[1] });
    });
  }

  /* ---------------- click delegation ---------------- */
  d.addEventListener('click', function (e) {
    if (e.defaultPrevented && !e.__somin) return;
    var a = e.target.closest && e.target.closest('a, button, [data-lead-form]');
    if (!a) return;
    var modified = e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1;

    var lf = a.getAttribute('data-lead-form');
    if (lf && !modified) {
      if (openLeadForm(lf, a)) { e.preventDefault(); }
      return;
    }
    var href = a.getAttribute('href') || '';
    if (!href) return;
    if (/^https?:\/\/(?:www\.)?calendly\.com\//i.test(href) && !modified && !a.hasAttribute('data-no-popup')) {
      e.preventDefault();
      openCalendly(href, a);
      return;
    }
    var info = ctaInfo(a);
    if (/^https?:\/\/cloud\.somin\.ai\//i.test(href)) {
      track(/signin|login/i.test(href) ? 'login_click' : 'platform_click', { funnel_stage: 'intent', cta_text: info.cta_text, cta_id: info.cta_id, link_url: href.split('?')[0] });
    } else if (/^mailto:/i.test(href)) {
      track('email_click', { funnel_stage: 'intent', cta_text: info.cta_text });
    } else if (/^tel:/i.test(href)) {
      track('phone_click', { funnel_stage: 'intent', cta_text: info.cta_text });
    } else if (a.hasAttribute('data-track')) {
      track(a.getAttribute('data-track'), { funnel_stage: a.getAttribute('data-funnel-stage') || '', cta_text: info.cta_text, cta_id: info.cta_id, link_url: href });
    }
  }, true);

  /* ---------------- thank-you pages ---------------- */
  function thankYou() {
    if (page.page_type !== 'thank_you') return;
    var rid = qs.get('rid');
    track('thank_you_view', { funnel_stage: 'conversion', form_type: html.getAttribute('data-lead-type') || '', case_study: qs.get('cs') || '', response_id: rid || '', from_page: qs.get('from') || '' });
  }

  function onReady(fn) { if (d.readyState !== 'loading') fn(); else d.addEventListener('DOMContentLoaded', fn); }
  onReady(function () {
    mountInlineForms();
    thankYou();
    var auto = qs.get('open');
    if (auto && CONFIG.lead_forms[auto]) openLeadForm(auto, null);
  });
})(window, document);
