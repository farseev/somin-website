"""Branded 1200x630 Open Graph cards (SOMIN wordmark + eyebrow + title + visual).
Run from the repo root after a build: python3 scripts/og_cards.py <dir with Montserrat m1.ttf(500) m2.ttf(800) m3.ttf(900)>
Jobs live in scripts/og_cards.json; images go to static/assets/img/og/card-<name>.jpg."""
import json, re, html, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
FD = sys.argv[1] if len(sys.argv) > 1 else '/tmp/fonts'
F500, F800, F900 = (f'{FD}/m1.ttf', f'{FD}/m2.ttf', f'{FD}/m3.ttf')
TEAL, INK, WHITE, SOFT = (45, 191, 156), (22, 32, 31), (255, 255, 255), (201, 209, 208)
OUT = Path('static/assets/img/og')

def wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def card(name, eyebrow, title, image):
    W, H = 1200, 630
    bg = Image.new('RGB', (W, H), INK)
    im = Image.open(image).convert('RGB')
    # cover-fit the visual into the right 62%
    rw, rh = 760, H
    r = max(rw / im.width, rh / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    l, t = (im.width - rw) // 2, (im.height - rh) // 2
    bg.paste(im.crop((l, t, l + rw, t + rh)), (W - rw, 0))
    # fade into the text panel
    mask = Image.new('L', (W, H)); md = ImageDraw.Draw(mask)
    for x in range(W):
        md.line([(x, 0), (x, H)], fill=255 if x < 470 else max(0, int(255 * (1 - (x - 470) / 230))))
    bg = Image.composite(Image.new('RGB', (W, H), INK), bg, mask)
    d = ImageDraw.Draw(bg)
    wm = ImageFont.truetype(F800, 30)
    d.text((64, 58), 'SO', font=wm, fill=TEAL); d.text((64 + d.textlength('SO', font=wm), 58), 'MIN', font=wm, fill=WHITE)
    ey = ImageFont.truetype(F800, 17)
    d.text((64, 150), eyebrow.upper(), font=ey, fill=TEAL, spacing=0)
    for size in (58, 52, 46, 40, 36):
        tf = ImageFont.truetype(F900, size)
        lines = wrap(d, title, tf, 520)
        if len(lines) <= 5 and len(lines) * size * 1.12 <= 330: break
    y = 186
    for ln in lines:
        d.text((64, y), ln, font=tf, fill=WHITE); y += int(size * 1.12)
    d.rounded_rectangle((64, 548, 64 + 4, 548 + 26), 2, fill=TEAL)
    d.text((80, 548), 'somin.ai', font=ImageFont.truetype(F500, 22), fill=SOFT)
    bg.save(OUT / f'card-{name}.jpg', 'JPEG', quality=86, optimize=True, progressive=True)
    return f'/assets/img/og/card-{name}.jpg'

def h1_of(slug):
    t = Path(f'_site/{slug}/index.html' if slug else '_site/index.html').read_text(encoding='utf-8')
    m = re.search(r'<h1[^>]*>(.*?)</h1>', t, re.S)
    s = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))).strip() if m else ''
    return re.sub(r'\s+([.,!?])', r'\1', s)

if __name__ == '__main__':
    jobs = json.loads(Path(__file__).with_name('og_cards.json').read_text())
    for j in jobs:
        title = j.get('title') or h1_of(j['slug'])
        print(card(j['name'], j['eyebrow'], title, j['image']), '←', title)
