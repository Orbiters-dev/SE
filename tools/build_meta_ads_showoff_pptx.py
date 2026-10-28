"""
ORBI Grosmimi JP — Meta Ads 운영 체계 (Show off PPT, 2026-05-18)

외부 노출용. 자연어 + 처음 보는 사람도 이해할 수 있게.
전문 용어 (percentile, Lifecycle, Off Rule 등) 풀어서 사용.

저장: C:\\Users\\orbit\\Desktop\\s\\메타\\08_meta_ads_showoff.pptx
"""
import sys
import io
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = Path(r"C:\Users\orbit\Desktop\s\performance marketing\META ADS 관리용\operations\08_meta_ads_showoff.pptx")
OUT.parent.mkdir(parents=True, exist_ok=True)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SLIDE_W = prs.slide_width
SLIDE_H = prs.slide_height

# 컬러
NAVY = RGBColor(0x1F, 0x29, 0x37)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
ACCENT2 = RGBColor(0xDB, 0x27, 0x77)
LIGHT = RGBColor(0xF9, 0xFA, 0xFB)
GRAY = RGBColor(0x6B, 0x72, 0x80)
GREEN = RGBColor(0x05, 0x96, 0x69)
RED = RGBColor(0xDC, 0x26, 0x26)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def add_blank_slide():
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_text(slide, x, y, w, h, text, font_size=18, bold=False,
             color=NAVY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             font_name="Malgun Gothic"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Pt(0); tf.margin_right = Pt(0)
    tf.margin_top = Pt(0); tf.margin_bottom = Pt(0)
    lines = text.split("\n") if "\n" in text else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = font_name
    return tb


def add_rect(slide, x, y, w, h, fill=ACCENT):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    return shape


def add_header_bar(slide, page_num, total, section, title, subtitle=None):
    add_text(slide, Inches(0.5), Inches(0.3), Inches(8), Inches(0.4),
             section, font_size=12, color=GRAY, bold=True)
    add_text(slide, Inches(11.5), Inches(0.3), Inches(1.5), Inches(0.4),
             f"{page_num} / {total}", font_size=10, color=GRAY, align=PP_ALIGN.RIGHT)
    add_text(slide, Inches(0.5), Inches(0.7), Inches(12), Inches(0.9),
             title, font_size=30, bold=True, color=NAVY)
    add_rect(slide, Inches(0.5), Inches(1.55), Inches(0.8), Emu(40000), fill=ACCENT)
    if subtitle:
        add_text(slide, Inches(0.5), Inches(1.7), Inches(12), Inches(0.5),
                 subtitle, font_size=14, color=GRAY)


TOTAL = 15


# ============================================================
# Slide 1 — 표지
# ============================================================
s = add_blank_slide()
add_rect(s, 0, 0, SLIDE_W, SLIDE_H, fill=NAVY)
add_rect(s, Inches(0), Inches(6.0), SLIDE_W, Inches(0.15), fill=ACCENT)
add_rect(s, Inches(9.5), Inches(0), Inches(0.15), SLIDE_H, fill=ACCENT2)

add_text(s, Inches(0.7), Inches(2.0), Inches(12), Inches(0.6),
         "ORBI / Grosmimi JP", font_size=22, color=WHITE)
add_text(s, Inches(0.7), Inches(2.6), Inches(12), Inches(1.2),
         "메타 광고", font_size=60, bold=True, color=WHITE)
add_text(s, Inches(0.7), Inches(3.6), Inches(12), Inches(1.0),
         "우리는 이렇게 운영합니다", font_size=40, bold=True, color=ACCENT)

add_text(s, Inches(0.7), Inches(5.2), Inches(12), Inches(0.5),
         "일본 시장 인스타그램 광고 운영 체계와 일일 자동화",
         font_size=18, color=WHITE)

add_text(s, Inches(0.7), Inches(6.5), Inches(12), Inches(0.4),
         "2026-05-19",
         font_size=12, color=GRAY)


# ============================================================
# Slide 2 — 어떤 광고를 다루나 (배경)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 2, TOTAL, "1. 배경", "어떤 광고를 운영하나요?")

add_text(s, Inches(0.5), Inches(2.0), Inches(12.3), Inches(0.7),
         "일본 인스타그램에서 우리 제품 (유아용 스트로컵)을 노출시키는 광고입니다.",
         font_size=20, color=NAVY)

add_text(s, Inches(0.5), Inches(2.8), Inches(12.3), Inches(0.5),
         "광고는 2가지 형태로 들어갑니다.",
         font_size=16, color=GRAY)

types = [
    ("이미지 광고", "우리가 직접 만든 사진/이미지를 그대로 게시", ACCENT2),
    ("인플루언서 영상 광고", "협업 인플루언서가 만든 영상 게시물을\n광고로 다시 노출 (Whitelisting)", ACCENT),
]
y0 = Inches(3.7)
for i, (name, body, color) in enumerate(types):
    x = Inches(0.7 + i * 6.3)
    add_rect(s, x, y0, Inches(5.9), Inches(2.5), fill=LIGHT)
    add_rect(s, x, y0, Inches(5.9), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(5.9), Inches(0.5),
             name, font_size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.4), y0 + Inches(1.0), Inches(5.1), Inches(1.4),
             body, font_size=14, color=NAVY)

