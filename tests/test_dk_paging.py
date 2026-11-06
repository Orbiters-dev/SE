"""data_keeper_client.query_rows — /query/ 를 next_offset 으로 끝까지 이어 읽는지.

실제 DK 서버는 부르지 않는다. requests.get 을 가짜 서버로 바꿔 나가는 요청(limit·offset)과 돌려받은 행을 본다.
"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import data_keeper_client as dkc  # noqa: E402


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeServer:
    """서버 계약을 흉내 낸다 — 한 응답 최대 cap 행, 남으면 next_offset."""

    def __init__(self, rows, cap=2, fail=()):
        self.rows, self.cap, self.fail = rows, cap, list(fail)
        self.calls = []

    def __call__(self, url, params=None, **kw):
        self.calls.append(dict(params))
        assert len(self.calls) <= 20, "멈추지 않고 계속 묻는다"
        if int(params["limit"]) < 1:   # 서버는 limit 1 미만을 400 으로 막는다
            return FakeResp(400)
        if self.fail:
            return self.fail.pop(0)
        limit = min(int(params["limit"]), self.cap)
        off = int(params.get("offset", 0))
        page = self.rows[off:off + limit]
        nxt = off + limit if off + limit < len(self.rows) else None
        return FakeResp(body={"rows": page, "limit": limit, "offset": off, "next_offset": nxt})


@pytest.fixture
def server(monkeypatch):
    sleeps = []
    monkeypatch.setattr(dkc.time, "sleep", sleeps.append)
    monkeypatch.setattr(dkc, "PAGE_ROWS", 2)

    def install(rows, **kw):
        srv = FakeServer(rows, **kw)
        srv.sleeps = sleeps
        monkeypatch.setattr(dkc.requests, "get", srv)
        return srv
    return install


ROWS = [{"id": i} for i in range(5, 0, -1)]   # -id 정렬: 5,4,3,2,1


def test_follows_next_offset_until_null(server):
    srv = server(ROWS)
    assert dkc.query_rows({"table": "content_posts"}) == ROWS
    assert [(c["offset"], c["limit"]) for c in srv.calls] == [(0, 2), (2, 2), (4, 2)]
    assert srv.sleeps == [dkc.PAGE_GAP_SEC] * 2   # 장 사이만 쉰다


def test_single_page_when_next_offset_null(server):
    srv = server(ROWS[:2])
    assert dkc.query_rows({"table": "t"}) == ROWS[:2]
    assert len(srv.calls) == 1 and srv.sleeps == []


def test_retries_429_after_retry_after(server, capsys):
    srv = server(ROWS, fail=[FakeResp(429, headers={"Retry-After": "60"})])
    assert dkc.query_rows({"table": "t"}) == ROWS
    assert srv.calls[0] == srv.calls[1]            # 같은 장을 다시 물었다
    assert srv.sleeps[0] == 60
    assert "HTTP 429" in capsys.readouterr().err


def test_503_without_retry_after_backs_off(server):
    srv = server(ROWS[:1], fail=[FakeResp(503)])
    assert dkc.query_rows({"table": "t"}) == ROWS[:1]
    assert srv.sleeps == [dkc.PAGE_GAP_SEC * 2]


def test_gives_up_after_max_tries(server):
    srv = server(ROWS, fail=[FakeResp(429)] * dkc.MAX_TRIES)
    with pytest.raises(requests.HTTPError):
        dkc.query_rows({"table": "t"})
    assert len(srv.calls) == dkc.MAX_TRIES


def test_max_rows_smaller_than_table_stops_and_warns(server, capsys):
    srv = server(ROWS)
    assert dkc.query_rows({"table": "t"}, max_rows=3) == ROWS[:3]
    assert [(c["offset"], c["limit"]) for c in srv.calls] == [(0, 2), (2, 1)]
    assert "limit 3 에서 멈췄다" in capsys.readouterr().err


def test_max_rows_equal_to_table_does_not_warn(server, capsys):
    server(ROWS)
    assert dkc.query_rows({"table": "t"}, max_rows=5) == ROWS
    assert "멈췄다" not in capsys.readouterr().err


def test_failure_mid_way_raises_instead_of_partial(server):
    srv = server(ROWS)
    real = srv.__call__
    srv_calls = []

    def flaky(url, params=None, **kw):
        srv_calls.append(params)
        return FakeResp(500) if len(srv_calls) == 2 else real(url, params=params, **kw)
    dkc.requests.get = flaky
    with pytest.raises(requests.HTTPError):
        dkc.query_rows({"table": "t"})


def test_row_shifted_into_next_page_is_kept_once(server):
    # 첫 장을 읽은 뒤 새 행(id 6)이 맨 앞에 끼면 offset 2 장에 id 4 가 다시 온다.
    srv = server(ROWS)
    real = srv.__call__

    def shifting(url, params=None, **kw):
        if params["offset"] == 2:
            srv.rows = [{"id": 6}] + ROWS
        return real(url, params=params, **kw)
    dkc.requests.get = shifting
    ids = [r["id"] for r in dkc.query_rows({"table": "t"})]
    assert ids == [5, 4, 3, 2, 1]


def test_rows_without_id_are_all_kept(server):
    rows = [{"username": "a"}, {"username": "a"}, {"username": "b"}]
    server(rows)
    assert dkc.query_rows({"table": "t", "fields": "username"}) == rows


def test_token_header_and_params_sent(server):
    srv = server(ROWS[:1])
    seen = {}
    real = srv.__call__

    def spy(url, params=None, **kw):
        seen.update(kw)
        return real(url, params=params, **kw)
    dkc.requests.get = spy
    dkc.query_rows({"table": "content_posts", "region": "jp"}, token="T")
    assert seen["headers"] == {"Authorization": "Bearer T"}
    assert srv.calls[0]["region"] == "jp" and srv.calls[0]["table"] == "content_posts"


def test_get_default_reads_every_page(server):
    srv = server(ROWS)
    assert dkc.DataKeeper().get("content_posts") == ROWS
    assert len(srv.calls) == 3


def test_get_explicit_limit_is_max_rows(server):
    srv = server(ROWS)
    assert dkc.DataKeeper().get("content_posts", limit=1) == ROWS[:1]
    assert srv.calls[0]["limit"] == 1


def test_handle_only_on_second_page_reaches_follower_map(server, monkeypatch):
    """IG DM 팔로워 — 서버 첫 장(1만 행) 밖의 핸들도 들어와야 한다."""
    import ig_dm_follower_enrich as fe
    rows = [{"username": "new_a", "followers": 10}, {"username": "new_b", "followers": 20},
            {"username": "old_c", "followers": 30}]
    server(rows)
    assert fe.fetch_dk_followers() == {"new_a": 10, "new_b": 20, "old_c": 30}


def test_follower_fetch_failure_is_none(server):
    import ig_dm_follower_enrich as fe
    server(ROWS, fail=[FakeResp(500)])
    assert fe.fetch_dk_followers() is None


def test_first_post_from_second_page(server):
    """IG DM 여정 — 핸들의 가장 이른 투고가 둘째 장에 있어도 첫 투고일로 잡힌다."""
    import ig_dm_kpi_aggregate as agg
    rows = [
        {"post_date": "2026-10-01", "username": "@Han", "source_keywords": "grosmimi"},
        {"post_date": "2026-09-15", "username": "other", "source_keywords": "grosmimi"},
        {"post_date": "2026-08-03", "username": "han", "source_keywords": "Grosmimi jp"},
    ]
    server(rows)
    assert agg.fetch_dk_first_posts() == {"han": "2026-08-03", "other": "2026-09-15"}


def test_ci_daily_row_count_comes_from_tables_not_a_capped_read(monkeypatch):
    # 행을 읽어 세면 한도(1만)에서 멈춰 큰 표가 1만으로 보였다 — /tables/ 의 전체 수를 써야 한다.
    import run_ci_daily

    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(url)
        assert url.endswith("/tables/"), url
        return FakeResp(body={"tables": {"content_posts": {"count": 32406, "domain": "content"}}})

    monkeypatch.setattr(dkc.requests, "get", fake_get)
    run_ci_daily._dk_table_counts.cache_clear()
    assert run_ci_daily.pg_table_count("content_posts") == 32406
    assert run_ci_daily.pg_table_count("missing_table") is None
    assert len(calls) == 1   # 표마다 묻지 않고 한 번
