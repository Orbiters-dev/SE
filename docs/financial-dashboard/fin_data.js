const FIN_DATA = {
 "generated_pst": "2026-03-21 14:13 PST",
 "through_date": "2026-03-20",
 "months": [
  "2025-06",
  "2025-07",
  "2025-08",
  "2025-09",
  "2025-10",
  "2025-11",
  "2025-12",
  "2026-01",
  "2026-02",
  "2026-03"
 ],
 "data_sources": [
  {
   "name": "shopify_orders_daily",
   "label": "Shopify Orders",
   "rows": 2468,
   "min_date": "2025-05-16",
   "max_date": "2026-03-21",
   "refresh": "2x daily"
  },
  {
   "name": "amazon_sales_daily",
   "label": "Amazon Sales (SP-API)",
   "rows": 867,
   "min_date": "2025-05-16",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  },
  {
   "name": "amazon_ads_daily",
   "label": "Amazon Ads",
   "rows": 2011,
   "min_date": "2025-12-10",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  },
  {
   "name": "meta_ads_daily",
   "label": "Meta Ads",
   "rows": 6368,
   "min_date": "2025-05-16",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  },
  {
   "name": "google_ads_daily",
   "label": "Google Ads",
   "rows": 741,
   "min_date": "2025-05-16",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  },
  {
   "name": "ga4_daily",
   "label": "GA4 Analytics",
   "rows": 3313,
   "min_date": "2025-05-16",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  },
  {
   "name": "amazon_ads_search_terms",
   "label": "Amazon Search Terms",
   "rows": 10000,
   "min_date": "2026-02-28~2026-03-06",
   "max_date": "2026-03-07~2026-03-13",
   "refresh": "1x daily"
  },
  {
   "name": "gsc_daily",
   "label": "Google Search Console",
   "rows": 5510,
   "min_date": "2026-02-19",
   "max_date": "2026-03-20",
   "refresh": "2x daily"
  }
 ],
 "partial_month": {
  "month": "2026-03",
  "days_elapsed": 20,
  "days_in_month": 31,
  "is_partial": true,
  "multiplier": 1.55
 },
 "summary": {
  "7d": {
   "total_revenue": 168654,
   "shopify_revenue": 17932,
   "amazon_revenue": 150721,
   "total_orders": 6881,
   "total_ad_spend": 29932,
   "ad_attributed_sales": 98300,
   "organic_revenue": 70354,
   "gross_margin": 106673,
   "gm_pct": 63.2,
   "contribution_margin": 76063,
   "cm_pct": 45.1,
   "mer": 5.63,
   "roas": 3.28,
   "discount_rate": 3.6
  },
  "30d": {
   "total_revenue": 678458,
   "shopify_revenue": 80464,
   "amazon_revenue": 597994,
   "total_orders": 27285,
   "total_ad_spend": 129573,
   "ad_attributed_sales": 449660,
   "organic_revenue": 228798,
   "gross_margin": 431306,
   "gm_pct": 63.6,
   "contribution_margin": 296520,
   "cm_pct": 43.7,
   "mer": 5.24,
   "roas": 3.47,
   "discount_rate": 6.1
  },
  "mtd": {
   "total_revenue": 466946,
   "shopify_revenue": 53828,
   "amazon_revenue": 413117,
   "total_orders": 18798,
   "total_ad_spend": 87270,
   "ad_attributed_sales": 304843,
   "organic_revenue": 162103,
   "gross_margin": 295854,
   "gm_pct": 63.4,
   "contribution_margin": 204737,
   "cm_pct": 43.8,
   "mer": 5.35,
   "roas": 3.49,
   "discount_rate": 6.7
  }
 },
 "brand_revenue": {
  "Grosmimi": {
   "monthly": [
    540650,
    707647,
    619650,
    542939,
    614006,
    643945,
    557654,
    624480,
    554741,
    444936
   ],
   "monthly_proj": [
    540650,
    707647,
    619650,
    542939,
    614006,
    643945,
    557654,
    624480,
    554741,
    689651
   ],
   "color": "#8b5cf6"
  },
  "Naeiae": {
   "monthly": [
    17503,
    18264,
    12996,
    10933,
    5792,
    28572,
    29155,
    12259,
    12271,
    11672
   ],
   "monthly_proj": [
    17503,
    18264,
    12996,
    10933,
    5792,
    28572,
    29155,
    12259,
    12271,
    18092
   ],
   "color": "#eab308"
  },
  "CHA&MOM": {
   "monthly": [
    1798,
    4619,
    5195,
    8511,
    7663,
    11824,
    7647,
    8431,
    6797,
    3256
   ],
   "monthly_proj": [
    1798,
    4619,
    5195,
    8511,
    7663,
    11824,
    7647,
    8431,
    6797,
    5047
   ],
   "color": "#0ea5e9"
  },
  "Alpremio": {
   "monthly": [
    1762,
    2804,
    2752,
    4319,
    6101,
    6171,
    5146,
    6391,
    7786,
    5008
   ],
   "monthly_proj": [
    1762,
    2804,
    2752,
    4319,
    6101,
    6171,
    5146,
    6391,
    7786,
    7762
   ],
   "color": "#f97316"
  },
  "Other": {
   "monthly": [
    5863,
    12433,
    12502,
    6160,
    4758,
    4779,
    1165,
    2373,
    11759,
    2074
   ],
   "monthly_proj": [
    5863,
    12433,
    12502,
    6160,
    4758,
    4779,
    1165,
    2373,
    11759,
    3215
   ],
   "color": "#94a3b8"
  }
 },
 "channel_revenue": {
  "Onzenna D2C": {
   "monthly": [
    81841,
    103139,
    115369,
    118461,
    99750,
    100215,
    72542,
    95418,
    72668,
    38732
   ],
   "monthly_proj": [
    81841,
    103139,
    115369,
    118461,
    99750,
    100215,
    72542,
    95418,
    72668,
    60035
   ],
   "color": "#6366f1"
  },
  "Amazon MP": {
   "monthly": [
    463835,
    638488,
    531452,
    448886,
    529292,
    586032,
    511846,
    533042,
    498734,
    413117
   ],
   "monthly_proj": [
    463835,
    638488,
    531452,
    448886,
    529292,
    586032,
    511846,
    533042,
    498734,
    640331
   ],
   "color": "#f59e0b"
  },
  "TikTok Shop": {
   "monthly": [
    0,
    0,
    0,
    0,
    23,
    94,
    137,
    0,
    150,
    126
   ],
   "monthly_proj": [
    0,
    0,
    0,
    0,
    23,
    94,
    137,
    0,
    150,
    195
   ],
   "color": "#ec4899"
  },
  "Target+": {
   "monthly": [
    91,
    302,
    912,
    270,
    343,
    292,
    9566,
    9495,
    11945,
    11961
   ],
   "monthly_proj": [
    91,
    302,
    912,
    270,
    343,
    292,
    9566,
    9495,
    11945,
    18540
   ],
   "color": "#ef4444"
  },
  "B2B": {
   "monthly": [
    21809,
    3839,
    5362,
    5245,
    8911,
    8658,
    6675,
    15979,
    9857,
    3009
   ],
   "monthly_proj": [
    21809,
    3839,
    5362,
    5245,
    8911,
    8658,
    6675,
    15979,
    9857,
    4664
   ],
   "color": "#10b981"
  }
 },
 "ad_performance": {
  "Amazon Ads": {
   "spend": [
    0,
    0,
    0,
    0,
    0,
    0,
    34382,
    79637,
    80371,
    64970
   ],
   "spend_proj": [
    0,
    0,
    0,
    0,
    0,
    0,
    34382,
    79637,
    80371,
    100704
   ],
   "sales": [
    0,
    0,
    0,
    0,
    0,
    0,
    224013,
    387330,
    360432,
    282340
   ],
   "sales_proj": [
    0,
    0,
    0,
    0,
    0,
    0,
    224013,
    387330,
    360432,
    437627
   ],
   "impressions": [
    0,
    0,
    0,
    0,
    0,
    0,
    7547539,
    15751413,
    17256495,
    12163976
   ],
   "clicks": [
    0,
    0,
    0,
    0,
    0,
    0,
    41325,
    88386,
    84643,
    67073
   ],
   "color": "#f59e0b"
  },
  "Meta CVR": {
   "spend": [
    4565,
    6207,
    9258,
    11827,
    13227,
    14236,
    15207,
    15871,
    17112,
    7854
   ],
   "spend_proj": [
    4565,
    6207,
    9258,
    11827,
    13227,
    14236,
    15207,
    15871,
    17112,
    12174
   ],
   "sales": [
    18541,
    23396,
    38960,
    41768,
    32225,
    35888,
    29513,
    37226,
    32394,
    11078
   ],
   "sales_proj": [
    18541,
    23396,
    38960,
    41768,
    32225,
    35888,
    29513,
    37226,
    32394,
    17171
   ],
   "impressions": [
    220256,
    361563,
    520941,
    687766,
    881813,
    648350,
    568714,
    807660,
    990018,
    521281
   ],
   "clicks": [
    5411,
    8837,
    12477,
    19820,
    31234,
    23842,
    14389,
    24287,
    39496,
    20642
   ],
   "color": "#3b82f6"
  },
  "Meta Traffic": {
   "spend": [
    2250,
    2321,
    2273,
    2934,
    4728,
    11380,
    9086,
    11530,
    9647,
    7013
   ],
   "spend_proj": [
    2250,
    2321,
    2273,
    2934,
    4728,
    11380,
    9086,
    11530,
    9647,
    10870
   ],
   "sales": [
    167,
    105,
    193,
    248,
    71,
    84,
    0,
    0,
    59,
    0
   ],
   "sales_proj": [
    167,
    105,
    193,
    248,
    71,
    84,
    0,
    0,
    59,
    0
   ],
   "impressions": [
    261562,
    262267,
    294771,
    499127,
    725777,
    1386356,
    1056655,
    1757662,
    1209196,
    821398
   ],
   "clicks": [
    24443,
    26565,
    24672,
    25285,
    39523,
    79960,
    78127,
    129046,
    102683,
    71658
   ],
   "color": "#93c5fd"
  },
  "Google Ads": {
   "spend": [
    9635,
    13051,
    13380,
    12939,
    13764,
    13984,
    12712,
    11117,
    12652,
    7434
   ],
   "spend_proj": [
    9635,
    13051,
    13380,
    12939,
    13764,
    13984,
    12712,
    11117,
    12652,
    11523
   ],
   "sales": [
    24251,
    39573,
    60199,
    77665,
    52756,
    54925,
    28010,
    21556,
    19707,
    11426
   ],
   "sales_proj": [
    24251,
    39573,
    60199,
    77665,
    52756,
    54925,
    28010,
    21556,
    19707,
    17710
   ],
   "impressions": [
    906416,
    1045420,
    1310621,
    971704,
    871130,
    822193,
    722451,
    782256,
    794105,
    663267
   ],
   "clicks": [
    8009,
    9648,
    10902,
    9051,
    8376,
    7955,
    6644,
    8476,
    9426,
    6619
   ],
   "color": "#10b981"
  }
 },
 "ads_landing": {
  "Onzenna": {
   "spend": [
    14201,
    19258,
    22638,
    24766,
    26991,
    28220,
    27919,
    26988,
    29764,
    15288
   ],
   "spend_proj": [
    14201,
    19258,
    22638,
    24766,
    26991,
    28220,
    27919,
    26988,
    29764,
    23696
   ],
   "revenue": [
    81841,
    103139,
    115369,
    118461,
    99750,
    100215,
    72542,
    95418,
    72668,
    38732
   ],
   "revenue_proj": [
    81841,
    103139,
    115369,
    118461,
    99750,
    100215,
    72542,
    95418,
    72668,
    60035
   ],
   "platforms": "Google Ads + Meta CVR",
   "color": "#6366f1"
  },
  "Amazon": {
   "spend": [
    2250,
    2321,
    2273,
    2934,
    4728,
    11380,
    43467,
    91168,
    90019,
    71983
   ],
   "spend_proj": [
    2250,
    2321,
    2273,
    2934,
    4728,
    11380,
    43467,
    91168,
    90019,
    111574
   ],
   "revenue": [
    463835,
    638488,
    531452,
    448886,
    529292,
    586032,
    511846,
    533042,
    498734,
    413117
   ],
   "revenue_proj": [
    463835,
    638488,
    531452,
    448886,
    529292,
    586032,
    511846,
    533042,
    498734,
    640331
   ],
   "platforms": "Amazon Ads + Meta Traffic",
   "color": "#f59e0b"
  }
 },
 "ad_start_idx": 7,
 "brand_performance": {
  "Grosmimi": {
   "total_sales": [
    624480,
    554741,
    444936
   ],
   "total_sales_proj": [
    624480,
    554741,
    689651
   ],
   "ad_spend": [
    92352,
    92614,
    73192
   ],
   "ad_spend_proj": [
    92352,
    92614,
    113448
   ],
   "ad_sales": [
    406758,
    375257,
    292382
   ],
   "ad_sales_proj": [
    406758,
    375257,
    453192
   ],
   "organic": [
    217722,
    179484,
    152554
   ],
   "organic_proj": [
    217722,
    179484,
    236459
   ],
   "color": "#8b5cf6"
  },
  "Naeiae": {
   "total_sales": [
    12259,
    12271,
    11672
   ],
   "total_sales_proj": [
    12259,
    12271,
    18092
   ],
   "ad_spend": [
    2744,
    2276,
    1606
   ],
   "ad_spend_proj": [
    2744,
    2276,
    2489
   ],
   "ad_sales": [
    5929,
    6347,
    5264
   ],
   "ad_sales_proj": [
    5929,
    6347,
    8159
   ],
   "organic": [
    6330,
    5924,
    6408
   ],
   "organic_proj": [
    6330,
    5924,
    9932
   ],
   "color": "#eab308"
  },
  "CHA&MOM": {
   "total_sales": [
    8431,
    6797,
    3256
   ],
   "total_sales_proj": [
    8431,
    6797,
    5047
   ],
   "ad_spend": [
    1636,
    2200,
    1824
   ],
   "ad_spend_proj": [
    1636,
    2200,
    2827
   ],
   "ad_sales": [
    4508,
    2868,
    858
   ],
   "ad_sales_proj": [
    4508,
    2868,
    1330
   ],
   "organic": [
    3923,
    3929,
    2398
   ],
   "organic_proj": [
    3923,
    3929,
    3717
   ],
   "color": "#0ea5e9"
  },
  "Alpremio": {
   "total_sales": [
    6391,
    7786,
    5008
   ],
   "total_sales_proj": [
    6391,
    7786,
    7762
   ],
   "ad_spend": [
    619,
    2692,
    1492
   ],
   "ad_spend_proj": [
    619,
    2692,
    2313
   ],
   "ad_sales": [
    500,
    2271,
    1318
   ],
   "ad_sales_proj": [
    500,
    2271,
    2043
   ],
   "organic": [
    5891,
    5515,
    3690
   ],
   "organic_proj": [
    5891,
    5515,
    5720
   ],
   "color": "#f97316"
  },
  "Other": {
   "total_sales": [
    2373,
    11759,
    2074
   ],
   "total_sales_proj": [
    2373,
    11759,
    3215
   ],
   "ad_spend": [
    20805,
    20001,
    9157
   ],
   "ad_spend_proj": [
    20805,
    20001,
    14193
   ],
   "ad_sales": [
    28417,
    25849,
    5021
   ],
   "ad_sales_proj": [
    28417,
    25849,
    7783
   ],
   "organic": [
    0,
    0,
    0
   ],
   "organic_proj": [
    0,
    0,
    0
   ],
   "color": "#94a3b8"
  }
 },
 "paid_organic": {
  "paid": [
   42958,
   63075,
   99352,
   119681,
   85053,
   90896,
   281536,
   446112,
   412592,
   304843
  ],
  "paid_proj": [
   42958,
   63075,
   99352,
   119681,
   85053,
   90896,
   281536,
   446112,
   412592,
   472507
  ],
  "organic": [
   530481,
   695126,
   566245,
   459340,
   558023,
   609173,
   320395,
   210196,
   192521,
   164176
  ],
  "organic_proj": [
   530481,
   695126,
   566245,
   459340,
   558023,
   609173,
   320395,
   210196,
   192521,
   254473
  ]
 },
 "waterfall": {
  "revenue": [
   573439,
   758201,
   665597,
   579021,
   643076,
   700069,
   601931,
   656308,
   605113,
   469019
  ],
  "revenue_proj": [
   573439,
   758201,
   665597,
   579021,
   643076,
   700069,
   601931,
   656308,
   605113,
   726979
  ],
  "cogs": [
   237213,
   319599,
   250562,
   216986,
   250072,
   280762,
   227237,
   243697,
   211802,
   171092
  ],
  "cogs_proj": [
   237213,
   319599,
   250562,
   216986,
   250072,
   280762,
   227237,
   243697,
   211802,
   265193
  ],
  "gross_margin": [
   336226,
   438602,
   415035,
   362034,
   393004,
   419308,
   374694,
   412612,
   393311,
   297928
  ],
  "gross_margin_proj": [
   336226,
   438602,
   415035,
   362034,
   393004,
   419308,
   374694,
   412612,
   393311,
   461788
  ],
  "ad_spend": [
   16451,
   21579,
   24911,
   27700,
   31719,
   39600,
   71387,
   118156,
   119783,
   87270
  ],
  "ad_spend_proj": [
   16451,
   21579,
   24911,
   27700,
   31719,
   39600,
   71387,
   118156,
   119783,
   135268
  ],
  "discounts": [
   22945,
   9984,
   11560,
   7605,
   3671,
   19673,
   9079,
   16081,
   6326,
   3877
  ],
  "discounts_proj": [
   22945,
   9984,
   11560,
   7605,
   3671,
   19673,
   9079,
   16081,
   6326,
   6009
  ],
  "seeding": [
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0
  ],
  "seeding_proj": [
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0
  ],
  "mkt_total": [
   39396,
   31562,
   36471,
   35305,
   35390,
   59273,
   80465,
   134237,
   126108,
   91147
  ],
  "mkt_total_proj": [
   39396,
   31562,
   36471,
   35305,
   35390,
   59273,
   80465,
   134237,
   126108,
   141278
  ],
  "contribution_margin": [
   296830,
   407040,
   378564,
   326729,
   357614,
   360035,
   294229,
   278375,
   267202,
   206780
  ],
  "contribution_margin_proj": [
   296830,
   407040,
   378564,
   326729,
   357614,
   360035,
   294229,
   278375,
   267202,
   320509
  ]
 },
 "search_queries": [
  {
   "query": "grosmimi straw cup",
   "impressions": 52983,
   "clicks": 2425,
   "ctr": 4.58,
   "spend": 1156.46,
   "sales": 20321.83,
   "orders": 0,
   "acos": 5.7,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cups for toddlers 1-3",
   "impressions": 313215,
   "clicks": 1363,
   "ctr": 0.44,
   "spend": 1066.69,
   "sales": 4952.9,
   "orders": 0,
   "acos": 21.5,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cup for 6 month old",
   "impressions": 68746,
   "clicks": 284,
   "ctr": 0.41,
   "spend": 366.44,
   "sales": 517.6,
   "orders": 0,
   "acos": 70.8,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "b0bmjcwyb6",
   "impressions": 38156,
   "clicks": 331,
   "ctr": 0.87,
   "spend": 364.51,
   "sales": 1353.0,
   "orders": 0,
   "acos": 26.9,
   "cvr": 0.0,
   "brand": "Naeiae"
  },
  {
   "query": "straw cups for toddlers 1-3",
   "impressions": 49868,
   "clicks": 363,
   "ctr": 0.73,
   "spend": 353.18,
   "sales": 1089.4,
   "orders": 0,
   "acos": 32.4,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "grosmimi",
   "impressions": 46632,
   "clicks": 776,
   "ctr": 1.66,
   "spend": 307.25,
   "sales": 8025.38,
   "orders": 0,
   "acos": 3.8,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cup with straw",
   "impressions": 44368,
   "clicks": 183,
   "ctr": 0.41,
   "spend": 257.06,
   "sales": 566.1,
   "orders": 0,
   "acos": 45.4,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "grosmimi straw replacement",
   "impressions": 9736,
   "clicks": 629,
   "ctr": 6.46,
   "spend": 256.08,
   "sales": 8016.07,
   "orders": 0,
   "acos": 3.2,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby sippy cup with straw",
   "impressions": 31833,
   "clicks": 115,
   "ctr": 0.36,
   "spend": 237.8,
   "sales": 188.5,
   "orders": 0,
   "acos": 126.2,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "grossini straw cup",
   "impressions": 25272,
   "clicks": 366,
   "ctr": 1.45,
   "spend": 212.29,
   "sales": 3486.8,
   "orders": 0,
   "acos": 6.1,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby sippy cup",
   "impressions": 44938,
   "clicks": 172,
   "ctr": 0.38,
   "spend": 206.41,
   "sales": 877.0,
   "orders": 0,
   "acos": 23.5,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cup for 6+ month old",
   "impressions": 32029,
   "clicks": 116,
   "ctr": 0.36,
   "spend": 157.17,
   "sales": 473.7,
   "orders": 0,
   "acos": 33.2,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "gross mimi straw cup",
   "impressions": 29030,
   "clicks": 224,
   "ctr": 0.77,
   "spend": 141.02,
   "sales": 1725.5,
   "orders": 0,
   "acos": 8.2,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby straw cups 6-12 months",
   "impressions": 24381,
   "clicks": 71,
   "ctr": 0.29,
   "spend": 136.15,
   "sales": 153.2,
   "orders": 0,
   "acos": 88.9,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "straw cup",
   "impressions": 17160,
   "clicks": 129,
   "ctr": 0.75,
   "spend": 131.66,
   "sales": 481.2,
   "orders": 0,
   "acos": 27.4,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "toddler straw cups",
   "impressions": 18786,
   "clicks": 111,
   "ctr": 0.59,
   "spend": 130.56,
   "sales": 617.4,
   "orders": 0,
   "acos": 21.1,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby straw cup",
   "impressions": 23037,
   "clicks": 189,
   "ctr": 0.82,
   "spend": 121.03,
   "sales": 734.5,
   "orders": 0,
   "acos": 16.5,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "nuk sippy cup",
   "impressions": 58923,
   "clicks": 162,
   "ctr": 0.27,
   "spend": 110.08,
   "sales": 369.4,
   "orders": 0,
   "acos": 29.8,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "grosmimi stainless steel straw cup",
   "impressions": 15221,
   "clicks": 177,
   "ctr": 1.16,
   "spend": 102.77,
   "sales": 1457.46,
   "orders": 0,
   "acos": 7.1,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "straw sippy cup",
   "impressions": 19202,
   "clicks": 120,
   "ctr": 0.62,
   "spend": 101.6,
   "sales": 410.4,
   "orders": 0,
   "acos": 24.8,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "toddler straw cup",
   "impressions": 16753,
   "clicks": 115,
   "ctr": 0.69,
   "spend": 98.17,
   "sales": 465.06,
   "orders": 0,
   "acos": 21.1,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby sippy cup straw",
   "impressions": 13987,
   "clicks": 58,
   "ctr": 0.41,
   "spend": 91.1,
   "sales": 22.8,
   "orders": 0,
   "acos": 399.6,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "b0dq63hvl1",
   "impressions": 4740,
   "clicks": 135,
   "ctr": 2.85,
   "spend": 84.25,
   "sales": 57.4,
   "orders": 0,
   "acos": 146.8,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "weighted straw cup",
   "impressions": 15457,
   "clicks": 125,
   "ctr": 0.81,
   "spend": 78.83,
   "sales": 343.0,
   "orders": 0,
   "acos": 23.0,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cups for toddlers",
   "impressions": 18240,
   "clicks": 60,
   "ctr": 0.33,
   "spend": 76.62,
   "sales": 45.6,
   "orders": 0,
   "acos": 168.0,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "baby cup with straw",
   "impressions": 8494,
   "clicks": 38,
   "ctr": 0.45,
   "spend": 75.95,
   "sales": 122.0,
   "orders": 0,
   "acos": 62.3,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "b0f3ln98nq",
   "impressions": 8166,
   "clicks": 126,
   "ctr": 1.54,
   "spend": 75.19,
   "sales": 28.7,
   "orders": 0,
   "acos": 262.0,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "nuk sippy cups for toddlers 1-3",
   "impressions": 20054,
   "clicks": 82,
   "ctr": 0.41,
   "spend": 71.52,
   "sales": 57.4,
   "orders": 0,
   "acos": 124.6,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "grosmimi replacement",
   "impressions": 9307,
   "clicks": 234,
   "ctr": 2.51,
   "spend": 65.92,
   "sales": 2280.19,
   "orders": 0,
   "acos": 2.9,
   "cvr": 0.0,
   "brand": "Grosmimi"
  },
  {
   "query": "sippy cups",
   "impressions": 17291,
   "clicks": 76,
   "ctr": 0.44,
   "spend": 65.15,
   "sales": 391.0,
   "orders": 0,
   "acos": 16.7,
   "cvr": 0.0,
   "brand": "Grosmimi"
  }
 ],
 "search_by_brand": {
  "CHA&MOM": [
   {
    "query": "b0b3fvl358",
    "impressions": 3745,
    "clicks": 10,
    "ctr": 0.27,
    "spend": 25.5,
    "sales": 26.5,
    "orders": 0,
    "acos": 96.2,
    "cvr": 0.0
   },
   {
    "query": "b0b3fvq6l6",
    "impressions": 682,
    "clicks": 3,
    "ctr": 0.44,
    "spend": 11.34,
    "sales": 26.5,
    "orders": 0,
    "acos": 42.8,
    "cvr": 0.0
   },
   {
    "query": "b00jf3s29y",
    "impressions": 791,
    "clicks": 4,
    "ctr": 0.51,
    "spend": 7.8,
    "sales": 26.5,
    "orders": 0,
    "acos": 29.4,
    "cvr": 0.0
   },
   {
    "query": "b00ehd9872",
    "impressions": 185,
    "clicks": 3,
    "ctr": 1.62,
    "spend": 5.48,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b01j3ett0u",
    "impressions": 109,
    "clicks": 2,
    "ctr": 1.83,
    "spend": 5.06,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0ckymfyd9",
    "impressions": 27,
    "clicks": 2,
    "ctr": 7.41,
    "spend": 4.18,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b09mvmnw5m",
    "impressions": 646,
    "clicks": 2,
    "ctr": 0.31,
    "spend": 3.87,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0cbnch27v",
    "impressions": 90,
    "clicks": 2,
    "ctr": 2.22,
    "spend": 3.77,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b09jl8d41t",
    "impressions": 1454,
    "clicks": 2,
    "ctr": 0.14,
    "spend": 3.66,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0fxkbpxtb",
    "impressions": 21,
    "clicks": 4,
    "ctr": 19.05,
    "spend": 3.22,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0dkxm6s1w",
    "impressions": 3,
    "clicks": 1,
    "ctr": 33.33,
    "spend": 3.03,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0cstflrk4",
    "impressions": 220,
    "clicks": 1,
    "ctr": 0.45,
    "spend": 2.95,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b07nsbtz22",
    "impressions": 13,
    "clicks": 1,
    "ctr": 7.69,
    "spend": 2.94,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b07c66wvdj",
    "impressions": 85,
    "clicks": 1,
    "ctr": 1.18,
    "spend": 2.88,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0dsvnld2d",
    "impressions": 6,
    "clicks": 1,
    "ctr": 16.67,
    "spend": 2.76,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b00idsjx7m",
    "impressions": 258,
    "clicks": 3,
    "ctr": 1.16,
    "spend": 2.59,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "b0cgzkjqpn",
    "impressions": 1,
    "clicks": 1,
    "ctr": 100.0,
    "spend": 2.54,
    "sales": 56.2,
    "orders": 0,
    "acos": 4.5,
    "cvr": 0.0
   },
   {
    "query": "attitude baby lotion",
    "impressions": 4,
    "clicks": 1,
    "ctr": 25.0,
    "spend": 2.39,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "cha and mom",
    "impressions": 10,
    "clicks": 4,
    "ctr": 40.0,
    "spend": 2.34,
    "sales": 81.7,
    "orders": 0,
    "acos": 2.9,
    "cvr": 0.0
   },
   {
    "query": "baby lotion",
    "impressions": 177,
    "clicks": 1,
    "ctr": 0.56,
    "spend": 2.34,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   }
  ],
  "Naeiae": [
   {
    "query": "b0bmjcwyb6",
    "impressions": 38156,
    "clicks": 331,
    "ctr": 0.87,
    "spend": 364.51,
    "sales": 1353.0,
    "orders": 0,
    "acos": 26.9,
    "cvr": 0.0
   },
   {
    "query": "b0bmh153y7",
    "impressions": 4834,
    "clicks": 37,
    "ctr": 0.77,
    "spend": 30.93,
    "sales": 221.4,
    "orders": 0,
    "acos": 14.0,
    "cvr": 0.0
   },
   {
    "query": "baby snacks",
    "impressions": 3141,
    "clicks": 28,
    "ctr": 0.89,
    "spend": 27.83,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "puffed rice",
    "impressions": 2145,
    "clicks": 30,
    "ctr": 1.4,
    "spend": 25.43,
    "sales": 24.6,
    "orders": 0,
    "acos": 103.4,
    "cvr": 0.0
   },
   {
    "query": "toddler snacks",
    "impressions": 1090,
    "clicks": 17,
    "ctr": 1.56,
    "spend": 17.74,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "떡뻥",
    "impressions": 78,
    "clicks": 19,
    "ctr": 24.36,
    "spend": 13.19,
    "sales": 196.8,
    "orders": 0,
    "acos": 6.7,
    "cvr": 0.0
   },
   {
    "query": "baby rice crackers",
    "impressions": 174,
    "clicks": 9,
    "ctr": 5.17,
    "spend": 12.58,
    "sales": 24.6,
    "orders": 0,
    "acos": 51.1,
    "cvr": 0.0
   },
   {
    "query": "dried sweet potatoes for humans",
    "impressions": 449,
    "clicks": 13,
    "ctr": 2.9,
    "spend": 11.44,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "rice puffs",
    "impressions": 417,
    "clicks": 11,
    "ctr": 2.64,
    "spend": 9.4,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "low calorie snacks",
    "impressions": 565,
    "clicks": 10,
    "ctr": 1.77,
    "spend": 8.8,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "baby snack",
    "impressions": 266,
    "clicks": 8,
    "ctr": 3.01,
    "spend": 7.77,
    "sales": 24.6,
    "orders": 0,
    "acos": 31.6,
    "cvr": 0.0
   },
   {
    "query": "korean snacks",
    "impressions": 834,
    "clicks": 9,
    "ctr": 1.08,
    "spend": 7.63,
    "sales": 49.2,
    "orders": 0,
    "acos": 15.5,
    "cvr": 0.0
   },
   {
    "query": "baby teething snacks",
    "impressions": 524,
    "clicks": 6,
    "ctr": 1.15,
    "spend": 6.42,
    "sales": 24.6,
    "orders": 0,
    "acos": 26.1,
    "cvr": 0.0
   },
   {
    "query": "baby puffs snacks",
    "impressions": 118,
    "clicks": 6,
    "ctr": 5.08,
    "spend": 6.29,
    "sales": 49.2,
    "orders": 0,
    "acos": 12.8,
    "cvr": 0.0
   },
   {
    "query": "sweet potato sticks",
    "impressions": 113,
    "clicks": 7,
    "ctr": 6.19,
    "spend": 6.1,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "korean baby food",
    "impressions": 138,
    "clicks": 6,
    "ctr": 4.35,
    "spend": 5.85,
    "sales": 49.2,
    "orders": 0,
    "acos": 11.9,
    "cvr": 0.0
   },
   {
    "query": "b08tqn3h7t",
    "impressions": 1589,
    "clicks": 15,
    "ctr": 0.94,
    "spend": 5.8,
    "sales": 73.8,
    "orders": 0,
    "acos": 7.9,
    "cvr": 0.0
   },
   {
    "query": "rice snacks",
    "impressions": 188,
    "clicks": 5,
    "ctr": 2.66,
    "spend": 5.07,
    "sales": 24.6,
    "orders": 0,
    "acos": 20.6,
    "cvr": 0.0
   },
   {
    "query": "rice cakes",
    "impressions": 540,
    "clicks": 6,
    "ctr": 1.11,
    "spend": 4.74,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   },
   {
    "query": "puff rice",
    "impressions": 54,
    "clicks": 5,
    "ctr": 9.26,
    "spend": 4.72,
    "sales": 0.0,
    "orders": 0,
    "acos": 0,
    "cvr": 0.0
   }
  ],
  "Grosmimi": [
   {
    "query": "grosmimi straw cup",
    "impressions": 52983,
    "clicks": 2425,
    "ctr": 4.58,
    "spend": 1156.46,
    "sales": 20321.83,
    "orders": 0,
    "acos": 5.7,
    "cvr": 0.0
   },
   {
    "query": "sippy cups for toddlers 1-3",
    "impressions": 313215,
    "clicks": 1363,
    "ctr": 0.44,
    "spend": 1066.69,
    "sales": 4952.9,
    "orders": 0,
    "acos": 21.5,
    "cvr": 0.0
   },
   {
    "query": "sippy cup for 6 month old",
    "impressions": 68746,
    "clicks": 284,
    "ctr": 0.41,
    "spend": 366.44,
    "sales": 517.6,
    "orders": 0,
    "acos": 70.8,
    "cvr": 0.0
   },
   {
    "query": "straw cups for toddlers 1-3",
    "impressions": 49868,
    "clicks": 363,
    "ctr": 0.73,
    "spend": 353.18,
    "sales": 1089.4,
    "orders": 0,
    "acos": 32.4,
    "cvr": 0.0
   },
   {
    "query": "grosmimi",
    "impressions": 46632,
    "clicks": 776,
    "ctr": 1.66,
    "spend": 307.25,
    "sales": 8025.38,
    "orders": 0,
    "acos": 3.8,
    "cvr": 0.0
   },
   {
    "query": "sippy cup with straw",
    "impressions": 44368,
    "clicks": 183,
    "ctr": 0.41,
    "spend": 257.06,
    "sales": 566.1,
    "orders": 0,
    "acos": 45.4,
    "cvr": 0.0
   },
   {
    "query": "grosmimi straw replacement",
    "impressions": 9736,
    "clicks": 629,
    "ctr": 6.46,
    "spend": 256.08,
    "sales": 8016.07,
    "orders": 0,
    "acos": 3.2,
    "cvr": 0.0
   },
   {
    "query": "baby sippy cup with straw",
    "impressions": 31833,
    "clicks": 115,
    "ctr": 0.36,
    "spend": 237.8,
    "sales": 188.5,
    "orders": 0,
    "acos": 126.2,
    "cvr": 0.0
   },
   {
    "query": "grossini straw cup",
    "impressions": 25272,
    "clicks": 366,
    "ctr": 1.45,
    "spend": 212.29,
    "sales": 3486.8,
    "orders": 0,
    "acos": 6.1,
    "cvr": 0.0
   },
   {
    "query": "baby sippy cup",
    "impressions": 44938,
    "clicks": 172,
    "ctr": 0.38,
    "spend": 206.41,
    "sales": 877.0,
    "orders": 0,
    "acos": 23.5,
    "cvr": 0.0
   },
   {
    "query": "sippy cup for 6+ month old",
    "impressions": 32029,
    "clicks": 116,
    "ctr": 0.36,
    "spend": 157.17,
    "sales": 473.7,
    "orders": 0,
    "acos": 33.2,
    "cvr": 0.0
   },
   {
    "query": "gross mimi straw cup",
    "impressions": 29030,
    "clicks": 224,
    "ctr": 0.77,
    "spend": 141.02,
    "sales": 1725.5,
    "orders": 0,
    "acos": 8.2,
    "cvr": 0.0
   },
   {
    "query": "baby straw cups 6-12 months",
    "impressions": 24381,
    "clicks": 71,
    "ctr": 0.29,
    "spend": 136.15,
    "sales": 153.2,
    "orders": 0,
    "acos": 88.9,
    "cvr": 0.0
   },
   {
    "query": "straw cup",
    "impressions": 17160,
    "clicks": 129,
    "ctr": 0.75,
    "spend": 131.66,
    "sales": 481.2,
    "orders": 0,
    "acos": 27.4,
    "cvr": 0.0
   },
   {
    "query": "toddler straw cups",
    "impressions": 18786,
    "clicks": 111,
    "ctr": 0.59,
    "spend": 130.56,
    "sales": 617.4,
    "orders": 0,
    "acos": 21.1,
    "cvr": 0.0
   },
   {
    "query": "baby straw cup",
    "impressions": 23037,
    "clicks": 189,
    "ctr": 0.82,
    "spend": 121.03,
    "sales": 734.5,
    "orders": 0,
    "acos": 16.5,
    "cvr": 0.0
   },
   {
    "query": "nuk sippy cup",
    "impressions": 58923,
    "clicks": 162,
    "ctr": 0.27,
    "spend": 110.08,
    "sales": 369.4,
    "orders": 0,
    "acos": 29.8,
    "cvr": 0.0
   },
   {
    "query": "grosmimi stainless steel straw cup",
    "impressions": 15221,
    "clicks": 177,
    "ctr": 1.16,
    "spend": 102.77,
    "sales": 1457.46,
    "orders": 0,
    "acos": 7.1,
    "cvr": 0.0
   },
   {
    "query": "straw sippy cup",
    "impressions": 19202,
    "clicks": 120,
    "ctr": 0.62,
    "spend": 101.6,
    "sales": 410.4,
    "orders": 0,
    "acos": 24.8,
    "cvr": 0.0
   },
   {
    "query": "toddler straw cup",
    "impressions": 16753,
    "clicks": 115,
    "ctr": 0.69,
    "spend": 98.17,
    "sales": 465.06,
    "orders": 0,
    "acos": 21.1,
    "cvr": 0.0
   }
  ],
  "test": [
   {
    "query": "test query",
    "impressions": 10,
    "clicks": 1,
    "ctr": 10.0,
    "spend": 0.5,
    "sales": 1.0,
    "orders": 0,
    "acos": 50.0,
    "cvr": 0.0
   }
  ]
 },
 "gsc_queries": [
  {
   "query": "onzenna",
   "impressions": 373,
   "clicks": 79,
   "ctr": 21.18,
   "position": 4.2
  },
  {
   "query": "zezebaebae",
   "impressions": 273,
   "clicks": 61,
   "ctr": 22.34,
   "position": 4.3
  },
  {
   "query": "grosmimi",
   "impressions": 1606,
   "clicks": 33,
   "ctr": 2.05,
   "position": 8.3
  },
  {
   "query": "grosmimi stainless steel plate",
   "impressions": 84,
   "clicks": 7,
   "ctr": 8.33,
   "position": 5.8
  },
  {
   "query": "beemymagic stainless steel",
   "impressions": 110,
   "clicks": 6,
   "ctr": 5.45,
   "position": 4.7
  },
  {
   "query": "grosmimi stainless steel",
   "impressions": 373,
   "clicks": 6,
   "ctr": 1.61,
   "position": 7.0
  },
  {
   "query": "beemymagic",
   "impressions": 89,
   "clicks": 6,
   "ctr": 6.74,
   "position": 5.0
  },
  {
   "query": "zezebebe",
   "impressions": 52,
   "clicks": 6,
   "ctr": 11.54,
   "position": 3.6
  },
  {
   "query": "grosmimi stainless steel food tray with 5 compartment",
   "impressions": 25,
   "clicks": 5,
   "ctr": 20.0,
   "position": 5.9
  },
  {
   "query": "grosmimi straw cup",
   "impressions": 2347,
   "clicks": 5,
   "ctr": 0.21,
   "position": 9.6
  },
  {
   "query": "bamboo bebe gauze",
   "impressions": 31,
   "clicks": 5,
   "ctr": 16.13,
   "position": 6.4
  },
  {
   "query": "grosmimi tumbler cap",
   "impressions": 44,
   "clicks": 4,
   "ctr": 9.09,
   "position": 2.8
  },
  {
   "query": "alpremio",
   "impressions": 175,
   "clicks": 4,
   "ctr": 2.29,
   "position": 5.2
  },
  {
   "query": "cha and mom",
   "impressions": 20,
   "clicks": 4,
   "ctr": 20.0,
   "position": 2.0
  },
  {
   "query": "cha&mom",
   "impressions": 42,
   "clicks": 4,
   "ctr": 9.52,
   "position": 3.6
  },
  {
   "query": "best korean baby products",
   "impressions": 24,
   "clicks": 4,
   "ctr": 16.67,
   "position": 4.1
  },
  {
   "query": "hattung",
   "impressions": 18,
   "clicks": 3,
   "ctr": 16.67,
   "position": 2.4
  },
  {
   "query": "grosmimi straw replacement",
   "impressions": 156,
   "clicks": 3,
   "ctr": 1.92,
   "position": 7.8
  },
  {
   "query": "grosmimi stainless steel straw cup",
   "impressions": 229,
   "clicks": 3,
   "ctr": 1.31,
   "position": 8.2
  },
  {
   "query": "zezebaebae reviews",
   "impressions": 96,
   "clicks": 3,
   "ctr": 3.12,
   "position": 4.6
  }
 ],
 "keyword_rankings": {
  "7d": [
   {
    "query": "onzenna",
    "clicks": 25,
    "impressions": 109,
    "avg_position": 3.1,
    "ctr": 22.94,
    "weekly_positions": [
     3.1
    ]
   },
   {
    "query": "zezebaebae",
    "clicks": 19,
    "impressions": 55,
    "avg_position": 3.3,
    "ctr": 34.55,
    "weekly_positions": [
     3.3
    ]
   },
   {
    "query": "grosmimi",
    "clicks": 9,
    "impressions": 357,
    "avg_position": 7.7,
    "ctr": 2.52,
    "weekly_positions": [
     7.7
    ]
   },
   {
    "query": "bamboo bebe gauze",
    "clicks": 4,
    "impressions": 19,
    "avg_position": 6.9,
    "ctr": 21.05,
    "weekly_positions": [
     6.9
    ]
   },
   {
    "query": "zezebebe",
    "clicks": 3,
    "impressions": 13,
    "avg_position": 3.4,
    "ctr": 23.08,
    "weekly_positions": [
     3.4
    ]
   },
   {
    "query": "grosmimi stainless steel plate",
    "clicks": 3,
    "impressions": 35,
    "avg_position": 2.9,
    "ctr": 8.57,
    "weekly_positions": [
     2.9
    ]
   },
   {
    "query": "grosmimi stainless steel",
    "clicks": 2,
    "impressions": 101,
    "avg_position": 8.2,
    "ctr": 1.98,
    "weekly_positions": [
     8.2
    ]
   },
   {
    "query": "alpremio nursing seat",
    "clicks": 2,
    "impressions": 16,
    "avg_position": 3.0,
    "ctr": 12.5,
    "weekly_positions": [
     3.0
    ]
   },
   {
    "query": "grosmimi replacement cap",
    "clicks": 2,
    "impressions": 6,
    "avg_position": 2.0,
    "ctr": 33.33,
    "weekly_positions": [
     2.0
    ]
   },
   {
    "query": "cha and mom",
    "clicks": 2,
    "impressions": 5,
    "avg_position": 1.0,
    "ctr": 40.0,
    "weekly_positions": [
     1.0
    ]
   },
   {
    "query": "zezebaebae reviews",
    "clicks": 1,
    "impressions": 20,
    "avg_position": 6.3,
    "ctr": 5.0,
    "weekly_positions": [
     6.3
    ]
   },
   {
    "query": "grosmimi straw cup",
    "clicks": 1,
    "impressions": 850,
    "avg_position": 10.3,
    "ctr": 0.12,
    "weekly_positions": [
     10.3
    ]
   },
   {
    "query": "hattung",
    "clicks": 1,
    "impressions": 4,
    "avg_position": 3.0,
    "ctr": 25.0,
    "weekly_positions": [
     3.0
    ]
   },
   {
    "query": "grossmimi",
    "clicks": 1,
    "impressions": 44,
    "avg_position": 4.6,
    "ctr": 2.27,
    "weekly_positions": [
     4.6
    ]
   },
   {
    "query": "grosmini",
    "clicks": 1,
    "impressions": 26,
    "avg_position": 6.5,
    "ctr": 3.85,
    "weekly_positions": [
     6.5
    ]
   },
   {
    "query": "grosmimi tumbler cap",
    "clicks": 1,
    "impressions": 9,
    "avg_position": 3.6,
    "ctr": 11.11,
    "weekly_positions": [
     3.6
    ]
   },
   {
    "query": "grosmimi straw replacement",
    "clicks": 1,
    "impressions": 24,
    "avg_position": 5.9,
    "ctr": 4.17,
    "weekly_positions": [
     5.9
    ]
   },
   {
    "query": "grosmimi straw cup review",
    "clicks": 1,
    "impressions": 13,
    "avg_position": 3.6,
    "ctr": 7.69,
    "weekly_positions": [
     3.6
    ]
   },
   {
    "query": "grosmimi stainless steel straw cup",
    "clicks": 1,
    "impressions": 57,
    "avg_position": 9.7,
    "ctr": 1.75,
    "weekly_positions": [
     9.7
    ]
   },
   {
    "query": "cha & mom",
    "clicks": 1,
    "impressions": 3,
    "avg_position": 1.0,
    "ctr": 33.33,
    "weekly_positions": [
     1.0
    ]
   },
   {
    "query": "beemymagic",
    "clicks": 1,
    "impressions": 19,
    "avg_position": 6.9,
    "ctr": 5.26,
    "weekly_positions": [
     6.9
    ]
   },
   {
    "query": "bamboo bebe",
    "clicks": 1,
    "impressions": 19,
    "avg_position": 10.1,
    "ctr": 5.26,
    "weekly_positions": [
     10.1
    ]
   },
   {
    "query": "korean baby bottle",
    "clicks": 1,
    "impressions": 5,
    "avg_position": 3.8,
    "ctr": 20.0,
    "weekly_positions": [
     3.8
    ]
   },
   {
    "query": "baby book stand for reading",
    "clicks": 1,
    "impressions": 4,
    "avg_position": 4.2,
    "ctr": 25.0,
    "weekly_positions": [
     4.2
    ]
   },
   {
    "query": "soft finger foods for 9 month old",
    "clicks": 1,
    "impressions": 5,
    "avg_position": 1.0,
    "ctr": 20.0,
    "weekly_positions": [
     1.0
    ]
   }
  ],
  "30d": [
   {
    "query": "onzenna",
    "clicks": 79,
    "impressions": 373,
    "avg_position": 4.2,
    "ctr": 21.18,
    "weekly_positions": [
     4.1,
     4.2,
     5.2,
     3.4,
     3.3
    ]
   },
   {
    "query": "zezebaebae",
    "clicks": 61,
    "impressions": 273,
    "avg_position": 4.3,
    "ctr": 22.34,
    "weekly_positions": [
     4.7,
     4.6,
     5.1,
     2.6,
     5.0
    ]
   },
   {
    "query": "grosmimi",
    "clicks": 33,
    "impressions": 1606,
    "avg_position": 8.3,
    "ctr": 2.05,
    "weekly_positions": [
     8.9,
     6.8,
     10.3,
     8.1,
     8.1
    ]
   },
   {
    "query": "grosmimi stainless steel plate",
    "clicks": 7,
    "impressions": 84,
    "avg_position": 5.8,
    "ctr": 8.33,
    "weekly_positions": [
     9.4,
     5.4,
     6.1,
     3.5,
     2.0
    ]
   },
   {
    "query": "beemymagic stainless steel",
    "clicks": 6,
    "impressions": 110,
    "avg_position": 4.7,
    "ctr": 5.45,
    "weekly_positions": [
     5.2,
     3.2,
     4.0,
     5.0,
     8.8
    ]
   },
   {
    "query": "grosmimi stainless steel",
    "clicks": 6,
    "impressions": 373,
    "avg_position": 7.0,
    "ctr": 1.61,
    "weekly_positions": [
     5.9,
     7.2,
     6.8,
     7.6,
     10.5
    ]
   },
   {
    "query": "beemymagic",
    "clicks": 6,
    "impressions": 89,
    "avg_position": 5.0,
    "ctr": 6.74,
    "weekly_positions": [
     4.1,
     4.6,
     4.4,
     6.8,
     4.0
    ]
   },
   {
    "query": "zezebebe",
    "clicks": 6,
    "impressions": 52,
    "avg_position": 3.6,
    "ctr": 11.54,
    "weekly_positions": [
     3.6,
     3.2,
     4.5,
     3.8,
     1.8
    ]
   },
   {
    "query": "grosmimi stainless steel food tray with 5 compartment",
    "clicks": 5,
    "impressions": 25,
    "avg_position": 5.9,
    "ctr": 20.0,
    "weekly_positions": [
     7.7,
     7.0,
     3.5,
     2.2,
     7.2
    ]
   },
   {
    "query": "grosmimi straw cup",
    "clicks": 5,
    "impressions": 2347,
    "avg_position": 9.6,
    "ctr": 0.21,
    "weekly_positions": [
     9.4,
     9.1,
     9.7,
     9.8,
     11.2
    ]
   },
   {
    "query": "bamboo bebe gauze",
    "clicks": 5,
    "impressions": 31,
    "avg_position": 6.4,
    "ctr": 16.13,
    "weekly_positions": [
     8.8,
     5.0,
     5.0,
     6.3,
     5.4
    ]
   },
   {
    "query": "grosmimi tumbler cap",
    "clicks": 4,
    "impressions": 44,
    "avg_position": 2.8,
    "ctr": 9.09,
    "weekly_positions": [
     3.2,
     2.9,
     1.2,
     3.4,
     1.8
    ]
   },
   {
    "query": "alpremio",
    "clicks": 4,
    "impressions": 175,
    "avg_position": 5.2,
    "ctr": 2.29,
    "weekly_positions": [
     5.6,
     5.7,
     5.0,
     4.3,
     4.0
    ]
   },
   {
    "query": "cha and mom",
    "clicks": 4,
    "impressions": 20,
    "avg_position": 2.0,
    "ctr": 20.0,
    "weekly_positions": [
     2.4,
     5.0,
     2.3,
     1.0,
     1.0
    ]
   },
   {
    "query": "cha&mom",
    "clicks": 4,
    "impressions": 42,
    "avg_position": 3.6,
    "ctr": 9.52,
    "weekly_positions": [
     5.9,
     2.6,
     4.4,
     2.4,
     null
    ]
   },
   {
    "query": "best korean baby products",
    "clicks": 4,
    "impressions": 24,
    "avg_position": 4.1,
    "ctr": 16.67,
    "weekly_positions": [
     6.2,
     3.0,
     2.3,
     4.5,
     null
    ]
   },
   {
    "query": "zezebaebae reviews",
    "clicks": 3,
    "impressions": 96,
    "avg_position": 4.6,
    "ctr": 3.12,
    "weekly_positions": [
     5.3,
     4.0,
     3.5,
     6.0,
     4.0
    ]
   },
   {
    "query": "hattung",
    "clicks": 3,
    "impressions": 18,
    "avg_position": 2.4,
    "ctr": 16.67,
    "weekly_positions": [
     2.7,
     1.5,
     2.3,
     4.0,
     2.0
    ]
   },
   {
    "query": "grosmimi straw replacement",
    "clicks": 3,
    "impressions": 156,
    "avg_position": 7.8,
    "ctr": 1.92,
    "weekly_positions": [
     9.0,
     7.1,
     8.3,
     6.2,
     5.1
    ]
   },
   {
    "query": "grosmimi stainless steel straw cup",
    "clicks": 3,
    "impressions": 229,
    "avg_position": 8.2,
    "ctr": 1.31,
    "weekly_positions": [
     7.7,
     7.2,
     8.6,
     8.4,
     11.9
    ]
   },
   {
    "query": "grosmimi replacement cap",
    "clicks": 3,
    "impressions": 42,
    "avg_position": 2.8,
    "ctr": 7.14,
    "weekly_positions": [
     2.7,
     2.5,
     5.2,
     2.2,
     2.0
    ]
   },
   {
    "query": "hattung say house",
    "clicks": 3,
    "impressions": 16,
    "avg_position": 3.8,
    "ctr": 18.75,
    "weekly_positions": [
     2.8,
     4.1,
     4.8,
     null,
     null
    ]
   },
   {
    "query": "commemoi",
    "clicks": 2,
    "impressions": 23,
    "avg_position": 4.0,
    "ctr": 8.7,
    "weekly_positions": [
     4.5,
     5.5,
     3.5,
     1.3,
     5.5
    ]
   },
   {
    "query": "grosmimi bottle",
    "clicks": 2,
    "impressions": 140,
    "avg_position": 7.7,
    "ctr": 1.43,
    "weekly_positions": [
     7.1,
     8.7,
     7.1,
     7.6,
     8.5
    ]
   },
   {
    "query": "grossmimi",
    "clicks": 2,
    "impressions": 157,
    "avg_position": 5.0,
    "ctr": 1.27,
    "weekly_positions": [
     5.5,
     5.5,
     4.6,
     4.4,
     5.3
    ]
   }
  ],
  "90d": [
   {
    "query": "zezebaebae",
    "clicks": 95,
    "impressions": 356,
    "avg_position": 3.8,
    "ctr": 26.69,
    "weekly_positions": [
     1.1,
     2.2,
     4.8,
     4.0,
     5.1,
     4.1,
     3.6
    ]
   },
   {
    "query": "onzenna",
    "clicks": 83,
    "impressions": 507,
    "avg_position": 4.3,
    "ctr": 16.37,
    "weekly_positions": [
     2.7,
     5.4,
     5.6,
     4.4,
     4.6,
     4.4,
     3.3
    ]
   },
   {
    "query": "grosmimi",
    "clicks": 62,
    "impressions": 2228,
    "avg_position": 8.3,
    "ctr": 2.78,
    "weekly_positions": [
     5.7,
     11.1,
     7.8,
     8.8,
     6.9,
     10.3,
     7.6
    ]
   },
   {
    "query": "grosmimi straw cup",
    "clicks": 43,
    "impressions": 2996,
    "avg_position": 9.3,
    "ctr": 1.44,
    "weekly_positions": [
     4.2,
     10.8,
     9.0,
     9.6,
     9.3,
     9.8,
     10.4
    ]
   },
   {
    "query": "grosmimi stainless steel",
    "clicks": 14,
    "impressions": 496,
    "avg_position": 6.2,
    "ctr": 2.82,
    "weekly_positions": [
     2.9,
     3.7,
     5.2,
     7.3,
     7.1,
     7.1,
     8.0
    ]
   },
   {
    "query": "zezebebe",
    "clicks": 12,
    "impressions": 75,
    "avg_position": 2.9,
    "ctr": 16.0,
    "weekly_positions": [
     1.0,
     1.0,
     3.5,
     3.0,
     5.3,
     2.7,
     3.6
    ]
   },
   {
    "query": "zezebaebae reviews",
    "clicks": 10,
    "impressions": 128,
    "avg_position": 3.8,
    "ctr": 7.81,
    "weekly_positions": [
     1.0,
     1.7,
     3.7,
     5.9,
     3.1,
     2.8,
     6.9
    ]
   },
   {
    "query": "grosmimi cup",
    "clicks": 9,
    "impressions": 736,
    "avg_position": 10.8,
    "ctr": 1.22,
    "weekly_positions": [
     5.0,
     12.7,
     13.0,
     11.9,
     10.8,
     11.0,
     10.7
    ]
   },
   {
    "query": "grosmimi stainless steel plate",
    "clicks": 8,
    "impressions": 108,
    "avg_position": 5.2,
    "ctr": 7.41,
    "weekly_positions": [
     2.5,
     8.3,
     11.5,
     7.7,
     8.0,
     4.1,
     2.1
    ]
   },
   {
    "query": "beemymagic",
    "clicks": 7,
    "impressions": 111,
    "avg_position": 5.2,
    "ctr": 6.31,
    "weekly_positions": [
     5.5,
     7.4,
     4.0,
     3.9,
     5.1,
     4.0,
     7.5
    ]
   },
   {
    "query": "cha&mom",
    "clicks": 7,
    "impressions": 70,
    "avg_position": 3.6,
    "ctr": 10.0,
    "weekly_positions": [
     3.8,
     2.5,
     4.0,
     5.1,
     2.8,
     3.3,
     3.0
    ]
   },
   {
    "query": "beemymagic stainless steel",
    "clicks": 6,
    "impressions": 155,
    "avg_position": 4.8,
    "ctr": 3.87,
    "weekly_positions": [
     5.4,
     4.2,
     6.0,
     4.0,
     3.7,
     4.6,
     6.0
    ]
   },
   {
    "query": "grosmimi stainless steel straw cup",
    "clicks": 6,
    "impressions": 317,
    "avg_position": 7.6,
    "ctr": 1.89,
    "weekly_positions": [
     2.0,
     9.6,
     7.5,
     7.2,
     8.6,
     7.5,
     10.0
    ]
   },
   {
    "query": "bamboo bebe gauze",
    "clicks": 6,
    "impressions": 40,
    "avg_position": 6.2,
    "ctr": 15.0,
    "weekly_positions": [
     5.1,
     8.0,
     10.5,
     6.5,
     null,
     5.0,
     6.7
    ]
   },
   {
    "query": "grosmimi stainless steel food tray with 5 compartment",
    "clicks": 5,
    "impressions": 26,
    "avg_position": 5.9,
    "ctr": 19.23,
    "weekly_positions": [
     null,
     null,
     7.3,
     7.3,
     7.0,
     2.0,
     5.5
    ]
   },
   {
    "query": "grosmimi tumbler cap",
    "clicks": 5,
    "impressions": 59,
    "avg_position": 3.0,
    "ctr": 8.47,
    "weekly_positions": [
     1.4,
     6.0,
     4.6,
     2.8,
     2.7,
     1.9,
     3.7
    ]
   },
   {
    "query": "alpremio",
    "clicks": 5,
    "impressions": 224,
    "avg_position": 5.1,
    "ctr": 2.23,
    "weekly_positions": [
     4.3,
     4.4,
     5.6,
     6.3,
     5.6,
     4.3,
     3.7
    ]
   },
   {
    "query": "grosmimi bottle",
    "clicks": 4,
    "impressions": 184,
    "avg_position": 7.3,
    "ctr": 2.17,
    "weekly_positions": [
     4.1,
     8.2,
     6.1,
     8.2,
     7.6,
     7.8,
     8.0
    ]
   },
   {
    "query": "grosmimi tumbler",
    "clicks": 4,
    "impressions": 115,
    "avg_position": 5.0,
    "ctr": 3.48,
    "weekly_positions": [
     2.7,
     6.8,
     6.0,
     6.8,
     4.3,
     2.9,
     4.4
    ]
   },
   {
    "query": "alpremio feeding seat",
    "clicks": 4,
    "impressions": 197,
    "avg_position": 5.2,
    "ctr": 2.03,
    "weekly_positions": [
     3.9,
     5.4,
     4.4,
     5.5,
     7.0,
     5.1,
     3.9
    ]
   },
   {
    "query": "grosmimi replacement cap",
    "clicks": 4,
    "impressions": 52,
    "avg_position": 2.9,
    "ctr": 7.69,
    "weekly_positions": [
     1.0,
     3.7,
     2.8,
     2.5,
     4.8,
     2.2,
     2.0
    ]
   },
   {
    "query": "cha and mom",
    "clicks": 4,
    "impressions": 23,
    "avg_position": 2.0,
    "ctr": 17.39,
    "weekly_positions": [
     1.3,
     null,
     2.0,
     3.4,
     1.0,
     2.3,
     1.0
    ]
   },
   {
    "query": "best korean baby products",
    "clicks": 4,
    "impressions": 31,
    "avg_position": 3.3,
    "ctr": 12.9,
    "weekly_positions": [
     1.0,
     1.0,
     7.5,
     5.8,
     2.3,
     4.3,
     2.0
    ]
   },
   {
    "query": "zezebae",
    "clicks": 4,
    "impressions": 6,
    "avg_position": 2.2,
    "ctr": 66.67,
    "weekly_positions": [
     1.0,
     1.7,
     3.5,
     null,
     null,
     null,
     null
    ]
   },
   {
    "query": "commemoi",
    "clicks": 3,
    "impressions": 31,
    "avg_position": 3.9,
    "ctr": 9.68,
    "weekly_positions": [
     3.2,
     5.0,
     null,
     3.9,
     4.7,
     4.3,
     3.0
    ]
   }
  ]
 },
 "kw_positions_summary": [
  {
   "query": "zezebaebae",
   "pos_7d": 3.3,
   "clicks_7d": 19,
   "impressions_7d": 55,
   "pos_30d": 4.3,
   "clicks_30d": 61,
   "impressions_30d": 273,
   "pos_90d": 3.8,
   "clicks_90d": 95,
   "impressions_90d": 356
  },
  {
   "query": "onzenna",
   "pos_7d": 3.1,
   "clicks_7d": 25,
   "impressions_7d": 109,
   "pos_30d": 4.2,
   "clicks_30d": 79,
   "impressions_30d": 373,
   "pos_90d": 4.3,
   "clicks_90d": 83,
   "impressions_90d": 507
  },
  {
   "query": "grosmimi",
   "pos_7d": 7.7,
   "clicks_7d": 9,
   "impressions_7d": 357,
   "pos_30d": 8.3,
   "clicks_30d": 33,
   "impressions_30d": 1606,
   "pos_90d": 8.3,
   "clicks_90d": 62,
   "impressions_90d": 2228
  },
  {
   "query": "grosmimi straw cup",
   "pos_7d": 10.3,
   "clicks_7d": 1,
   "impressions_7d": 850,
   "pos_30d": 9.6,
   "clicks_30d": 5,
   "impressions_30d": 2347,
   "pos_90d": 9.3,
   "clicks_90d": 43,
   "impressions_90d": 2996
  },
  {
   "query": "grosmimi stainless steel",
   "pos_7d": 8.2,
   "clicks_7d": 2,
   "impressions_7d": 101,
   "pos_30d": 7.0,
   "clicks_30d": 6,
   "impressions_30d": 373,
   "pos_90d": 6.2,
   "clicks_90d": 14,
   "impressions_90d": 496
  },
  {
   "query": "zezebebe",
   "pos_7d": 3.4,
   "clicks_7d": 3,
   "impressions_7d": 13,
   "pos_30d": 3.6,
   "clicks_30d": 6,
   "impressions_30d": 52,
   "pos_90d": 2.9,
   "clicks_90d": 12,
   "impressions_90d": 75
  },
  {
   "query": "zezebaebae reviews",
   "pos_7d": 6.3,
   "clicks_7d": 1,
   "impressions_7d": 20,
   "pos_30d": 4.6,
   "clicks_30d": 3,
   "impressions_30d": 96,
   "pos_90d": 3.8,
   "clicks_90d": 10,
   "impressions_90d": 128
  },
  {
   "query": "grosmimi cup",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": 10.8,
   "clicks_90d": 9,
   "impressions_90d": 736
  },
  {
   "query": "grosmimi stainless steel plate",
   "pos_7d": 2.9,
   "clicks_7d": 3,
   "impressions_7d": 35,
   "pos_30d": 5.8,
   "clicks_30d": 7,
   "impressions_30d": 84,
   "pos_90d": 5.2,
   "clicks_90d": 8,
   "impressions_90d": 108
  },
  {
   "query": "beemymagic",
   "pos_7d": 6.9,
   "clicks_7d": 1,
   "impressions_7d": 19,
   "pos_30d": 5.0,
   "clicks_30d": 6,
   "impressions_30d": 89,
   "pos_90d": 5.2,
   "clicks_90d": 7,
   "impressions_90d": 111
  },
  {
   "query": "cha&mom",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 3.6,
   "clicks_30d": 4,
   "impressions_30d": 42,
   "pos_90d": 3.6,
   "clicks_90d": 7,
   "impressions_90d": 70
  },
  {
   "query": "bamboo bebe gauze",
   "pos_7d": 6.9,
   "clicks_7d": 4,
   "impressions_7d": 19,
   "pos_30d": 6.4,
   "clicks_30d": 5,
   "impressions_30d": 31,
   "pos_90d": 6.2,
   "clicks_90d": 6,
   "impressions_90d": 40
  },
  {
   "query": "beemymagic stainless steel",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 4.7,
   "clicks_30d": 6,
   "impressions_30d": 110,
   "pos_90d": 4.8,
   "clicks_90d": 6,
   "impressions_90d": 155
  },
  {
   "query": "grosmimi stainless steel straw cup",
   "pos_7d": 9.7,
   "clicks_7d": 1,
   "impressions_7d": 57,
   "pos_30d": 8.2,
   "clicks_30d": 3,
   "impressions_30d": 229,
   "pos_90d": 7.6,
   "clicks_90d": 6,
   "impressions_90d": 317
  },
  {
   "query": "alpremio",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 5.2,
   "clicks_30d": 4,
   "impressions_30d": 175,
   "pos_90d": 5.1,
   "clicks_90d": 5,
   "impressions_90d": 224
  },
  {
   "query": "grosmimi stainless steel food tray with 5 compartment",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 5.9,
   "clicks_30d": 5,
   "impressions_30d": 25,
   "pos_90d": 5.9,
   "clicks_90d": 5,
   "impressions_90d": 26
  },
  {
   "query": "grosmimi tumbler cap",
   "pos_7d": 3.6,
   "clicks_7d": 1,
   "impressions_7d": 9,
   "pos_30d": 2.8,
   "clicks_30d": 4,
   "impressions_30d": 44,
   "pos_90d": 3.0,
   "clicks_90d": 5,
   "impressions_90d": 59
  },
  {
   "query": "alpremio feeding seat",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": 5.2,
   "clicks_90d": 4,
   "impressions_90d": 197
  },
  {
   "query": "best korean baby products",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 4.1,
   "clicks_30d": 4,
   "impressions_30d": 24,
   "pos_90d": 3.3,
   "clicks_90d": 4,
   "impressions_90d": 31
  },
  {
   "query": "cha and mom",
   "pos_7d": 1.0,
   "clicks_7d": 2,
   "impressions_7d": 5,
   "pos_30d": 2.0,
   "clicks_30d": 4,
   "impressions_30d": 20,
   "pos_90d": 2.0,
   "clicks_90d": 4,
   "impressions_90d": 23
  },
  {
   "query": "grosmimi bottle",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 7.7,
   "clicks_30d": 2,
   "impressions_30d": 140,
   "pos_90d": 7.3,
   "clicks_90d": 4,
   "impressions_90d": 184
  },
  {
   "query": "grosmimi replacement cap",
   "pos_7d": 2.0,
   "clicks_7d": 2,
   "impressions_7d": 6,
   "pos_30d": 2.8,
   "clicks_30d": 3,
   "impressions_30d": 42,
   "pos_90d": 2.9,
   "clicks_90d": 4,
   "impressions_90d": 52
  },
  {
   "query": "grosmimi tumbler",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": 5.0,
   "clicks_90d": 4,
   "impressions_90d": 115
  },
  {
   "query": "zezebae",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": 2.2,
   "clicks_90d": 4,
   "impressions_90d": 6
  },
  {
   "query": "commemoi",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 4.0,
   "clicks_30d": 2,
   "impressions_30d": 23,
   "pos_90d": 3.9,
   "clicks_90d": 3,
   "impressions_90d": 31
  },
  {
   "query": "alpremio nursing seat",
   "pos_7d": 3.0,
   "clicks_7d": 2,
   "impressions_7d": 16,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "baby book stand for reading",
   "pos_7d": 4.2,
   "clicks_7d": 1,
   "impressions_7d": 4,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "bamboo bebe",
   "pos_7d": 10.1,
   "clicks_7d": 1,
   "impressions_7d": 19,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "cha & mom",
   "pos_7d": 1.0,
   "clicks_7d": 1,
   "impressions_7d": 3,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "grosmimi straw cup review",
   "pos_7d": 3.6,
   "clicks_7d": 1,
   "impressions_7d": 13,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "grosmimi straw replacement",
   "pos_7d": 5.9,
   "clicks_7d": 1,
   "impressions_7d": 24,
   "pos_30d": 7.8,
   "clicks_30d": 3,
   "impressions_30d": 156,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "grosmini",
   "pos_7d": 6.5,
   "clicks_7d": 1,
   "impressions_7d": 26,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "grossmimi",
   "pos_7d": 4.6,
   "clicks_7d": 1,
   "impressions_7d": 44,
   "pos_30d": 5.0,
   "clicks_30d": 2,
   "impressions_30d": 157,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "hattung",
   "pos_7d": 3.0,
   "clicks_7d": 1,
   "impressions_7d": 4,
   "pos_30d": 2.4,
   "clicks_30d": 3,
   "impressions_30d": 18,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "hattung say house",
   "pos_7d": null,
   "clicks_7d": 0,
   "impressions_7d": 0,
   "pos_30d": 3.8,
   "clicks_30d": 3,
   "impressions_30d": 16,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "korean baby bottle",
   "pos_7d": 3.8,
   "clicks_7d": 1,
   "impressions_7d": 5,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  },
  {
   "query": "soft finger foods for 9 month old",
   "pos_7d": 1.0,
   "clicks_7d": 1,
   "impressions_7d": 5,
   "pos_30d": null,
   "clicks_30d": 0,
   "impressions_30d": 0,
   "pos_90d": null,
   "clicks_90d": 0,
   "impressions_90d": 0
  }
 ],
 "keyword_volumes": [
  {
   "keyword": "tinted sunscreen",
   "brand": "Onzenna",
   "search_volume": 40500,
   "cpc": 2.75,
   "competition_index": 100,
   "monthly_trend": [
    40500,
    27100,
    40500,
    33100,
    40500,
    40500
   ]
  },
  {
   "keyword": "korean sunscreen",
   "brand": "Onzenna",
   "search_volume": 33100,
   "cpc": 1.67,
   "competition_index": 100,
   "monthly_trend": [
    27100,
    22200,
    22200,
    27100,
    27100,
    33100
   ]
  },
  {
   "keyword": "korean snacks",
   "brand": "Naeiae",
   "search_volume": 22200,
   "cpc": 1.8,
   "competition_index": 65,
   "monthly_trend": [
    27100,
    27100,
    22200,
    22200,
    22200,
    18100
   ]
  },
  {
   "keyword": "grosmimi",
   "brand": "Grosmimi",
   "search_volume": 1900,
   "cpc": 2.95,
   "competition_index": 100,
   "monthly_trend": [
    2400,
    2400,
    2400,
    1900,
    2400,
    1900
   ]
  },
  {
   "keyword": "pop rice",
   "brand": "Naeiae",
   "search_volume": 1600,
   "cpc": 0.95,
   "competition_index": 52,
   "monthly_trend": [
    1600,
    1600,
    1600,
    1600,
    1900,
    1600
   ]
  },
  {
   "keyword": "mineral sunscreen spf50",
   "brand": "Onzenna",
   "search_volume": 1000,
   "cpc": 2.5,
   "competition_index": 100,
   "monthly_trend": [
    480,
    590,
    390,
    390,
    1000,
    880
   ]
  },
  {
   "keyword": "organic rice puff",
   "brand": "Naeiae",
   "search_volume": 320,
   "cpc": 1.75,
   "competition_index": 97,
   "monthly_trend": [
    480,
    140,
    140,
    170,
    720,
    590
   ]
  },
  {
   "keyword": "떡뻥",
   "brand": "Naeiae",
   "search_volume": 170,
   "cpc": 0.71,
   "competition_index": 88,
   "monthly_trend": [
    170,
    320,
    170,
    140,
    170,
    110
   ]
  },
  {
   "keyword": "pop rice snack",
   "brand": "Naeiae",
   "search_volume": 90,
   "cpc": 2.42,
   "competition_index": 98,
   "monthly_trend": [
    70,
    90,
    70,
    70,
    90,
    110
   ]
  },
  {
   "keyword": "cha and mom",
   "brand": "CHA&MOM",
   "search_volume": 30,
   "cpc": 5.97,
   "competition_index": 5,
   "monthly_trend": [
    10,
    10,
    10,
    10,
    90,
    170
   ]
  },
  {
   "keyword": "naeiae pop rice snack",
   "brand": "Naeiae",
   "search_volume": 20,
   "cpc": 3.23,
   "competition_index": 90,
   "monthly_trend": [
    10,
    10,
    10,
    10,
    10,
    20
   ]
  },
  {
   "keyword": "onzenna",
   "brand": "Onzenna",
   "search_volume": 20,
   "cpc": 14.28,
   "competition_index": 15,
   "monthly_trend": [
    0,
    0,
    0,
    0,
    30,
    210
   ]
  },
  {
   "keyword": "chamom",
   "brand": "CHA&MOM",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "korean infant snack",
   "brand": "CHA&MOM",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "korean baby food",
   "brand": "CHA&MOM",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "baby chew toy",
   "brand": "Grosmimi",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "grosmimi teether",
   "brand": "Grosmimi",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "baby teething toy",
   "brand": "Grosmimi",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "silicone baby teether",
   "brand": "Grosmimi",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "baby teether",
   "brand": "Grosmimi",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "baby teething snacks",
   "brand": "Naeiae",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "rice snack baby",
   "brand": "Naeiae",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "korean baby snack",
   "brand": "Naeiae",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "baby rice crackers",
   "brand": "Naeiae",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "onzenna skincare",
   "brand": "Onzenna",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  },
  {
   "keyword": "onzenna sunscreen",
   "brand": "Onzenna",
   "search_volume": 0,
   "cpc": 0.0,
   "competition_index": 0,
   "monthly_trend": []
  }
 ],
 "brand_analytics": {
  "Grosmimi": [
   {
    "term": "grosmimi straw cup",
    "rank": 28204,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 10.39,
    "conv_share": 6.35,
    "is_ours": true
   },
   {
    "term": "grosmimi straw replacement",
    "rank": 143204,
    "asin_rank": 2,
    "asin_name": "Grosmimi Replacements (Straw only 4-counts, Stage 2)",
    "click_share": 26.96,
    "conv_share": 22.22,
    "is_ours": true
   },
   {
    "term": "grosmimi straw replacement",
    "rank": 149314,
    "asin_rank": 1,
    "asin_name": "Grosmimi Replacements (Straw kit 2-Counts, Stage 2)",
    "click_share": 45.91,
    "conv_share": 43.38,
    "is_ours": true
   },
   {
    "term": "grosmimi straw replacement",
    "rank": 149314,
    "asin_rank": 3,
    "asin_name": "Grosmimi Replacements (Straw kit 4-counts, Stage2)",
    "click_share": 7.73,
    "conv_share": 4.11,
    "is_ours": true
   },
   {
    "term": "grosmimi",
    "rank": 201149,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 11.18,
    "conv_share": 1.59,
    "is_ours": true
   },
   {
    "term": "grosmimi",
    "rank": 201149,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 6.65,
    "conv_share": 1.59,
    "is_ours": true
   },
   {
    "term": "grosmimi stainless steel straw cup",
    "rank": 261534,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Insulated 316 Stainless Steel Spill Proof Straw Cup, Water bottle with ",
    "click_share": 20.93,
    "conv_share": 4.35,
    "is_ours": true
   },
   {
    "term": "grosmimi stainless steel straw cup",
    "rank": 261534,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Insulated 316 Stainless Steel Spill Proof Straw Cup, Water bottle with ",
    "click_share": 9.3,
    "conv_share": 6.52,
    "is_ours": true
   },
   {
    "term": "grosmimi stainless steel straw cup",
    "rank": 302673,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Insulated 316 Stainless Steel Spill Proof Straw Cup, Water bottle with ",
    "click_share": 28.25,
    "conv_share": 2.5,
    "is_ours": true
   },
   {
    "term": "stainless steel straw cup toddler",
    "rank": 370764,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Insulated 316 Stainless Steel Spill Proof Straw Cup, Water bottle with ",
    "click_share": 7.07,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "milk bottle for toddlers 3-5",
    "rank": 486118,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 6.38,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "grosmimi sippy cup",
    "rank": 608273,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 16.81,
    "conv_share": 15.0,
    "is_ours": true
   },
   {
    "term": "grosmimi sippy cup",
    "rank": 608273,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Slow Flow Toddler Tumbler Water Bottle BPA Free 10 oz. (Stainless Steel",
    "click_share": 8.85,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vaso entrenador para bebe de 1 año",
    "rank": 640583,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 8.41,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vasos para niños de 2 años",
    "rank": 782755,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 5.68,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vasos para bebes 1 año",
    "rank": 818519,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 8.33,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "toddler milk bottle 2 year old",
    "rank": 820209,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 7.14,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vasos para niños de 2 años",
    "rank": 849064,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 7.41,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vasos para niños de 2 años",
    "rank": 849064,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 6.17,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "vasos para bebes 1 año",
    "rank": 931443,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Flip Top Spill Proof Sippy Cup, PPSU, BPA Free, 10 oz, Stage 2 Straw fo",
    "click_share": 6.76,
    "conv_share": 0.0,
    "is_ours": true
   }
  ],
  "Naeiae": [
   {
    "term": "grosmimi straw cup",
    "rank": 23326,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 15.52,
    "conv_share": 3.14,
    "is_ours": true
   },
   {
    "term": "grosmimi straw cup",
    "rank": 28204,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 8.68,
    "conv_share": 1.84,
    "is_ours": true
   },
   {
    "term": "grossini straw cup",
    "rank": 192475,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 18.44,
    "conv_share": 11.76,
    "is_ours": true
   },
   {
    "term": "grosmimi",
    "rank": 201149,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 13.9,
    "conv_share": 1.59,
    "is_ours": true
   },
   {
    "term": "grossini straw cup",
    "rank": 230641,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 10.69,
    "conv_share": 6.25,
    "is_ours": true
   },
   {
    "term": "grossini straw cup",
    "rank": 230641,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 8.97,
    "conv_share": 2.5,
    "is_ours": true
   },
   {
    "term": "grosmimi sippy cup",
    "rank": 526120,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 10.77,
    "conv_share": 10.0,
    "is_ours": true
   },
   {
    "term": "grosmimi sippy cup",
    "rank": 608273,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 13.27,
    "conv_share": 5.0,
    "is_ours": true
   },
   {
    "term": "grosmimi cup",
    "rank": 969585,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 18.31,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "yugwa korean rice puff snack",
    "rank": 997786,
    "asin_rank": 2,
    "asin_name": "Naeiae Pop Organic Snack, Rice Puffs Teething Snack for Babies & Toddlers (100% ",
    "click_share": 20.29,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "straw cup for milk",
    "rank": 1014108,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 8.82,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "grosmimi weighted straw",
    "rank": 1278446,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 3.7,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "grosmimi cup",
    "rank": 1302817,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 15.09,
    "conv_share": 14.29,
    "is_ours": true
   },
   {
    "term": "grosmimi cup",
    "rank": 1302817,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 11.32,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "grossmimi",
    "rank": 1437839,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 18.75,
    "conv_share": 11.11,
    "is_ours": true
   },
   {
    "term": "rice snack",
    "rank": 1500176,
    "asin_rank": 3,
    "asin_name": "Naeiae Pop Organic Snack, Rice Puffs Teething Snack for Babies & Toddlers (100% ",
    "click_share": 8.7,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "glass straw cup toddler",
    "rank": 1533188,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 11.11,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "glass sippy cups for babies",
    "rank": 1680673,
    "asin_rank": 2,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 7.32,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "grossmimi",
    "rank": 1716977,
    "asin_rank": 3,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 7.5,
    "conv_share": 0.0,
    "is_ours": true
   },
   {
    "term": "spill-proof straw cups for toddlers",
    "rank": 1804297,
    "asin_rank": 1,
    "asin_name": "GROSMIMI Spill Proof no Spill Magic Sippy Cup with Straw with Handle for Baby an",
    "click_share": 7.89,
    "conv_share": 0.0,
    "is_ours": true
   }
  ]
 },
 "brand_analytics_category": [
  {
   "term": "baby wipes",
   "rank": 137,
   "asin_rank": 1,
   "asin_name": "Amazon Elements Baby Wipes, Sensitive, Unscented, Cleans Gently, 810 Count, Flip",
   "click_share": 7.98,
   "conv_share": 7.03,
   "is_ours": false
  },
  {
   "term": "baby wipes",
   "rank": 137,
   "asin_rank": 2,
   "asin_name": "Huggies Natural Care Sensitive Baby Wipes, Unscented, Hypoallergenic, 6 Flip-Top",
   "click_share": 7.43,
   "conv_share": 6.82,
   "is_ours": false
  },
  {
   "term": "baby wipes",
   "rank": 137,
   "asin_rank": 3,
   "asin_name": "Huggies Natural Care Sensitive Baby Wipes, Unscented, Hypoallergenic, 99% Purifi",
   "click_share": 6.56,
   "conv_share": 3.26,
   "is_ours": false
  },
  {
   "term": "water wipes",
   "rank": 1981,
   "asin_rank": 2,
   "asin_name": "WaterWipes Sensitive+ Newborn & Baby Wipes, 3-In-1 Cleans, Cares, Protects, 99.9",
   "click_share": 16.27,
   "conv_share": 10.02,
   "is_ours": false
  },
  {
   "term": "water wipes",
   "rank": 1981,
   "asin_rank": 3,
   "asin_name": "WaterWipes Sensitive+ Newborn & Baby Wipes, 3-In-1 Cleans, Cares, Protects, 99.9",
   "click_share": 13.84,
   "conv_share": 12.32,
   "is_ours": false
  },
  {
   "term": "water wipes",
   "rank": 2050,
   "asin_rank": 1,
   "asin_name": "WaterWipes Sensitive+ Newborn & Baby Wipes, 3-In-1 Cleans, Cares, Protects, 99.9",
   "click_share": 32.08,
   "conv_share": 23.31,
   "is_ours": false
  },
  {
   "term": "toddler cups",
   "rank": 5924,
   "asin_rank": 2,
   "asin_name": "Dr. Brown's Milestones Baby's First Straw Cup, Training Cup with Weighted Straw,",
   "click_share": 8.41,
   "conv_share": 2.46,
   "is_ours": false
  },
  {
   "term": "toddler cups",
   "rank": 6085,
   "asin_rank": 1,
   "asin_name": "Zak Designs Kelso Toddler Cups For Travel or At Home, 15oz 2-Pack Durable Plasti",
   "click_share": 12.32,
   "conv_share": 3.16,
   "is_ours": false
  },
  {
   "term": "toddler cups",
   "rank": 6085,
   "asin_rank": 3,
   "asin_name": "Munchkin Sippy Cups for Toddlers 1-3, Spill Proof Miracle 360 Cup, 10 Ounce, 2 P",
   "click_share": 3.1,
   "conv_share": 3.43,
   "is_ours": false
  },
  {
   "term": "sippy cup",
   "rank": 15868,
   "asin_rank": 2,
   "asin_name": "NUK Fun Grips Hard Spout Sippy Cup, 10 oz. | Easy to Hold, BPA Free, Spill Proof",
   "click_share": 5.13,
   "conv_share": 3.91,
   "is_ours": false
  },
  {
   "term": "sippy cup",
   "rank": 15868,
   "asin_rank": 3,
   "asin_name": "Tommee Tippee Insulated 9oz Sporty Spout Toddler Water Bottle, No Spill, Sippy C",
   "click_share": 4.23,
   "conv_share": 2.27,
   "is_ours": false
  },
  {
   "term": "sippy cup",
   "rank": 16609,
   "asin_rank": 1,
   "asin_name": "Munchkin Sippy Cup for 6 Month Old and Up, Spill Proof Miracle 360 Toddler Cups ",
   "click_share": 7.97,
   "conv_share": 6.52,
   "is_ours": false
  },
  {
   "term": "baby bottle",
   "rank": 22401,
   "asin_rank": 1,
   "asin_name": "Dr. Brown's Natural Flow Anti-Colic Options+ Narrow Baby Bottle, 8 oz/250 mL, wi",
   "click_share": 7.48,
   "conv_share": 6.29,
   "is_ours": false
  },
  {
   "term": "baby bottle",
   "rank": 22401,
   "asin_rank": 2,
   "asin_name": "NUK Smooth Flow Anti Colic Baby Bottle, 5 oz, Elephant",
   "click_share": 4.68,
   "conv_share": 5.63,
   "is_ours": false
  },
  {
   "term": "baby bottle",
   "rank": 23252,
   "asin_rank": 3,
   "asin_name": "Dr. Brown's Anti-Colic Options+ Narrow Sippy Bottle Starter Kit, 8oz/250mL, with",
   "click_share": 4.27,
   "conv_share": 6.2,
   "is_ours": false
  }
 ],
 "traffic_sources": [
  {
   "source": "direct / none",
   "sessions": 20891,
   "users": 0,
   "revenue": 0.0,
   "conversions": 476,
   "conv_rate": 2.28
  }
 ],
 "pnl_polar": {
  "months": [
   "Jun 25",
   "Jul 25",
   "Aug 25",
   "Sep 25",
   "Oct 25",
   "Nov 25",
   "Dec 25",
   "FY2025",
   "Jan 26",
   "Feb 26",
   "Mar 26"
  ],
  "fy2025_idx": 7,
  "brand_sales": {
   "Grosmimi": {
    "values": [
     540650,
     707647,
     619650,
     542939,
     614006,
     643945,
     557654,
     4226491,
     624480,
     554741,
     444936
    ],
    "color": "#8b5cf6"
   },
   "Naeiae": {
    "values": [
     17503,
     18264,
     12996,
     10933,
     5792,
     28572,
     29155,
     123215,
     12259,
     12271,
     11672
    ],
    "color": "#eab308"
   },
   "CHA&MOM": {
    "values": [
     1798,
     4619,
     5195,
     8511,
     7663,
     11824,
     7647,
     47257,
     8431,
     6797,
     3256
    ],
    "color": "#0ea5e9"
   },
   "Alpremio": {
    "values": [
     1762,
     2804,
     2752,
     4319,
     6101,
     6171,
     5146,
     29055,
     6391,
     7786,
     5008
    ],
    "color": "#f97316"
   },
   "Other": {
    "values": [
     5863,
     12433,
     12502,
     6160,
     4758,
     4779,
     1165,
     47660,
     2373,
     11759,
     2074
    ],
    "color": "#94a3b8"
   }
  },
  "total_revenue": [
   573439,
   758201,
   665597,
   579021,
   643076,
   700069,
   601931,
   4521334,
   656308,
   605113,
   469019
  ],
  "cogs": [
   237213,
   319599,
   250562,
   216986,
   250072,
   280762,
   227237,
   1782431,
   243697,
   211802,
   171092
  ],
  "gross_margin": [
   336226,
   438602,
   415035,
   362034,
   393004,
   419308,
   374694,
   2738903,
   412612,
   393311,
   297928
  ],
  "ad_spend": {
   "onzenna": [
    16451,
    21579,
    24911,
    27700,
    31719,
    39600,
    37005,
    198965,
    38519,
    39411,
    22300
   ],
   "amazon": [
    0,
    0,
    0,
    0,
    0,
    0,
    34382,
    34382,
    79637,
    80371,
    64970
   ],
   "total": [
    16451,
    21579,
    24911,
    27700,
    31719,
    39600,
    71387,
    233347,
    118156,
    119783,
    87270
   ]
  },
  "ad_spend_detail": {
   "google": [
    9635,
    13051,
    13380,
    12939,
    13764,
    13984,
    12712,
    89465,
    11117,
    12652,
    7434
   ],
   "amz_grosmimi": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
   ],
   "amz_chaenmom": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
   ],
   "amz_naeiae": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
   ]
  },
  "sales_from_ads": {
   "onzenna": [
    42958,
    63075,
    99352,
    119681,
    85053,
    90896,
    57523,
    558538,
    58782,
    52161,
    22503
   ],
   "amazon": [
    0,
    0,
    0,
    0,
    0,
    0,
    224013,
    224013,
    387330,
    360432,
    282340
   ],
   "total": [
    42958,
    63075,
    99352,
    119681,
    85053,
    90896,
    281536,
    782551,
    446112,
    412592,
    304843
   ]
  },
  "organic": {
   "onzenna": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
   ],
   "amazon": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
   ],
   "total": [
    530481,
    695126,
    566245,
    459340,
    558023,
    609173,
    320395,
    3738783,
    210196,
    192521,
    164176
   ]
  },
  "influencer_spend": [
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0
  ],
  "cm_after_ads": [
   319775,
   417023,
   390124,
   334334,
   361285,
   379708,
   303307,
   2505556,
   294456,
   273528,
   210658
  ],
  "cm_final": [
   319775,
   417023,
   390124,
   334334,
   361285,
   379708,
   303307,
   2505556,
   294456,
   273528,
   210658
  ]
 }
};