add_text(s, Inches(0.5), Inches(6.6), Inches(12.3), Inches(0.5),
         "광고 한 개당 평균 일 ₩3,000~₩6,000 정도 지출. 동시에 5~15개 광고를 운영합니다.",
         font_size=13, color=GRAY)


# ============================================================
# Slide 3 — 핵심 한 줄
# ============================================================
s = add_blank_slide()
add_header_bar(s, 3, TOTAL, "2. 핵심 아이디어", "이 체계를 한 줄로 설명하면")

add_text(s, Inches(0.5), Inches(2.5), Inches(12.3), Inches(1.5),
         "\"KPI\"와 \"광고 정리 기준\"은 다르게 다룹니다.",
         font_size=40, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

add_text(s, Inches(1.0), Inches(4.4), Inches(11.3), Inches(0.7),
         "KPI = 우리가 가고 싶은 곳 (고정).",
         font_size=20, color=NAVY, align=PP_ALIGN.CENTER)

add_text(s, Inches(1.0), Inches(5.0), Inches(11.3), Inches(0.7),
         "광고 정리 기준 = 우리 광고들 중에서 어떤 걸 꺼야 할지 (상대적).",
         font_size=20, color=NAVY, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.3), Inches(12.3), Inches(0.5),
         "둘을 섞어 쓰면 \"KPI 미달 = 즉시 끄기\"가 되어 사실상 모든 광고를 꺼야 합니다.",
         font_size=14, color=GRAY, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.5), Inches(6.8), Inches(12.3), Inches(0.5),
         "그래서 분리해서, 우리 광고들끼리만 비교해 판단합니다.",
         font_size=14, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 4 — 운영 목표 (KPI)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 4, TOTAL, "3. KPI",
               "우리가 가고 싶은 곳 — 광고 1개당 기준")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "광고 1개당 얼마면 잘하고 있는지의 기준입니다. KPI 미달이라고 즉시 끄지는 않습니다.",
         font_size=14, color=GRAY)

kpis = [
    ("인플루언서 영상 광고",
     "CTR 8% 이상",
     "100번 노출되면 8번 클릭\n(CTR = 클릭률)",
     ACCENT),
    ("이미지 광고",
     "CTR 4% 이상",
     "100번 노출되면 4번 클릭",
     ACCENT2),
    ("공통",
     "CPC ₩100 이하",
     "한 명 클릭 데려오는 데 ₩100 이하\n(CPC = 클릭당 비용)",
     GREEN),
]
y0 = Inches(2.7)
for i, (name, target, body, color) in enumerate(kpis):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(3.8), fill=LIGHT)
    add_rect(s, x, y0, Inches(4.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(4.0), Inches(0.5),
             name, font_size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.0), Inches(4.0), Inches(1.0),
             target, font_size=22, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(2.4), Inches(4.0), Inches(1.0),
             body, font_size=13, color=GRAY, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.7), Inches(12.3), Inches(0.5),
         "운영 시 \"몇 개 광고가 KPI 달성 / 몇 개 미달\"인지 매일 카운트만 합니다.",
         font_size=13, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 5 — 광고 정리 기준 (4가지 신호)
