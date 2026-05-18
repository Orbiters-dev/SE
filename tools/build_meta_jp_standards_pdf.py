"""
Meta JP 광고 운영 기준 PDF 생성 (2026-05-11)

세은 + 메타몽 협의 산출물.
- 광고 단위 의사결정 룰 (지선 SOP 기반)
- 인플루언서 3등급 (A/B/C) + S 후보
- Peer 비교 윈도우 방식
- 의사결정 cadence

저장: C:\\Users\\orbit\\Desktop\\s\\메타\\06_meta_jp_operation_standards.pdf
"""
import io
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBd", r"C:\Windows\Fonts\malgunbd.ttf"))

OUT = Path(r"C:\Users\orbit\Desktop\s\메타\06_meta_jp_operation_standards.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()

H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="MalgunBd",
                    fontSize=17, leading=24, spaceBefore=22, spaceAfter=14,
                    textColor=colors.HexColor("#1a1a1a"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="MalgunBd",
                    fontSize=12.5, leading=18, spaceBefore=16, spaceAfter=8,
                    textColor=colors.HexColor("#333333"))
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="MalgunBd",
                    fontSize=11, leading=16, spaceBefore=10, spaceAfter=6,
                    textColor=colors.HexColor("#555555"))
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Malgun",
                      fontSize=10.5, leading=17, alignment=TA_LEFT,
                      spaceBefore=2, spaceAfter=4)
BULLET = ParagraphStyle("Bullet", parent=BODY, leftIndent=16, bulletIndent=4,
                        spaceBefore=2, spaceAfter=6)
NOTE = ParagraphStyle("Note", parent=BODY, leftIndent=4,
                      fontSize=10, textColor=colors.HexColor("#555555"),
                      spaceBefore=4, spaceAfter=10)
META = ParagraphStyle("Meta", parent=BODY, fontSize=9.5,
                      textColor=colors.HexColor("#6b7280"),
                      spaceBefore=2, spaceAfter=8)

doc = SimpleDocTemplate(str(OUT), pagesize=A4,
                        leftMargin=18*mm, rightMargin=18*mm,
                        topMargin=18*mm, bottomMargin=18*mm,
                        title="Meta JP 광고 운영 기준 2026-05-11")

story = []


def make_table(data, col_widths, header_rows=1, body_align="LEFT"):
    t = Table(data, colWidths=col_widths, repeatRows=header_rows)
    style = [
        ("FONTNAME", (0,0), (-1,header_rows-1), "MalgunBd"),
        ("FONTNAME", (0,header_rows), (-1,-1), "Malgun"),
        ("FONTSIZE", (0,0), (-1,-1), 9.5),
        ("BACKGROUND", (0,0), (-1,header_rows-1), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0,0), (-1,header_rows-1), colors.white),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,header_rows-1), "CENTER"),
        ("ALIGN", (0,header_rows), (-1,-1), body_align),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0,header_rows), (-1,-1),
            [colors.HexColor("#ffffff"), colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
    ]
    t.setStyle(TableStyle(style))
    return t


# ============================================================
# 표지
# ============================================================
story.append(Paragraph("Meta JP 광고 운영 기준", H1))
story.append(Paragraph("Grosmimi JP · act_4117678028561958 · 2026-05-11", META))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "세은 + 메타몽 협의 산출물. 지선 SOP(meta_jp_optimization, ads-meta 46-check) + "
    "WL_2026 캠페인 14일 실측 + 캘빈 가이드(Discovery → Winners)를 종합하여 "
    "JP 광고 운영의 단일 기준선을 정한다. 모든 임계값은 1~2주 적용 후 재조정 전제.",
    BODY))

# ============================================================
# 1. 운영 철학 (3대 원칙)
# ============================================================
story.append(Paragraph("1. 운영 철학 (3대 원칙)", H1))

story.append(Paragraph("① 학습 단계 존중", H2))
story.append(Paragraph(
    "Meta 알고리즘 학습이 완료되기 전(3일 또는 1,000 노출 미만)에는 과도한 개입을 피한다. "
    "섣부른 Kill은 예산 낭비. Testing 풀과 Proven 풀을 분리 운영해서 학습 단계를 보호한다.",
    BODY))

