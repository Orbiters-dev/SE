"""
ORBI Grosmimi JP — Meta Ads 운영 기준 v2 (2026-05-22)

대상: 메타 광고 기본 어휘 (CTR/CPC/Reach/Frequency/Ad Set 등) 는 아는 사람.
톤: 우리만 쓰는 jargon (percentile / Off Rule / Graduation / VTR / ABO·CBO / delivery 등) 만 자연어화.
2026-05-15 ~ 5/21 에 새로 합의된 룰 전부 반영.

저장: C:\\Users\\orbit\\Desktop\\s\\메타\\09_meta_ads_standards_v2.pptx
"""
import io
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = Path(r"C:\Users\orbit\Desktop\s\performance marketing\META ADS 관리용\operations\09_meta_ads_standards_v2.pptx")
OUT.parent.mkdir(parents=True, exist_ok=True)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SLIDE_W = prs.slide_width
SLIDE_H = prs.slide_height

NAVY = RGBColor(0x1F, 0x29, 0x37)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
ACCENT2 = RGBColor(0xDB, 0x27, 0x77)
LIGHT = RGBColor(0xF9, 0xFA, 0xFB)
GRAY = RGBColor(0x6B, 0x72, 0x80)
GREEN = RGBColor(0x05, 0x96, 0x69)
RED = RGBColor(0xDC, 0x26, 0x26)
AMBER = RGBColor(0xD9, 0x77, 0x06)
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
             title, font_size=28, bold=True, color=NAVY)
    add_rect(slide, Inches(0.5), Inches(1.55), Inches(0.8), Emu(40000), fill=ACCENT)
    if subtitle:
        add_text(slide, Inches(0.5), Inches(1.7), Inches(12), Inches(0.5),
                 subtitle, font_size=14, color=GRAY)


TOTAL = 16


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
         "Meta Ads 운영 기준", font_size=54, bold=True, color=WHITE)
add_text(s, Inches(0.7), Inches(3.7), Inches(12), Inches(0.9),
         "2026년 5월 현재 — 풀 percentile 기반 자체 기준",
         font_size=26, bold=True, color=ACCENT)

add_text(s, Inches(0.7), Inches(5.2), Inches(12), Inches(0.5),
         "캠페인 구조 · ON/Off 룰 · Testing→Proven 졸업 · 예산 정책 · 분석 사이클",
         font_size=16, color=WHITE)

add_text(s, Inches(0.7), Inches(6.5), Inches(12), Inches(0.4),
         "v2 / 2026-05-22 — 5/15 Off Rule 재설계 · 5/19 ON 게이트 · 5/21 Graduation 반영",
         font_size=11, color=GRAY)


# ============================================================
# Slide 2 — 광고 풀 구조 (2×2 매트릭스)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 2, TOTAL, "1. 풀 구조",
               "광고를 4개 그룹으로 나눠서 운영합니다",
               subtitle="협업 형태(PAID/GIFT) × 학습 단계(Testing/Proven) 2축 분리")

add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.5),
         "한 풀로 묶어 평가하면 비용 회수 압력과 데이터 성숙도가 섞여 부정확해집니다.",
         font_size=13, color=GRAY)

mat_x = Inches(3.2)
mat_y = Inches(3.4)
cell_w = Inches(3.6)
cell_h = Inches(1.6)

