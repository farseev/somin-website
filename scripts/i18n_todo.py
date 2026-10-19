#!/usr/bin/env python3
"""List what still needs translating, per language.

Run after a build:   python3 build.py && python3 scripts/i18n_todo.py [--write]
- Refreshes data/i18n/source.json (segment key -> English source) from the built English pages.
- Prints, per language, how many segments have no translation in data/i18n/<lang>.json.
- With --write, writes _i18n_todo/<lang>.tsv ("key<TAB>English" per line) for a translator. Translations come back as
  "key<TAB>translation" lines and are merged with scripts/i18n_merge.py. Keep every placeholder exactly: <g1>…</g1>
  wraps inline markup (links, bold), <x2/> stands for an inline element that stays as is, {1} is a number.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402

SITE = ROOT / '_site'
sm = (SITE / 'sitemap-en.xml').read_text(encoding='utf-8')
paths = [m.group(1)[len('https://somin.ai'):] for m in re.finditer(r'<url><loc>([^<]+)</loc>(?:<lastmod>[^<]*</lastmod>)?<xhtml', sm)]
found = i18n.extract(SITE, paths)
src_file = i18n.I18N_DIR / 'source.json'
i18n.I18N_DIR.mkdir(parents=True, exist_ok=True)
src_file.write_text(json.dumps(found, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
words = sum(len(i18n.PH_RE.sub(' ', s).split()) for s in found.values())
print(f'{len(paths)} pages, {len(found)} segments, {words:,} English words -> {src_file.relative_to(ROOT)}')
out = ROOT / '_i18n_todo'
for code, seg, *_ in i18n.LANGS:
    tm = i18n.load_tm(code)
    todo = {k: v for k, v in found.items() if k not in tm or not i18n.valid(v, tm[k])}
    tw = sum(len(i18n.PH_RE.sub(' ', s).split()) for s in todo.values())
    print(f'  {code:8s} missing {len(todo):6d} segments ({tw:,} words)')
    if '--write' in sys.argv and todo:
        out.mkdir(exist_ok=True)
        (out / f'{seg}.tsv').write_text(''.join(f'{k}\t{v}\n' for k, v in todo.items()), encoding='utf-8')
