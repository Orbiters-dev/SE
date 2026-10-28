# -*- coding: utf-8 -*-
"""
GROSMIMI Modular Poster Mockup v1
A4 가로 (1654x1170 @ 150dpi), 텍스트+레이아웃 위주 mockup.
파츠/아기 이미지는 placeholder.
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT_PATH = os.path.join(os.path.dirname(__file__), "poster_v1.png")

# A4 가로 150dpi
W, H = 1754, 1240

# Colors
BG = "#FFFFFF"
INK = "#2F2F33"
SUB = "#777777"
LABEL_BG = "#FFE5E0"
LABEL_BG_HI = "#F8C7BA"
ARROW = "#B5DFF5"
EFFECT = "#C97B6E"
CARD_BG = "#FAFAFA"
CARD_HI = "#FFF6F2"
LINE = "#E8E8E8"

# Fonts (Windows)
F_DIR = "C:/Windows/Fonts"
def font(name, size):
    return ImageFont.truetype(os.path.join(F_DIR, name), size)

f_hero = font("YuGothB.ttc", 78)
f_hero2 = font("YuGothB.ttc", 78)
f_sub = font("YuGothR.ttc", 28)
f_label = font("YuGothB.ttc", 26)
f_step = font("YuGothB.ttc", 44)
f_step_sub = font("YuGothR.ttc", 22)
f_effect = font("YuGothB.ttc", 32)
f_desc = font("YuGothR.ttc", 22)
f_closing = font("YuGothB.ttc", 36)
f_closing_sub = font("YuGothR.ttc", 22)
f_hash = font("YuGothR.ttc", 22)
f_ph = font("YuGothR.ttc", 18)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# ============ ① HERO ============
hero_x = 80
hero_y = 70
d.text((hero_x, hero_y), "1本で、0ヶ月から2歳まで。", font=f_hero, fill=INK)
d.text((hero_x, hero_y + 110), "パーツを替えるだけで、赤ちゃんの「いま」にずっと寄り添う。", font=f_sub, fill=SUB)
d.text((hero_x, hero_y + 145), "グロミミのモジュラー設計。", font=f_sub, fill=SUB)

# 우측 상단 작은 라벨
brand_label = "GROSMIMI JAPAN  |  Modular Bottle System"
bbox = d.textbbox((0, 0), brand_label, font=f_sub)
d.text((W - 80 - (bbox[2] - bbox[0]), hero_y + 30), brand_label, font=f_sub, fill=SUB)

# 디바이더
div_y = 250
d.line([(80, div_y), (W - 80, div_y)], fill=LINE, width=2)

# ============ ② STEP 카드 3개 ============
card_top = 290
card_h = 720
card_margin = 70
card_gap = 30
card_w = (W - 2 * card_margin - 2 * card_gap) // 3

def draw_card(idx, title_jp, title_sub, label_text, label_color, baby_caption,
              parts_caption, effect, desc1, desc2, highlight=False):
    x = card_margin + idx * (card_w + card_gap)
    y = card_top
    card_bg = CARD_HI if highlight else CARD_BG
    d.rounded_rectangle((x, y, x + card_w, y + card_h), radius=24, fill=card_bg, outline=LINE, width=2)

    # 월령 라벨
    label_w = 240
    label_h = 50
    lx = x + (card_w - label_w) // 2
    ly = y + 30
    d.rounded_rectangle((lx, ly, lx + label_w, ly + label_h), radius=25, fill=label_color)
    bbox = d.textbbox((0, 0), label_text, font=f_label)
    tw = bbox[2] - bbox[0]
    d.text((lx + (label_w - tw) // 2, ly + 8), label_text, font=f_label, fill=INK)

    # 아기 이미지 placeholder (원형)
    baby_size = 240
    bx = x + (card_w - baby_size) // 2
    by = ly + label_h + 25
    d.ellipse((bx, by, bx + baby_size, by + baby_size), fill="#EFE9E4", outline="#DDD3CB", width=2)
    cap_bbox = d.textbbox((0, 0), baby_caption, font=f_ph)
    cw = cap_bbox[2] - cap_bbox[0]
    d.text((bx + (baby_size - cw) // 2, by + baby_size // 2 - 12), baby_caption, font=f_ph, fill="#A99B8C")

    # 파츠 이미지 placeholder (사각)
    parts_w, parts_h = 220, 120
    px = x + (card_w - parts_w) // 2
    py = by + baby_size + 20
    d.rounded_rectangle((px, py, px + parts_w, py + parts_h), radius=12, fill="#F0F4F8", outline="#D5DEE5", width=2)
    pbox = d.textbbox((0, 0), parts_caption, font=f_ph)
    pw = pbox[2] - pbox[0]
    d.text((px + (parts_w - pw) // 2, py + parts_h // 2 - 12), parts_caption, font=f_ph, fill="#7B8C9B")

    # 스테이지 타이틀
    title_y = py + parts_h + 25
    bbox = d.textbbox((0, 0), title_jp, font=f_step)
    tw = bbox[2] - bbox[0]
    d.text((x + (card_w - tw) // 2, title_y), title_jp, font=f_step, fill=INK)

    if title_sub:
        bbox = d.textbbox((0, 0), title_sub, font=f_step_sub)
        tw = bbox[2] - bbox[0]
        d.text((x + (card_w - tw) // 2, title_y + 55), title_sub, font=f_step_sub, fill=SUB)
        eff_y = title_y + 90
    else:
        eff_y = title_y + 60

    # 효과음
    bbox = d.textbbox((0, 0), effect, font=f_effect)
    tw = bbox[2] - bbox[0]
    d.text((x + (card_w - tw) // 2, eff_y), effect, font=f_effect, fill=EFFECT)

    # 설명
    desc_y = eff_y + 50
    for line in [desc1, desc2]:
        if not line:
            continue
        bbox = d.textbbox((0, 0), line, font=f_desc)
        tw = bbox[2] - bbox[0]
        d.text((x + (card_w - tw) // 2, desc_y), line, font=f_desc, fill="#555555")
        desc_y += 32


draw_card(0, "ニップル", "", "0〜6ヶ月", LABEL_BG,
          "[赤ちゃん画像]", "[ニップルパーツ]", "ごくごく",
          "5段階の穴の形で、月齢に合わせて", "ミルクの流量を調整。")

draw_card(1, "ストロー", "Stage 1 → Stage 2", "6ヶ月〜", LABEL_BG_HI,
          "[赤ちゃん画像]", "[Stage1 + Stage2]", "ちゅーちゅー",
          "やわらかい→かため、噛みぐせや", "成長に合わせてストロー交換可能。",
          highlight=True)

draw_card(2, "タンブラー", "ワンタッチ式", "18ヶ月〜", LABEL_BG,
          "[赤ちゃん画像]", "[タンブラーキャップ]", "ぐびっ",
          "ワンタッチ開閉で、コップ飲みへの", "卒業もスムーズに。")

# 카드 사이 화살표
arrow_y = card_top + card_h // 2 - 10
for i in range(2):
    ax = card_margin + (i + 1) * card_w + i * card_gap + 5
    # 화살표 (간단하게 삼각형)
    d.polygon([
        (ax, arrow_y),
        (ax + card_gap - 10, arrow_y + 10),
        (ax, arrow_y + 20)
    ], fill=ARROW)

# ============ ③ 하단 본체 + 클로징 ============
bot_y = card_top + card_h + 30
bot_h = H - bot_y - 30

# 좌측 본체 placeholder
body_w = 230
body_h = bot_h - 20
body_x = card_margin + 50
body_y = bot_y + 10
d.rounded_rectangle((body_x, body_y, body_x + body_w, body_y + body_h), radius=20, fill="#EEF1F5", outline="#D5DEE5", width=2)
cap = "[ボトル本体]"
bbox = d.textbbox((0, 0), cap, font=f_ph)
cw = bbox[2] - bbox[0]
d.text((body_x + (body_w - cw) // 2, body_y + body_h // 2 - 12), cap, font=f_ph, fill="#7B8C9B")

# 우측 클로징 카피
close_x = body_x + body_w + 60
close_y = bot_y + 30
d.text((close_x, close_y), "ボトルはひとつ。パーツを替えるだけ。", font=f_closing, fill=INK)
d.text((close_x, close_y + 50), "赤ちゃんの成長と、ずっと一緒に。", font=f_closing, fill=INK)
d.text((close_x, close_y + 110), "0ヶ月のニップル、6ヶ月のストロー、18ヶ月のタンブラー。", font=f_closing_sub, fill=SUB)
d.text((close_x, close_y + 140), "1本のグロミミが、赤ちゃんの全ステージに寄り添います。", font=f_closing_sub, fill=SUB)

# 해시태그 (최하단 우측)
hash_text = "#グロミミ   #grosmimi   #ストローマグ   @grosmimi_japan"
bbox = d.textbbox((0, 0), hash_text, font=f_hash)
hw = bbox[2] - bbox[0]
d.text((W - 80 - hw, H - 40), hash_text, font=f_hash, fill=SUB)

img.save(OUT_PATH, "PNG", dpi=(150, 150))
print(f"saved: {OUT_PATH}")
print(f"size: {W}x{H}")