add_text(s, mat_x + cell_w, mat_y - Inches(0.55), cell_w, Inches(0.4),
         "Testing (게시 1~14일)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
add_text(s, mat_x + cell_w*2, mat_y - Inches(0.55), cell_w, Inches(0.4),
         "Proven (졸업 후)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

add_text(s, mat_x - Inches(1.8), mat_y + Inches(0.5), Inches(1.7), Inches(0.4),
         "PAID (유상 협업)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.RIGHT)
add_text(s, mat_x - Inches(1.8), mat_y + cell_h + Inches(0.5), Inches(1.7), Inches(0.4),
         "GIFT (무상 협업)", font_size=13, bold=True, color=NAVY, align=PP_ALIGN.RIGHT)

cells = [
    (0, 0, "PAID × Testing", "비용 회수 압력 + 데이터 미성숙\n무리한 Off X · 학습 보호 우선", ACCENT2),
    (0, 1, "PAID × Proven", "졸업한 회수 압력 광고\n부진하면 우선 정리 대상", RED),
    (1, 0, "GIFT × Testing", "데이터 수집 단계\nOff 액션 자체 보류", GRAY),
    (1, 1, "GIFT × Proven", "Top 성과면 PAID 전환 검토\n예산 압력 낮아 보존 우선", GREEN),
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

add_text(s, Inches(0.5), Inches(6.8), Inches(12.3), Inches(0.4),
         "광고 이름에 PAID/GIFT 라벨로 박혀 있어 자동 분류됩니다 (2026-05-15 17개 ad rename 완료).",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 3 — 통화·계정 가정
# ============================================================
s = add_blank_slide()
add_header_bar(s, 3, TOTAL, "2. 통화 가정",
               "JP 계정 통화는 KRW 입니다 (¥ 아님)",
               subtitle="일본 시장 타겟이라 ¥ 로 가정하기 쉬운 함정")

add_rect(s, Inches(0.7), Inches(2.5), Inches(11.9), Inches(1.4), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.7), Inches(11.3), Inches(0.4),
         "Ad Account act_4117678028561958 (Grosmimi JP)",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(3.1), Inches(11.3), Inches(0.6),
         "currency = KRW",
         font_size=36, bold=True, color=WHITE)

add_text(s, Inches(0.5), Inches(4.4), Inches(12.3), Inches(0.5),
         "Ads Manager 표시는 ¥ 처럼 보여도 실제 청구·집계 통화는 원화입니다.",
         font_size=15, color=NAVY)
add_text(s, Inches(0.5), Inches(5.0), Inches(12.3), Inches(0.5),
         "이 자료의 모든 금액 (CPC, 일 지출, KPI ₩100) 도 원화 기준입니다.",
         font_size=15, color=NAVY)

add_rect(s, Inches(0.7), Inches(5.9), Inches(11.9), Inches(1.2), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.4),
         "왜 짚는가",
         font_size=12, bold=True, color=GRAY)
add_text(s, Inches(1.0), Inches(6.4), Inches(11.3), Inches(0.6),
         "내부 SOP·외부 보고서가 ¥ 표기로 carry over 되어 환산 사고가 반복됨.\n작업 전 Graph API 로 currency 필드 직접 확인 후 진행이 룰.",
         font_size=12, color=NAVY)


# ============================================================
# Slide 4 — Creative와 Budget 독립
# ============================================================
s = add_blank_slide()
add_header_bar(s, 4, TOTAL, "3. 두 가지 레버",
               "Creative (소재) 와 Budget (예산) 은 별도로 다룹니다",
               subtitle='"A 대신 B" 묶음 X — 각 레버 독립 판단')

add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.5),
         "광고 성과를 움직일 수 있는 두 가지 손잡이가 있고, 우리는 이 둘을 따로 본다는 입장입니다.",
         font_size=13, color=GRAY)

cards = [
    ("Creative 레버", "소재 (영상 / 이미지) 자체를 바꾸는 액션",
     "현재 우리가 주로 쓰는 레버 — 새 콜라보 발주\n인플루언서 매칭, 영상 구조, 후크 변경",
     "활성 운용 중", ACCENT),
    ("Budget 레버", "예산·구조 (캠페인·Ad Set 레벨) 를 바꾸는 액션",
     "현재 보류 중 — 매출 매칭 도구 완성 전까지\n증액 권고 안 함 (ROI 미검증)",
     "현재 보류", AMBER),
]
y0 = Inches(3.1)
for i, (name, sub, body, status, color) in enumerate(cards):
    x = Inches(0.7 + i * 6.3)
    add_rect(s, x, y0, Inches(5.9), Inches(3.5), fill=LIGHT)
    add_rect(s, x, y0, Inches(5.9), Inches(0.8), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(5.9), Inches(0.5),
             name, font_size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.4), y0 + Inches(1.0), Inches(5.1), Inches(0.5),
             sub, font_size=13, color=GRAY)
    add_text(s, x + Inches(0.4), y0 + Inches(1.6), Inches(5.1), Inches(1.4),
             body, font_size=13, color=NAVY)
    add_rect(s, x + Inches(0.4), y0 + Inches(2.9), Inches(5.1), Inches(0.5), fill=color)
    add_text(s, x + Inches(0.4), y0 + Inches(2.95), Inches(5.1), Inches(0.4),
             status, font_size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.85), Inches(12.3), Inches(0.4),
         "두 레버를 묶어서 \"예산 증액 대신 신규 영상\" 식으로 트레이드오프 X — 각각 따로 판단.",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 5 — ON 진입 기준 (D+3 VTR)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 5, TOTAL, "4. ON 진입 기준",
               "어떤 영상을 광고로 돌릴지 — D+3 VTR 게이트",
               subtitle="ON 후 끄면 학습이 망가지므로 사전 선별로 잡습니다")

add_rect(s, Inches(0.7), Inches(2.4), Inches(11.9), Inches(0.95), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.55), Inches(11.3), Inches(0.4),
         "지표 — D+3 VTR (View-to-Follower Ratio, 조회율)",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(2.95), Inches(11.3), Inches(0.4),
         "게시 후 3일 시점 조회수  ÷  게시 시점 팔로워 수  × 100%",
         font_size=16, bold=True, color=WHITE)

gates = [
    ("VTR < 100%",
     "ON 안 함",
     "본인 팔로워조차 다 도달 못함\n= 영상 hook 약함\n알고리즘 외부 explore 푸시 없음",
     RED),
    ("VTR 100~200%",
     "ON 고려",
     "본인 팔로워 거의 도달\n+ 약간의 외부 explore 시작\n= 평균선",
     ACCENT2),
    ("VTR 200% 이상",
     "적극 ON",
     "외부 explore 푸시 통과\n= hook 통한 신호 확인\n광고 효율 기대 가능",
     GREEN),
]
y0 = Inches(3.6)
for i, (band, action, body, color) in enumerate(gates):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.6), fill=LIGHT)
    add_rect(s, x, y0, Inches(4.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(4.0), Inches(0.5),
             band, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.9), Inches(4.0), Inches(0.6),
             action, font_size=22, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.7), Inches(4.0), Inches(0.9),
             body, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.4), Inches(11.9), Inches(0.75), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.5), Inches(11.3), Inches(0.4),
         "PAID / GIFT 풀 차등 없이 통합 기준 — VTR 200%+ 면 무상 영상이라도 적극 ON.",
         font_size=12, color=NAVY)
