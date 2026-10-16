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

  /* ---------- thank-you-case-study: release the download link ---------- */
  var rel = d.querySelector('[data-cs-release]');
  if (rel) {
    var manifest = {};
    try { manifest = JSON.parse(d.getElementById('cs-manifest').textContent); } catch (e) {}
    var qs = new URLSearchParams(location.search);
    var key = qs.get('cs') || '';
    var item = manifest[key];
    var unlocked = !!qs.get('rid');
    try { unlocked = unlocked || !!localStorage.getItem('somin_cs_unlocked_' + key); } catch (e) {}
    var show = function (sel) { d.querySelectorAll('[data-cs-state]').forEach(function (n) { n.hidden = n.getAttribute('data-cs-state') !== sel; }); };
    if (!item) { show('unknown'); }
    else {
      d.querySelectorAll('[data-cs-title]').forEach(function (n) { n.textContent = item.title; });
      d.querySelectorAll('[data-cs-meta]').forEach(function (n) { n.textContent = 'PDF · ' + item.size_mb + ' MB'; });
      d.querySelectorAll('[data-cs-cover]').forEach(function (n) { if (item.cover) { n.src = item.cover; n.hidden = false; } });
      d.querySelectorAll('[data-cs-page]').forEach(function (n) { if (item.page) { n.href = item.page; n.hidden = false; } else n.hidden = true; });
      d.querySelectorAll('[data-cs-request]').forEach(function (n) { n.setAttribute('data-case-study', key); n.setAttribute('data-case-study-label', item.title); n.href = '/get-case-study/?cs=' + encodeURIComponent(key); });
      var shown = 0;
      d.querySelectorAll('[data-cs-more]').forEach(function (n) { var hide = n.getAttribute('href') === item.page || shown >= 6; n.hidden = hide; if (!hide) shown++; });
      if (unlocked) {
        show('ready');
        var dl = d.querySelector('[data-cs-download]'), view = d.querySelector('[data-cs-view]');
        dl.href = item.download; view.href = item.view;
        [dl, view].forEach(function (a) {
          a.addEventListener('click', function () { track('case_study_download', { funnel_stage: 'conversion', case_study: key, cta_text: a.textContent.trim(), link_url: a.href }); });
        });
        if (qs.get('rid') && !sessionStorage.getItem('somin_cs_auto_' + key)) {
          try { sessionStorage.setItem('somin_cs_auto_' + key, '1'); } catch (e) {}
        }
      } else { show('locked'); }
    }
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

  /* ---------- footer year ---------- */
  d.querySelectorAll('[data-year]').forEach(function (n) { n.textContent = new Date().getFullYear(); });
})(window, document);
