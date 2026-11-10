"""DK 읽기 실패가 fin_data.js 를 빈 값으로 덮지 않는지.

재시도 끝에 실패한 읽기는 FAILED_READS 에 남고, generate_fin_data 는 그것을 보고 파일을 쓰지 않은 채 1 로 끝난다.
실제 DK 서버와 Amazon 은 부르지 않는다. requests 를 가짜로 바꾸고 운영과 같은 dk.get·generate() 경로로 부른다.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import data_keeper_client as dkc  # noqa: E402
import generate_fin_data as gfd  # noqa: E402

ROW_DATE = (date.today() - timedelta(days=2)).isoformat()


class FakeResp:
    def __init__(self, status=200, rows=(), headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._rows = list(rows)

    def json(self):
        return {"rows": self._rows, "next_offset": None}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")


class FakeDK:
    """표마다 행 하나를 주고, fail 에 든 표는 상태 코드 목록을 차례로 돌려준다(다 쓰면 200)."""

    def __init__(self, fail=None):
        self.fail = {t: list(codes) for t, codes in (fail or {}).items()}
        self.calls = []

    def __call__(self, url, params=None, **kw):
        table = params.get("table")
        self.calls.append(table)
        codes = self.fail.get(table)
        if codes:
            return FakeResp(codes.pop(0), headers={"Retry-After": "0"})
        return FakeResp(rows=[{"id": 1, "date": ROW_DATE, "brand": "Grosmimi", "channel": "Onzenna D2C"}])


@pytest.fixture
def dk(monkeypatch):
    dkc.FAILED_READS.clear()
    monkeypatch.setattr(dkc.time, "sleep", lambda s: None)

    def no_post(*a, **kw):
        raise requests.ConnectionError("시험에서는 Amazon 을 부르지 않는다")
    monkeypatch.setattr(requests, "post", no_post)

    def install(**kw):
        srv = FakeDK(**kw)
        monkeypatch.setattr(requests, "get", srv)
        return srv
    yield install
    dkc.FAILED_READS.clear()


@pytest.fixture
def output(tmp_path, monkeypatch):
    out = tmp_path / "fin_data.js"
    out.write_bytes(b"const FIN_DATA = {\"search_ranking\": {\"dates\": [\"prev\"]}};")
    monkeypatch.setattr(gfd, "OUTPUT", out)
    monkeypatch.setattr(sys, "argv", ["generate_fin_data.py"])
    return out


def test_read_failing_every_retry_is_recorded(dk):
    srv = dk(fail={"amazon_search_ranking": [429] * dkc.MAX_TRIES})
    assert dkc.DataKeeper().get("amazon_search_ranking", days=90) == []
    assert srv.calls.count("amazon_search_ranking") == dkc.MAX_TRIES
    assert [t for t, _ in dkc.FAILED_READS] == ["amazon_search_ranking"]
    assert "429" in dkc.FAILED_READS[0][1]


def test_read_recovered_by_retry_is_not_recorded(dk):
    srv = dk(fail={"amazon_search_ranking": [429]})
    rows = dkc.DataKeeper().get("amazon_search_ranking", days=90)
    assert len(rows) == 1 and srv.calls.count("amazon_search_ranking") == 2
    assert dkc.FAILED_READS == []


def test_gate_keeps_previous_file_and_exits_1(dk, output, capsys):
    before = output.read_bytes()
    dk(fail={"amazon_search_ranking": [429] * dkc.MAX_TRIES})
    with pytest.raises(SystemExit) as exc:
        gfd.generate()
    assert exc.value.code == 1
    assert output.read_bytes() == before
    assert "::error::" in capsys.readouterr().out


def test_failure_of_optional_table_only_still_writes(dk, output):
    # amazon_sqp_brand 는 운영에서 매번 400 이다 — 이 실패로 대시보드가 멈추면 안 된다.
    before = output.read_bytes()
    dk(fail={"amazon_sqp_brand": [400]})
    gfd.generate()
    assert [t for t, _ in dkc.FAILED_READS] == ["amazon_sqp_brand"]
    after = output.read_text(encoding="utf-8")
    assert output.read_bytes() != before
    assert '"search_ranking": {\n  "dates": [\n   "' + ROW_DATE in after