add_text(s, Inches(1.0), Inches(6.85), Inches(11.3), Inches(0.4),
         "ON 후 7일은 손대지 않습니다 (다음 슬라이드).",
         font_size=11, color=GRAY)


# ============================================================
# Slide 6 — ON 후 학습 보호
# ============================================================
s = add_blank_slide()
add_header_bar(s, 6, TOTAL, "5. 학습 단계 보호",
               "ON 직후 7일은 손대지 않습니다",
               subtitle="메타 알고리즘 학습 중에 변경하면 처음부터 다시 학습")

stages = [
    ("D+0 ~ D+6", "학습 중", "조회만\n예산·소재·타겟 변경 X\nOff 액션 X", RED),
    ("D+7", "학습 종료", "Off Rule 4축\n정식 적용 시작", ACCENT2),
    ("D+8 ~ D+30", "Testing 운영", "성과 게이트로\n매일 모니터링\nGraduation 후보 추적", GREEN),
    ("D+30 이후", "Proven 후보", "졸업 기준 hit 시\nProven 으로 이동", NAVY),
]
y0 = Inches(2.6)
for i, (when, name, action, color) in enumerate(stages):
    x = Inches(0.7 + i * 3.15)
    add_rect(s, x, y0, Inches(3.0), Inches(3.2), fill=LIGHT)
    add_rect(s, x, y0, Inches(3.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(3.0), Inches(0.5),
             when, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.0), Inches(3.0), Inches(0.6),
             name, font_size=20, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.9), Inches(3.0), Inches(1.2),
             action, font_size=12, color=GRAY, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.1), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(6.25), Inches(11.3), Inches(0.4),
         "왜 7일인가",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(6.65), Inches(11.3), Inches(0.4),
         "메타는 광고 ON 후 50개 전환 또는 7일 누적 학습을 통해 분배 (delivery) 알고리즘을 안정화. 이전 변경은 학습 리셋.",
         font_size=12, color=WHITE)


# ============================================================
# Slide 7 — Off Rule (4축)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 7, TOTAL, "6. Off Rule",
               "끄기 기준 — 4가지 신호 (첫 신호는 2중 게이트)",
               subtitle="우리 풀끼리 줄 세우고 + 절대 기준 동시 hit 만 강한 신호")

axes = [
    ("축 1 — 풀 하위 20% AND 절대 기준 동시 hit",
     "우리 광고들끼리 줄 세워 하위 20% (P20) 이고,\n동시에 CTR < KPI×0.5 또는 CPC > KPI×2 인 경우만 Off.\n한쪽만 hit 이면 1~2주 모니터링 후 재평가.",
     "가장 중요 · 2중 게이트",
     ACCENT),
    ("축 2 — Frequency 2.5 이상",
     "같은 사람에게 평균 2.5번 이상 노출.\n반복 노출 시 클릭 의지 소실.\n광고비 무관 즉시 점검 대상.",
     "피로도 신호",
     RED),
    ("축 3 — 최근 7일 CTR 15% 이상 하락",
     "검증 완료 광고가 갑자기 효율 떨어지는 경우.\n다른 인플루언서와 새 콜라보 발주 (같은 영상 재의뢰 X).",
     "추세 신호 (velocity)",
     ACCENT2),
    ("축 4 — D+60 단독 폐기",
     "예전엔 \"60일 경과 = 자동 Off 검토\".\n이제는 시간 단독으로 Off X — 성과 부진 또는\ndelivery 실패와 함께 hit 시에만.",
     "5/19 룰 변경",
     GRAY),
]
y0 = Inches(2.4)
for i, (name, cond, label, color) in enumerate(axes):
    col = i % 2
    row = i // 2
    x = Inches(0.7 + col * 6.3)
    y = y0 + Inches(row * 2.3)
    add_rect(s, x, y, Inches(5.9), Inches(2.1), fill=LIGHT)
    add_rect(s, x, y, Inches(0.15), Inches(2.1), fill=color)
    add_text(s, x + Inches(0.4), y + Inches(0.15), Inches(5.3), Inches(0.45),
             label, font_size=11, bold=True, color=color)
    add_text(s, x + Inches(0.4), y + Inches(0.55), Inches(5.3), Inches(0.5),
             name, font_size=13, bold=True, color=NAVY)
    add_text(s, x + Inches(0.4), y + Inches(1.05), Inches(5.3), Inches(1.0),
             cond, font_size=11, color=GRAY)

