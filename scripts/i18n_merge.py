#!/usr/bin/env python3
"""Merge translated segments into the translation memory.

    python3 scripts/i18n_merge.py <lang-code or path segment> file1.tsv [file2.tsv …]

Each line is "key<TAB>translation". A line is accepted only if the key exists in data/i18n/source.json and the translation
keeps exactly the source's placeholders (<gN>…</gN>, <xN/>, {N}); everything else is reported and skipped.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402

arg = sys.argv[1]
code = next((l[0] for l in i18n.LANGS if arg in (l[0], l[1])), None)
if not code:
    raise SystemExit(f'unknown language {arg}')
src = json.loads((i18n.I18N_DIR / 'source.json').read_text(encoding='utf-8'))
tm = i18n.load_tm(code)
ok = bad = unknown = 0
for f in sys.argv[2:]:
    for n, line in enumerate(Path(f).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or '\t' not in line:
            continue
        k, tr = line.split('\t', 1)
        k, tr = k.strip(), tr.strip()
        if k not in src:
            unknown += 1
            continue
        if not tr or not i18n.valid(src[k], tr):
            bad += 1
            print(f'  skip {f}:{n} {k}: placeholders differ', file=sys.stderr)
            continue
        tm[k] = tr
        ok += 1
p = i18n.I18N_DIR / f'{i18n.SEG_OF[code]}.json'
p.write_text(json.dumps(dict(sorted(tm.items())), ensure_ascii=False, indent=0), encoding='utf-8')
print(f'{code}: merged {ok}, skipped {bad} (placeholders), {unknown} unknown keys -> {p.relative_to(ROOT)} ({len(tm)} entries)')