# ============================================================
s = add_blank_slide()
# ============================================================
# Slide 5 — 광고 ON 진입 기준 (D+3 VTR)
# ============================================================
add_header_bar(s, 5, TOTAL, "4. 광고 ON 진입 기준",
               "어떤 영상을 광고로 돌릴까 — D+3 VTR 게이트")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "사전에 엄격히 선별합니다. 광고 켠 후 끄는 건 메타 알고리즘 학습을 망가뜨려서.",
         font_size=14, color=GRAY)

add_rect(s, Inches(0.7), Inches(2.55), Inches(11.9), Inches(0.9), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.7), Inches(11.3), Inches(0.4),
         "지표 — D+3 VTR (View-to-Follower Ratio)",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(3.05), Inches(11.3), Inches(0.4),
         "게시 후 3일 시점 조회수  ÷  게시 시점 팔로워 수  ×  100%",
         font_size=16, bold=True, color=WHITE)

gates = [
    ("VTR < 100%",
     "ON X",
     "본인 팔로워조차 다 도달 못 함\n= 영상 hook 약함\n알고리즘 푸시 안 함",
     RED),
    ("VTR 100~200%",
     "ON 고려",
     "본인 팔로워 거의 도달\n+ 약간 외부 explore\n= 평균선",
     ACCENT2),
    ("VTR 200% 이상",
     "적극 ON",
     "외부 explore 푸시 통과\n= 영상 hook 통한 신호\n광고 효율 기대",
     GREEN),
]
y0 = Inches(3.7)
for i, (band, action, body, color) in enumerate(gates):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.6), fill=LIGHT)
    add_rect(s, x, y0, Inches(4.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(4.0), Inches(0.5),
             band, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.9), Inches(4.0), Inches(0.6),
             action, font_size=22, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.7), Inches(4.0), Inches(1.0),
             body, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.5), Inches(11.9), Inches(0.7), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.6), Inches(11.3), Inches(0.4),
         "ON 후 최소 7일 유지",
         font_size=13, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(6.95), Inches(11.3), Inches(0.4),
         "광고 시작 직후 끄면 알고리즘 학습이 망가집니다. 7일 후부터 정리 기준 적용.",
         font_size=11, color=GRAY)


# ============================================================
# Slide 6 — 광고 정리 기준 (4가지 신호)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 6, TOTAL, "5. 광고 정리 기준",
               "어떤 광고를 꺼야 할지 — 4가지 신호")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "아래 4가지 신호로 \"끄기 후보\"를 분류합니다. 첫 신호는 2중 게이트로 보수적으로.",
         font_size=14, color=GRAY)

axes = [
    ("하위 20% + 절대 기준\n둘 다 해당",
     "우리 광고들끼리 줄 세워 하위 20%이고,\n동시에 CTR이 KPI의 절반 미만이거나\nCPC가 KPI의 2배 초과인 광고만 정리.\n한쪽만 해당이면 정리 X, 1~2주 관찰.",
     "가장 중요한 신호 (2중 게이트)",
     ACCENT),
    ("광고 게시 60일 경과",
     "광고 영상은 시간이 지나면\n자연스럽게 효율이 떨어집니다.\n60일 지나면 점검 대상.",
     "자연 노화 신호",
     ACCENT2),
    ("Frequency 3.0 이상",
     "같은 사람에게 평균 3번 이상 노출.\n반복 노출 시 클릭 의지가 사라집니다.\n광고비와 무관하게 즉시 점검.",
     "피로도 신호",
     RED),
    ("최근 7일 CTR 15% 이상 하락",
     "검증 완료된 광고가\n갑자기 효율 떨어지는 경우.\n신규 영상 의뢰 검토.",
     "추세 신호",
     GRAY),
]
for i, (name, cond, label, color) in enumerate(axes):
    col = i % 2
    row = i // 2
    x = Inches(0.7 + col * 6.3)
    y = Inches(2.6 + row * 2.35)
    add_rect(s, x, y, Inches(5.9), Inches(2.15), fill=LIGHT)
    add_rect(s, x, y, Inches(0.15), Inches(2.15), fill=color)
    add_text(s, x + Inches(0.4), y + Inches(0.15), Inches(5.3), Inches(0.45),
             label, font_size=11, bold=True, color=color)
    add_text(s, x + Inches(0.4), y + Inches(0.55), Inches(5.3), Inches(0.7),
             name, font_size=16, bold=True, color=NAVY)
    add_text(s, x + Inches(0.4), y + Inches(1.25), Inches(5.3), Inches(0.85),
             cond, font_size=12, color=GRAY)


