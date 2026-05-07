"""
楽天スーパーセール バナー生成ツール
出力: .tmp/rakuten_banner_1080x1080.png
"""

from PIL import Image, ImageDraw, ImageFont
import os

# ── 設定 ──────────────────────────────────────────────
W, H = 1080, 1080
OUT_PATH = os.path.join(os.path.dirname(__file__), "../.tmp/rakuten_banner_1080x1080.png")

# カラー
RED      = "#BF0000"
GOLD     = "#FFD700"
WHITE    = "#FFFFFF"
DARKRED  = "#8B0000"
LIGHTGRAY= "#F5F5F5"
GRAY     = "#AAAAAA"

# フォント
FONT_BOLD   = "C:/Windows/Fonts/meiryob.ttc"
FONT_REGULAR= "C:/Windows/Fonts/meiryo.ttc"

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def center_text(draw, y, text, font, fill, img_width=W):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (img_width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]  # height

def draw_rounded_rect(draw, xy, radius, fill, outline=None, outline_width=0):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                            outline=outline, width=outline_width)

# ── 描画 ──────────────────────────────────────────────
img  = Image.new("RGB", (W, H), LIGHTGRAY)
draw = ImageDraw.Draw(img)

# 背景
draw.rectangle([0, 0, W, H], fill=WHITE)

# ── 上部赤帯 ──────────────────────────────────────────
TOP_BAR_H = 200
draw.rectangle([0, 0, W, TOP_BAR_H], fill=RED)

# 「楽天スーパーセール」
f_label = load_font(FONT_BOLD, 42)
center_text(draw, 22, "✦  楽 天 ス ー パ ー セ ー ル  ✦", f_label, GOLD)

# 「最終日」
f_big = load_font(FONT_BOLD, 90)
center_text(draw, 80, "最  終  日", f_big, WHITE)

# ── 先着バッジ ────────────────────────────────────────
BADGE_Y = 230
BADGE_H = 110
BADGE_X0, BADGE_X1 = 120, W - 120
draw_rounded_rect(draw, [BADGE_X0, BADGE_Y, BADGE_X1, BADGE_Y + BADGE_H],
                  radius=55, fill=GOLD, outline=RED, outline_width=5)

f_badge = load_font(FONT_BOLD, 58)
center_text(draw, BADGE_Y + 8, "⚡  先着 30名様限定  ⚡", f_badge, RED)

f_badge_sub = load_font(FONT_REGULAR, 26)
center_text(draw, BADGE_Y + 72, "数量がなくなり次第終了", f_badge_sub, DARKRED)

# ── 商品ボックス ──────────────────────────────────────
BOX_Y = 380
BOX_H = 280
BOX_X0, BOX_X1 = 240, W - 240
draw_rounded_rect(draw, [BOX_X0, BOX_Y, BOX_X1, BOX_Y + BOX_H],
                  radius=24, fill=WHITE, outline="#DDDDDD", outline_width=3)

# 商品名
f_product = load_font(FONT_BOLD, 64)
center_text(draw, BOX_Y + 60, "ベビーストロー", f_product, "#222222")

f_catch = load_font(FONT_REGULAR, 30)
center_text(draw, BOX_Y + 148, "離乳食・お出かけに大活躍", f_catch, "#888888")

# 写真プレースホルダー注記
f_note = load_font(FONT_REGULAR, 22)
center_text(draw, BOX_Y + 210, "※ ここに商品写真を配置してください", f_note, "#BBBBBB")

# ── 価格エリア ────────────────────────────────────────
PRICE_Y = 700

# 通常価格（取り消し線）
f_price_label = load_font(FONT_REGULAR, 30)
center_text(draw, PRICE_Y, "通常価格", f_price_label, GRAY)

f_price_old = load_font(FONT_BOLD, 56)
old_text = "¥○,○○○"
bbox_old = draw.textbbox((0, 0), old_text, font=f_price_old)
old_w = bbox_old[2] - bbox_old[0]
old_x = W // 2 - old_w - 60
old_y = PRICE_Y + 42
draw.text((old_x, old_y), old_text, font=f_price_old, fill=GRAY)
# 取り消し線
line_y = old_y + (bbox_old[3] - bbox_old[1]) // 2
draw.line([old_x, line_y, old_x + old_w, line_y], fill=RED, width=5)

# 矢印
f_arrow = load_font(FONT_BOLD, 64)
arr_bbox = draw.textbbox((0, 0), "▶", font=f_arrow)
arr_x = W // 2 - (arr_bbox[2] - arr_bbox[0]) // 2
draw.text((arr_x, old_y + 8), "▶", font=f_arrow, fill=RED)

# 50% OFF ボックス
OFF_X0 = W // 2 + 50
OFF_X1 = W - 80
OFF_Y0 = PRICE_Y + 30
OFF_Y1 = PRICE_Y + 180
draw_rounded_rect(draw, [OFF_X0, OFF_Y0, OFF_X1, OFF_Y1],
                  radius=20, fill=RED)

f_off_label = load_font(FONT_BOLD, 30)
off_label = "期間限定"
bbox_l = draw.textbbox((0, 0), off_label, font=f_off_label)
draw.text(((OFF_X0 + OFF_X1 - (bbox_l[2]-bbox_l[0])) // 2, OFF_Y0 + 10),
          off_label, font=f_off_label, fill=GOLD)

f_off_num = load_font(FONT_BOLD, 100)
f_off_pct = load_font(FONT_BOLD, 50)
num_bbox = draw.textbbox((0, 0), "50", font=f_off_num)
pct_bbox = draw.textbbox((0, 0), "% OFF", font=f_off_pct)

total_w = (num_bbox[2]-num_bbox[0]) + (pct_bbox[2]-pct_bbox[0])
start_x = (OFF_X0 + OFF_X1 - total_w) // 2
num_y = OFF_Y0 + 44
draw.text((start_x, num_y), "50", font=f_off_num, fill=WHITE)
draw.text((start_x + (num_bbox[2]-num_bbox[0]), num_y + 40), "% OFF", font=f_off_pct, fill=GOLD)

# ── 下部赤帯 ──────────────────────────────────────────
BOT_Y = H - 120
draw.rectangle([0, BOT_Y, W, H], fill=RED)

f_bot = load_font(FONT_BOLD, 38)
f_shop = load_font(FONT_BOLD, 32)

# 左：本日限り
draw.text((50, BOT_Y + 18), "⏰  本日限り！お見逃しなく", font=f_bot, fill=WHITE)

# 右：楽天市場 ショップ名（金色バッジ風）
shop_text = "楽天市場 【ショップ名】"
bbox_s = draw.textbbox((0, 0), shop_text, font=f_shop)
sx = W - (bbox_s[2]-bbox_s[0]) - 50
draw_rounded_rect(draw, [sx - 14, BOT_Y + 22, W - 36, BOT_Y + 86],
                  radius=20, fill=GOLD)
draw.text((sx, BOT_Y + 28), shop_text, font=f_shop, fill=RED)

# ── 保存 ──────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
img.save(OUT_PATH, "PNG", dpi=(300, 300))
print(f"✅ 保存完了: {os.path.abspath(OUT_PATH)}")