story.append(Paragraph("② 데이터 기준 의사결정", H2))
story.append(Paragraph(
    "직감 X. 임계값 기반 판단. 단, 일본 시장 특수상황(공휴일·골든위크·연말연시·계절성)은 주석으로 기록.",
    BODY))

story.append(Paragraph("③ 픽셀 X 환경 전제", H2))
story.append(Paragraph(
    "Rakuten Pixel은 LPV까지만 정상 발화. Purchase 이벤트 안 잡힘. "
    "광고 단위 효율은 CPC + CTR + CPLPV + Frequency 4개 지표로 판단하고, "
    "전체 ROI는 월 1회 Meta 총 spend vs Rakuten 총매출 시계열 매칭으로 검증.",
    BODY))

# ============================================================
# 2. 에셋별 KPI 목표
# ============================================================
story.append(Paragraph("2. 에셋별 KPI 목표 (JP) — 북극성 (5/15 재정의)", H1))
story.append(Paragraph(
    "<b>KPI ≠ Off Rule</b>. KPI는 고정 북극성 (목표), Off Rule은 동적 작동 임계 (3장). "
    "두 룰을 섞으면 풀 평균이 KPI 미달이라 거의 모든 광고가 Off 대상이 되어 무력화됨.",
    BODY))
story.append(Spacer(1, 4))

kpi_data = [
    ["에셋 타입", "CPC 기준", "CTR 기준", "운용 방식"],
    ["이미지", "≤ ₩100", "≥ 4.0%", "달성 카운터 (n개/총m개)"],
    ["WL (인플루언서, PAID + GIFT)", "≤ ₩100", "≥ 8.0%", "달성 카운터 (n개/총m개)"],
]
story.append(make_table(kpi_data, [55*mm, 25*mm, 25*mm, 55*mm]))
story.append(Paragraph(
    "<b>운용 (5/15):</b> KPI는 \"몇 개 광고가 달성 / 미달인지\" 카운터로만 사용. "
    "달성 광고는 풀별 percentile (P90 이상)에서 별도 S 후보로 발굴. "
    "외부 시장 평균(Triple Whale 1.91% 등) Off 트리거 사용 X — 풀 자체 percentile만 유효.",
    META))

# ============================================================
# 3. 광고 단위 의사결정 룰 (3/5/7일)
# ============================================================
story.append(Paragraph("3. Off Rule (5/15 재설계 — 4축)", H1))
story.append(Paragraph(
    "외부 시장 평균 폐기. <b>풀 자체 percentile + 시간 sunset + Freq + velocity</b> 4축으로 "
    "동적 Off 임계 판정. 풀 분리: <b>PAID/GIFT × Testing/Proven 4-way</b>.",
    BODY))
story.append(Spacer(1, 4))

off_data = [
    ["#", "축", "조건", "액션"],
    ["1", "풀 P20 미달", "풀 percentile P20 이하 + spend ≥ ₩30K (메인 트리거)", "Off 검토"],
    ["2", "시간 sunset", "D+60 이상 (자연 노화)", "Off 검토 + 신규 변형 의뢰"],
    ["3", "피로도", "Freq ≥ 3.0 (spend 무관)", "즉시 Off"],
    ["4", "velocity 하락", "Proven D+15+, trailing 7d CTR delta < -15%", "신규 변형 우선"],
]
story.append(make_table(off_data, [10*mm, 28*mm, 75*mm, 47*mm]))

story.append(Paragraph("풀별 해석 차등", H2))
pool_data = [
    ["풀", "Off 해석", "S 후보 (P90 이상)"],
    ["PAID × Proven", "회수 압력 큼 → P20 + spend ≥ ₩30K 만으로도 Off 충분", "회수 검증 winner — 증액 우선"],
    ["PAID × Testing", "spend ≥ ₩30K 누적 후에만 판정. 미달 = 학습 보류", "졸업 후보 — Proven adset 이동"],
    ["GIFT × Proven", "비용 회수 압력 약함 → 즉시 Off 보단 신규 변형 우선", "PAID 풀로 캐스팅 전환 검토"],
    ["GIFT × Testing", "데이터만 누적. 변경 X (학습 리셋)", "내부 데이터 누적 신호"],
]
story.append(make_table(pool_data, [35*mm, 70*mm, 55*mm]))