# ============================================================
# Slide 6 — 왜 우리 광고들끼리만 비교하나
# ============================================================
s = add_blank_slide()
add_header_bar(s, 7, TOTAL, "6. 판단 방식",
               "왜 \"우리 광고들끼리만\" 비교하나요?")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.6),
         "외부에서 발표되는 시장 평균 (예: \"유아용품 광고 평균 CTR 1.91%\")을",
         font_size=16, color=NAVY)
add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.6),
         "기준으로 쓰지 않는 이유 — 우리 상황과 다르기 때문입니다.",
         font_size=16, color=NAVY)

reasons = [
    ("우리 광고는 15개,\n시장 데이터는 50만 개",
     "광고 수가 다르면 \"평균\"의 의미가 달라집니다.\n적은 광고로 큰 시장 평균과 비교는 부정확."),
    ("우리는 매출 데이터가 안 잡힘",
     "결제는 라쿠텐에서 이뤄지는데\n그쪽 데이터를 메타 광고로 가져오지 못합니다.\n시장 평균은 매출 포함 데이터라 비교 불가."),
    ("매출 압력이 낮음",
     "회수 안 되는 광고를 일찍 끄지 않아도 되는\n상태라 효율 좋은 광고만 남은 풀입니다.\n시장과 단순 비교가 공평하지 않음."),
]
y0 = Inches(3.4)
for i, (title, body) in enumerate(reasons):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(3.4), fill=LIGHT)
    add_text(s, x + Inches(0.3), y0 + Inches(0.3), Inches(3.4), Inches(1.0),
             title, font_size=15, bold=True, color=ACCENT)
    add_text(s, x + Inches(0.3), y0 + Inches(1.6), Inches(3.4), Inches(1.7),
             body, font_size=12, color=GRAY)


# ============================================================
# Slide 7 — 광고를 4개 그룹으로 나눠서 본다
# ============================================================
s = add_blank_slide()
add_header_bar(s, 8, TOTAL, "7. 풀 분리",
               "광고들을 4개 그룹으로 나눠서 봅니다")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.6),
         "왜 나눠 보는가 — 광고마다 \"회수 압력\"과 \"성숙도\"가 달라서, 같은 기준으로 비교하면 부정확.",
         font_size=14, color=GRAY)

mat_x = Inches(2.8)
mat_y = Inches(3.2)
cell_w = Inches(3.8)
cell_h = Inches(1.7)

