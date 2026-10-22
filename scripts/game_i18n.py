#!/usr/bin/env python3
"""Translation memory for the Insight Chain game content (static/assets/game/cases/*.json).

The game fetches its case content at run time, so i18n.py (which translates built HTML) cannot reach it. This module
extracts every translatable string from the case files, keys it by sha1 of the English text (16 hex chars, same scheme as
data/i18n), and writes localized copies to _site/assets/game/<lang path segment>/cases/<id>.json during the build.
A string with no translation stays English, so the game never breaks.

    python3 scripts/game_i18n.py --todo        write _game_todo/<lang>-<n>.tsv chunks (key<TAB>English) per language
    python3 scripts/game_i18n.py --merge <lang> file.tsv [...]   merge "key<TAB>translation" lines into data/game_i18n/<lang>.json
    python3 scripts/game_i18n.py --stats       translated share per language
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / 'static/assets/game/cases'
TM_DIR = ROOT / 'data/game_i18n'
SKIP_KEYS = {'id', 'img', 'href', 'ref', 'kind', 'type', 'pid', 'faces', 'ind', 'client', 'page', 'stage', 'pg', 'p', 'a'}
ID_RE = re.compile(r'^[ptaP]\d+$')


def key_of(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:16]


def translatable(path, k, v):
    if not isinstance(v, str) or k in SKIP_KEYS or ID_RE.match(v):
        return False
    if k == 'name' and 'personas' in path:     # persona names stay as written
        return False
    if v.startswith(('game/', 'inline/', '/assets', '#', 'http')):
        return False
    return bool(re.search(r'[A-Za-z]{3}', v))


def walk(o, fn, path=(), key=None):
    """Rebuild o, replacing each translatable string with fn(string)."""
    if isinstance(o, dict):
        return {k: walk(v, fn, path + (k,), k) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, fn, path, key) for v in o]
    if translatable(path, key, o):
        return fn(o)
    return o


def case_files():
    return sorted(CASES.glob('*.json'))


def extract():
    found = {}
    for f in case_files():
        walk(json.loads(f.read_text(encoding='utf-8')), lambda s: found.setdefault(key_of(s), s) and s)
    return found


def load_tm(seg):
    p = TM_DIR / f'{seg}.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def localize(obj, tm):
    return walk(obj, lambda s: tm.get(key_of(s)) or s)


def build_localized(out_root, langs):
    """langs: iterable of path segments (e.g. 'ja'). Writes <out_root>/assets/game/<seg>/cases/<id>.json."""
    n = 0
    for seg in langs:
        tm = load_tm(seg)
        if not tm:
            continue
        d = out_root / 'assets/game' / seg / 'cases'
        d.mkdir(parents=True, exist_ok=True)
        for f in case_files():
            data = localize(json.loads(f.read_text(encoding='utf-8')), tm)
            (d / f.name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            n += 1
    return n


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    import i18n
    src = extract()
    if '--todo' in sys.argv:
        out = ROOT / '_game_todo'
        out.mkdir(exist_ok=True)
        items = list(src.items())
        chunks, cur, w = [], [], 0
        for k, v in items:
            cur.append((k, v)); w += len(v.split())
            if w > 11500:
                chunks.append(cur); cur, w = [], 0
        if cur:
            chunks.append(cur)
        for code, seg, *_ in i18n.LANGS:
            tm = load_tm(seg)
            for n, ch in enumerate(chunks, 1):
                rows = [(k, v) for k, v in ch if k not in tm]
                if rows:
                    (out / f'{seg}-{n}.tsv').write_text(''.join(f'{k}\t{v}\n' for k, v in rows), encoding='utf-8')
        print(len(src), 'strings,', sum(len(v.split()) for v in src.values()), 'words,', len(chunks), 'chunks per language')
    elif '--merge' in sys.argv:
        i = sys.argv.index('--merge'); seg = next(l[1] for l in i18n.LANGS if sys.argv[i + 1] in (l[0], l[1]))
        tm = load_tm(seg); ok = bad = 0
        for f in sys.argv[i + 2:]:
            for line in Path(f).read_text(encoding='utf-8').splitlines():
                k, _, t = line.partition('\t')
                if k in src and t.strip():
                    tm[k] = t.strip(); ok += 1
                else:
                    bad += 1
        TM_DIR.mkdir(exist_ok=True)
        (TM_DIR / f'{seg}.json').write_text(json.dumps(tm, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{seg}: merged {ok}, skipped {bad} -> {len(tm)} entries')
    else:
        for code, seg, *_ in i18n.LANGS:
            tm = load_tm(seg)
            print(f'{code:8s} {sum(1 for k in src if k in tm)}/{len(src)}')