story.append(Paragraph("Lifecycle 게이트 (변경 동결)", H2))
lc_data = [
    ["단계", "기준", "허용 액션"],
    ["newborn", "D+7 미만", "조회만. 증액·OFF·교체 X (학습 리셋)"],
    ["testing", "D+7 ~ D+14", "spend ≥ ₩30K 누적 후 평가. 변경 최소화"],
    ["proven", "D+15 ~ D+59", "정상 운영. KPI 카운터 + Off Rule + S 후보 평가"],
    ["sunset", "D+60+", "Off 검토 자동 트리거 (축 2)"],
]
story.append(make_table(lc_data, [25*mm, 30*mm, 105*mm]))

story.append(Paragraph("증액 실행 룰", H2))
story.append(Paragraph(
    "• 1회 ≤ 30% (Meta 학습 보호선) / ≤ 50% (Proven 안정 광고만)<br/>"
    "• 24시간 이상 유지 후 재판단<br/>"
    "• 같은 ad set 안 동시 증액 X (학습 리셋 발생)<br/>"
    "• 신생 / sunset / Off 트리거 hit 광고는 증액 후보에서 자동 제외 (5/15)",
    BULLET))

# ============================================================
# 4. 인플루언서 등급 (A / B / C 3단계)
# ============================================================
story.append(PageBreak())
story.append(Paragraph("4. 인플루언서 등급 (A / B / C 3단계)", H1))
story.append(Paragraph(
    "WL 광고 1개 = 인플루언서 1명 1콘텐츠. ad 단위 광고 성과 = 인플루언서 등급. "
    "CPV(organic) 등급과 정합성 맞춰 동일 A/B/C 체계 채택.",
    BODY))
story.append(Spacer(1, 4))

tier_data = [
    ["등급", "기준", "액션"],
    ["A (Proven)",
     "spend ≥ ₩30K  +  CPLPV ≤ peer · 95%",
     "Proven 풀 유지 + 1회 +20% 증액.<br/>"
     "S 후보(CPLPV ≤ peer · 70%)는 변형 5종 발주 + 차기 협업 1순위"],
    ["B (Testing / 관찰)",
     "spend < ₩30K · 학습 미통과",
     "노출 누적 우선, D+7~D+14 재진단.<br/>"
     "임계 통과 시 A 졸업"],
    ["C (OFF)",
     "위 Off Rule (A/B/C/D) 중 하나라도 트리거",
     "즉시 OFF. 인플루언서 차기 협업은 "
     "organic CPV 별도 평가 후 결정.<br/>"
     "<b>KPI 8% 미달 단독</b>은 Off 근거 X (풀 평균 자체가 KPI 미달이라)"],
]
tier_rows = [[Paragraph(c, BODY) for c in row] for row in tier_data]
tier_rows[0] = [Paragraph(f"<b>{c}</b>", BODY) for c in tier_data[0]]
story.append(make_table(tier_rows, [32*mm, 50*mm, 78*mm]))

story.append(Paragraph("14일 실측 적용 (2026-04-27 ~ 2026-05-10, WL_2026 캠페인)", H2))
real_data = [
    ["등급", "ad", "Ad Set", "spend", "CPLPV", "peer 대비"],
    ["A (S 후보)", "AD G coni · 20260303", "Stainless Proven", "₩182,623", "₩76", "−19%"],
    ["A (S 후보)", "AD D ichikuru_fufu · 20260320", "PPSU Proven", "₩334,144", "₩88", "(풀 99.7%)"],
    ["A", "AD L mugi_ikuji · 20260403", "Stainless Proven", "₩124,260", "₩90", "−4%"],
    ["A", "AD I shiro · 20260317", "Stainless Proven", "₩190,605", "₩126", "+34%"],
    ["B", "AD N komugiko · 20260424", "Stainless Testing", "₩362,620", "₩140", "n/a (Testing peer)"],
    ["B", "monyuru · 20260225", "PPSU Testing", "₩158,576", "₩127", "n/a"],
    ["B", "AD F miki · 20260428", "PPSU Testing", "₩125,178", "₩220", "관찰 (D+13, peer 비교 보류)"],
    ["C 후보", "—", "—", "—", "—", "현재 해당 없음 (Freq·CPLPV·150% 임계 미돌파)"],
]
story.append(make_table(real_data, [24*mm, 42*mm, 30*mm, 22*mm, 18*mm, 28*mm], body_align="LEFT"))

