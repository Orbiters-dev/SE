"""
ORBI / Grosmimi JP — Meta Ads 운영 기준 통합본 (2026-05-18)

지금까지 (4/20 ~ 5/18) 세은 + 메타몽이 합의·정리한 Meta Ads 기준 전부 통합.
기존 06_meta_jp_operation_standards.pdf 의 확장판.

저장: C:\\Users\\orbit\\Desktop\\s\\메타\\07_meta_ads_full_standards.pdf
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

OUT = Path(r"C:\Users\orbit\Desktop\s\메타\07_meta_ads_full_standards.pdf")
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
                        title="ORBI Meta Ads Full Standards 2026-05-18")

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
story.append(Paragraph("ORBI / Grosmimi JP", H1))
story.append(Paragraph("Meta Ads 운영 기준 통합본", H1))
story.append(Paragraph("act_4117678028561958 · 2026-05-18", META))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "본 문서는 2026-04-20 ~ 2026-05-18 사이 세은 + 메타몽이 합의·정리한 "
    "Grosmimi Japan Meta Ads 운영 기준 전체를 통합한다. "
    "KPI · Off Rule · 풀 분리 · Lifecycle Gate · Creative 가이드 · "
    "Whitelisting · Daily 자동화 · 계정 기본 정보 · Industry consensus.",
    BODY))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>핵심 원칙 4가지</b><br/>"
    "① KPI(북극성) ≠ Off Rule(작동 임계)<br/>"
    "② 외부 시장 평균 폐기 — 풀 자체 percentile만<br/>"
    "③ 풀 분리 (PAID/GIFT × Testing/Proven) + Lifecycle Gate<br/>"
    "④ Creative와 Budget은 별도 영역",
    BULLET))

# ============================================================
# 0. 계정 기본 정보
# ============================================================
story.append(Paragraph("0. 계정 기본 정보", H1))
acct_data = [
    ["항목", "값", "비고"],
    ["계정 ID", "act_4117678028561958", "Grosmimi JP (단일)"],
    ["시장", "Japan", "타겟 지역"],
    ["Timezone", "Asia/Tokyo", "—"],
    ["Currency", "KRW (₩)", "JP 타겟이라고 JPY 가정 X. 모든 spend/CPC = ₩"],
    ["분석 대상", "JP만", "US 멀티브랜드는 별도 담당. 메타몽은 JP만"],
]
story.append(make_table(acct_data, [25*mm, 50*mm, 85*mm]))
story.append(Paragraph(
    "<b>주의:</b> Meta Ads Manager UI에서도 KRW 표기. 지선 SOP의 ¥ 표기는 "
    "실제 의미는 ₩. 작업 시작 시 Graph API <i>?fields=currency,timezone_name</i> 1회 확인.",
    META))

# ============================================================
# 1. 운영 철학 (5/15 합의 기반)
# ============================================================
story.append(Paragraph("1. 운영 철학", H1))
story.append(Paragraph("KPI는 고정 북극성, Off Rule은 동적 작동 임계. 섞으면 무력화.", BODY))

phil_data = [
    ["원칙", "내용", "사유"],
    ["KPI ≠ Off Rule",
     "KPI는 목표 카운터, Off Rule은 풀 percentile 기반 동적 임계",
     "풀 평균이 KPI 미달이라 KPI를 Off로 쓰면 거의 모든 광고가 Off 대상 됨"],
    ["외부 시장 평균 폐기",
     "Triple Whale 1.91% 등 시장 평균 직접 Off 트리거 사용 X",
     "우리 풀 size 17개 vs 시장 500~1000+. percentile 노이즈 차이 + conv 데이터 없음"],
    ["풀 분리",
     "PAID/GIFT × Testing/Proven 4-way + newborn 동결",
     "회수 압력·학습 단계 다른 광고를 한 풀로 평가하면 진단 정확도 하락"],
    ["Creative ≠ Budget",
     "두 영역은 독립. 동시 진행 가능. \"A 대신 B\" 묶음 X",
     "creative 강화 = 의뢰·기획 영역, budget 운용 = 입찰·예산 영역. 대체재 X 보완재"],
    ["메타몽 mutate scope",
     "지시받은 필드만. name edit 받으면 name만",
     "다른 필드 동시 변경 시 학습 리셋·정지·예산 변경 등 부작용 큼"],
]
story.append(make_table(phil_data, [30*mm, 70*mm, 60*mm]))

# ============================================================
# 2. KPI 북극성
# ============================================================
story.append(PageBreak())
story.append(Paragraph("2. KPI 북극성 (고정)", H1))
story.append(Paragraph("픽셀 없는 환경에서 광고 단위 즉시 판정 가능한 목표 기준.", BODY))

kpi_data = [
    ["에셋 타입", "CPC 기준", "CTR 기준", "운용 방식"],
    ["이미지", "≤ ₩100", "≥ 4.0%", "달성 카운터 (n/m개)"],
    ["WL (인플루언서, PAID + GIFT)", "≤ ₩100", "≥ 8.0%", "달성 카운터 (n/m개)"],
]
story.append(make_table(kpi_data, [55*mm, 25*mm, 25*mm, 55*mm]))
story.append(Paragraph(
    "<b>운용 룰 (5/15):</b><br/>"
    "• KPI는 \"몇 개 광고가 달성 / 미달인지\" 카운터로만 사용<br/>"
    "• 평균값 비교 X (Off Rule과 분리)<br/>"
    "• 달성 광고는 풀별 percentile (P90 이상)에서 별도 S 후보로 발굴<br/>"
    "• KPI 미달도 Off 트리거 X (Off Rule 4축이 별도 판정)",
    BULLET))

# ============================================================
# 3. Off Rule 4축
# ============================================================
story.append(Paragraph("3. Off Rule — 4축 동적 임계", H1))
story.append(Paragraph(
    "<b>풀 자체 percentile + 시간 sunset + Freq + velocity</b>. "
    "외부 시장 평균 폐기. 풀 분리 (PAID/GIFT × Testing/Proven) 위에서 작동.",
    BODY))

off_data = [
    ["#", "축", "조건", "액션"],
    ["1", "풀 P20 미달", "풀 percentile P20 이하 + spend ≥ ₩30K (메인 트리거)",
     "Off 검토"],
    ["2", "시간 sunset", "D+60 이상 (자연 노화)",
     "Off 검토 + 신규 변형 의뢰"],
    ["3", "피로도", "Freq ≥ 3.0 (spend 무관)",
     "즉시 Off"],
    ["4", "velocity 하락", "Proven D+15+, trailing 7d CTR delta < -15%",
     "신규 변형 우선"],
]
story.append(make_table(off_data, [10*mm, 28*mm, 75*mm, 47*mm]))

story.append(Paragraph("풀별 해석 차등", H2))
pool_data = [
    ["풀", "Off 해석", "S 후보 (P90 이상)"],
    ["PAID × Proven",
     "회수 압력 큼 → P20 + spend ≥ ₩30K 만으로도 Off 충분",
     "회수 검증 winner — 증액 우선 (1회 ≤ 30%)"],
    ["PAID × Testing",
     "spend ≥ ₩30K 누적 후에만 판정. 미달 = 학습 보류",
     "졸업 후보 — Proven adset 이동"],
    ["GIFT × Proven",
     "비용 회수 압력 약함 → 즉시 Off 보단 신규 변형 우선",
     "PAID 풀로 캐스팅 전환 검토"],
    ["GIFT × Testing",
     "데이터만 누적. 변경 X (학습 리셋)",
     "내부 데이터 누적 신호"],
]
story.append(make_table(pool_data, [35*mm, 70*mm, 55*mm]))

# ============================================================
# 4. Lifecycle Gate
# ============================================================
story.append(Paragraph("4. Lifecycle Gate (변경 동결 룰)", H1))
story.append(Paragraph(
    "광고 등록 후 시간에 따라 허용 액션이 다름. ad_name 끝 yymmdd 기준 D+N 계산.",
    BODY))

lc_data = [
    ["단계", "기준", "허용 액션"],
    ["newborn", "D+7 미만",
     "조회만. 증액·OFF·교체 X (학습 리셋 위험)"],
    ["testing", "D+7 ~ D+14",
     "spend ≥ ₩30K 누적 후 평가. 변경 최소화"],
    ["proven", "D+15 ~ D+59",
     "정상 운영. KPI 카운터 + Off Rule + S 후보 평가"],
    ["sunset", "D+60+",
     "Off 검토 자동 트리거 (Off Rule 축 2)"],
]
story.append(make_table(lc_data, [25*mm, 30*mm, 105*mm]))

# ============================================================
# 5. S 후보 발굴
# ============================================================
story.append(Paragraph("5. S 후보 발굴 (Top 10%)", H1))
story.append(Paragraph(
    "풀별 P90 이상 + spend ≥ ₩30K + 풀 n ≥ 6. "
    "정통 5% 룰을 풀 size 보정해 10%로 보수 설정.",
    BODY))

s_data = [
    ["조건", "값", "근거"],
    ["풀 percentile", "P90 이상 (Top 10%)",
     "Motion 5% winner 룰을 풀 size 보정 (17개)"],
    ["spend 최소",  "≥ ₩30K",
     "Meta 학습 통과 임계. 미달 ad는 의미 추출 어려움"],
    ["풀 n 최소", "≥ 6",
     "n=6 미만은 percentile 노이즈 큼"],
    ["lifecycle", "Proven (D+15 ~ D+59)",
     "Testing은 검증 미완. sunset은 자연 노화 진행"],
    ["Off 트리거 hit", "제외",
     "sunset + S 후보 모순 방지 (dedup)"],
]
story.append(make_table(s_data, [25*mm, 50*mm, 85*mm]))

# ============================================================
# 6. Creative 표준
# ============================================================
story.append(PageBreak())
story.append(Paragraph("6. Creative 표준 (영상 광고)", H1))
story.append(Paragraph("인플루언서 영상 광고의 구조 표준 + 필수 3요소 + 의뢰 전략.", BODY))

video_data = [
    ["부분", "길이/위치", "내용"],
    ["Hook", "첫 3초",
     "Shocking · 흥미. \"Wow moment\". 보고 싶게"],
    ["Education", "Hook 직후",
     "의학·발달 지식 (예: 6개월쯤 이가 나기 시작한다)"],
    ["Benefit", "중반",
     "제품 쓰면 아이한테 뭐가 좋은가 (구강 발달 등)"],
    ["Result", "후반",
     "실제 사용 후 아이가 어떻게 됐는가"],
    ["Ending", "마지막",
     "마무리 (CTA 포함 가능)"],
]
story.append(make_table(video_data, [25*mm, 30*mm, 105*mm]))

story.append(Paragraph(
    "<b>필수 3요소:</b> Hook · Education · Benefit. 이 셋은 무조건 포함. "
    "Result/Ending은 영상 톤·길이 따라 조정 가능.",
    NOTE))

story.append(Paragraph("바이럴 영상 의뢰 전략", H2))
viral_data = [
    ["단계", "내용"],
    ["1", "TikTok / Instagram에서 관련 분야 바이럴 영상 리서치"],
    ["2", "참고 기준: 좋아요·뷰 < <b>저장 + 공유 + 코멘트</b>"],
    ["3", "특히 <b>제품 자체 질문이 코멘트에 많은 영상</b> = 바이럴 신호"],
    ["4", "참고할 hook 가진 영상을 인플루언서 10명한테 <b>동시</b> 의뢰"],
    ["5", "같은 해시태그·주제 풀이라 한 명 뜨면 전부 바이럴 효과"],
]
story.append(make_table(viral_data, [12*mm, 148*mm]))

story.append(Paragraph("좋은 컨텐츠 지표 (우선순위)", H2))
metric_data = [
    ["순위", "지표", "의미"],
    ["1", "저장 수", "다시 보고 싶다 / 참고하고 싶다 = 강한 관심"],
    ["2", "제품 질문 코멘트", "구매 의향 단계 진입 신호"],
    ["3", "공유 수", "다른 사람에게 추천할 가치"],
    ["4", "좋아요·뷰", "표면 노출, 약한 신호"],
]
story.append(make_table(metric_data, [12*mm, 35*mm, 113*mm]))

# ============================================================
# 7. Creative AI 이미지 방향성
# ============================================================
story.append(Paragraph("7. AI 이미지 방향성 (Gemini용)", H1))
img_data = [
    ["요소", "방향"],
    ["인물", "단발 여아, 6-24개월 (앞모습, 인물 확대)"],
    ["배경", "일본 근린 (집·공원·카페). 클리셰 X"],
    ["앵글", "정면 + 클로즈업 중심"],
    ["조명", "자연광. 인공조명 강조 X"],
    ["NEGATIVE", "대머리 baby (Gemini 기본 출력 — 머리카락 명시 필수)"],
    ["NEGATIVE", "2명 등장 시 한 명만 예쁘게 (1명으로 한정)"],
    ["NEGATIVE", "거꾸로 든 컵 → 물방울 자동 추가 (자세 명시)"],
]
story.append(make_table(img_data, [30*mm, 130*mm]))

# ============================================================
# 8. JP 광고 카피 톤
# ============================================================
story.append(Paragraph("8. JP 광고 카피 톤", H1))
copy_data = [
    ["요소", "기준"],
    ["타겟", "6-24개월 맘"],
    ["메인 제품", "머그 (PPSU / Stainless / One Touch)"],
    ["오노마토페", "1개 이하 (과다 X)"],
    ["어려운 한자어", "사용 X (히라가나·카타카나 비중 높임)"],
    ["헤드라인", "≤ 40자"],
    ["본문", "≤ 125자"],
    ["CTA", "「楽天で見る」 · 「詳しくはこちら」 등 평이"],
]
story.append(make_table(copy_data, [30*mm, 130*mm]))

# ============================================================
# 9. Whitelisting (인플루언서 영상)
# ============================================================
story.append(PageBreak())
story.append(Paragraph("9. Whitelisting (Use Existing Post)", H1))
story.append(Paragraph(
    "협업 인플루언서 게시 영상을 광고로 돌리는 작업. "
    "Partnership Ad Code 잠긴 경우 \"Use existing post + partner content\" 우선.",
    BODY))

wl_data = [
    ["방법", "내용"],
    ["1) Graph API",
     "GET /{ig-user-id}/media — 가장 안정"],
    ["2) Ads Manager Use existing post",
     "Page 연결되어 있으면 검색에서 자동 노출"],
    ["3) Partner Content Grid",
     "화이트리스팅 권한 부여 시 자동 등장"],
    ["4) URL 파싱",
     "IG Reel URL shortcode → media ID 변환 (외부 도구)"],
]
story.append(make_table(wl_data, [55*mm, 105*mm]))

story.append(Paragraph(
    "<b>주의:</b> Processing 상태 광고 thumbnail은 Page 프로필로 fallback. "
    "Active 되면 영상으로 자동 변경. WL 권한은 인플루언서 측 사전 확인 필수 "
    "(메타몽 직접 DM X — 인플루언서 매니저/리공이 영역).",
    META))

# ============================================================
# 10. Rakuten Pixel 신호
# ============================================================
story.append(Paragraph("10. Rakuten Pixel 신호 범위", H1))
pixel_data = [
    ["Pixel 이벤트", "Rakuten에서 작동?"],
    ["Landing Page View", "✅ 정상 (70~89% 비율)"],
    ["Link Click", "✅ (Meta 자체 추적)"],
    ["Purchase / Conversion", "❌ 안 잡힘 (외부 사이트 + 결제 Pixel 미설치)"],
    ["ROAS / 매출 매핑", "❌ 본질적으로 불가 (Meta spend × Rakuten 매출 매칭 도구로 별도 처리 예정)"],
]
story.append(make_table(pixel_data, [55*mm, 105*mm]))

story.append(Paragraph(
    "<b>Performance goal 권장:</b> Maximize number of <b>landing page views</b>. "
    "Link clicks 최적화는 LPV가 안 잡히는 케이스에만 (Rakuten은 잡히니 X).",
    NOTE))

# ============================================================
# 11. CPC/CTR all vs link click
# ============================================================
story.append(Paragraph("11. CPC/CTR — (all) vs (link click)", H1))
cpc_data = [
    ["컬럼", "분모", "의미"],
    ["CPC (link) / CTR (link)",
     "Link Clicks (외부 URL 클릭만)",
     "진짜 랜딩 도착 효율"],
    ["CPC (all) / CTR (all)",
     "All Clicks (link click + 더보기 + 프로필 + 이모지·반응)",
     "인게이지먼트 종합 — 세은 기준"],
]
story.append(make_table(cpc_data, [40*mm, 60*mm, 60*mm]))

story.append(Paragraph(
    "<b>세은 기준 = (all).</b> Graph API insights ctr/cpc 필드 = all clicks 기준 (공식). "
    "메타몽 daily 리포트 CTR/CPC = Ads Manager <i>CTR (all) / CPC (all)</i> 와 일치. "
    "별도 변환 불필요.",
    NOTE))

# ============================================================
# 12. ad-level 노출 몰빵 진단
# ============================================================
story.append(Paragraph("12. ad-level 노출 몰빵 진단 (학습단계)", H1))
story.append(Paragraph(
    "같은 ad set 안 ad 여러 개일 때 한쪽만 노출되고 다른 쪽 CPC/CTR 공란 — "
    "망가진 게 아니라 학습단계 자동 베팅. 클릭=0이면 분자 0이라 CTR 계산 불가.",
    BODY))

diag_data = [
    ["순위", "액션", "적용 시점"],
    ["①", "24~48h 더 대기", "등록 직후 ~ 48h"],
    ["②", "약한 ad만 별도 ad set로 복제 / Advantage+ Creative 전환",
     "48h 지나도 spend 1% 미만"],
    ["③", "약한 ad 종료 + 썸네일/카피 교체", "②에도 노출 못 받으면"],
]
story.append(make_table(diag_data, [12*mm, 100*mm, 48*mm]))

# ============================================================
# 13. 증액 실행 룰
# ============================================================
story.append(Paragraph("13. 증액 실행 룰", H1))
story.append(Paragraph(
    "• 1회 ≤ 30% (Meta 학습 보호선) / ≤ 50% (Proven 안정 광고만)<br/>"
    "• 24시간 이상 유지 후 재판단<br/>"
    "• 같은 ad set 안 동시 증액 X (학습 리셋 발생)<br/>"
    "• newborn / sunset / Off 트리거 hit 광고는 증액 후보에서 자동 제외 (5/15)",
    BULLET))

# ============================================================
# 14. Industry Consensus (참고)
# ============================================================
story.append(PageBreak())
story.append(Paragraph("14. Industry Consensus (참고)", H1))
story.append(Paragraph(
    "광고주들이 본인 풀에서 어디를 winner / kill로 자르는지 — 3개 출처 일치 수치. "
    "우리 17개 풀에 정통 적용 X — Top 10% / Bottom 20% 보수 설정.",
    BODY))

ind_data = [
    ["출처", "데이터 규모", "Winner %", "Kill %"],
    ["Motion 2026",
     "550K ads / $1.3B spend",
     "5%",
     "50% kill + 45% middle"],
    ["Alex Neiman (DTC)",
     "1,847 ads / 6 brands",
     "5.1% (94개)",
     "Bottom 60% kill (week 3)"],
    ["coinis framework",
     "—",
     "Day 14+ scale",
     "CTR < 1% + 3× CPA + 0 conv"],
]
story.append(make_table(ind_data, [38*mm, 42*mm, 28*mm, 52*mm]))

story.append(Paragraph("우리 풀 적용 (5/15 합의)", H2))
ours_data = [
    ["정통 룰", "우리 풀 (보수 보정)"],
    ["Top 5% winner", "Top 10% (S 후보) — 1~2개"],
    ["Bottom 60% kill",
     "Bottom 20% (P20) Off 후보 — 3~4개 + spend ≥ ₩30K 필터"],
]
story.append(make_table(ours_data, [50*mm, 110*mm]))

# ============================================================
# 15. Daily 자동화 (구현 완료)
# ============================================================
story.append(Paragraph("15. Daily 자동화 (구현 완료)", H1))
story.append(Paragraph(
    "GitHub Actions cron으로 매일 KST 09:00경 자동 발송. 5중 다중 cron + dedup 가드.",
    BODY))

auto_data = [
    ["컴포넌트", "역할"],
    ["tools/meta_jp_daily.py",
     "1d/7d/14d 모드별 리포트 생성. KPI 카운터 + Off 권장 + BEST/WORST + 발견 + 조언"],
    [".github/workflows/meta_jp_daily.yml",
     "cron 5개 (KST 08:47/09:02/09:17/09:32/09:52) + dedup 가드 + Gmail 발송"],
    ["Gemini Auditor",
     "발송 전 본문 숫자 정합성 검증. 80점+ PASS 시에만 발송"],
    ["발송 채널",
     "Gmail (orbiters11@gmail.com → se.heo@orbiters.co.kr)"],
]
story.append(make_table(auto_data, [60*mm, 100*mm]))

# ============================================================
# 16. 향후 과제
# ============================================================
story.append(Paragraph("16. 향후 과제 (우선순위 순)", H1))
todo_data = [
    ["#", "과제", "단계", "예상 효과"],
    ["1", "Meta spend × Rakuten 매출 월간 매칭 도구",
     "이번 달", "캘빈 가이드 C단계 — 전체 ROI 가시화"],
    ["2", "PAID/GIFT KPI 차등 적용 평가",
     "6주 후", "회수 압력 차이 반영. 현재는 동일 풀 평가"],
    ["3", "S 후보 인플루언서 차기 협업 자동 발굴",
     "다음 달", "P90+ Top performer 풀 확대"],
    ["4", "Frequency ≥ 2.3 자동 alert + 교체 후보 제안",
     "다음 달", "Ad fatigue 선제 대응"],
    ["5", "주 1회 인플루언서 등급 갱신 도구 (A/B/C + S)",
     "다음 달", "차기 협업·증액 의사결정 자동화"],
    ["6", "Daily 리포트 7d delta 표시 정밀화 (CPC ±0.x% 처리)",
     "다음 주", "audit 점수 80 → 90+ 끌어올림"],
]
story.append(make_table(todo_data, [10*mm, 75*mm, 22*mm, 53*mm]))

# ============================================================
# 부록: 변경 이력
# ============================================================
story.append(Paragraph("부록. 변경 이력", H1))
hist_data = [
    ["일자", "변경"],
    ["2026-04-20", "Meta JP 광고 분석 Grosmimi Japan 단일 계정으로 한정 (US 분리)"],
    ["2026-05-06", "Rakuten Pixel LPV 작동 확인 (70~89%). Purchase X"],
    ["2026-05-06", "CPC/CTR (all) vs (link click) 차이 + 세은 기준 (all) 명시"],
    ["2026-05-07", "ad-level 노출 몰빵 = 학습단계 정상 진단 체크리스트"],
    ["2026-05-08", "Testing → Proven 2-stage 졸업 시스템 코드화"],
    ["2026-05-11", "currency = KRW 확정. ¥ 표기 폐기"],
    ["2026-05-11", "Off Rule 5/11판 (A/B/C/D 4트리거) — 풀 평균 기반"],
    ["2026-05-12", "Creative 영역 ≠ Budget 영역 분리 합의"],
    ["2026-05-12", "영상 5~6부분 구조 + 필수 3요소 + 바이럴 의뢰 전략"],
    ["2026-05-15", "<b>대규모 합의:</b> KPI ≠ Off Rule 분리 / 외부 시장 평균 폐기 / 풀 P20+sunset+Freq+velocity 4축 / 17개 ad PAID/GIFT 라벨 rename"],
    ["2026-05-18", "B-1~B-7 + PDF 섹션 2·3·8 + audit follow-up 전부 commit. 9시 보고 미발송 회귀 fix"],
]
story.append(make_table(hist_data, [25*mm, 135*mm]))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "본 기준은 살아있는 문서. 6주 운영 후 풀 분포 percentile로 임계 확정. "
    "변경 사유는 git 커밋 메시지 + 메모리 파일에 기록.",
    META))

doc.build(story)
print(f"[OK] saved {OUT} ({OUT.stat().st_size:,} bytes)")
