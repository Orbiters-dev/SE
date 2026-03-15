const BACKTEST_LOG = {
 "grosmimi": [
  {
   "brand": "grosmimi",
   "period": {
    "start": "2026-01-13",
    "end": "2026-03-13",
    "days": 60
   },
   "waste_backtest": {
    "total_actual_spend": 166969.91,
    "total_simulated_save": 71048.74,
    "save_pct": 42.6,
    "negated_terms_count": 1422
   },
   "bid_backtest": {
    "total_actual_spend": 117174.23,
    "total_actual_sales": 516336.42,
    "actual_roas": 4.41,
    "total_sim_spend": 113865.13,
    "total_sim_sales": 543872.59,
    "sim_roas": 4.78,
    "roas_delta": 0.37,
    "underperformer_count": 17,
    "scalable_count": 14
   },
   "timeline": [
    {
     "month": "2026-01",
     "monthly_save": 6254.1,
     "cumulative": 6254.1
    },
    {
     "month": "2026-02",
     "monthly_save": 21919.1,
     "cumulative": 28173.2
    },
    {
     "month": "2026-03",
     "monthly_save": 11209.46,
     "cumulative": 39382.66
    }
   ],
   "top_waste_terms": [
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "baby straw cup",
     "actual_spend": 7096.49,
     "conversions": 659,
     "would_save": 6358.12,
     "negated_after": "2026-01-20",
     "windows": 48
    },
    {
     "campaign": "SP_flip top_manual",
     "search_term": "sippy cups for toddlers 1-3",
     "actual_spend": 6131.25,
     "conversions": 751,
     "would_save": 5623.09,
     "negated_after": "2026-01-20",
     "windows": 40
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "straw sippy cup",
     "actual_spend": 4734.12,
     "conversions": 340,
     "would_save": 4119.46,
     "negated_after": "2026-01-20",
     "windows": 43
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "straw cups for toddlers 1-3",
     "actual_spend": 6983.3,
     "conversions": 608,
     "would_save": 3339.03,
     "negated_after": "2026-02-17",
     "windows": 36
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "sippy cups for toddlers 1-3",
     "actual_spend": 3114.55,
     "conversions": 228,
     "would_save": 3106.54,
     "negated_after": "2026-01-13",
     "windows": 49
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "straw cup",
     "actual_spend": 2780.22,
     "conversions": 379,
     "would_save": 2644.62,
     "negated_after": "2026-01-13",
     "windows": 32
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "sippy cup for 6 month old",
     "actual_spend": 2324.71,
     "conversions": 103,
     "would_save": 2121.69,
     "negated_after": "2026-01-20",
     "windows": 39
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "stainless steel straw cup toddler",
     "actual_spend": 1973.53,
     "conversions": 77,
     "would_save": 1942.16,
     "negated_after": "2026-01-13",
     "windows": 30
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "sippy cup with straw",
     "actual_spend": 2985.9,
     "conversions": 146,
     "would_save": 1687.61,
     "negated_after": "2026-02-10",
     "windows": 32
    },
    {
     "campaign": "SP_ppsu_manual",
     "search_term": "baby straw cups 6-12 months",
     "actual_spend": 1354.51,
     "conversions": 73,
     "would_save": 1316.14,
     "negated_after": "2026-01-13",
     "windows": 19
    }
   ],
   "generated_at": "2026-03-14T23:45:54.391733"
  },
  {
   "brand": "grosmimi",
   "brand_display": "Grosmimi",
   "period": {
    "start": "2026-01-14",
    "end": "2026-03-14",
    "days": 60
   },
   "data_inputs": {
    "search_term_rows": 7120,
    "keyword_rows": 137,
    "unique_search_terms": 6746,
    "unique_keywords": 54,
    "unique_campaigns": 11,
    "data_source": "DataKeeper PG",
    "date_format": "7-day SUMMARY chunks"
   },
   "waste_backtest": {
    "total_actual_spend": 22401.66,
    "total_simulated_save": 4404.55,
    "save_pct": 19.7,
    "negated_terms_count": 51,
    "rule_threshold": 5.0,
    "rule_window_days": 14,
    "rule_description": "If cumulative zero-conv spend >= $5.0 over 14d windows ¡æ add negative. Savings start from NEXT window."
   },
   "top_waste_terms": [
    {
     "campaign": "263965495217853",
     "search_term": "baby straw cup",
     "actual_spend": 1204.74,
     "conversions": 86,
     "would_save": 948.03,
     "negated_after": "2026-03-07",
     "windows": 6
    },
    {
     "campaign": "289220267376704",
     "search_term": "sippy cups for toddlers 1-3",
     "actual_spend": 711.13,
     "conversions": 95,
     "would_save": 703.7,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "straw sippy cup",
     "actual_spend": 471.77,
     "conversions": 36,
     "would_save": 463.99,
     "negated_after": "2026-03-07",
     "windows": 6
    },
    {
     "campaign": "263965495217853",
     "search_term": "sippy cup with straw",
     "actual_spend": 449.73,
     "conversions": 21,
     "would_save": 444.45,
     "negated_after": "2026-03-07",
     "windows": 5
    },
    {
     "campaign": "263965495217853",
     "search_term": "sippy cups for toddlers 1-3",
     "actual_spend": 404.45,
     "conversions": 26,
     "would_save": 383.27,
     "negated_after": "2026-03-07",
     "windows": 7
    },
    {
     "campaign": "263965495217853",
     "search_term": "sippy cup for 6 month old",
     "actual_spend": 358.32,
     "conversions": 11,
     "would_save": 349.46,
     "negated_after": "2026-03-07",
     "windows": 4
    },
    {
     "campaign": "263965495217853",
     "search_term": "stainless steel straw cup toddler",
     "actual_spend": 261.83,
     "conversions": 10,
     "would_save": 255.35,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "baby sippy cup",
     "actual_spend": 236.34,
     "conversions": 14,
     "would_save": 231.06,
     "negated_after": "2026-03-07",
     "windows": 6
    },
    {
     "campaign": "263965495217853",
     "search_term": "sippy cup",
     "actual_spend": 120.09,
     "conversions": 10,
     "would_save": 114.42,
     "negated_after": "2026-03-07",
     "windows": 9
    },
    {
     "campaign": "340267150899607",
     "search_term": "sippy cups for toddlers 1-3",
     "actual_spend": 91.77,
     "conversions": 27,
     "would_save": 86.38,
     "negated_after": "2026-03-07",
     "windows": 4
    },
    {
     "campaign": "263965495217853",
     "search_term": "toddler sippy cups",
     "actual_spend": 64.38,
     "conversions": 2,
     "would_save": 48.0,
     "negated_after": "2026-03-07",
     "windows": 4
    },
    {
     "campaign": "263965495217853",
     "search_term": "316 stainless steel cup",
     "actual_spend": 53.49,
     "conversions": 0,
     "would_save": 41.92,
     "negated_after": "2026-03-07",
     "windows": 4
    },
    {
     "campaign": "263965495217853",
     "search_term": "transition sippy cup",
     "actual_spend": 58.64,
     "conversions": 2,
     "would_save": 33.77,
     "negated_after": "2026-03-07",
     "windows": 4
    },
    {
     "campaign": "263965495217853",
     "search_term": "spill proof straw cups for toddlers",
     "actual_spend": 53.86,
     "conversions": 6,
     "would_save": 26.89,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "ubmom straw cup",
     "actual_spend": 31.63,
     "conversions": 0,
     "would_save": 25.12,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "munchkin straw cup",
     "actual_spend": 31.93,
     "conversions": 1,
     "would_save": 22.49,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "straw cup for milk",
     "actual_spend": 37.6,
     "conversions": 0,
     "would_save": 22.1,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "nuk learner straw cup",
     "actual_spend": 24.17,
     "conversions": 1,
     "would_save": 19.17,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "glass sippy cups for toddlers 1-3",
     "actual_spend": 33.44,
     "conversions": 2,
     "would_save": 19.11,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "milk sippy cup for toddlers 1-3",
     "actual_spend": 27.98,
     "conversions": 1,
     "would_save": 18.72,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "baby first straw cup",
     "actual_spend": 29.55,
     "conversions": 0,
     "would_save": 17.63,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "kids straw cups",
     "actual_spend": 20.97,
     "conversions": 3,
     "would_save": 13.52,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "nuk sippy cups for toddlers 1-3",
     "actual_spend": 17.07,
     "conversions": 0,
     "would_save": 11.51,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "toddler cup with straw",
     "actual_spend": 20.26,
     "conversions": 0,
     "would_save": 9.94,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "sippy cup for 1+ year old",
     "actual_spend": 18.89,
     "conversions": 0,
     "would_save": 9.64,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "stainless steel baby straw cup",
     "actual_spend": 23.71,
     "conversions": 0,
     "would_save": 9.63,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "oxo tot straw cup",
     "actual_spend": 15.96,
     "conversions": 0,
     "would_save": 8.58,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "dr brown sippy cups",
     "actual_spend": 13.29,
     "conversions": 1,
     "would_save": 7.38,
     "negated_after": "2026-03-07",
     "windows": 2
    },
    {
     "campaign": "263965495217853",
     "search_term": "dr browns sippy cup",
     "actual_spend": 28.17,
     "conversions": 2,
     "would_save": 6.82,
     "negated_after": "2026-03-07",
     "windows": 3
    },
    {
     "campaign": "263965495217853",
     "search_term": "straw cup for baby",
     "actual_spend": 23.6,
     "conversions": 0,
     "would_save": 5.16,
     "negated_after": "2026-03-07",
     "windows": 2
    }
   ],
   "bid_backtest": {
    "total_actual_spend": 20102.48,
    "total_actual_sales": 81679.29,
    "actual_roas": 4.06,
    "total_sim_spend": 18658.02,
    "total_sim_sales": 85612.73,
    "sim_roas": 4.59,
    "roas_delta": 0.53,
    "underperformer_count": 17,
    "scalable_count": 8,
    "rule_reduce_threshold": 2.0,
    "rule_reduce_pct": 0.2,
    "rule_scale_threshold": 5.0,
    "rule_scale_pct": 0.15,
    "rule_description": "ROAS < 2.0x ¡æ bid -20% | ROAS > 5.0x ¡æ bid +15% | In-range: hold"
   },
   "bid_underperformers": [
    {
     "campaign": "263965495217853",
     "keyword": "straw sippy cup for baby",
     "match_type": "BROAD",
     "actual_roas": 1.89,
     "actual_spend": 4931.44,
     "actual_sales": 9320.44,
     "sim_spend": 3945.15,
     "sim_roas": 2.36,
     "estimated_save": 986.29,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "infant sippy cups",
     "match_type": "PHRASE",
     "actual_roas": 1.75,
     "actual_spend": 813.15,
     "actual_sales": 1424.7,
     "sim_spend": 650.52,
     "sim_roas": 2.19,
     "estimated_save": 162.63,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "sippy cups for baby",
     "match_type": "EXACT",
     "actual_roas": 1.61,
     "actual_spend": 632.75,
     "actual_sales": 1016.4,
     "sim_spend": 506.2,
     "sim_roas": 2.01,
     "estimated_save": 126.55,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "toddler sippy cups",
     "match_type": "EXACT",
     "actual_roas": 1.99,
     "actual_spend": 595.99,
     "actual_sales": 1185.0,
     "sim_spend": 476.79,
     "sim_roas": 2.49,
     "estimated_save": 119.2,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "sippy cups with straw for infant",
     "match_type": "BROAD",
     "actual_roas": 1.21,
     "actual_spend": 529.26,
     "actual_sales": 642.2,
     "sim_spend": 423.41,
     "sim_roas": 1.52,
     "estimated_save": 105.85,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "sippy cups for toddlers",
     "match_type": "EXACT",
     "actual_roas": 1.57,
     "actual_spend": 244.29,
     "actual_sales": 383.23,
     "sim_spend": 195.43,
     "sim_roas": 1.96,
     "estimated_save": 48.86,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "sippy cup with straw for infant",
     "match_type": "BROAD",
     "actual_roas": 0.25,
     "actual_spend": 101.5,
     "actual_sales": 24.9,
     "sim_spend": 81.2,
     "sim_roas": 0.31,
     "estimated_save": 20.3,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "first straw cup",
     "match_type": "BROAD",
     "actual_roas": 1.64,
     "actual_spend": 88.51,
     "actual_sales": 145.1,
     "sim_spend": 70.81,
     "sim_roas": 2.05,
     "estimated_save": 17.7,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "340267150899607",
     "keyword": "milk cup for toddlers 1-3",
     "match_type": "EXACT",
     "actual_roas": 1.95,
     "actual_spend": 77.2,
     "actual_sales": 150.8,
     "sim_spend": 61.76,
     "sim_roas": 2.44,
     "estimated_save": 15.44,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "baby sippy cups",
     "match_type": "EXACT",
     "actual_roas": 1.25,
     "actual_spend": 58.88,
     "actual_sales": 73.5,
     "sim_spend": 47.1,
     "sim_roas": 1.56,
     "estimated_save": 11.78,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "straw sippy cups for infant",
     "match_type": "BROAD",
     "actual_roas": 1.24,
     "actual_spend": 33.23,
     "actual_sales": 41.3,
     "sim_spend": 26.58,
     "sim_roas": 1.55,
     "estimated_save": 6.65,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "sippy cup with straw for baby",
     "match_type": "BROAD",
     "actual_roas": 0.0,
     "actual_spend": 31.17,
     "actual_sales": 0.0,
     "sim_spend": 24.94,
     "sim_roas": 0.0,
     "estimated_save": 6.23,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "first sippy cup",
     "match_type": "EXACT",
     "actual_roas": 1.23,
     "actual_spend": 18.55,
     "actual_sales": 22.8,
     "sim_spend": 14.84,
     "sim_roas": 1.54,
     "estimated_save": 3.71,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "baby straw bottle",
     "match_type": "PHRASE",
     "actual_roas": 0.0,
     "actual_spend": 3.91,
     "actual_sales": 0.0,
     "sim_spend": 3.13,
     "sim_roas": 0.0,
     "estimated_save": 0.78,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "412813716858145",
     "keyword": "baby bottle with straw",
     "match_type": "EXACT",
     "actual_roas": 0.0,
     "actual_spend": 3.17,
     "actual_sales": 0.0,
     "sim_spend": 2.54,
     "sim_roas": 0.0,
     "estimated_save": 0.63,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "straw sippy cups for baby",
     "match_type": "BROAD",
     "actual_roas": 0.0,
     "actual_spend": 2.72,
     "actual_sales": 0.0,
     "sim_spend": 2.18,
     "sim_roas": 0.0,
     "estimated_save": 0.54,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "infant straw cup",
     "match_type": "BROAD",
     "actual_roas": 0.0,
     "actual_spend": 2.12,
     "actual_sales": 0.0,
     "sim_spend": 1.7,
     "sim_roas": 0.0,
     "estimated_save": 0.42,
     "action": "reduce_bid -20%"
    }
   ],
   "bid_scalable": [
    {
     "campaign": "340267150899607",
     "keyword": "grosmimi",
     "match_type": "EXACT",
     "actual_roas": 21.01,
     "actual_spend": 1139.3,
     "actual_sales": 23939.39,
     "sim_spend": 1310.2,
     "sim_sales": 27530.3,
     "extra_profit": 3420.01,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "380111568693446",
     "keyword": "grosmimi replacement",
     "match_type": "PHRASE",
     "actual_roas": 25.08,
     "actual_spend": 60.75,
     "actual_sales": 1523.34,
     "sim_spend": 69.86,
     "sim_sales": 1751.84,
     "extra_profit": 219.39,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "412813716858145",
     "keyword": "baby water bottle",
     "match_type": "PHRASE",
     "actual_roas": 15.53,
     "actual_spend": 27.28,
     "actual_sales": 423.6,
     "sim_spend": 31.37,
     "sim_sales": 487.14,
     "extra_profit": 59.45,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "toddler water bottle",
     "match_type": "EXACT",
     "actual_roas": 19.55,
     "actual_spend": 4.88,
     "actual_sales": 95.4,
     "sim_spend": 5.61,
     "sim_sales": 109.71,
     "extra_profit": 13.58,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "412813716858145",
     "keyword": "sippy cups",
     "match_type": "EXACT",
     "actual_roas": 7.93,
     "actual_spend": 12.14,
     "actual_sales": 96.3,
     "sim_spend": 13.96,
     "sim_sales": 110.74,
     "extra_profit": 12.62,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "straw cup for milk",
     "match_type": "BROAD",
     "actual_roas": 33.8,
     "actual_spend": 2.0,
     "actual_sales": 67.6,
     "sim_spend": 2.3,
     "sim_sales": 77.74,
     "extra_profit": 9.84,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "340267150899607",
     "keyword": "toddler straw cup",
     "match_type": "PHRASE",
     "actual_roas": 5.36,
     "actual_spend": 10.17,
     "actual_sales": 54.5,
     "sim_spend": 11.7,
     "sim_sales": 62.67,
     "extra_profit": 6.65,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "263965495217853",
     "keyword": "first cup for baby",
     "match_type": "BROAD",
     "actual_roas": 5.47,
     "actual_spend": 4.17,
     "actual_sales": 22.8,
     "sim_spend": 4.8,
     "sim_sales": 26.22,
     "extra_profit": 2.79,
     "action": "scale_bid +15%"
    }
   ],
   "timeline": [],
   "execution_history": [],
   "config_used": {
    "brand_key": "grosmimi",
    "seller": "GROSMIMI USA",
    "total_daily_budget": 3000.0,
    "manual_target_acos": 20.0,
    "auto_target_acos": 30.0
   },
   "generated_at": "2026-03-15 00:31 PST"
  }
 ],
 "naeiae": [
  {
   "brand": "naeiae",
   "brand_display": "Naeiae",
   "period": {
    "start": "2026-02-13",
    "end": "2026-03-14",
    "days": 30
   },
   "data_inputs": {
    "search_term_rows": 353,
    "keyword_rows": 33,
    "unique_search_terms": 349,
    "unique_keywords": 15,
    "unique_campaigns": 2,
    "data_source": "DataKeeper PG",
    "date_format": "7-day SUMMARY chunks"
   },
   "waste_backtest": {
    "total_actual_spend": 561.62,
    "total_simulated_save": 0.98,
    "save_pct": 0.2,
    "negated_terms_count": 1,
    "rule_threshold": 5.0,
    "rule_window_days": 14,
    "rule_description": "If cumulative zero-conv spend >= $5.0 over 14d windows ¡æ add negative. Savings start from NEXT window."
   },
   "top_waste_terms": [
    {
     "campaign": "444108265805305",
     "search_term": "baby snacks",
     "actual_spend": 20.12,
     "conversions": 0,
     "would_save": 0.98,
     "negated_after": "2026-03-07",
     "windows": 2
    }
   ],
   "bid_backtest": {
    "total_actual_spend": 74.97,
    "total_actual_sales": 98.4,
    "actual_roas": 1.31,
    "total_sim_spend": 66.16,
    "total_sim_sales": 105.78,
    "sim_roas": 1.6,
    "roas_delta": 0.29,
    "underperformer_count": 3,
    "scalable_count": 1,
    "rule_reduce_threshold": 2.0,
    "rule_reduce_pct": 0.2,
    "rule_scale_threshold": 5.0,
    "rule_scale_pct": 0.15,
    "rule_description": "ROAS < 2.0x ¡æ bid -20% | ROAS > 5.0x ¡æ bid +15% | In-range: hold"
   },
   "bid_underperformers": [
    {
     "campaign": "444108265805305",
     "keyword": "baby snack",
     "match_type": "EXACT",
     "actual_roas": 0.0,
     "actual_spend": 32.11,
     "actual_sales": 0.0,
     "sim_spend": 25.69,
     "sim_roas": 0.0,
     "estimated_save": 6.42,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "444108265805305",
     "keyword": "toddler snack",
     "match_type": "EXACT",
     "actual_roas": 0.0,
     "actual_spend": 13.71,
     "actual_sales": 0.0,
     "sim_spend": 10.97,
     "sim_roas": 0.0,
     "estimated_save": 2.74,
     "action": "reduce_bid -20%"
    },
    {
     "campaign": "444108265805305",
     "keyword": "rice snack",
     "match_type": "EXACT",
     "actual_roas": 0.0,
     "actual_spend": 2.93,
     "actual_sales": 0.0,
     "sim_spend": 2.34,
     "sim_roas": 0.0,
     "estimated_save": 0.59,
     "action": "reduce_bid -20%"
    }
   ],
   "bid_scalable": [
    {
     "campaign": "444108265805305",
     "keyword": "baby puff snack",
     "match_type": "EXACT",
     "actual_roas": 7.82,
     "actual_spend": 6.29,
     "actual_sales": 49.2,
     "sim_spend": 7.23,
     "sim_sales": 56.58,
     "extra_profit": 6.44,
     "action": "scale_bid +15%"
    }
   ],
   "timeline": [],
   "execution_history": [
    {
     "type": "baseline",
     "date": "2026-03-08",
     "before_roas_7d": 2.44,
     "before_acos_7d": 41.0,
     "negatives_added": 5,
     "bid_reductions": 4,
     "keywords_harvested": 6,
     "wasted_spend_blocked": 72.91
    },
    {
     "date": "2026-03-08",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "pop rice snack",
     "spend_7d": 14.68,
     "sales_7d": 147.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 9.9% < target 25.0%, 6 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "¶±»½",
     "spend_7d": 14.77,
     "sales_7d": 123.0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 12.0% < target 25.0%, 5 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "naeiae pop rice snack",
     "spend_7d": 10.23,
     "sales_7d": 98.4,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 10.4% < target 25.0%, 4 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "baby teething snacks",
     "spend_7d": 14.13,
     "sales_7d": 73.8,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 19.1% < target 25.0%, 3 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "pop rice snack baby",
     "spend_7d": 14.65,
     "sales_7d": 73.8,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 19.9% < target 25.0%, 3 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "negate_high_acos",
     "campaign": "(auto)",
     "keyword": "puffed rice",
     "spend_7d": 32.17,
     "sales_7d": 24.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "ACOS 130.8% > 50.0% threshold",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "negate_zero_sales",
     "campaign": "(auto)",
     "keyword": "baby snacks",
     "spend_7d": 27.76,
     "sales_7d": 0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "$27.76 spent, 28 clicks, 0 sales (>3.0x target CPA)",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "negate_high_acos",
     "campaign": "(auto)",
     "keyword": "toddler snacks",
     "spend_7d": 25.22,
     "sales_7d": 24.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "ACOS 102.5% > 50.0% threshold",
     "status": "OK"
    },
    {
     "date": "2026-03-08",
     "action": "negate_zero_sales",
     "campaign": "(auto)",
     "keyword": "yugwa korean rice puff snack",
     "spend_7d": 15.18,
     "sales_7d": 0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "$15.18 spent, 16 clicks, 0 sales (>3.0x target CPA)",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "pop rice snack",
     "spend_7d": 14.68,
     "sales_7d": 147.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 9.9% < target 25.0%, 6 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "b0bmh153y7",
     "spend_7d": 12.66,
     "sales_7d": 123.0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 10.3% < target 25.0%, 5 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "¶±»½",
     "spend_7d": 14.77,
     "sales_7d": 123.0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 12.0% < target 25.0%, 5 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "naeiae pop rice snack",
     "spend_7d": 10.23,
     "sales_7d": 98.4,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 10.4% < target 25.0%, 4 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "b08tqn3h7t",
     "spend_7d": 5.9,
     "sales_7d": 73.8,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 8.0% < target 25.0%, 3 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "baby teething snacks",
     "spend_7d": 14.13,
     "sales_7d": 73.8,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 19.1% < target 25.0%, 3 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "harvest",
     "campaign": "(auto)",
     "keyword": "pop rice snack baby",
     "spend_7d": 14.65,
     "sales_7d": 73.8,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "Profitable ST: ACOS 19.9% < target 25.0%, 3 sales",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "negate_high_acos",
     "campaign": "(auto)",
     "keyword": "puffed rice",
     "spend_7d": 32.17,
     "sales_7d": 24.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "ACOS 130.8% > 50.0% threshold",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "negate_zero_sales",
     "campaign": "(auto)",
     "keyword": "baby snacks",
     "spend_7d": 27.76,
     "sales_7d": 0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "$27.76 spent, 28 clicks, 0 sales (>3.0x target CPA)",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "negate_high_acos",
     "campaign": "(auto)",
     "keyword": "toddler snacks",
     "spend_7d": 25.22,
     "sales_7d": 24.6,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "ACOS 102.5% > 50.0% threshold",
     "status": "OK"
    },
    {
     "date": "2026-03-09",
     "action": "negate_zero_sales",
     "campaign": "(auto)",
     "keyword": "yugwa korean rice puff snack",
     "spend_7d": 15.18,
     "sales_7d": 0,
     "roas_7d": null,
     "bid_change": null,
     "new_budget": null,
     "reason": "$15.18 spent, 16 clicks, 0 sales (>3.0x target CPA)",
     "status": "OK"
    }
   ],
   "config_used": {
    "brand_key": "naeiae",
    "seller": "Fleeters Inc",
    "total_daily_budget": 150.0,
    "manual_target_acos": 25.0,
    "auto_target_acos": 35.0
   },
   "generated_at": "2026-03-15 00:31 PST"
  }
 ],
 "chaenmom": [
  {
   "brand": "chaenmom",
   "brand_display": "CHA&MOM",
   "period": {
    "start": "2026-02-13",
    "end": "2026-03-14",
    "days": 30
   },
   "data_inputs": {
    "search_term_rows": 32,
    "keyword_rows": 112,
    "unique_search_terms": 30,
    "unique_keywords": 30,
    "unique_campaigns": 5,
    "data_source": "DataKeeper PG",
    "date_format": "7-day SUMMARY chunks"
   },
   "waste_backtest": {
    "total_actual_spend": 52.19,
    "total_simulated_save": 0.0,
    "save_pct": 0.0,
    "negated_terms_count": 0,
    "rule_threshold": 5.0,
    "rule_window_days": 14,
    "rule_description": "If cumulative zero-conv spend >= $5.0 over 14d windows ¡æ add negative. Savings start from NEXT window."
   },
   "top_waste_terms": [],
   "bid_backtest": {
    "total_actual_spend": 53.39,
    "total_actual_sales": 281.4,
    "actual_roas": 5.27,
    "total_sim_spend": 60.46,
    "total_sim_sales": 323.61,
    "sim_roas": 5.35,
    "roas_delta": 0.08,
    "underperformer_count": 1,
    "scalable_count": 2,
    "rule_reduce_threshold": 2.0,
    "rule_reduce_pct": 0.2,
    "rule_scale_threshold": 5.0,
    "rule_scale_pct": 0.15,
    "rule_description": "ROAS < 2.0x ¡æ bid -20% | ROAS > 5.0x ¡æ bid +15% | In-range: hold"
   },
   "bid_underperformers": [
    {
     "campaign": "306557038962339",
     "keyword": "korean baby lotion",
     "match_type": "EXACT",
     "actual_roas": 0.0,
     "actual_spend": 2.67,
     "actual_sales": 0.0,
     "sim_spend": 2.14,
     "sim_roas": 0.0,
     "estimated_save": 0.53,
     "action": "reduce_bid -20%"
    }
   ],
   "bid_scalable": [
    {
     "campaign": "306557038962339",
     "keyword": "baby lotion",
     "match_type": "BROAD",
     "actual_roas": 5.1,
     "actual_spend": 43.92,
     "actual_sales": 224.0,
     "sim_spend": 50.51,
     "sim_sales": 257.6,
     "extra_profit": 27.01,
     "action": "scale_bid +15%"
    },
    {
     "campaign": "306557038962339",
     "keyword": "baby moisture lotion",
     "match_type": "BROAD",
     "actual_roas": 8.44,
     "actual_spend": 6.8,
     "actual_sales": 57.4,
     "sim_spend": 7.82,
     "sim_sales": 66.01,
     "extra_profit": 7.59,
     "action": "scale_bid +15%"
    }
   ],
   "timeline": [],
   "execution_history": [
    {
     "date": "2026-03-14",
     "action": "pause",
     "campaign": "CHA&MOM_Keyword_Lotion_SP_Manual",
     "keyword": "",
     "spend_7d": 6.7,
     "sales_7d": 0.0,
     "roas_7d": 0.0,
     "bid_change": null,
     "new_budget": null,
     "reason": "[MANUAL] 7d ROAS 0.0x (ACOS None%) | 30d ROAS 0.0x | target ACOS 30.0% | ",
     "status": "OK"
    },
    {
     "date": "2026-03-14",
     "action": "reduce_bid",
     "campaign": "CHA&MOM _Competitor Targeting_SP_Manual",
     "keyword": "",
     "spend_7d": 39.15,
     "sales_7d": 53.0,
     "roas_7d": 1.35,
     "bid_change": -30,
     "new_budget": null,
     "reason": "[MANUAL] 7d ROAS 1.35x (ACOS 73.9%) | 30d ROAS 1.13x | target ACOS 30.0% | 7d vs",
     "status": "OK"
    },
    {
     "date": "2026-03-14",
     "action": "increase_budget",
     "campaign": "CHA&MOM_Cream_SP_Auto",
     "keyword": "",
     "spend_7d": 3.75,
     "sales_7d": 115.8,
     "roas_7d": 30.88,
     "bid_change": 10,
     "new_budget": 60.0,
     "reason": "[AUTO] 7d ROAS 30.88x (ACOS 3.2%) | 30d ROAS 15.15x | target ACOS 40.0% | 7d vs ",
     "status": "OK"
    },
    {
     "date": "2026-03-14",
     "action": "increase_budget",
     "campaign": "CHA&MOM_Wash_SP_Auto",
     "keyword": "",
     "spend_7d": 7.77,
     "sales_7d": 55.2,
     "roas_7d": 7.1,
     "bid_change": 10,
     "new_budget": 60.0,
     "reason": "[AUTO] 7d ROAS 7.1x (ACOS 14.1%) | 30d ROAS 7.87x | target ACOS 40.0% | 7d vs 30",
     "status": "OK"
    },
    {
     "date": "2026-03-15",
     "action": "reduce_bid",
     "campaign": "CHA&MOM _Competitor Targeting_SP_Manual",
     "keyword": "",
     "spend_7d": 37.15,
     "sales_7d": 53.0,
     "roas_7d": 1.43,
     "bid_change": -30,
     "new_budget": null,
     "reason": "[MANUAL] 7d ROAS 1.43x (ACOS 70.1%) | 30d ROAS 1.43x | target ACOS 30.0% | 7d vs",
     "status": "OK"
    },
    {
     "date": "2026-03-15",
     "action": "increase_budget",
     "campaign": "CHA&MOM_Cream_SP_Auto",
     "keyword": "",
     "spend_7d": 3.75,
     "sales_7d": 115.8,
     "roas_7d": 30.88,
     "bid_change": 10,
     "new_budget": 75.0,
     "reason": "[AUTO] 7d ROAS 30.88x (ACOS 3.2%) | 30d ROAS 30.88x | target ACOS 40.0% | 7d vs ",
     "status": "OK"
    },
    {
     "date": "2026-03-15",
     "action": "increase_budget",
     "campaign": "CHA&MOM_Wash_SP_Auto",
     "keyword": "",
     "spend_7d": 6.87,
     "sales_7d": 28.7,
     "roas_7d": 4.18,
     "bid_change": 15,
     "new_budget": 75.0,
     "reason": "[AUTO] 7d ROAS 4.18x (ACOS 23.9%) | 30d ROAS 4.18x | target ACOS 40.0% | 7d vs 3",
     "status": "OK"
    }
   ],
   "config_used": {
    "brand_key": "chaenmom",
    "seller": "Orbitool",
    "total_daily_budget": 150.0,
    "manual_target_acos": 30.0,
    "auto_target_acos": 40.0
   },
   "generated_at": "2026-03-15 00:31 PST"
  }
 ]
};
