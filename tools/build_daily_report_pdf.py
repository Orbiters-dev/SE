"""
일일 보고 PDF 생성 (2026-05-07)
1) CRM 개발 진척
2) 메타 광고 (BEST/WORST = CTR + CPC 둘 다)
3) 기타 작업
"""
import io
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBd", r"C:\Windows\Fonts\malgunbd.ttf"))

OUT = Path(r"C:\Users\orbit\Desktop\SE\.tmp\daily_report_20260507.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()

H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="MalgunBd",
                    fontSize=17, leading=24,
                    spaceBefore=22, spaceAfter=14,
                    textColor=colors.HexColor("#1a1a1a"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="MalgunBd",
                    fontSize=12.5, leading=18,
                    spaceBefore=16, spaceAfter=8,
                    textColor=colors.HexColor("#333333"))
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Malgun",
                      fontSize=10.5, leading=17, alignment=TA_LEFT,
                      spaceBefore=2, spaceAfter=4)
BULLET = ParagraphStyle("Bullet", parent=BODY,
                        leftIndent=16, bulletIndent=4,
                        spaceBefore=2, spaceAfter=7)
LINK = ParagraphStyle("Link", parent=BODY, fontName="Malgun", fontSize=9.5,
                      leading=14, textColor=colors.HexColor("#1a73e8"))
NOTE = ParagraphStyle("Note", parent=BODY, leftIndent=4,
                      fontSize=10, textColor=colors.HexColor("#555555"),
                      spaceBefore=4, spaceAfter=10)

doc = SimpleDocTemplate(str(OUT), pagesize=A4,
                        leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=18*mm, bottomMargin=18*mm,
                        title="Daily Report 2026-05-07")

story = []

story.append(Paragraph("일일 보고 — 2026-05-07", H1))
story.append(Spacer(1, 6))

# ============================================================
# 1) CRM 개발 진척
# ============================================================
story.append(Paragraph("1) CRM 개발 진척", H1))

story.append(Paragraph("JP CRM status 변경 버튼 버그 잡음", H2))
story.append(Paragraph(
    "• <b>증상</b>: 인플루언서 status 바꾸는 버튼 누르면 에러 → 안 바뀜", BULLET))
story.append(Paragraph(
    "• <b>원인</b>: 프론트(밀리초)와 백엔드(마이크로초) 시간 정밀도 불일치", BULLET))
story.append(Paragraph(
    "• <b>100% 재현·검증 완료</b>", BULLET))

story.append(Paragraph("부수 작업", H2))
story.append(Paragraph(
    "• django_phases/crm 코드 흐름 분석", BULLET))
story.append(Paragraph(
    "• orbitools-code-edit MCP 등록 — 앞으로 CRM 코드 작업 시 이 도구 우선 사용", BULLET))
story.append(Paragraph(
    "• <b>CRM KPI 분리 작업 중</b> — fit하지 않은 인플루언서를 Archived 칸에 모아 분석 → "
    "fit한 인플루언서 서칭 기준으로 활용",
    BULLET))

story.append(Paragraph("원기님께 부탁한 것", H2))
story.append(Paragraph(
    '• <b>WONGI PR #570 검토·머지 요청</b>'
    '<br/><font size="9" color="#1a73e8">'
    '<link href="https://github.com/Orbiters-dev/WONGI/pull/570">'
    'https://github.com/Orbiters-dev/WONGI/pull/570</link></font>',
    BULLET))
story.append(Paragraph(
    "• <b>EC2 MCP 서버 git 권한 에러 해결 요청</b>", BULLET))
story.append(Paragraph(
    "• JP CRM 인스타 컨택자 이관 방식 옵션 A 진행 여부", BULLET))
story.append(Paragraph(
    "• ManyChat 자동 발송 셋업 진행 여부", BULLET))

# ============================================================
# 2) 메타 광고
# ============================================================
story.append(Paragraph("2) 메타 광고 (JP)", H1))

