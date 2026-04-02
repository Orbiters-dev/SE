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


class TestGate1:
    def test_loop1_dk_vs_fin_passes_within_tolerance(self):
        from ppc_cross_verifier import gate1_loop1_dk_vs_fin
        dk_summary = {"spend_7d": 500.0, "sales_7d": 2000.0}
        fin_summary = {"spend_7d": 502.0, "sales_7d": 2010.0}
        result = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
        assert result["pass"] is True

    def test_loop1_dk_vs_fin_fails_outside_tolerance(self):
        from ppc_cross_verifier import gate1_loop1_dk_vs_fin
        dk_summary = {"spend_7d": 500.0, "sales_7d": 2000.0}
        fin_summary = {"spend_7d": 600.0, "sales_7d": 2000.0}
        result = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
        assert result["pass"] is False
        assert any("spend" in f.get("check", "") for f in result["failures"])

    def test_loop2_dk_vs_ppc_passes(self):
        from ppc_cross_verifier import gate1_loop2_dk_vs_ppc
        dk_campaigns = {"camp1": {"spend_7d": 100.0, "acos_7d": 25.0}}
        ppc_campaigns = {"camp1": {"spend_7d": 100.5, "acos_7d": 25.3}}
        result = gate1_loop2_dk_vs_ppc(dk_campaigns, ppc_campaigns)
        assert result["pass"] is True

    def test_loop3_three_way_passes_when_all_match(self):
        from ppc_cross_verifier import gate1_loop3_three_way
        l1 = {"pass": True, "failures": []}
        l2 = {"pass": True, "failures": []}
        result = gate1_loop3_three_way(l1, l2, insights_path=None)
        assert result["pass"] is True

    def test_loop3_three_way_fails_on_prior_failure(self):
        from ppc_cross_verifier import gate1_loop3_three_way
        l1 = {"pass": False, "failures": [{"check": "spend", "detail": "20% off"}]}
        l2 = {"pass": True, "failures": []}
        result = gate1_loop3_three_way(l1, l2, insights_path=None)
        assert result["pass"] is False

    def test_run_gate1_returns_result_in_fallback(self):
        from ppc_cross_verifier import run_gate1
        with patch("ppc_cross_verifier.test_datakeeper_connection", return_value=False):
            with patch("ppc_cross_verifier.load_fin_data", return_value={"generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST"), "ad_performance": {"amazon": {"7d": {"spend": 500, "sales": 2000}}}}):
                with patch("ppc_cross_verifier.load_ppc_data", return_value={"generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST")}):
                    result = run_gate1(brand="naeiae")
                    assert result["gate"] == 1
                    assert result["fallback_mode"] is True
                    assert result["budget_override"] == 0.70


class TestGate2:
    def test_loop1_freshness_passes_recent_proposal(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        ts = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M:%S PST")
        result = gate2_loop1_freshness(ts, daily_spend=100)
        assert result["pass"] is True

    def test_loop1_freshness_fails_old_proposal(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        ts = "2025-01-01 00:00:00 PST"
        result = gate2_loop1_freshness(ts, daily_spend=100)
        assert result["pass"] is False

    def test_loop1_high_spend_uses_tighter_limit(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        past = datetime.now(ZoneInfo("America/Los_Angeles")) - timedelta(hours=2, minutes=30)
        ts = past.strftime("%Y-%m-%d %H:%M:%S PST")
        result_low = gate2_loop1_freshness(ts, daily_spend=100)
        result_high = gate2_loop1_freshness(ts, daily_spend=1500)
        assert result_low["pass"] is True   # 3h limit
        assert result_high["pass"] is False  # 2h limit

    def test_loop2_ceiling_passes_within_limits(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 80, "new_daily_budget": 95,
             "current_bid": 1.5, "proposed_bid": 1.7, "brand": "naeiae"},
        ]
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is True

    def test_loop2_ceiling_blocks_over_max(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 80, "new_daily_budget": 200,
             "current_bid": 1.5, "proposed_bid": 1.7, "brand": "naeiae"},
        ]
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is False

    def test_loop2_rate_limit_blocks_large_change(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 50, "new_daily_budget": 80,
             "current_bid": 1.5, "proposed_bid": 1.5, "brand": "naeiae"},
        ]  # +60% budget change > 30% limit
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is False
        assert any("rate_limit" in f.get("check", "") for f in result["failures"])

    def test_loop3_tacos_warns_high(self):
        from ppc_cross_verifier import gate2_loop3_financial
        result = gate2_loop3_financial(
            proposed_spend_delta=500, current_total_sales=2000, current_tacos=0.10
        )
        assert any(w.get("check") == "tacos_impact" for w in result.get("warnings", []))