add_text(s, Inches(0.5), Inches(7.05), Inches(12.3), Inches(0.4),
         "Off 의사결정은 4개 축 신호를 합쳐 메타몽 / 세은이 판단. 자동 Off 액션은 없음.",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 8 — WL 광고 수명
# ============================================================
s = add_blank_slide()
add_header_bar(s, 8, TOTAL, "7. WL 광고 수명",
               "Whitelisting 영상은 3~6개월 운용",
               subtitle="시간만으로 끄지 않습니다 — 성과 부진과 함께 hit 시에만")

add_rect(s, Inches(0.7), Inches(2.3), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.45), Inches(11.3), Inches(0.4),
         "Whitelisting (WL) — 인플루언서 게시물을 광고로 재활용",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(2.85), Inches(11.3), Inches(0.4),
         "표준 운용 기간: 3 ~ 6 개월",
         font_size=22, bold=True, color=WHITE)

add_text(s, Inches(0.5), Inches(3.7), Inches(12.3), Inches(0.5),
         "Off 조건",
         font_size=15, bold=True, color=NAVY)

conds = [
    ("✅ Off OK", "성과 부진 (Off Rule 축 1 hit) — 풀 하위 20% + 절대 기준 동시", GREEN),
    ("✅ Off OK", "delivery 실패 — 노출 분배 0 또는 극저 (메타 알고리즘 push 중단)", GREEN),
    ("❌ Off X", "단순 D+60 / D+90 / D+180 도달 — 시간 자체로는 끄지 않음", RED),
    ("⚠ 보류", "Frequency 3.0 hit 도 단독으론 Off X — 다른 축과 함께 hit 시 재평가", AMBER),
]
y0 = Inches(4.2)
for i, (mark, body, color) in enumerate(conds):
    y = y0 + Inches(i * 0.62)
    add_rect(s, Inches(0.7), y, Inches(11.9), Inches(0.55), fill=LIGHT)
    add_rect(s, Inches(0.7), y, Inches(0.12), Inches(0.55), fill=color)
    add_text(s, Inches(1.0), y + Inches(0.12), Inches(1.7), Inches(0.4),
             mark, font_size=12, bold=True, color=color)
    add_text(s, Inches(2.7), y + Inches(0.12), Inches(10.0), Inches(0.4),
             body, font_size=12, color=NAVY)

add_text(s, Inches(0.5), Inches(7.0), Inches(12.3), Inches(0.4),
         "예전 룰 (D+60 sunset 자동 Off 후보) 은 2026-05-19 폐기됨.",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 9 — Graduation 게이트 (triple share)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 9, TOTAL, "8. Graduation",
               "Testing → Proven 졸업 기준 (Triple Share)",
               subtitle="알고리즘이 \"이 광고는 검증됐다\" 라고 인정한 풀로 이동시키는 룰")

add_rect(s, Inches(0.7), Inches(2.3), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.45), Inches(11.3), Inches(0.4),
         "필수 조건 — 아래 5개 게이트 모두 통과",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(2.85), Inches(11.3), Inches(0.4),
         "(분배 점유 3개) + (성과 게이트 2개) 모두 hit",
         font_size=18, bold=True, color=WHITE)

add_text(s, Inches(0.5), Inches(3.6), Inches(12.3), Inches(0.5),
         "Triple Share — 풀 안에서 분배·반응·LP 도달을 모두 점유한 광고만 졸업",
         font_size=13, bold=True, color=NAVY)

shares = [
    ("Spend Share",
     "7일 누적 광고비 점유율",
     "≥ 50%",
     "분배 받은 비중",
     ACCENT),
    ("Click Share",
     "7일 누적 클릭 점유율",
     "≥ 50%",
     "실제 반응 비중",
     ACCENT2),
    ("LPV Share",
     "7일 누적 LP 도달 점유율",
     "≥ 50%",
     "LP까지 끌고 간 비중",
     GREEN),
]
y0 = Inches(4.2)
for i, (name, sub, target, body, color) in enumerate(shares):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.0), fill=LIGHT)
    add_rect(s, x, y0, Inches(4.0), Inches(0.5), fill=color)
    add_text(s, x, y0 + Inches(0.08), Inches(4.0), Inches(0.4),
             name, font_size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.65), Inches(4.0), Inches(0.4),
             sub, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.05), Inches(4.0), Inches(0.5),
             target, font_size=24, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.55), Inches(4.0), Inches(0.4),
             body, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.4), Inches(11.9), Inches(0.75), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.5), Inches(11.3), Inches(0.4),
         "+ 성과 게이트 — CTR · CPC · Frequency 가 KPI 기준 통과 시에만 졸업",
         font_size=12, bold=True, color=NAVY)
add_text(s, Inches(1.0), Inches(6.85), Inches(11.3), Inches(0.4),
         "분배만 점유한 \"fake winner\" (CTR 낮은데 spend share 50%+) 거르는 장치.",
         font_size=11, color=GRAY)


# ============================================================
# Slide 10 — 외부 시장 평균 사용 금지
# ============================================================
s = add_blank_slide()
add_header_bar(s, 10, TOTAL, "9. 판단 기준",
               '"외부 시장 평균" 은 끄기 임계로 쓰지 않습니다',
               subtitle="우리 풀끼리만 비교 (percentile · 시간 · Freq · velocity)")

add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.5),
         '예: "유아용품 광고 평균 CTR 1.91%" 같은 외부 벤치마크를 Off 트리거로 쓰지 않습니다.',
         font_size=14, color=NAVY)

