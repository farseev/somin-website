#!/usr/bin/env python3
"""Check a translated chunk:  python3 check.py <chunk.tsv> <translated.tsv>
Prints missing keys and lines whose placeholders (<gN>, </gN>, <xN/>, {N}) differ from the source. Exit 0 = all good."""
import re, sys
PH = re.compile(r'</?g\d+>|<x\d+/>|\{\d+\}')
src = dict(l.rstrip('\n').split('\t', 1) for l in open(sys.argv[1], encoding='utf-8') if '\t' in l)
got = {}
bad = []
for n, l in enumerate(open(sys.argv[2], encoding='utf-8'), 1):
    l = l.rstrip('\n')
    if not l.strip():
        continue
    if '\t' not in l:
        bad.append(f'line {n}: no TAB'); continue
    k, t = l.split('\t', 1)
    if k not in src:
        bad.append(f'line {n}: unknown key {k}'); continue
    if sorted(PH.findall(src[k])) != sorted(PH.findall(t)):
        bad.append(f'line {n}: placeholders differ for {k}: {sorted(PH.findall(src[k]))} vs {sorted(PH.findall(t))}')
    got[k] = t
missing = [k for k in src if k not in got]
for b in bad[:50]: print(b)
print(f'{len(got)}/{len(src)} translated, {len(missing)} missing, {len(bad)} problems')
if missing: print('missing keys:', ' '.join(missing[:40]))
sys.exit(0 if not bad and not missing else 1)