story.append(Paragraph(
    "peer 비교 baseline은 같은 ad set의 평균 (Testing peer ↔ Proven peer 분리). "
    "현재 코드는 14일 누적 단순 평균이라 stage 섞임 → 5번 항목에서 수정 예정.",
    META))

# ============================================================
# 5. Peer 비교 방식 (윈도우 기반)
# ============================================================
story.append(Paragraph("5. Peer 비교 방식 — 윈도우 기반", H1))
story.append(Paragraph(
    "광고마다 launch 시점이 달라 (D+13 ~ D+69) 14일 단순 평균에 넣으면 "
    "라이프스테이지가 다른 광고가 같은 baseline에 섞임 → 부정확. "
    "같은 윈도우끼리 묶어 비교한다.",
    BODY))
story.append(Spacer(1, 4))

peer_data = [
    ["단계", "비교 baseline", "용도"],
    ["Testing 풀 (D+1 ~ D+14)",
     "같은 풀의 D+1 ~ D+7 누적 평균",
     "졸업 판정 (Testing → Proven)"],
    ["Proven 풀 (D+15+)",
     "같은 풀의 trailing 7일 rolling 평균",
     "단가 추세 감시 + 효율 악화 조기 감지"],
    ["신생 (D+7 미만)",
     "peer 비교 X · '노출 누적 중' 라벨만",
     "데이터 부족 — 변경·증액 동결"],
]
peer_rows = [[Paragraph(c, BODY) for c in row] for row in peer_data]
peer_rows[0] = [Paragraph(f"<b>{c}</b>", BODY) for c in peer_data[0]]
story.append(make_table(peer_rows, [50*mm, 58*mm, 52*mm]))

story.append(Paragraph("구현 메모", H2))
story.append(Paragraph(
    "• ad_name 끝 8자리 (예: 20260424) 파싱 → launch_date<br/>"
    "• 분석 시점에서 D+N 계산, 본문에 함께 표시 (예: 'AD N komugiko [D+17]')<br/>"
    "• <b>tools/meta_jp_daily.py</b> line 436~443 단일 평균 로직 → "
    "Testing/Proven 분리 + 윈도우 누적으로 교체 필요",
    BULLET))

# ============================================================
# 6. 의사결정 cadence
# ============================================================
story.append(PageBreak())
story.append(Paragraph("6. 의사결정 cadence", H1))

cadence_data = [
    ["주기", "작업", "도구 / 상태"],
    ["매일 09:00 KST",
     "1d 자동 분석 메일 (Testing/Proven · A후보 · 발견 3축)",
     "meta_jp_daily.py --mode 1d · 자동 (cron 5개 다중화 fix 완료)"],
    ["매일 09:00 KST (수동)",
     "어제 spend/CTR/Freq 점검 후 3일·5일·7일 룰 적용",
     "위 메일 + Ads Manager 직접 확인"],
    ["주 1회 (월요일)",
     "Testing → Proven 졸업 / Sunset 결정 · 신규 인플루언서 발굴",
     "meta_jp_creative_notion.py (지선 자동화) · 가동 여부 재점검"],
    ["주 1회 (월요일)",
     "인플루언서 등급 갱신 (A/B/C 재평가, peer 윈도우 기반)",
     "신규 도구 필요 (Phase 2)"],
    ["월 1회",
     "Meta 총 spend vs Rakuten 총매출 시계열 매칭 (캘빈 가이드 C단계)",
     "신규 도구 필요 — 현재 없음"],
]
cadence_rows = [[Paragraph(c, BODY) for c in row] for row in cadence_data]
cadence_rows[0] = [Paragraph(f"<b>{c}</b>", BODY) for c in cadence_data[0]]
story.append(make_table(cadence_rows, [32*mm, 58*mm, 70*mm]))