reasons = [
    ("우리 광고는 15개,\n시장 데이터는 50만 개",
     "표본 크기 차이로 \"평균\" 의미가 달라집니다.\n적은 광고로 큰 시장과 비교하면 통계가 출렁여 부정확.",
     ACCENT),
    ("매출 데이터 미연결",
     "결제는 Rakuten LP 에서.\nMeta Pixel Purchase 미작동 — ROI 미검증.\n시장 평균은 매출 포함 데이터라 비교 공평하지 않음.",
     ACCENT2),
    ("우리 풀은 이미 효율 선별된 풀",
     "회수 압력이 낮아 부진 광고를 일찍 끄지 않는 운영.\n자연스럽게 효율 좋은 광고만 남은 상태 → \n시장 풀과 단순 비교 X.",
     GREEN),
]
y0 = Inches(3.1)
for i, (title, body, color) in enumerate(reasons):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(3.4), fill=LIGHT)
    add_rect(s, x, y0, Inches(0.12), Inches(3.4), fill=color)
    add_text(s, x + Inches(0.35), y0 + Inches(0.25), Inches(3.5), Inches(1.1),
             title, font_size=14, bold=True, color=color)
    add_text(s, x + Inches(0.35), y0 + Inches(1.6), Inches(3.5), Inches(1.7),
             body, font_size=11, color=GRAY)

add_rect(s, Inches(0.7), Inches(6.8), Inches(11.9), Inches(0.5), fill=NAVY)
add_text(s, Inches(1.0), Inches(6.87), Inches(11.3), Inches(0.4),
         "참고용으로만 인용 — Motion(2026) winner 5% / kill 50% · Alex Neiman bottom 60% / 우리는 보수적 P20.",
         font_size=11, color=WHITE)


# ============================================================
# Slide 11 — 예산 정책
# ============================================================
s = add_blank_slide()
add_header_bar(s, 11, TOTAL, "10. 예산 정책",
               "광고 예산은 늘리지 않습니다 (현재)",
               subtitle="매출 매칭 도구 완성 전까지 ROI 미검증 — Creative 레버만 운용")

add_rect(s, Inches(0.7), Inches(2.4), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.55), Inches(11.3), Inches(0.4),
         "현재 정책",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(2.95), Inches(11.3), Inches(0.5),
         "예산 증액 · CBO 자동 분배 변경 모두 권고 X",
         font_size=18, bold=True, color=WHITE)

reasons = [
    ("ABO 한계",
     "Ad Set 단위 예산 (ABO) 으로 운영 중.\n증액 시 메타 알고리즘이 분배를 다시 함 →\n지금 잘 나오는 광고 비중 유지 보장 X.",
     ACCENT),
    ("Purchase 미작동",
     "JP 는 Rakuten LP 라\nMeta Pixel 의 Purchase 이벤트가 안 잡힙니다.\n광고별 매출 측정 불가 → ROI 미검증.",
     ACCENT2),
    ("외부 자문 일관",
     "자연 검색 약한 상태에서 광고 예산만\n늘려도 매출은 비례 증가 안 함 — 외부 컨설팅도\n매출 매칭 선결 권고.",
     GREEN),
]
y0 = Inches(3.7)
for i, (title, body, color) in enumerate(reasons):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(2.4), fill=LIGHT)
    add_rect(s, x, y0, Inches(0.12), Inches(2.4), fill=color)
    add_text(s, x + Inches(0.35), y0 + Inches(0.2), Inches(3.5), Inches(0.5),
             title, font_size=15, bold=True, color=color)
    add_text(s, x + Inches(0.35), y0 + Inches(0.85), Inches(3.5), Inches(1.5),
             body, font_size=11, color=GRAY)

add_rect(s, Inches(0.7), Inches(6.4), Inches(11.9), Inches(0.85), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.5), Inches(11.3), Inches(0.4),
         "정책 해제 조건",
         font_size=12, bold=True, color=GRAY)
add_text(s, Inches(1.0), Inches(6.85), Inches(11.3), Inches(0.4),
         "메타 광고비 × Rakuten 매출 매칭 도구 완성 후 — ROI 가시화되면 증액 룰 재개정",
         font_size=13, color=NAVY)


# ============================================================
# Slide 12 — 최근 운영 케이스 (5/20~5/21 ON / Graduate)
# ============================================================
s = add_blank_slide()
add_header_bar(s, 12, TOTAL, "11. 최근 운영 케이스",
               "5/20 ~ 5/21 ON · Graduate 4건",
               subtitle="PAID/GIFT 라벨 + adset 풀별 적용 룰 매핑")