add_text(s, mat_x + cell_w, mat_y - Inches(0.55), cell_w, Inches(0.4),
         "검증 중 (게시 7~14일)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
add_text(s, mat_x + cell_w*2, mat_y - Inches(0.55), cell_w, Inches(0.4),
         "검증 완료 (게시 15일 이후)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

add_text(s, mat_x - Inches(1.7), mat_y + Inches(0.5), Inches(1.7), Inches(0.4),
         "유료 협업", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.RIGHT)
add_text(s, mat_x - Inches(1.7), mat_y + cell_h + Inches(0.5), Inches(1.7), Inches(0.4),
         "무료 협업 (선물 제공)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.RIGHT)

cells = [
    (0, 0, "유료 × 검증 중", "검증 후 성과 좋으면\n검증 완료 그룹으로 이동", ACCENT2),
    (0, 1, "유료 × 검증 완료", "비용 회수 압력이 크므로\n부진하면 빠르게 정리", RED),
    (1, 0, "무료 × 검증 중", "데이터 수집 단계\n조작 X (학습 망가짐)", GRAY),
    (1, 1, "무료 × 검증 완료", "Top 광고라면 유료 협업으로\n전환 검토", GREEN),
]
for row, col, title, body, color in cells:
    x = mat_x + cell_w * (col + 1)
    y = mat_y + cell_h * row
    add_rect(s, x, y, cell_w, cell_h, fill=LIGHT)
    add_rect(s, x, y, Inches(0.1), cell_h, fill=color)
    add_text(s, x + Inches(0.25), y + Inches(0.2), cell_w - Inches(0.4), Inches(0.45),
             title, font_size=14, bold=True, color=NAVY)
    add_text(s, x + Inches(0.25), y + Inches(0.75), cell_w - Inches(0.4), Inches(0.9),
             body, font_size=11, color=GRAY)


# ============================================================
# Slide 8 — 광고 나이별 운영 규칙
# ============================================================
s = add_blank_slide()
add_header_bar(s, 9, TOTAL, "8. 광고 나이별 규칙",
               "갓 시작한 광고는 건드리지 않습니다")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "메타 광고는 초기에 \"학습\"을 합니다. 학습 중 변경하면 처음부터 다시 학습해야 합니다.",
         font_size=13, color=GRAY)
add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.5),
         "그래서 광고 나이에 따라 허용되는 작업이 다릅니다.",
         font_size=13, color=GRAY)

stages = [
    ("초기", "1~6일", "조회만\n예산·소재 변경 X", RED),
    ("검증 중", "7~14일", "광고비 ₩30K 누적\n후 평가", ACCENT2),
    ("검증 완료", "15~59일", "정상 운영\n증액·정리 평가", GREEN),
    ("노화", "60일 이상", "정리 검토 자동\n시작", GRAY),
]
y0 = Inches(3.3)
for i, (name, period, action, color) in enumerate(stages):
    x = Inches(0.7 + i * 3.15)
    add_rect(s, x, y0, Inches(3.0), Inches(3.0), fill=LIGHT)
    add_rect(s, x, y0, Inches(3.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(3.0), Inches(0.5),
             name, font_size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.0), Inches(3.0), Inches(0.6),
             period, font_size=22, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(2.0), Inches(3.0), Inches(0.9),
             action, font_size=12, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 9 — 인플루언서 영상의 5단계 구조
# ============================================================
s = add_blank_slide()
add_header_bar(s, 10, TOTAL, "9. 영상 만드는 법",
               "효과적인 인플루언서 영상의 5단계 구조")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "인플루언서 영상이 잘 팔리려면 아래 5단계가 들어가야 합니다. 처음 3단계는 필수입니다.",
         font_size=14, color=GRAY)

