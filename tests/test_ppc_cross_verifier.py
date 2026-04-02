"""Tests for PPC Cross-Verifier — Gates 1 & 2."""
import sys, os, json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


class TestTimezoneAlignment:
    def test_aligned_date_range_returns_pst_dates(self):
        from ppc_cross_verifier import aligned_date_range
        start, end = aligned_date_range(days_back=7)
        assert len(start) == 10
        assert len(end) == 10
        assert start < end

    def test_assert_tz_aligned_passes_on_match(self):
        from ppc_cross_verifier import assert_tz_aligned
        dates = ("2026-04-01", "2026-04-02")
        assert_tz_aligned(dates, dates, dates)

    def test_assert_tz_aligned_fails_on_mismatch(self):
        from ppc_cross_verifier import assert_tz_aligned
        import pytest
        with pytest.raises(AssertionError, match="TZ mismatch"):
            assert_tz_aligned(
                ("2026-04-01", "2026-04-02"),
                ("2026-04-01", "2026-04-03"),
                ("2026-04-01", "2026-04-02"),
            )


class TestDataLoaders:
    def test_load_fin_data_parses_js(self, tmp_path):
        from ppc_cross_verifier import load_fin_data
        js_file = tmp_path / "fin_data.js"
        js_file.write_text(
            'const FIN_DATA = {"generated_pst": "2026-04-02 15:00 PST", '
            '"ad_performance": {"amazon": {"7d": {"spend": 500.0, "sales": 2000.0}}}};\n',
            encoding="utf-8",
        )
        data = load_fin_data(str(js_file))
        assert data["generated_pst"] == "2026-04-02 15:00 PST"
        assert data["ad_performance"]["amazon"]["7d"]["spend"] == 500.0

    def test_load_ppc_data_parses_js(self, tmp_path):
        from ppc_cross_verifier import load_ppc_data
        js_file = tmp_path / "data.js"
        js_file.write_text(
            'const PPC_DATA = {"generated_pst": "2026-04-02 10:00 PST", '
            '"naeiae": {"2026-04-02": {"campaigns": []}}};\n',
            encoding="utf-8",
        )
        data = load_ppc_data(str(js_file))
        assert "generated_pst" in data

    def test_check_freshness_passes_recent(self):
        from ppc_cross_verifier import check_freshness
        recent = datetime.now().strftime("%Y-%m-%d %H:%M PST")
        result = check_freshness(recent, max_hours=24)
        assert result["pass"] is True

    def test_check_freshness_fails_stale(self):
        from ppc_cross_verifier import check_freshness
        old = "2026-01-01 00:00 PST"
        result = check_freshness(old, max_hours=24)
        assert result["pass"] is False


class TestDataKeeperFallback:
    @patch("ppc_cross_verifier.DataKeeper")
    def test_fallback_mode_when_dk_down(self, mock_dk_cls):
        from ppc_cross_verifier import test_datakeeper_connection
        mock_dk = MagicMock()
        mock_dk.get.side_effect = Exception("Connection refused")
        mock_dk_cls.return_value = mock_dk
        assert test_datakeeper_connection() is False
