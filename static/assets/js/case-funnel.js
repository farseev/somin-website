/* Insight-chain creative library. One chain at a time; every TOFU / MOFU / BOFU line for that chain. */
(function () {
  var STAGES = [
    ['TOFU', 'Awareness'],
    ['MOFU', 'Consideration'],
    ['BOFU', 'Conversion']
  ];

  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function render(root, block) {
    var chains = block.chains || [];
    if (!chains.length) return;
    var current = 0;

    function card(it) {
      var img = it.img
        ? '<img src="' + esc(it.img) + '" alt="' + esc(it.text) + '" loading="lazy" decoding="async">'
        : '';
      var concept = it.concept ? '<small>' + esc(it.concept) + '</small>' : '';
      return '<article class="cs-chain-card">' + img + '<p>' + esc(it.text) + '</p>' + concept + '</article>';
    }

    function paint() {
      var ch = chains[current];
      var label = ch.persona || ch.tension || 'Chain';
      var buttons = chains.map(function (c, i) {
        var name = c.persona || c.tension || ('Chain ' + (i + 1));
        var sub = c.persona ? c.tension : (c.angle || '');
        return '<button type="button" aria-pressed="' + (i === current ? 'true' : 'false') + '">' +
          '<strong>' + esc(name) + '</strong>' +
          (sub ? '<span>' + esc(sub) + '</span>' : '') +
          '</button>';
      }).join('');
      var cols = STAGES.map(function (st) {
        var items = (ch.items || []).filter(function (it) { return it.stage === st[0]; });
        if (!items.length) return '';
        return '<div class="cs-chain-col"><h3>' + esc(st[0]) + ' · ' + esc(st[1]) + '</h3>' + items.map(card).join('') + '</div>';
      }).join('');
      var meta = [ch.arch, ch.angle].filter(Boolean).join(' · ');
      root.innerHTML =
        '<div class="cs-chain-picks" role="group" aria-label="Insight chains">' + buttons + '</div>' +
        '<p class="cs-chain-meta"><strong>' + esc(label) + '</strong>' + (meta ? ' · ' + esc(meta) : '') + '</p>' +
        '<div class="cs-chain-board">' + cols + '</div>';
      var btns = root.querySelectorAll('.cs-chain-picks button');
      btns.forEach(function (btn, i) {
        btn.addEventListener('click', function () {
          current = i;
          paint();
        });
      });
    }

    paint();
  }

  function boot(data) {
    document.querySelectorAll('.cs-chain[data-case]').forEach(function (el) {
      var block = data[el.getAttribute('data-case')];
      if (block) render(el, block);
    });
  }

  var nodes = document.querySelectorAll('.cs-chain[data-case]');
  if (!nodes.length) return;
  fetch('/assets/data/case-funnels.json', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) { if (data) boot(data); });
})();