class TestBudgetRecommendation:
    def test_tier1_ceiling_lift_when_at_max_and_high_roas(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "Naeiae Rice Pop - SP - Manual", "campaignId": "1",
             "currentDailyBudget": 100, "roas_7d": 7.38, "acos_7d": 13.6,
             "spend_7d": 163, "sales_7d": 1205, "targeting_type": "MANUAL"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tier1 = [r for r in rec["recommendations"] if r["tier"] == 1]
        assert len(tier1) == 1
        assert tier1[0]["recommended"] > 100

    def test_tier2_rebalance_when_manual_much_better(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "SP-Manual", "campaignId": "1", "currentDailyBudget": 100,
             "roas_7d": 7.38, "acos_7d": 13.6, "spend_7d": 163, "sales_7d": 1205,
             "targeting_type": "MANUAL"},
            {"name": "SP-Auto", "campaignId": "2", "currentDailyBudget": 100,
             "roas_7d": 1.54, "acos_7d": 64.9, "spend_7d": 176, "sales_7d": 271,
             "targeting_type": "AUTO"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tier2 = [r for r in rec["recommendations"] if r["tier"] == 2]
        assert len(tier2) == 1
        assert tier2[0]["manual_share"]["recommended"] > 0.60

    def test_no_recommendation_when_roas_low(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "SP-Manual", "campaignId": "1", "currentDailyBudget": 50,
             "roas_7d": 1.2, "acos_7d": 83.0, "spend_7d": 100, "sales_7d": 120,
             "targeting_type": "MANUAL"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tier1 = [r for r in rec["recommendations"] if r["tier"] == 1]
        tier3 = [r for r in rec["recommendations"] if r["tier"] == 3 and r.get("type") == "increase_total_daily_budget"]
        assert len(tier1) == 0
        assert len(tier3) == 0


class TestSocialTrends:
    def test_extract_social_keywords(self):
        from ppc_cross_verifier import get_social_trend_keywords
        mock_posts = [
            {"hashtags": "#babyfood,#organicsnack,#babyfood", "transcript": "this organic baby melt snack is great for toddlers"},
            {"hashtags": "#babyfood,#ricepuff", "transcript": "baby loves this rice puff melt snack"},
        ]
        with patch("ppc_cross_verifier.DataKeeper") as mock_dk_cls:
            mock_dk = MagicMock()
            mock_dk.get.return_value = mock_posts
            mock_dk_cls.return_value = mock_dk
            result = get_social_trend_keywords("naeiae", days=30)
            assert result["post_count"] == 2
            top_tags = dict(result["top_hashtags"])
            assert top_tags.get("babyfood", 0) >= 2

    def test_find_untapped_keywords(self):
        from ppc_cross_verifier import find_untapped_social_keywords
        social = [("baby melt snack", 8), ("organic rice puff", 5), ("toddler food", 3)]
        ppc_terms = ["rice puff baby", "naeiae rice pop", "baby snack organic"]
        untapped = find_untapped_social_keywords(social, ppc_terms)
        names = [u["keyword"] for u in untapped]
        assert "baby melt snack" in names

    def test_detect_hashtag_surge(self):
        from ppc_cross_verifier import detect_hashtag_surge
        posts_7d = [{"hashtags": "#babyledweaning"} for _ in range(7)]
        posts_30d = posts_7d + [{"hashtags": "#babyledweaning"} for _ in range(3)]
        with patch("ppc_cross_verifier.DataKeeper") as mock_dk_cls:
            mock_dk = MagicMock()
            mock_dk.get.side_effect = [posts_7d, posts_30d]
            mock_dk_cls.return_value = mock_dk
            surges = detect_hashtag_surge("naeiae")
            assert len(surges) >= 1
            assert surges[0]["hashtag"] == "babyledweaning"
            assert surges[0]["surge_ratio"] > 2.0


class TestEndToEnd:
    """Smoke tests using mocked data sources."""

    @patch("ppc_cross_verifier.test_datakeeper_connection", return_value=False)
    @patch("ppc_cross_verifier.load_fin_data")
    @patch("ppc_cross_verifier.load_ppc_data")
    def test_gate1_fallback_mode(self, mock_ppc, mock_fin, mock_dk):
        from ppc_cross_verifier import run_gate1
        mock_fin.return_value = {
            "generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST"),
            "ad_performance": {"amazon": {"7d": {"spend": 500, "sales": 2000}}},
        }
        mock_ppc.return_value = {
            "generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST"),
        }
        result = run_gate1(brand="naeiae")
        assert result["fallback_mode"] is True
        assert result["budget_override"] == 0.70
        assert result["gate"] == 1

    def test_full_budget_recommendation_naeiae_scenario(self):
        """Real Naeiae scenario: Manual ROAS 7.38x at $100 ceiling, Auto ACOS 64.9%."""
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "Naeiae Rice Pop - SP - Manual", "campaignId": "1",
             "currentDailyBudget": 100, "roas_7d": 7.38, "acos_7d": 13.6,
             "spend_7d": 163, "sales_7d": 1205, "targeting_type": "MANUAL"},
            {"name": "Naeiae Rice Pop - SP - Auto", "campaignId": "2",
             "currentDailyBudget": 100, "roas_7d": 1.54, "acos_7d": 64.9,
             "spend_7d": 176, "sales_7d": 271, "targeting_type": "AUTO"},
        ]
        config = {
            "total_daily_budget": 150,
            "max_single_campaign_budget": 100,
            "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}},
        }
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tiers = {r["tier"] for r in rec["recommendations"]}
        assert 1 in tiers, "Should recommend lifting campaign ceiling"
        assert 2 in tiers, "Should recommend rebalancing Manual/Auto"
        assert rec["summary"]["manual_roas_7d"] == 7.38
        assert rec["summary"]["auto_roas_7d"] == 1.54
