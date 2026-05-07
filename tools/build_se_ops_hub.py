#!/usr/bin/env python3
"""
build_se_ops_hub.py — Merge 5 SE-related n8n workflows into one "[SE] Operations Hub"

Reads cached workflow JSONs from .tmp/, repositions nodes by agent section,
and outputs a single merged workflow JSON ready for n8n POST.

Sections:
  1. 마존이 (Amazon JP)         y=300,  x=0~800
  2. 쿠텐이 (Rakuten JP)        y=300,  x=1200~2400
  3. 인플루언서 매니저 (DM)      y=1200, x=0~1200
  4. 인획이 (IG 콘텐츠)          y=1200, x=1400~2000  (sticky only)
  5. 깍두기 (잡무)               y=2200, x=0~800      (sticky only)
  6. 리포터 (KPI/PPC)           y=2200, x=1000~1800   (sticky only)
  7. 아인슈타인 (효율감사)       y=2200, x=2000~2600   (sticky only)
"""

import json
import os
import copy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, ".tmp")


def load_wf(filename):
    path = os.path.join(TMP, filename)
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def offset_nodes(nodes, dx, dy):
    """Shift all node positions by (dx, dy)."""
    for n in nodes:
        pos = n.get("position", [0, 0])
        n["position"] = [pos[0] + dx, pos[1] + dy]
    return nodes


def rename_node(node, old_name, new_name):
    """Rename a node and return the mapping."""
    node["name"] = new_name
    return (old_name, new_name)


def rekey_connections(connections, rename_map):
    """Update connection keys and target node names based on rename_map."""
    new_conns = {}
    for src_name, outputs in connections.items():
        actual_src = rename_map.get(src_name, src_name)
        new_outputs = {}
        for output_key, conns_list in outputs.items():
            new_list = []
            for conn_group in conns_list:
                new_group = []
                for c in conn_group:
                    c2 = dict(c)
                    c2["node"] = rename_map.get(c2["node"], c2["node"])
                    new_group.append(c2)
                new_list.append(new_group)
            new_outputs[output_key] = new_list
        new_conns[actual_src] = new_outputs
    return new_conns


def make_sticky(name, content, position, width=460, height=None, color=None):
    """Create a sticky note node."""
    params = {"content": content}
    if width:
        params["width"] = width
    if height:
        params["height"] = height
    if color:
        params["color"] = color  # n8n sticky colors: 1-7
    return {
        "parameters": params,
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": position,
        "id": "",  # n8n generates
        "name": name,
    }


