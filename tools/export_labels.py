"""
ラベル画像を個別ファイルに切り出して印刷用サイズに変換するスクリプト
- RABEL.png   → 90×82mm × 5枚
- RABEL_1.png → 56×56mm（56パイ円形）× 3枚
- RABEL_2.png → 125×55mm × 2枚
出力先: C:/Users/Puser/Downloads/RABEL/output/
"""

import os
from PIL import Image

INPUT_DIR = "C:/Users/Puser/Downloads/RABEL"
OUTPUT_DIR = "C:/Users/Puser/Downloads/RABEL/output"
PRINT_DPI = 300

os.makedirs(OUTPUT_DIR, exist_ok=True)


def mm_to_px(mm, dpi=PRINT_DPI):
    return round(mm * dpi / 25.4)


def crop_and_save(img, box, target_mm_w, target_mm_h, out_path):
    """指定領域を切り出し → 300DPIのターゲットサイズにリサイズ → 保存"""
    cropped = img.crop(box)  # (left, top, right, bottom)
    target_w = mm_to_px(target_mm_w)
    target_h = mm_to_px(target_mm_h)
    resized = cropped.resize((target_w, target_h), Image.LANCZOS)
    resized.save(out_path, dpi=(PRINT_DPI, PRINT_DPI))
    print(f"  Saved: {os.path.basename(out_path)}  ({target_w}x{target_h}px @ {PRINT_DPI}dpi = {target_mm_w}x{target_mm_h}mm)")


# ──────────────────────────────────────────────
# RABEL.png — 90×82mm ラベル 5枚
# 上段3枚: 行 14-370, 列 18-408 / 429-820 / 842-1233
# 下段2枚: 行 439-795, 列 18-408 / 429-820
# ──────────────────────────────────────────────
print("=== RABEL.png (90×82mm) ===")
img_r = Image.open(f"{INPUT_DIR}/RABEL.png").convert("RGBA")

labels_rabel = [
    # (left, top, right, bottom, name)
    (18,  14,  408, 370, "RABEL_01_PPSU-A"),
    (429, 14,  820, 370, "RABEL_02_PPSU-B"),
    (842, 14, 1233, 370, "RABEL_03_STAINLESS"),
    (18,  439, 408, 795, "RABEL_04_PPSU-A_v2"),
    (429, 439, 820, 795, "RABEL_05_PPSU-B_v2"),
]

for left, top, right, bottom, name in labels_rabel:
    out_path = f"{OUTPUT_DIR}/{name}.png"
    crop_and_save(img_r, (left, top, right, bottom), 90, 82, out_path)


# ──────────────────────────────────────────────
# RABEL_2.png — 125×55mm ラベル 2枚
# 1行: 行 32-331, 列 14-692 / 753-1431
# ──────────────────────────────────────────────
print("\n=== RABEL_2.png (125×55mm) ===")
img_r2 = Image.open(f"{INPUT_DIR}/RABEL_2.png").convert("RGBA")

labels_rabel2 = [
    (14,  32, 692, 331, "RABEL2_01_SILICONE-NIPPLE"),
    (753, 32, 1431, 331, "RABEL2_02_REPLACEMENT-STRAW"),
]

for left, top, right, bottom, name in labels_rabel2:
    out_path = f"{OUTPUT_DIR}/{name}.png"
    crop_and_save(img_r2, (left, top, right, bottom), 125, 55, out_path)


# ──────────────────────────────────────────────
# RABEL_1.png — 56パイ（56×56mm）円形ラベル 3枚  ※すでに300DPI
# 行: 229-891 (662px = 56mm)
# 列: 125-787 / 955-1617 / 1772-2434 (各662px)
# ──────────────────────────────────────────────
print("\n=== RABEL_1.png (56パイ / 56×56mm) ===")
img_r1 = Image.open(f"{INPUT_DIR}/RABEL_1.png").convert("RGB")

labels_rabel1 = [
    (125,  229, 787,  891, "RABEL1_01_PPSU-A_56mm"),
    (955,  229, 1617, 891, "RABEL1_02_PPSU-B_56mm"),
    (1772, 229, 2434, 891, "RABEL1_03_STAINLESS_56mm"),
]

for left, top, right, bottom, name in labels_rabel1:
    out_path = f"{OUTPUT_DIR}/{name}.png"
    # RABEL_1.png はすでに300DPIなのでリサイズ不要、そのまま保存
    cropped = img_r1.crop((left, top, right, bottom))
    cropped.save(out_path, dpi=(PRINT_DPI, PRINT_DPI))
    w, h = cropped.size
    print(f"  Saved: {name}.png  ({w}x{h}px @ {PRINT_DPI}dpi = {w/PRINT_DPI*25.4:.1f}x{h/PRINT_DPI*25.4:.1f}mm)")


print(f"\n完了！ 出力先: {OUTPUT_DIR}")
print(f"合計: {len(labels_rabel) + len(labels_rabel1) + len(labels_rabel2)} ファイル")