# 전체 성과
story.append(Paragraph("전체 성과 (5/6 일일)", H2))
data = [
    ["지표", "값", "전일 대비"],
    ["지출", "₩132,143", "-8.4%"],
    ["CTR", "6.65%", "+4.4%"],
    ["CPC", "₩73", "-11.6%"],
]
t = Table(data, colWidths=[40*mm, 50*mm, 40*mm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
    ("FONTNAME", (0, 0), (-1, 0), "MalgunBd"),
    ("FONTSIZE", (0, 0), (-1, -1), 10.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(t)
story.append(Spacer(1, 8))
story.append(Paragraph(
    "→ 비용 줄고 효율 올라간 긍정적 흐름. 알림 없음.", NOTE))

# 캠페인별
story.append(Paragraph("캠페인별", H2))
story.append(Paragraph(
    "• <b>Rakuten_WL_2026</b> (주력) — 지출 ₩108,251 / CTR <b>7.56%</b>",
    BULLET))
story.append(Paragraph(
    "• <b>Rakuten Traffic image</b> — CTR <b>3.54%</b> (상대적으로 낮음)",
    BULLET))

# 이번 주 신규 광고
story.append(Paragraph("이번 주 신규 광고", H2))
new_ads_header = ["등록일", "유형", "광고", "캠페인 / Adset", "URL"]
new_ads_rows = [
    [
        "5/7",
        Paragraph("ppsu WL<br/>Testing<br/>(영상)", BODY),
        Paragraph("AD G — fliptop<br/>(yukina, 5/1)", BODY),
        Paragraph(
            "Rakuten_WL_2026<br/>"
            "<font color='#777' size='9'>Grosmimi | PPSU | WL | Testing</font>",
            BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DYBNVs3jDct/" '
            'color="#1a73e8">instagram.com/p/DYBNVs3jDct</link>', LINK),
    ],
    [
        "5/6",
        Paragraph("stainless<br/>이미지", BODY),
        Paragraph("Stainless | AD E", BODY),
        Paragraph("Rakuten | Traffic | image", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DX_dRIxDL_A/" '
            'color="#1a73e8">instagram.com/p/DX_dRIxDL_A</link>', LINK),
    ],
    [
        "5/6",
        Paragraph("stainless<br/>이미지", BODY),
        Paragraph("Stainless | AD F", BODY),
        Paragraph("Rakuten | Traffic | image", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DX_dsd3jFcV/" '
            'color="#1a73e8">instagram.com/p/DX_dsd3jFcV</link>', LINK),
    ],
]
t = Table([new_ads_header] + new_ads_rows,
          colWidths=[12*mm, 24*mm, 38*mm, 44*mm, 52*mm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
    ("FONTNAME", (0, 0), (-1, 0), "MalgunBd"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff8e1")),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ALIGN", (0, 1), (1, -1), "CENTER"),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(t)
story.append(Paragraph(
    "→ 5/6 stainless 이미지 2개는 학습 단계, 5/8 재진단 예정.", NOTE))

# BEST — CTR + CPC 종합
story.append(Paragraph("BEST 광고 (CTR + CPC 종합)", H2))
best_header = ["순위", "광고", "CTR", "CPC", "URL"]
best_rows = [
    [
        "1위",
        Paragraph("AD D — ppsu<br/>(ichikuru_fufu, 3/20)", BODY),
        Paragraph("<b>9.99%</b>", BODY),
        Paragraph("₩64", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DWF9m9PDCJ4/" '
            'color="#1a73e8">DWF9m9PDCJ4</link>', LINK),
    ],
    [
        "2위",
        Paragraph("AD I — stainless<br/>(shiro, 3/17)", BODY),
        Paragraph("8.34%", BODY),
        Paragraph("<b>₩49</b>", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DVrzj-9jBSB/" '
            'color="#1a73e8">DVrzj-9jBSB</link>', LINK),
    ],
    [
        "3위",
        Paragraph("AD G — stainless<br/>(coni, 3/3)", BODY),
        Paragraph("7.75%", BODY),
        Paragraph("₩60", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DVaI-S-DP_D/" '
            'color="#1a73e8">DVaI-S-DP_D</link>', LINK),
    ],
]
t = Table([best_header] + best_rows,
          colWidths=[12*mm, 52*mm, 22*mm, 22*mm, 62*mm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
    ("FONTNAME", (0, 0), (-1, 0), "MalgunBd"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5e9")),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN", (0, 1), (0, -1), "CENTER"),
    ("ALIGN", (2, 1), (3, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(t)
story.append(Paragraph(
    "→ AD D ichikuru_fufu = CTR 1위. AD I shiro = CPC 1위 (₩49). "
    "벤치 CTR 1.71% 대비 BEST는 5.8배.", NOTE))

# WORST — CTR + CPC 종합
story.append(Paragraph("WORST 광고 (CTR + CPC 종합)", H2))
worst_header = ["광고", "CTR", "CPC", "지출", "URL"]
worst_rows = [
    [
        Paragraph("Stainless AD D 이미지<br/>(셋업 4/3)", BODY),
        Paragraph("<b>1.86%</b>", BODY),
        Paragraph("<b>₩172</b>", BODY),
        Paragraph("₩1,377", BODY),
        Paragraph(
            '<link href="https://www.instagram.com/p/DWqG26WjCBt/" '
            'color="#1a73e8">DWqG26WjCBt</link>', LINK),
    ],
    [
        Paragraph("One Touch AD A<br/>(셋업 2/27)", BODY),
        Paragraph("3.75%", BODY),
        Paragraph("₩106", BODY),
        Paragraph("₩16,162", BODY),
        Paragraph("(고지출 비효율)", BODY),
    ],
]
t = Table([worst_header] + worst_rows,
          colWidths=[52*mm, 22*mm, 22*mm, 24*mm, 50*mm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
    ("FONTNAME", (0, 0), (-1, 0), "MalgunBd"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffebee")),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN", (1, 1), (3, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(t)
story.append(Paragraph(
    "→ Stainless AD D = CTR·CPC 둘 다 최악 (BEST 대비 CTR 5배·CPC 3배 차이). "
    "One Touch AD A는 지출 큰데 효율 평범.", NOTE))

# 공부 중
story.append(Paragraph("공부 중", H2))
story.append(Paragraph(
    "일본 메타 광고 운영법 정리 — 목표 = LPV / 3일 안에 CPC ¥200 넘으면 즉시 Kill / "
    "광고 이름 규칙 / Breakdown Effect", BODY))

# ============================================================
# 3) 기타 작업
# ============================================================
story.append(Paragraph("3) 기타 작업", H1))

story.append(Paragraph("JP 도쿄 박람회 카탈로그 수정", H2))

story.append(Paragraph("틱톡 브랜드 계정 차단 건 해결 작업", H2))
story.append(Paragraph(
    "차단 풀기 위해 꾸준한 게시물 업로드 + 육아 계정 응답이 필요.<br/>"
    "오늘 진행:",
    BODY))
story.append(Paragraph(
    "• 게시물 1건 업로드", BULLET))
story.append(Paragraph(
    "• 육아 계정 서칭 및 좋아요", BULLET))
story.append(Paragraph(
    "• #grosmimi 태그로 업로드된 게시물 리포스트", BULLET))

story.append(Paragraph("인플루언서 신규 리치아웃", H2))
story.append(Paragraph(
    "신규 6명 리치아웃 → 1명 답신 수신.",
    BODY))

story.append(Paragraph("인플루언서 시딩 발송", H2))
story.append(Paragraph(
    "• <b>@mooomin_baby</b> (武本様) — stainless", BULLET))
story.append(Paragraph(
    "• <b>@monemama.life</b> (水谷様) — fliptop", BULLET))
story.append(Paragraph(
    "• <b>@sota__no__mama</b> (岡田様) — ppsu", BULLET))

story.append(Paragraph("인플루언서 신규 스케줄 조정", H2))
story.append(Paragraph(
    "• <b>@bebi_mon_ikuj</b> (村井様) — stainless", BULLET))
story.append(Paragraph(
    "• <b>@hi_mama327</b> (上林様) — stainless", BULLET))
story.append(Paragraph(
    "• <b>@yuka_riku1009</b> (石川様) — ppsu", BULLET))

# ============================================================
# 캘린더 이미지 (마지막, 헤더 없음)
# ============================================================
cal_path = r"C:\Users\orbit\Desktop\SE\.tmp\calendar_input.png"
cal_w = 170 * mm
cal_h = cal_w * 698 / 1795
story.append(RLImage(cal_path, width=cal_w, height=cal_h))

doc.build(story)
print(f"OK: {OUT}")
print(f"size: {OUT.stat().st_size:,} bytes")