parts = [
    ("1. 후크",
     "첫 3초",
     "보는 사람이 \"어?\" 하고 멈춰서 계속 보고 싶어지는 부분",
     ACCENT2, "필수"),
    ("2. 정보 제공",
     "후크 직후",
     "의학·발달 지식 (예: \"6개월쯤 되면 아이 이가 이렇게 나기 시작합니다\")",
     ACCENT, "필수"),
    ("3. 제품 효과",
     "중반",
     "이 제품을 쓰면 아이에게 어떤 점이 좋은지",
     GREEN, "필수"),
    ("4. 실제 결과",
     "후반",
     "우리 아이가 이 제품을 쓴 후 어떻게 됐는지",
     GRAY, "선택"),
    ("5. 마무리",
     "마지막",
     "구매 페이지로 안내",
     GRAY, "선택"),
]
y0 = Inches(2.7)
for i, (name, pos, body, color, req) in enumerate(parts):
    y = y0 + Inches(i * 0.88)
    add_rect(s, Inches(0.7), y, Inches(11.9), Inches(0.78), fill=LIGHT)
    add_rect(s, Inches(0.7), y, Inches(0.15), Inches(0.78), fill=color)
    add_text(s, Inches(1.1), y + Inches(0.15), Inches(2.5), Inches(0.5),
             name, font_size=16, bold=True, color=NAVY)
    add_text(s, Inches(3.7), y + Inches(0.2), Inches(1.7), Inches(0.4),
             pos, font_size=12, color=GRAY)
    add_text(s, Inches(5.5), y + Inches(0.2), Inches(5.5), Inches(0.4),
             body, font_size=12, color=NAVY)
    req_color = RED if req == "필수" else GRAY
    add_text(s, Inches(11.1), y + Inches(0.2), Inches(1.3), Inches(0.4),
             req, font_size=12, bold=True, color=req_color, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 10 — 바이럴 영상 만드는 법
# ============================================================
s = add_blank_slide()
add_header_bar(s, 11, TOTAL, "10. 바이럴 전략",
               "한 명이 뜨면 다 같이 뜨는 방식")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "한 명한테 의뢰해서 잘 되길 기다리지 않습니다. 비슷한 영상을 동시에 여러 명에게 뿌립니다.",
         font_size=14, color=GRAY)

steps = [
    ("1", "리서치", "TikTok / 인스타그램에서\n관련 분야 바이럴 영상 찾기"),
    ("2", "평가", "좋아요·뷰 X\n저장·공유·댓글 수로 판단"),
    ("3", "선별", "제품에 대한 질문 댓글이\n많은 영상을 우선 참고"),
    ("4", "동시 의뢰", "참고할 영상을 골라\n인플루언서 10명에게 동시 발주"),
    ("5", "바이럴", "같은 주제 풀에서\n한 명 뜨면 비슷한 영상들도\n같이 추천 알고리즘 탐"),
]
y0 = Inches(2.7)
for i, (num, title, body) in enumerate(steps):
    x = Inches(0.5 + i * 2.55)
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.8), y0, Inches(0.7), Inches(0.7))
    circ.fill.solid(); circ.fill.fore_color.rgb = ACCENT
    circ.line.fill.background()
    add_text(s, x + Inches(0.8), y0 + Inches(0.1), Inches(0.7), Inches(0.5),
             num, font_size=22, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.0), Inches(2.3), Inches(0.5),
             title, font_size=16, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.6), Inches(2.3), Inches(2.0),
             body, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)
    if i < 4:
        add_text(s, x + Inches(2.2), y0 + Inches(0.15), Inches(0.5), Inches(0.5),
                 "→", font_size=24, color=GRAY, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.5), Inches(12.3), Inches(0.5),
         "왜 \"좋아요\"가 아니라 \"저장·댓글\"인가 — 좋아요는 가벼운 반응, 저장·댓글은 진짜 관심 신호.",
         font_size=12, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 11 — 매일 자동으로 돌아가는 파이프라인
# ============================================================
s = add_blank_slide()
add_header_bar(s, 12, TOTAL, "11. 일일 자동화",
               "매일 아침 9시, 자동으로 보고서가 옵니다")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "수동 작업 없이 매일 아침 9시경 메일로 자동 발송. 5단계 파이프라인이 순서대로 실행됩니다.",
         font_size=14, color=GRAY)

flow = [
    ("자동 시작",
     "매일 아침 5번\n나눠서 시도\n(누락 방지)",
     ACCENT),
    ("중복 방지",
     "오늘 이미 발송됐으면\n자동 건너뛰기",
     ACCENT2),
    ("보고서 생성",
     "어제 광고 데이터로\n표·차트·발견 정리",
     GREEN),
    ("자동 검증",
     "AI가 보고서 숫자\n정확성 점검\n80점 이상 통과",
     GRAY),
    ("메일 발송",
     "PASS 시에만\n담당자 메일로\n자동 발송",
     NAVY),
]
y0 = Inches(2.7)
box_w = Inches(2.3)
gap = Inches(0.15)
total_w = box_w * 5 + gap * 4
start_x = (SLIDE_W - total_w) // 2