def build():
    # Load all workflows
    wf_amazon = load_wf("wf_amazon.json")
    wf_rakuten_hub = load_wf("wf_rakuten_hub.json")
    wf_rakuten_pipeline = load_wf("wf_rakuten_pipeline.json")
    wf_dm = load_wf("wf_dm_automation.json")
    wf_rakuten_daily = load_wf("wf_rakuten_daily_order.json")

    all_nodes = []
    all_connections = {}

    # ──────────────────────────────────────────
    # HEADER (y=0)
    # ──────────────────────────────────────────
    header_content = """## [SE] Operations Hub — 세은 에이전트 전체 통합

### 에이전트 7명
| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | 🟦 마존이 | Amazon JP 주문처리·요약 |
| 2 | 🟧 쿠텐이 | Rakuten JP 주문·순위·리포트 |
| 3 | 🟪 인플루언서 매니저 | IG DM 자동화·계약서 |
| 4 | 🟩 인획이 | IG 콘텐츠 기획 (GitHub Actions) |
| 5 | 🟨 깍두기 | 잡무·메일·트위터부대 |
| 6 | 🟥 리포터 | KPI·PPC 리포트 |
| 7 | ⬜ 아인슈타인 | 효율/창의성 감사 |

### 운영 규칙
- 모든 에이전트는 **세은 확인 없이 외부 전송 금지**
- n8n 직접 접근 불가 → **항상 API**
- 최종 산출물은 클라우드 저장 (Sheets/Teams)
- `.tmp/`는 처리용만"""

    all_nodes.append(make_sticky(
        "🏠 Operations Hub Overview",
        header_content,
        [0, -200],
        width=800,
        height=420,
        color=6
    ))

    # ──────────────────────────────────────────
    # SECTION 1: 마존이 (y=300, x=0~800)
    # ──────────────────────────────────────────
    amazon_sticky_content = """## 🟦 마존이 — Amazon JP 운영

**역할**: KSE 주문등록, 옵션코드, 배송접수, Excel 다운로드, 주문요약
**스케줄**: 매일 13:30 주문요약 → Teams
**도구**: `kse_amazon_order.py`, `kse_order_summary.py`, `amazon_sp_api.py`

### 플로우
```
Order Data Webhook → Generate Summary → Build Card → Teams → Respond
```"""

    all_nodes.append(make_sticky(
        "🟦 마존이 Section",
        amazon_sticky_content,
        [0, 280],
        width=700,
        height=280,
        color=4
    ))

    # Extract functional nodes from Amazon workflow (skip sticky notes)
    amazon_rename_map = {}
    amazon_nodes = []
    for n in wf_amazon["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue  # skip existing stickies
        new_node = copy.deepcopy(n)
        old_name = new_node["name"]
        new_name = f"🟦 {old_name}"
        new_node["name"] = new_name
        new_node["id"] = ""  # let n8n regenerate
        amazon_rename_map[old_name] = new_name
        amazon_nodes.append(new_node)

    # Reposition: base at x=0, y=600
    # Original positions range: x=-100..1100, y=1350
    # Move to x=0, y=600
    for n in amazon_nodes:
        orig = n["position"]
        n["position"] = [orig[0] + 100, 600]  # shift x by +100 (so -100 becomes 0), y=600 fixed

    all_nodes.extend(amazon_nodes)

    amazon_conns = rekey_connections(wf_amazon.get("connections", {}), amazon_rename_map)
    all_connections.update(amazon_conns)

    # Also bring over the reference stickies as a combined one
    ref_content = """### Amazon 참고사항
- **TXT 변환**: KSE 형식 (OrderId, Item, Qty, OptionCode)
- **Product Types**: GROSMIMI / NAEIAE / ORBITOOL
- **옵션코드**: OPTION_MAP 사용, 풀 상품명(색상 포함) 확인
- **배송접수**: 배송접수 후 송장번호 자동 입력
- **Excel 업로드**: 세은 직접 처리 (에이전트 금지)"""

    all_nodes.append(make_sticky(
        "🟦 Amazon 참고",
        ref_content,
        [0, 750],
        width=700,
        height=220,
        color=4
    ))

    # ──────────────────────────────────────────
    # SECTION 2: 쿠텐이 (y=300, x=1200~2400)
    # ──────────────────────────────────────────
    rakuten_sticky_content = """## 🟧 쿠텐이 — Rakuten JP 운영

**역할**: RMS 주문확인, 메일발송, KSE 주문수집, 옵션코드, 배송접수, 송장입력
**스케줄**:
- 09:00 모닝 리마인더 (평일)
- 13:30 키워드 순위 추적 → Teams
- 17:30 일일 리포트 → Teams
**도구**: `rakuten_order_confirm.py`, `kse_rakuten_order.py`, `rakuten_tracking_input.py`"""

    all_nodes.append(make_sticky(
        "🟧 쿠텐이 Section",
        rakuten_sticky_content,
        [1200, 280],
        width=700,
        height=280,
        color=2
    ))

    # ─── Rakuten Hub nodes ───
    rakuten_hub_rename = {}
    rakuten_hub_nodes = []
    for n in wf_rakuten_hub["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        new_node = copy.deepcopy(n)
        old_name = new_node["name"]
        new_name = f"🟧 {old_name}"
        new_node["name"] = new_name
        new_node["id"] = ""
        rakuten_hub_rename[old_name] = new_name
        rakuten_hub_nodes.append(new_node)

    # Reposition: original x=560..1660, y=500..1140
    # Target: x starting at 1200, y starting at 600
    # Shift: dx = 1200-560 = 640, dy = 600-500 = 100
    for n in rakuten_hub_nodes:
        orig = n["position"]
        n["position"] = [orig[0] + 640, orig[1] + 100]

    all_nodes.extend(rakuten_hub_nodes)
    rakuten_hub_conns = rekey_connections(wf_rakuten_hub.get("connections", {}), rakuten_hub_rename)
    all_connections.update(rakuten_hub_conns)

    # ─── Rakuten Pipeline nodes ───
    rakuten_pipe_rename = {}
    rakuten_pipe_nodes = []
    for n in wf_rakuten_pipeline["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        new_node = copy.deepcopy(n)
        old_name = new_node["name"]
        # Avoid name collision with hub
        new_name = f"🟧P {old_name}"
        new_node["name"] = new_name
        new_node["id"] = ""
        rakuten_pipe_rename[old_name] = new_name
        rakuten_pipe_nodes.append(new_node)

    # Reposition: original x=200..2180, y=60..640
    # Target: below hub nodes, x=1200, y=1350
    # Shift: dx = 1200-200 = 1000, dy = 1350-200 = 1150
    for n in rakuten_pipe_nodes:
        orig = n["position"]
        n["position"] = [orig[0] + 1000, orig[1] + 1150]

    all_nodes.extend(rakuten_pipe_nodes)
    rakuten_pipe_conns = rekey_connections(wf_rakuten_pipeline.get("connections", {}), rakuten_pipe_rename)
    all_connections.update(rakuten_pipe_conns)

    # ─── Rakuten Daily Order Report nodes ───
    rakuten_daily_rename = {}
    rakuten_daily_nodes = []
    for n in wf_rakuten_daily["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        new_node = copy.deepcopy(n)
        old_name = new_node["name"]
        new_name = f"🟧D {old_name}"
        new_node["name"] = new_name
        new_node["id"] = ""
        rakuten_daily_rename[old_name] = new_name
        rakuten_daily_nodes.append(new_node)

    # Reposition: original x=0..1000, y=0
    # Target: x=1200, y=2000
    for n in rakuten_daily_nodes:
        orig = n["position"]
        n["position"] = [orig[0] + 1200, orig[1] + 2000]

    all_nodes.extend(rakuten_daily_nodes)
    rakuten_daily_conns = rekey_connections(wf_rakuten_daily.get("connections", {}), rakuten_daily_rename)
    all_connections.update(rakuten_daily_conns)

    # Rakuten reference sticky
    rakuten_ref = """### Rakuten 파이프라인 구성
**Hub** (webhook): 주문 파이프라인 결과 → Teams 알림 (성공/에러)
**Pipeline** (webhook): 주문처리 결과 → 성공/경고/에러 분기 → Sheets 로그
**Daily Report** (schedule): 매일 전일 주문 RMS API 조회 → Teams"""

    all_nodes.append(make_sticky(
        "🟧 Rakuten 참고",
        rakuten_ref,
        [1200, 2150],
        width=700,
        height=180,
        color=2
    ))

    # ──────────────────────────────────────────
    # SECTION 3: 인플루언서 매니저 (y=1200, x=0~1200)
    # ──────────────────────────────────────────
    dm_sticky_content = """## 🟪 인플루언서 매니저 — DM 대화 + 계약서

**역할**: IG DM → Claude 초안 → Teams 승인 → 발송
**STEP 1~11 파이프라인**
**도구**: `influencer_rag.py`, `generate_influencer_contract.py`

### DM 플로우
```
ManyChat Webhook → Claude API → Teams 알림 → 승인/편집 → DM 발송
```
### 중요 규칙
- DM 작성 전 메모리 먼저 확인
- 템플릿 있으면 원문 그대로 사용
- 서명: GROSMIMI JAPAN만 (개인 이름 금지)"""

    all_nodes.append(make_sticky(
        "🟪 인플루언서 매니저 Section",
        dm_sticky_content,
        [0, 2600],
        width=700,
        height=340,
        color=5
    ))

    # DM Automation nodes
    dm_rename = {}
    dm_nodes = []
    for n in wf_dm["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        new_node = copy.deepcopy(n)
        old_name = new_node["name"]
        new_name = f"🟪 {old_name}"
        new_node["name"] = new_name
        new_node["id"] = ""
        dm_rename[old_name] = new_name
        dm_nodes.append(new_node)

    # Reposition: original x=240..1120, y=160..1060
    # Target: x=0, y=3000
    # Shift: dx = 0-240 = -240, dy = 3000-160 = 2840
    for n in dm_nodes:
        orig = n["position"]
        n["position"] = [orig[0] - 240, orig[1] + 2840]

    all_nodes.extend(dm_nodes)
    dm_conns = rekey_connections(wf_dm.get("connections", {}), dm_rename)
    all_connections.update(dm_conns)

    # ──────────────────────────────────────────
    # SECTION 4: 인획이 (y=1200, x=1400~2000) - sticky only
    # ──────────────────────────────────────────
    inhwoek_content = """## 🟩 인획이 — IG 콘텐츠 기획

**역할**: 주간 콘텐츠 기획안 30개 (meme:10, brand:10, mom_tip:10)
**스케줄**:
- 매주 수 10:00 경쟁사 분석
- 매주 금 14:00 기획안 생성
**도구**: `plan_weekly_content.py`, `scrape_ig_competitor.py`
**자동화**: GitHub Actions (`kikaku.yml`)

### 저장 위치
`C:\\Users\\orbit\\Desktop\\s\\요청하신 자료\\인스타그램 기획안\\EXCEL\\`

### 스타일 가이드
- Mom Tips: あるある공감 + チェックリスト
- 시리즈명: ママの「それ知りたかった！」
- 캐러셀 페이지별 이미지 구상 필수
- 주제 중복 방지: `.tmp/topic_history.json` 확인"""

    all_nodes.append(make_sticky(
        "🟩 인획이 Section",
        inhwoek_content,
        [1200, 2600],
        width=600,
        height=420,
        color=3
    ))

    # ──────────────────────────────────────────
    # SECTION 5: 깍두기 (y=2200, x=0~800) - sticky only
    # ──────────────────────────────────────────
    kkakdugi_content = """## 🟨 깍두기 — 잡무 전담

**역할**: 메일발송, Teams 알림, 트위터부대 운영, 파일변환, 토큰갱신

### 트위터부대 (ツイッター部隊)
| 멤버 | 역할 | 스케줄 |
|------|------|--------|
| 総監督 | 전일 실적 보고 | 매일 09:00 JST |
| 監督 | 투고 예정 보고 | 매일 09:00 JST |
| 企画マン | 주간 플랜 생성 | 매주 금 09:00 |
| ツイート | 자동 투고 | 매일 10:00/19:00 |
| コメンター | 공감 댓글 | 매일 12~16시 |
| 調査マン | 경쟁 조사 | 수·금 09:00 |
| ハッシュタグ | 해시태그 조사 | 금 09:00 |

**도구**: `send_gmail.py`, `teams_notify.py`, `twitter_*.py`
**자동화**: GitHub Actions (`tweet.yml`, `commenter.yml`, `chousa.yml` 등)"""

    all_nodes.append(make_sticky(
        "🟨 깍두기 Section",
        kkakdugi_content,
        [0, 4400],
        width=700,
        height=460,
        color=1
    ))

    # ──────────────────────────────────────────
    # SECTION 6: 리포터 (y=2200, x=1000~1800) - sticky only
    # ──────────────────────────────────────────
    reporter_content = """## 🟥 리포터 — KPI / 광고 리포트

**역할**: 월간 KPI 엑셀, 일일 PPC 브리핑, 광고 대시보드
**스케줄**:
- 매일 09:00 PPC 브리핑 → Teams
- 매월 KPI 리포트 생성

**도구**:
- `run_kpi_monthly.py` (검증이 → 골만이 → 포맷이)
- `run_ppc_briefing.py`
- `data_keeper_client.py`

**자동화**: GitHub Actions (`ppc_briefing.yml`, `kpi_weekly.yml`)

### KPI 파이프라인
```
검증이 (Pandera 스키마) → 골만이 (계산) → 포맷이 (Excel)
```"""

    all_nodes.append(make_sticky(
        "🟥 리포터 Section",
        reporter_content,
        [1000, 4400],
        width=600,
        height=400,
        color=7
    ))

    # ──────────────────────────────────────────
    # SECTION 7: 아인슈타인 (y=2200, x=2000~2600) - sticky only
    # ──────────────────────────────────────────
    einstein_content = """## ⬜ 아인슈타인 — 효율/창의성 감사

**역할**: 프로세스 진단, 개선 제안, 주간 헬스체크
**실행 없음** — 분석 + 제안만
**트리거**: 세은이 물어볼 때

### 감사 범위
- 에이전트별 작업 효율 분석
- 중복 작업 탐지
- 자동화 가능 영역 제안
- 비용 최적화 (API 호출, 토큰 사용)

### 주간 헬스체크 항목
- GitHub Actions 실패율
- Data Keeper 채널 freshness
- n8n 워크플로우 에러
- 인플루언서 파이프라인 병목"""

    all_nodes.append(make_sticky(
        "⬜ 아인슈타인 Section",
        einstein_content,
        [1800, 4400],
        width=600,
        height=380,
    ))

    # ──────────────────────────────────────────
    # Build final workflow JSON
    # ──────────────────────────────────────────
    workflow = {
        "name": "[SE] Operations Hub",
        "nodes": all_nodes,
        "connections": all_connections,
        "settings": {
            "executionOrder": "v1"
        },
        "staticData": None,
        "tags": [
            {"name": "SE-ops"}
        ]
    }

    # Write output
    out_path = os.path.join(TMP, "se_ops_hub.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    total_functional = sum(
        1 for n in all_nodes if n["type"] != "n8n-nodes-base.stickyNote"
    )
    total_sticky = sum(
        1 for n in all_nodes if n["type"] == "n8n-nodes-base.stickyNote"
    )

    print(f"Built [SE] Operations Hub")
    print(f"  Total nodes: {len(all_nodes)}")
    print(f"    Functional: {total_functional}")
    print(f"    Sticky notes: {total_sticky}")
    print(f"  Connections: {len(all_connections)} source nodes")
    print(f"  Output: {out_path}")


if __name__ == "__main__":
    build()