cases = [
    {
        "title": "komugiko",
        "label": "PAID · Stainless 300ml",
        "action": "Testing → Proven 졸업",
        "action_color": ACCENT,
        "date": "5/21",
        "data": "Testing 7d 누적\n₩146,497  ·  1,458 click  ·  960 LPV\nCTR 6.27%  ·  CPC ₩87  ·  Freq 1.49",
        "rule_head": "Graduation 게이트 (11p) PASS",
        "rule_body": "• triple share : spend / clicks / LPV 모두 ≥ 50%\n• CTR ≥ KPI×0.6 (4.8%) — 6.27% PASS\n• CPC ≤ KPI×1.5 (₩150) — ₩87 PASS\n• Freq < 3 — 1.49 PASS",
    },
    {
        "title": "rii",
        "label": "PAID · PPSU 300ml",
        "action": "Testing 신규 ON",
        "action_color": GREEN,
        "date": "5/21",
        "data": "누적 (D+1)\n₩11,605  ·  96 click  ·  72 LPV\nCTR 5.62%  ·  CPC ₩121  ·  Freq 1.08",
        "rule_head": "ON 게이트 (5p) — D+3 VTR",
        "rule_body": "• 영상 D+3 VTR 게이트 통과 → 광고화\n• 초기 CTR 5.62% (KPI×0.5 = 4.0% 통과)\n• CPC ₩121 (KPI×2 = ₩200 통과)\n• 학습 단계 7일 lock 진행 중",
    },
    {
        "title": "iroiro",
        "label": "GIFT · Stainless 200ml",
        "action": "Testing 신규 ON",
        "action_color": GREEN,
        "date": "5/20",
        "data": "누적 (D+2)\n₩18,368  ·  143 click  ·  62 LPV\nCTR 6.16%  ·  CPC ₩128  ·  Freq 1.12",
        "rule_head": "ON 게이트 (5p) — D+3 VTR",
        "rule_body": "• 영상 D+3 VTR 게이트 통과 → 광고화\n• CTR 6.16% (KPI×0.5 = 4.0% 통과)\n• CPC ₩128 (KPI×2 = ₩200 통과)\n• GIFT 풀 — 회수 압력 약함 → 변형 확보",
    },
    {
        "title": "meu",
        "label": "GIFT · Stainless 300ml",
        "action": "Testing 신규 ON · 모니터링",
        "action_color": AMBER,
        "date": "5/20",
        "data": "누적 (D+2)\n₩831  ·  3 click  ·  3 LPV\nCTR 2.61%  ·  CPC ₩277  ·  Freq 1.01",
        "rule_head": "ON 게이트 통과 / 평가 보류",
        "rule_body": "• 영상 D+3 VTR 게이트 통과 → 광고화\n• 절대 기준 hit (CTR < 4.0%, CPC > ₩200)\n• 단 imp 115 < delivery floor (5K)\n• Off Rule floor 미충족 → 모니터링 유지",
    },
]

# 2 x 2 그리드 — 박스 안 좌측 50% = 동작·데이터 / 우측 50% = 판단 기준
box_w = Inches(6.05)
box_h = Inches(2.35)
gx = [Inches(0.55), Inches(6.75)]
gy = [Inches(2.1), Inches(4.55)]
for i, c in enumerate(cases):
    col = i % 2
    row = i // 2
    x = gx[col]
    y = gy[row]
    add_rect(s, x, y, box_w, box_h, fill=LIGHT)
    add_rect(s, x, y, Inches(0.13), box_h, fill=c["action_color"])

    add_text(s, x + Inches(0.3), y + Inches(0.12), Inches(3.0), Inches(0.4),
             c["title"], font_size=17, bold=True, color=NAVY)
    add_text(s, x + Inches(0.3), y + Inches(0.5), Inches(4.0), Inches(0.3),
             c["label"], font_size=10, color=GRAY)
    add_rect(s, x + Inches(4.55), y + Inches(0.15), Inches(1.4), Inches(0.35), fill=c["action_color"])
    add_text(s, x + Inches(4.55), y + Inches(0.2), Inches(1.4), Inches(0.3),
             c["date"], font_size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    add_text(s, x + Inches(0.3), y + Inches(0.88), Inches(2.85), Inches(0.4),
             c["action"], font_size=12, bold=True, color=c["action_color"])
    add_text(s, x + Inches(0.3), y + Inches(1.25), Inches(2.85), Inches(1.0),
             c["data"], font_size=9, color=NAVY)

    add_rect(s, x + Inches(3.2), y + Inches(0.88), Inches(0.02), Inches(1.35), fill=GRAY)

    add_text(s, x + Inches(3.3), y + Inches(0.88), Inches(2.65), Inches(0.35),
             c["rule_head"], font_size=10, bold=True, color=c["action_color"])
    add_text(s, x + Inches(3.3), y + Inches(1.22), Inches(2.65), Inches(1.05),
             c["rule_body"], font_size=8, color=GRAY)

add_rect(s, Inches(0.55), Inches(7.05), Inches(12.25), Inches(0.35), fill=NAVY)
add_text(s, Inches(0.85), Inches(7.1), Inches(11.6), Inches(0.28),
         "Graduate = Testing 7d 누적 triple share / 신규 ON = D+3 VTR + 영상 평가 / 모니터링 = Off Rule delivery floor 미충족",
         font_size=9, color=WHITE)


# ============================================================
# Slide 13 — ad 단위 예산은 없다
# ============================================================
s = add_blank_slide()
add_header_bar(s, 13, TOTAL, "12. 구조 이해",
               '"광고(ad) 단위 예산" 이라는 건 존재하지 않습니다',
               subtitle="예산은 캠페인 / Ad Set 레벨만 — 광고 분배는 알고리즘 영역")

add_text(s, Inches(0.5), Inches(2.3), Inches(12.3), Inches(0.5),
         "Meta 구조에서 예산을 설정할 수 있는 단위는 두 곳 뿐입니다.",
         font_size=14, color=GRAY)

levels = [
    ("Campaign 레벨", "CBO (Campaign Budget Optimization)",
     "캠페인 1개에 일 예산 설정.\nAd Set 들 사이 자동 분배.",
     "예산 설정 O", GREEN),
    ("Ad Set 레벨", "ABO (Ad Set Budget Optimization)",
     "Ad Set 1개에 일 예산 설정.\n그 안의 Ad 들은 알고리즘 분배.",
     "예산 설정 O", GREEN),
    ("Ad 레벨", "개별 광고",
     "이 단위에 예산을 직접 설정 X.\n노출 분배는 메타 알고리즘 자체 판단.",
     "예산 설정 X", RED),
]
y0 = Inches(3.0)
for i, (name, sub, body, status, color) in enumerate(levels):
    x = Inches(0.7 + i * 4.3)
    add_rect(s, x, y0, Inches(4.0), Inches(3.3), fill=LIGHT)
    add_rect(s, x, y0, Inches(4.0), Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.15), Inches(4.0), Inches(0.5),
             name, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.3), y0 + Inches(1.0), Inches(3.4), Inches(0.4),
             sub, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.3), y0 + Inches(1.5), Inches(3.4), Inches(1.2),
             body, font_size=12, color=NAVY, align=PP_ALIGN.CENTER)
    add_rect(s, x + Inches(0.3), y0 + Inches(2.7), Inches(3.4), Inches(0.45), fill=color)
    add_text(s, x + Inches(0.3), y0 + Inches(2.75), Inches(3.4), Inches(0.4),
             status, font_size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.5), Inches(11.9), Inches(0.7), fill=NAVY)
