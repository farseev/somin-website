/* SOMIN — site UI behaviour (navigation, blog filters, countdowns, case-study download release).
   Tracking lives in tracking.js; this file only calls window.sominTrack() when it needs to record something. */
(function (w, d) {
  'use strict';
  var track = function (n, p) { if (w.sominTrack) w.sominTrack(n, p); };

  /* ---------- header: mobile menu + dropdowns ---------- */
  var header = d.querySelector('.site-header');
  if (header) {
    var toggle = header.querySelector('.nav-toggle');
    var nav = header.querySelector('.site-nav');
    if (toggle && nav) {
      toggle.addEventListener('click', function () {
        var open = header.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        d.documentElement.classList.toggle('nav-locked', open);
      });
    }
    header.querySelectorAll('.nav-item.has-sub > .nav-sub-toggle').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var item = btn.parentElement, open = !item.classList.contains('is-open');
        header.querySelectorAll('.nav-item.is-open').forEach(function (x) { if (x !== item) { x.classList.remove('is-open'); x.querySelector('.nav-sub-toggle').setAttribute('aria-expanded', 'false'); } });
        item.classList.toggle('is-open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });
    d.addEventListener('click', function (e) {
      if (!e.target.closest('.nav-item.has-sub')) header.querySelectorAll('.nav-item.is-open').forEach(function (x) { x.classList.remove('is-open'); });
    });
    d.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { header.classList.remove('is-open'); d.documentElement.classList.remove('nav-locked'); header.querySelectorAll('.nav-item.is-open').forEach(function (x) { x.classList.remove('is-open'); }); }
    });
    var onScroll = function () { header.classList.toggle('is-scrolled', w.scrollY > 8); };
    w.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  }

  /* ---------- countdowns: <div data-countdown="1759878000000"> ---------- */
  d.querySelectorAll('[data-countdown]').forEach(function (el) {
    var end = parseInt(el.getAttribute('data-countdown'), 10);
    var f = function (k, v) { var n = el.querySelector('[data-cd="' + k + '"]'); if (n) n.textContent = v; };
    var tick = function () {
      var s = Math.max(0, Math.floor((end - Date.now()) / 1000));
      f('d', Math.floor(s / 86400)); f('h', Math.floor(s % 86400 / 3600)); f('m', Math.floor(s % 3600 / 60)); f('s', s % 60);
      if (s > 0) setTimeout(tick, 1000);
    };
    tick();
  });

  /* ---------- blog index: topic filter + search ---------- */
  var grid = d.querySelector('[data-post-grid]');
  if (grid) {
    var cards = Array.prototype.slice.call(grid.querySelectorAll('[data-post]'));
    var chips = d.querySelectorAll('[data-topic]');
    var search = d.querySelector('[data-post-search]');
    var empty = d.querySelector('[data-post-empty]');
    var count = d.querySelector('[data-post-count]');
    var state = { topic: 'all', q: '' };
    var apply = function () {
      var shown = 0;
      cards.forEach(function (c) {
        var okT = state.topic === 'all' || (c.getAttribute('data-tags') || '').split('|').indexOf(state.topic) > -1;
        var okQ = !state.q || (c.getAttribute('data-search') || '').indexOf(state.q) > -1;
        var ok = okT && okQ; c.hidden = !ok; if (ok) shown++;
      });
      if (empty) empty.hidden = shown > 0;
      if (count) count.textContent = shown;
    };
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        state.topic = chip.getAttribute('data-topic');
        chips.forEach(function (c) { c.setAttribute('aria-pressed', c === chip ? 'true' : 'false'); });
        apply();
        track('blog_filter', { cta_text: state.topic, funnel_stage: 'awareness' });
        try { history.replaceState(null, '', state.topic === 'all' ? location.pathname : '#topic=' + encodeURIComponent(state.topic)); } catch (e) {}
      });
    });
    if (search) {
      var t; search.addEventListener('input', function () {
        state.q = search.value.trim().toLowerCase(); apply();
        clearTimeout(t); t = setTimeout(function () { if (state.q) track('blog_search', { cta_text: state.q.slice(0, 60), funnel_stage: 'awareness' }); }, 900);
      });
    }
    var m = location.hash.match(/topic=([^&]+)/);
    if (m) { var want = decodeURIComponent(m[1]); chips.forEach(function (c) { if (c.getAttribute('data-topic') === want) c.click(); }); }
  }

  /* ---------- article: TOC highlight, share, progress ---------- */
  var article = d.querySelector('[data-article]');
  if (article) {
    var bar = d.querySelector('.read-progress span');
    var tocLinks = Array.prototype.slice.call(d.querySelectorAll('.toc a'));
    var heads = tocLinks.map(function (a) { return d.getElementById(a.getAttribute('href').slice(1)); }).filter(Boolean);
    var sent = {};
    var onS = function () {
      var r = article.getBoundingClientRect();
      var p = Math.min(1, Math.max(0, (w.innerHeight - r.top) / (r.height + w.innerHeight * 0.2)));
      if (bar) bar.style.transform = 'scaleX(' + p + ')';
      [50, 90].forEach(function (q) { if (p * 100 >= q && !sent[q]) { sent[q] = 1; track('article_read_' + q, { funnel_stage: 'awareness' }); } });
      var cur = null; heads.forEach(function (h) { if (h.getBoundingClientRect().top < 140) cur = h.id; });
      tocLinks.forEach(function (a) { a.classList.toggle('is-active', a.getAttribute('href') === '#' + cur); });
    };
    w.addEventListener('scroll', onS, { passive: true }); onS();
    d.querySelectorAll('[data-copy-link]').forEach(function (b) {
      b.addEventListener('click', function () {
        var done = function () { b.classList.add('is-done'); setTimeout(function () { b.classList.remove('is-done'); }, 1600); };
        if (navigator.clipboard) navigator.clipboard.writeText(location.href.split('#')[0]).then(done, done); else done();
        track('share', { cta_text: 'copy_link', funnel_stage: 'awareness' });
      });
    });
    d.querySelectorAll('[data-share]').forEach(function (a) {
      a.addEventListener('click', function () { track('share', { cta_text: a.getAttribute('data-share'), funnel_stage: 'awareness' }); });
    });
  }

  /* ---------- thank-you-case-study: release + auto-start the download ---------- */
  // Unlocked only after the case-study Typeform was submitted in this browser (tracking.js stores the flag on submit),
  // or when arriving straight from the form redirect with a Typeform response id. Drive IDs are kept encoded in the page.
  var rel = d.querySelector('[data-cs-release]');
  if (rel) {
    var manifest = {};
    try { manifest = JSON.parse(d.getElementById('cs-manifest').textContent); } catch (e) {}
    var qs = new URLSearchParams(location.search);
    var key = qs.get('cs') || '';
    var rid = qs.get('rid') || '';
    var item = manifest[key];
    var flag = null;
    try { flag = localStorage.getItem('somin_cs_unlocked_' + key) || sessionStorage.getItem('somin_cs_unlocked_' + key); } catch (e) {}
    var fromSite = !!d.referrer && d.referrer.indexOf(location.origin) === 0;
    var unlocked = !!flag || (/^[A-Za-z0-9_-]{16,}$/.test(rid) && fromSite);
    var show = function (sel) { d.querySelectorAll('[data-cs-state]').forEach(function (n) { n.hidden = n.getAttribute('data-cs-state') !== sel; }); };
    var driveId = function (s) { try { return atob(String(s || '').split('').reverse().join('')); } catch (e) { return ''; } };
    var shown = 0;
    d.querySelectorAll('[data-cs-more]').forEach(function (n) { var hide = n.getAttribute('data-cs-key') === key || shown >= 6; n.hidden = hide; if (!hide) shown++; });
    if (!item) { show('unknown'); }
    else {
      d.querySelectorAll('[data-cs-title]').forEach(function (n) { n.textContent = item.title; });
      d.querySelectorAll('[data-cs-meta]').forEach(function (n) { n.textContent = (item.category ? item.category + ' · ' : '') + 'PDF · ' + item.size_mb + ' MB'; });
      d.querySelectorAll('[data-cs-cover]').forEach(function (n) { if (item.cover) { n.src = item.cover; n.hidden = false; } });
      d.querySelectorAll('[data-cs-page]').forEach(function (n) { n.href = item.page || '/cases-ai-marketing-strategy/'; if (!item.page) n.textContent = 'All case studies'; n.hidden = false; });
      d.querySelectorAll('[data-cs-request]').forEach(function (n) { n.setAttribute('data-case-study', key); n.setAttribute('data-case-study-label', item.title); n.href = '/get-case-study/?cs=' + encodeURIComponent(key); });
      var id = driveId(item.f);
      if (unlocked && id) {
        show('ready');
        var dlUrl = 'https://drive.usercontent.google.com/download?id=' + encodeURIComponent(id) + '&export=download&confirm=t';
        var dl = d.querySelector('[data-cs-download]'), view = d.querySelector('[data-cs-view]');
        dl.href = dlUrl; view.href = 'https://drive.google.com/file/d/' + encodeURIComponent(id) + '/view';
        [dl, view].forEach(function (a) {
          a.addEventListener('click', function () { track('case_study_download', { funnel_stage: 'conversion', case_study: key, cta_text: a.textContent.trim(), link_url: a.href }); });
        });
        // first visit right after the form: start the download automatically (once per response)
        var autoKey = 'somin_cs_auto_' + (rid || key);
        var done = false; try { done = !!sessionStorage.getItem(autoKey); } catch (e) {}
        if (rid && !done) {
          try { sessionStorage.setItem(autoKey, '1'); } catch (e) {}
          var note = d.querySelector('[data-cs-auto-note]'); if (note) note.hidden = false;
          setTimeout(function () {
            track('case_study_auto_download', { funnel_stage: 'conversion', case_study: key, link_url: dlUrl });
            w.location.assign(dlUrl);   // served as an attachment, so the page stays put
          }, 1200);
        }
      } else { show('locked'); }
    }
  }

  /* ---------- case-studies hub: section filter + search ---------- */
  var hub = d.querySelector('[data-cs-hub]');
  if (hub) {
    var groups = [].slice.call(hub.querySelectorAll('[data-cs-group]'));
    var fbtns = [].slice.call(d.querySelectorAll('[data-cs-filter]'));
    var hinput = d.querySelector('[data-cs-search]');
    var hempty = hub.querySelector('[data-cs-empty]');
    var hs = { s: 'all', q: '' };
    var happly = function () {
      var total = 0;
      groups.forEach(function (g) {
        var sec = g.getAttribute('data-cs-group'), n = 0;
        g.querySelectorAll('[data-cs-card]').forEach(function (c) {
          var ok = (hs.s === 'all' || hs.s === sec) && (!hs.q || (c.getAttribute('data-q') || '').indexOf(hs.q) > -1);
          c.hidden = !ok; if (ok) n++;
        });
        g.hidden = n === 0;
        var cnt = g.querySelector('[data-cs-count]'); if (cnt) cnt.textContent = n;
        total += n;
      });
      if (hempty) hempty.hidden = total > 0;
      fbtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-cs-filter') === hs.s)); });
    };
    fbtns.forEach(function (b) {
      b.addEventListener('click', function () {
        hs.s = b.getAttribute('data-cs-filter'); happly();
        try { history.replaceState(null, '', hs.s === 'all' ? location.pathname + location.search : '#' + hs.s); } catch (e) {}
        track('cases_filter', { cta_text: hs.s, funnel_stage: 'awareness' });
      });
    });
    if (hinput) {
      var ht;
      hinput.addEventListener('input', function () {
        hs.q = hinput.value.trim().toLowerCase(); happly();
        clearTimeout(ht); ht = setTimeout(function () { if (hs.q) track('cases_search', { cta_text: hs.q.slice(0, 60), funnel_stage: 'awareness' }); }, 900);
      });
    }
    var hh = (location.hash || '').replace('#', '');
    if (['brands', 'agencies', 'creators'].indexOf(hh) > -1) hs.s = hh;
    happly();
  }

  /* ---------- get-case-study page: label from ?cs= ---------- */
  var req = d.querySelector('[data-cs-request-page]');
  if (req) {
    var m2 = {}; try { m2 = JSON.parse(d.getElementById('cs-manifest').textContent); } catch (e) {}
    var k2 = new URLSearchParams(location.search).get('cs') || '';
    var it2 = m2[k2];
    if (it2) d.querySelectorAll('[data-cs-title]').forEach(function (n) { n.textContent = it2.title; });
    var inline = d.querySelector('[data-lead-form-inline="case_study"]');
    if (inline && k2) { inline.setAttribute('data-case-study', k2); if (it2) inline.setAttribute('data-case-study-label', it2.title); }
  }

  /* ---------- session replays: muted, load + play only while on screen ---------- */
  // <video data-replay data-src="/assets/video/x.mp4" poster="…" muted playsinline loop preload="none">
  // <div data-mm-player> … <button data-mm-tab data-src data-poster data-q data-skill data-step> … <video data-replay>
  var REDUCED = !!(w.matchMedia && w.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var replays = [].slice.call(d.querySelectorAll('video[data-replay]'));
  // H.264 MP4 everywhere it plays; VP9 WebM twin for browsers built without H.264 (some Linux Chromium builds)
  var canMp4 = (function () { try { return d.createElement('video').canPlayType('video/mp4; codecs="avc1.64001F"') !== ''; } catch (e) { return true; } })();
  var vurl = function (s) { return !canMp4 && /\.mp4$/.test(s) ? s.replace(/\.mp4$/, '.webm') : s; };
  var vload = function (v) { var s = v.getAttribute('data-src'); if (s && v.getAttribute('data-loaded') !== s) { v.setAttribute('data-loaded', s); v.src = vurl(s); } };
  var vplay = function (v) { vload(v); var p = v.play(); if (p && p.catch) p.catch(function () {}); };
  var vsync = function (v) {
    var t = v.__toggle; if (!t) return;
    t.setAttribute('aria-pressed', String(!v.paused)); t.setAttribute('aria-label', v.paused ? 'Play replay' : 'Pause replay');
  };
  replays.forEach(function (v) {
    var fig = v.closest('[data-replay-box], .mm-screen');
    v.__toggle = fig ? fig.querySelector('.mm-toggle') : null;
    var toggle = function () {
      if (v.paused) { v.__userPaused = false; vplay(v); track('replay_play', { cta_text: v.getAttribute('aria-label') || '', funnel_stage: 'awareness' }); }
      else { v.__userPaused = true; v.pause(); }
    };
    if (v.__toggle) v.__toggle.addEventListener('click', toggle);
    v.addEventListener('click', toggle);
    v.addEventListener('play', function () { vsync(v); });
    v.addEventListener('pause', function () { vsync(v); });
    vsync(v);
  });
  if ('IntersectionObserver' in w) {
    var vio = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var v = e.target;
        if (e.isIntersecting) { if (!REDUCED && !v.__userPaused) vplay(v); else vload(v); }
        else if (!v.paused) v.pause();
      });
    }, { threshold: 0.35 });
    replays.forEach(function (v) { vio.observe(v); });
  } else replays.forEach(vload);

  d.querySelectorAll('[data-mm-player]').forEach(function (pl) {
    var tabs = [].slice.call(pl.querySelectorAll('[data-mm-tab]'));
    var v = pl.querySelector('video[data-replay]');
    var q = pl.querySelector('[data-mm-q]'), sk = pl.querySelector('[data-mm-skill]');
    if (!v || !tabs.length) return;
    var idx = 0;
    var select = function (i, user) {
      idx = (i + tabs.length) % tabs.length;
      var t = tabs[idx];
      tabs.forEach(function (b, j) { b.setAttribute('aria-selected', String(j === idx)); b.tabIndex = j === idx ? 0 : -1; b.style.setProperty('--p', '0'); });
      v.setAttribute('data-src', t.getAttribute('data-src'));
      v.poster = t.getAttribute('data-poster');
      v.setAttribute('aria-label', t.getAttribute('data-q'));
      if (q) q.textContent = t.getAttribute('data-q');
      if (sk) sk.textContent = t.getAttribute('data-skill');
      if (v.getAttribute('data-loaded')) {
        if (user) v.__userPaused = false;
        if (user || (!REDUCED && !v.__userPaused)) vplay(v); else vload(v);
      }
      if (user) track('replay_step_click', { cta_text: t.getAttribute('data-step') || '', funnel_stage: 'awareness' });
    };
    tabs.forEach(function (b, i) {
      b.addEventListener('click', function () { select(i, true); });
      b.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); select(idx + (e.key === 'ArrowRight' ? 1 : -1), true); tabs[idx].focus(); }
      });
    });
    v.addEventListener('timeupdate', function () { if (v.duration) tabs[idx].style.setProperty('--p', (v.currentTime / v.duration).toFixed(3)); });
    v.addEventListener('ended', function () { tabs[idx].style.setProperty('--p', '1'); select(idx + 1); });
    select(0);
  });

  /* ---------- thank-you-plugin: release + auto-start the plugin download ---------- */
  // Same rule as the case studies: unlocked after the plugin Typeform was submitted in this browser, or when arriving
  // straight from the form redirect with a Typeform response id.
  var prel = d.querySelector('[data-plugin-release]');
  if (prel) {
    var pqs = new URLSearchParams(location.search);
    var prid = pqs.get('rid') || '';
    var pflag = null;
    try { pflag = localStorage.getItem('somin_plugin_unlocked') || sessionStorage.getItem('somin_lead_plugin'); } catch (e) {}
    var pfromSite = !!d.referrer && d.referrer.indexOf(location.origin) === 0;
    var punlocked = !!pflag || (/^[A-Za-z0-9_-]{16,}$/.test(prid) && pfromSite);
    d.querySelectorAll('[data-plugin-state]').forEach(function (n) { n.hidden = n.getAttribute('data-plugin-state') !== (punlocked ? 'ready' : 'locked'); });
    if (punlocked) {
      var pmain = '';
      d.querySelectorAll('[data-plugin-dl]').forEach(function (a) {
        a.href = a.getAttribute('data-plugin-dl');
        if (a.hasAttribute('data-plugin-main')) pmain = a.href;
        a.addEventListener('click', function () { track('plugin_download', { funnel_stage: 'conversion', cta_text: a.textContent.trim(), link_url: a.href }); });
      });
      var pkey = 'somin_plugin_auto_' + (prid || 'x');
      var pdone = false; try { pdone = !!sessionStorage.getItem(pkey); } catch (e) {}
      if (prid && pmain && !pdone) {
        try { sessionStorage.setItem(pkey, '1'); } catch (e) {}
        var pnote = d.querySelector('[data-plugin-auto-note]'); if (pnote) pnote.hidden = false;
        setTimeout(function () {
          track('plugin_auto_download', { funnel_stage: 'conversion', link_url: pmain });
          w.location.assign(pmain);   // served as application/octet-stream, so the page stays put
        }, 1200);
      }
    }
  }

  /* ---------- footer year ---------- */
  d.querySelectorAll('[data-year]').forEach(function (n) { n.textContent = new Date().getFullYear(); });
})(window, document);