# ============================================================
# 7. 캠페인 구조 (참고)
# ============================================================
story.append(Paragraph("7. 현재 캠페인 구조 (참고)", H1))

struct_data = [
    ["캠페인", "모드", "일예산", "ad set", "비고"],
    ["Rakuten_WL_2026", "ABO", "ad set 별 ₩24K~₩36K (총 ₩112K)",
     "PPSU/Stainless × Testing/Proven 4개",
     "본 운영 기준 적용 대상"],
    ["Rakuten | Traffic | image", "CBO", "₩25,000",
     "(별도)", "이미지 트래픽 — 본 기준 일부만 적용"],
]
story.append(make_table(struct_data, [40*mm, 16*mm, 42*mm, 35*mm, 27*mm]))

story.append(Paragraph(
    "ABO 유지가 효율적인 이유: ad set별 CPLPV 격차 75% (₩88 vs ₩154). "
    "CBO로 전환하면 알고리즘이 Proven으로 거의 다 몰빵 → Testing 파이프라인 사실상 정지. "
    "캘빈의 'Discovery → High Performing'은 우리의 'Testing → Proven' 분리로 이미 구현됨.",
    BODY))

# ============================================================
# 8. 향후 과제
# ============================================================
story.append(Paragraph("8. 향후 과제 (우선순위 순)", H1))

todo_data = [
    ["#", "과제", "단계", "예상 효과"],
    ["1", "Meta spend × Rakuten 매출 월간 매칭 도구",
     "이번 달", "캘빈 가이드 C단계 — 전체 ROI 가시화. CTR만으론 효율 미검증"],
    ["2", "PAID/GIFT KPI 차등 적용 평가 (6주 운영 데이터 누적 후)",
     "6주 후", "회수 압력 차이 반영. 현재는 동일 풀 평가"],
    ["3", "S 후보 인플루언서 차기 콘텐츠 협업 자동 발굴",
     "다음 달", "P90+ Top performer 풀 확대"],
    ["4", "Frequency ≥ 2.3 자동 alert + 교체 후보 제안",
     "다음 달", "Ad fatigue 선제 대응 (현재는 3.0 hit 후 사후)"],
    ["5", "주 1회 인플루언서 등급 갱신 도구 (A/B/C + S 후보 표시)",
     "다음 달", "차기 협업·증액 의사결정 자동화"],
]
story.append(make_table(todo_data, [10*mm, 75*mm, 22*mm, 53*mm]))

story.append(Spacer(1, 12))
story.append(Paragraph("완료 (2026-05-15 ~ 2026-05-18)", H2))
done_data = [
    ["완료 항목", "구현 위치"],
    ["KPI ≠ Off Rule 분리 + 외부 시장 평균 폐기 합의",
     "PDF 섹션 2 갱신"],
    ["헬퍼 5개 (parse_paid_flag / calc_days_live / lifecycle_stage / calc_percentiles / off_rule_check)",
     "tools/meta_jp_daily.py B-1~B-4"],
    ["4-way 풀 (PAID/GIFT × Testing/Proven) split + percentile",
     "best_worst_from_rows()"],
    ["build_findings 4-way 풀 + Off Rule + S 후보 + 신생 동결",
     "B-5"],
    ["velocity 추적 (Proven D+15+ trailing 7d CTR delta < -15%)",
     "analyze_7d() B-6"],
    ["KPI 카운터 + Off 권장 박스 (HTML 보고)",
     "render_kpi_counter / render_off_recommend_box B-7"],
    ["budget_increase_candidates 신생/sunset 자동 제외",
     "5/18 follow-up"],
]
story.append(make_table(done_data, [115*mm, 45*mm]))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "본 기준은 살아있는 문서. 6주 운영 후 풀 분포 percentile로 임계 확정. "
    "변경 사유는 git 커밋 메시지에 기록. <b>최근 변경: 2026-05-18</b> "
    "(KPI/Off Rule 분리 적용, 헬퍼 + 4-way 풀 + velocity + KPI 카운터 + Off 박스).",
    META))

doc.build(story)
print(f"[OK] saved {OUT} ({OUT.stat().st_size:,} bytes)")