add_text(s, Inches(1.0), Inches(6.6), Inches(11.3), Inches(0.4),
         "그래서 \"이 광고가 예산을 흡수했다 / 다른 광고로 예산이 밀렸다\" 같은 표현은 부정확합니다.",
         font_size=12, bold=True, color=WHITE)
add_text(s, Inches(1.0), Inches(6.95), Inches(11.3), Inches(0.4),
         "분배는 Ad Set 예산 안에서 알고리즘이 클릭·전환 신호 기반으로 결정.",
         font_size=11, color=WHITE)


# ============================================================
# Slide 13 — LPV / Pixel 신뢰 범위
# ============================================================
s = add_blank_slide()
add_header_bar(s, 14, TOTAL, "13. LP·전환 측정",
               "JP 는 Rakuten LP — LPV 까지만 신뢰",
               subtitle="Purchase 이벤트는 안 잡힙니다. Performance goal = LPV")

add_rect(s, Inches(0.7), Inches(2.3), Inches(11.9), Inches(1.0), fill=NAVY)
add_text(s, Inches(1.0), Inches(2.45), Inches(11.3), Inches(0.4),
         "현재 측정 가능 범위",
         font_size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(2.85), Inches(11.3), Inches(0.4),
         "Impression → Click → Landing Page View (LPV) 까지만 신뢰",
         font_size=16, bold=True, color=WHITE)

events = [
    ("Impression", "노출", "OK", GREEN),
    ("Link Click", "클릭", "OK", GREEN),
    ("LPV", "LP 도달", "70~89% 정상 발화", AMBER),
    ("Add to Cart", "장바구니", "Rakuten LP 라 미작동", RED),
    ("Purchase", "결제", "Rakuten LP 라 미작동", RED),
]
y0 = Inches(3.7)
col_w = Inches(2.5)
for i, (event, label, status, color) in enumerate(events):
    x = Inches(0.7 + i * col_w)
    add_rect(s, x, y0, col_w - Inches(0.15), Inches(2.4), fill=LIGHT)
    add_rect(s, x, y0, col_w - Inches(0.15), Inches(0.6), fill=color)
    add_text(s, x, y0 + Inches(0.13), col_w - Inches(0.15), Inches(0.4),
             event, font_size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.85), col_w - Inches(0.15), Inches(0.4),
             label, font_size=12, color=GRAY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.6), col_w - Inches(0.15), Inches(0.6),
             status, font_size=11, bold=True, color=color, align=PP_ALIGN.CENTER)

add_rect(s, Inches(0.7), Inches(6.3), Inches(11.9), Inches(0.9), fill=LIGHT)
add_text(s, Inches(1.0), Inches(6.4), Inches(11.3), Inches(0.4),
         "운영 결론",
         font_size=12, bold=True, color=GRAY)
add_text(s, Inches(1.0), Inches(6.8), Inches(11.3), Inches(0.4),
         "Performance goal = LPV (Landing Page View) — Purchase 로 설정 시 학습 데이터 부족으로 분배 실패.",
         font_size=12, color=NAVY)


# ============================================================
# Slide 14 — 분석 사이클
# ============================================================
s = add_blank_slide()
add_header_bar(s, 15, TOTAL, "14. 분석 사이클",
               "광고 1개의 lifecycle 전체 체크포인트",
               subtitle="D+3 (ON 판단) → D+7 (학습 종료) → D+30 (Graduation) → 일간 모니터링")