for i, (title, body, color) in enumerate(flow):
    x = start_x + (box_w + gap) * i
    add_rect(s, x, y0, box_w, Inches(3.2), fill=LIGHT)
    add_rect(s, x, y0, box_w, Inches(0.6), fill=color)
    add_text(s, x, y0 + Inches(0.1), box_w, Inches(0.5),
             title, font_size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.0), box_w, Inches(2.0),
             body, font_size=12, color=NAVY, align=PP_ALIGN.CENTER)
    if i < 4:
        add_text(s, x + box_w, y0 + Inches(1.3), gap, Inches(0.5),
                 "▶", font_size=14, color=GRAY, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.3), Inches(12.3), Inches(0.5),
         "보고서 내용: 어제 광고 성과 / KPI 달성 카운터 / 끄기 후보 광고 목록 /",
         font_size=12, color=GRAY, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.5), Inches(6.8), Inches(12.3), Inches(0.5),
         "BEST/WORST 광고 / 오늘의 발견 3가지 / 메타몽 (운영 AI) 조언",
         font_size=12, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 12 — 업계 평균과 비교
# ============================================================
s = add_blank_slide()
add_header_bar(s, 13, TOTAL, "12. 업계 평균과 비교",
               "광고주들은 보통 몇 %를 winner / kill로 자르나?")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "광고 업계 분석 3곳 — 보통 상위 5%만 살리고, 하위 50~60%는 빠르게 정리합니다.",
         font_size=14, color=GRAY)

sources = [
    ("Motion (2026 발표)",
     "55만 개 광고\n광고비 1.3B 달러 분석",
     "상위 5%",
     "하위 50% 정리"),
    ("Alex Neiman\n(DTC 6개 브랜드)",
     "1,847개 광고\n12개월 운영",
     "상위 5.1% (94개)",
     "3주차에 하위 60% 정리"),
    ("coinis (DTC 가이드)",
     "글로벌 DTC 광고 컨설팅",
     "14일 후 상위 광고 증액",
     "전환 0 + CPA 3배 = 즉시 정리"),
]
y0 = Inches(2.7)
for i, (name, scale, winner, kill) in enumerate(sources):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.5), fill=LIGHT)
    add_text(s, x, y0 + Inches(0.15), Inches(4.0), Inches(0.6),
             name, font_size=15, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.9), Inches(4.0), Inches(0.7),
             scale, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.55), Inches(4.0), Inches(0.4),
             winner, font_size=13, bold=True, color=GREEN, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(2.0), Inches(4.0), Inches(0.4),
             kill, font_size=13, bold=True, color=RED, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(5.7), Inches(11.9), Inches(1.3), fill=NAVY)
add_text(s, Inches(1.0), Inches(5.9), Inches(11), Inches(0.5),
         "우리는 좀 더 보수적으로 운영합니다",
         font_size=15, bold=True, color=WHITE)
add_text(s, Inches(1.0), Inches(6.4), Inches(11), Inches(0.5),
         "광고 수가 15개로 적어 통계가 출렁이기 쉬워서, 상위 10% / 하위 20%만 잘라 봅니다.",
         font_size=13, color=WHITE)


# ============================================================
# Slide 13 — 예산 정책 (현재 입장)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 14, TOTAL, "13. 운영 입장",
               "예산은 늘리지 않습니다 (현재)")

add_text(s, Inches(0.5), Inches(1.9), Inches(12.3), Inches(0.5),
         "효율이 좋은 광고가 있어도 예산을 늘리지 않습니다. 신규 영상 제작에 집중합니다.",
         font_size=15, color=NAVY)

add_rect(s, Inches(0.7), Inches(2.6), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.75), Inches(11.3), Inches(0.4),
         "현재 정책",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(3.15), Inches(11.3), Inches(0.5),
         "광고 예산 증액 X / 신규 영상 제작에 집중",
         font_size=18, bold=True, color=WHITE)

reasons = [
    ("광고 시스템 한계",
     "예산을 늘려도 메타 알고리즘이\n분배를 다시 합니다. 지금 잘 나오는\n광고의 비중이 유지된다는 보장이 없습니다.",
     ACCENT),
    ("매출 측정 불가",
     "결제는 라쿠텐에서 이뤄집니다.\n어떤 광고가 진짜 매출을 만들었는지\n광고 단위로 측정하지 못합니다.",
     ACCENT2),
    ("외부 자문 일관",
     "자연 검색 매출이 약한 상태에서\n광고 예산을 늘려도 매출은\n비례해 늘지 않는다는 조언이 일치합니다.",
     GREEN),
]
y0 = Inches(3.9)
for i, (title, body, color) in enumerate(reasons):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.2), fill=LIGHT)
    add_rect(s, x, y0, Inches(0.15), Inches(2.2), fill=color)
    add_text(s, x + Inches(0.4), y0 + Inches(0.2), Inches(3.4), Inches(0.5),
             title, font_size=15, bold=True, color=color)
    add_text(s, x + Inches(0.4), y0 + Inches(0.85), Inches(3.4), Inches(1.3),
             body, font_size=11, color=GRAY)

add_rect(s, Inches(0.7), Inches(6.3), Inches(11.9), Inches(0.85), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.4), Inches(11.3), Inches(0.4),
         "정책 해제 조건",
         font_size=12, bold=True, color=GRAY)
add_text(s, Inches(1.0), Inches(6.75), Inches(11.3), Inches(0.4),
         "메타 광고비 × 라쿠텐 매출 매칭 도구 완성 후 — ROI 가시화되면 재오픈 검토",
         font_size=13, color=NAVY)


# ============================================================
# Slide 14 — 앞으로 할 일 + 마무리
# ============================================================
s = add_blank_slide()
add_header_bar(s, 15, TOTAL, "14. 앞으로",
               "다음 단계 — 더 정확한 효율 측정으로")

todos = [
    ("이번 달",
     "메타 광고비 × 라쿠텐 매출 매칭 도구",
     "지금은 클릭률만 보고 판단. 진짜 매출과 연결해 ROI 가시화.",
     ACCENT),
    ("다음 달",
     "성과 좋은 인플루언서 자동 발굴",
     "상위 10% 광고를 만든 인플루언서를 자동 리스트업해 다음 협업 대상으로.",
     ACCENT2),
    ("다음 달",
     "광고 피로도 사전 알림",
     "같은 사람한테 2.3번 노출되면 미리 알림. 3.0번 도달 후 사후 대응 X.",
     GREEN),
    ("6주 후",
     "유료/무료 협업 기준 분리 재평가",
     "운영 데이터 6주 쌓이면 두 그룹에 다른 기준 적용 검토.",
     GRAY),
]
y0 = Inches(2.1)
for i, (when, title, body, color) in enumerate(todos):
    y = y0 + Inches(i * 1.0)
    add_rect(s, Inches(0.7), y, Inches(11.9), Inches(0.9), fill=LIGHT)
    add_rect(s, Inches(0.7), y, Inches(0.15), Inches(0.9), fill=color)
    add_text(s, Inches(1.1), y + Inches(0.25), Inches(1.8), Inches(0.5),
             when, font_size=14, bold=True, color=color)
    add_text(s, Inches(3.0), y + Inches(0.1), Inches(8.5), Inches(0.45),
             title, font_size=16, bold=True, color=NAVY)
    add_text(s, Inches(3.0), y + Inches(0.5), Inches(8.5), Inches(0.4),
             body, font_size=12, color=GRAY)

add_text(s, Inches(0.5), Inches(6.5), Inches(12.3), Inches(0.5),
         "이 운영 체계는 살아있는 문서입니다. 6주 후 운영 데이터 보고 기준을 재조정합니다.",
         font_size=12, color=GRAY, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.5), Inches(6.95), Inches(12.3), Inches(0.4),
         "변경 내역은 모두 기록으로 남깁니다.",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


prs.save(str(OUT))
print(f"[OK] saved {OUT} ({OUT.stat().st_size:,} bytes)")