phases = [
    ("D+3", "ON 진입 판단",
     "VTR 100/200% 게이트로\n광고 ON 여부 결정",
     "ON 결정", ACCENT),
    ("D+7", "학습 종료",
     "Off Rule 4축\n정식 적용 시작",
     "Off Rule ON", ACCENT2),
    ("D+8 ~ D+29", "Testing 모니터링",
     "일간 메일로\n끄기 후보 + 졸업 후보\n자동 표시",
     "일간 자동", GREEN),
    ("D+30 ~", "Graduation 평가",
     "Triple share + 성과 게이트\n통과 시 Proven 이동",
     "졸업", NAVY),
    ("이후", "Proven 운영",
     "PAID/GIFT × Proven\n풀에서 지속 모니터링\nWL 3~6개월 운용",
     "유지", GRAY),
]
y0 = Inches(2.5)
box_w = Inches(2.4)
gap = Inches(0.1)
total_w = box_w * 5 + gap * 4
start_x = (SLIDE_W - total_w) // 2

for i, (when, name, body, status, color) in enumerate(phases):
    x = start_x + (box_w + gap) * i
    add_rect(s, x, y0, box_w, Inches(3.7), fill=LIGHT)
    add_rect(s, x, y0, box_w, Inches(0.7), fill=color)
    add_text(s, x, y0 + Inches(0.13), box_w, Inches(0.4),
             when, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(0.95), box_w, Inches(0.5),
             name, font_size=14, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s, x, y0 + Inches(1.6), box_w, Inches(1.5),
             body, font_size=11, color=GRAY, align=PP_ALIGN.CENTER)
    add_rect(s, x + Inches(0.2), y0 + Inches(3.1), box_w - Inches(0.4), Inches(0.45), fill=color)
    add_text(s, x + Inches(0.2), y0 + Inches(3.15), box_w - Inches(0.4), Inches(0.4),
             status, font_size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    if i < 4:
        add_text(s, x + box_w, y0 + Inches(1.5), gap, Inches(0.5),
                 "▶", font_size=14, color=GRAY, align=PP_ALIGN.CENTER)

add_text(s, Inches(0.5), Inches(6.7), Inches(12.3), Inches(0.4),
         "일간 메일 — 아침 9시 자동. 어제 데이터 기준 KPI 카운터 / Off 후보 / Graduation 후보 / BEST·WORST.",
         font_size=11, color=GRAY, align=PP_ALIGN.CENTER)


# ============================================================
# Slide 15 — 운영 원칙
# ============================================================
s = add_blank_slide()
add_header_bar(s, 16, TOTAL, "15. 운영 원칙",
               "5가지 핵심 원칙",
               subtitle="기준은 살아있는 문서 — 운영 데이터 쌓이면 재조정")

principles = [
    ("1", "분리 운영",
     "Creative 와 Budget 은 별도 레버. \"A 대신 B\" 트레이드오프 X.",
     ACCENT),
    ("2", "자체 풀 비교",
     "외부 시장 평균은 끄기 임계로 X. 우리 광고 15개 풀끼리 percentile 비교.",
     ACCENT2),
    ("3", "학습 보호",
     "ON 후 7일 변경 금지. D+3 VTR 게이트로 사전 선별 우선.",
     GREEN),
    ("4", "수치 인용 의무",
     "의견·결론 1개당 수치 1개 이상. \"추세 같다\" \"가능성 있다\" 정성 표현 X.",
     NAVY),
    ("5", "실행은 세은",
     "메타몽 = 컨설팅·소재·분석 위임. 캠페인 mutate / 예산 변경 / 발행은 세은이 직접.",
     GRAY),
]
y0 = Inches(2.3)
for i, (num, title, body, color) in enumerate(principles):
    y = y0 + Inches(i * 0.85)
    add_rect(s, Inches(0.7), y, Inches(11.9), Inches(0.75), fill=LIGHT)
    add_rect(s, Inches(0.7), y, Inches(0.15), Inches(0.75), fill=color)
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.0), y + Inches(0.13), Inches(0.5), Inches(0.5))
    circ.fill.solid(); circ.fill.fore_color.rgb = color
    circ.line.fill.background()
    add_text(s, Inches(1.0), y + Inches(0.18), Inches(0.5), Inches(0.4),
             num, font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.7), y + Inches(0.1), Inches(2.5), Inches(0.4),
             title, font_size=15, bold=True, color=NAVY)
    add_text(s, Inches(4.3), y + Inches(0.18), Inches(8.3), Inches(0.5),
             body, font_size=12, color=GRAY)

add_rect(s, Inches(0.7), Inches(6.8), Inches(11.9), Inches(0.5), fill=NAVY)
add_text(s, Inches(1.0), Inches(6.87), Inches(11.3), Inches(0.4),
         "변경 내역 : 5/15 Off Rule 4축 재설계 · 5/19 ON 게이트 신설 · 5/19 D+60 단독 폐기 · 5/20 ad 단위 예산 정정 · 5/21 Graduation triple share",
         font_size=10, color=WHITE)


prs.save(str(OUT))
print(f"[OK] saved {OUT} ({OUT.stat().st_size:,} bytes)")
