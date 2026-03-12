"""Save Polar query results Q5-Q8 (ads) to JSON files."""
import json, os

DIR = os.path.dirname(os.path.abspath(__file__))

def save(name, columns, rows, total_data):
    table = [dict(zip(columns, r)) for r in rows]
    obj = {"tableData": table, "totalData": total_data}
    path = os.path.join(DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print(f"  Saved {name}: {len(table)} rows")

print("Saving Q5-Q8...")

# === Q5: Amazon Ads by Campaign ===
C5 = ["amazonads_campaign.raw.cost","amazonads_campaign.raw.attributed_sales","amazonads_campaign.raw.clicks","amazonads_campaign.raw.impressions","campaign","date"]
save("q5_amazon_ads_campaign.json", C5, [
[47564.45,114641,36586,9035137,"sp_ppsu_manual","2026-01-01"],
[30537.66,65820,21255,5654321,"sp_ppsu_manual","2026-02-01"],
[14695.44,88242,22729,3118253,"sp_flip top_manual","2026-01-01"],
[9064.85,48337,13573,2135542,"sp_flip top_manual","2026-02-01"],
[5280.11,9551,6662,793459,"sp_fliptop_auto","2026-01-01"],
[2968.24,5790,5330,936722,"sp_fliptop_auto","2026-02-01"],
[1757.21,17929,2957,708226,"sp_stage1_keyword","2026-01-01"],
[1626.28,26463,3122,62693,"sp_fliptop_defensive","2026-01-01"],
[1502.89,16975,2450,451222,"sp_knotted_manual","2026-01-01"],
[1468.92,14984,1630,194484,"sb-manual - 11/2/2022 10:20:00","2026-01-01"],
[1244.37,31078,2995,61388,"sp_stage1_10_defensive","2026-01-01"],
[1168.65,41225,3486,166270,"sp_replacements_defensive","2026-01-01"],
[1065.74,22627,2509,42739,"sp_stage1_6_defensive","2026-01-01"],
[938.91,8747,1472,432015,"sp_stage1_keyword","2026-02-01"],
[904.70,8371,1408,305223,"sp_knotted_manual","2026-02-01"],
[818.82,7896,794,130558,"sb-manual - 11/2/2022 10:20:00","2026-02-01"],
[762.04,13157,1495,21694,"sp_fliptop_defensive","2026-02-01"],
[738.06,23490,2111,85727,"sp_replacements_defensive","2026-02-01"],
[666.75,1750,389,156296,"cha&mom _competitor targeting_sp_manual","2026-01-01"],
[596.35,6791,1515,614073,"sp_ppsu_auto","2026-01-01"],
[556.14,1130,305,115180,"sp_manual_cha&mom _competitor targeting","2026-01-01"],
[538.88,11369,1278,28024,"sp_stage1_10_defensive","2026-02-01"],
[495.75,10102,1201,22811,"sp_stage1_6_defensive","2026-02-01"],
[274.23,495,154,83396,"cha&mom _competitor targeting_sp_manual","2026-02-01"],
[243.79,2425,638,449335,"sp_ppsu_auto","2026-02-01"],
[153.01,626,203,47149,"cha&mom_wash_sp_auto","2026-01-01"],
[151.88,860,188,66151,"cha&mom_lotion_sp_auto","2026-01-01"],
[150.15,512,151,60940,"cha&mom_lotion_sp_auto","2026-02-01"],
[140.68,400,68,47080,"cha&mom_keyword_lotion_sp_manual","2026-01-01"],
[126.19,145,222,76815,"sd_audiencetargeting","2026-01-01"],
[124.59,205,47,24549,"sd_stage2cup","2026-01-01"],
[116.82,287,62,42624,"cha&mom_keyword_lotion_sp_manual","2026-02-01"],
[106.72,664,144,33410,"sp_auto_cha&mom_wash","2026-01-01"],
[99.43,76,148,38905,"sd_audiencetargeting","2026-02-01"],
[91.74,287,47,23745,"sp_manual_cha&mom_keyword_lotion","2026-01-01"],
[69.86,401,97,39919,"sp_auto_cha&mom_lotion","2026-01-01"],
[67.98,290,91,38217,"cha&mom_cream_sp_auto","2026-01-01"],
[49.08,108,63,16738,"cha&mom_wash_sp_auto","2026-02-01"],
[48.94,77,27,11354,"sd_stage2cup","2026-02-01"],
[38.29,229,48,9743,"cha&mom_cream_sp_auto","2026-02-01"],
[34.94,115,47,17002,"sp_auto_cha&mom_cream","2026-01-01"],
[33.18,1387,266,20593,"sp_all_auto","2026-01-01"],
[8.85,290,91,8222,"sp_all_auto","2026-02-01"],
[0,0,0,0,"sb_offensive","2026-01-01"],
[0,0,0,0,"sb_offensive","2026-02-01"],
], [{"amazonads_campaign.raw.cost":129091.56,"amazonads_campaign.raw.attributed_sales":606341,"amazonads_campaign.raw.clicks":140054,"amazonads_campaign.raw.impressions":26427944}])

# === Q6: Facebook Ads by Campaign ===
C6 = ["facebookads_ad_platform_and_device.raw.spend","facebookads_ad_platform_and_device.raw.purchases_conversion_value","facebookads_ad_platform_and_device.raw.clicks","facebookads_ad_platform_and_device.raw.impressions","campaign","date"]
save("q6_facebook_ads_campaign.json", C6, [
[4615.07,0,67407,512079,"amz_traffic_dental mom & livfuselli (may, aug)_20251120-01","2026-01-01"],
[3715.96,8622.46,7098,133217,"shopify | cvr | wl | livfuselli (new)","2026-01-01"],
[3069.47,8308.89,2672,156691,"shopify | cvr | tumbler","2026-01-01"],
[2563.51,0,34438,253935,"amz_traffic_dental mom & livfuselli (may, aug)_20251120-01","2026-02-01"],
[2046.76,2042.62,2979,54160,"shopify | cvr | wl | livfuselli (new)","2026-02-01"],
[2038.31,0,23314,270054,"amz_traffic_dentalmom_wl_202601","2026-01-01"],
[1969.18,0,19725,321804,"amz_traffic_dental mom_stainless_strawcup_20260107","2026-01-01"],
[1708.46,4619.16,1502,59234,"shopify | cvr | gm | tumbler | wl - dental mom","2026-01-01"],
[1690.91,2850.60,1329,80474,"shopify | cvr | tumbler","2026-02-01"],
[1654.19,0,11643,259204,"amz_traffic_grosmimi_20251204","2026-01-01"],
[1367.29,58.77,11508,188112,"amz_traffic_dental mom_stainless_strawcup_20260107","2026-02-01"],
[1362.89,0,13467,168255,"amz_traffic_dentalmom_wl_202601","2026-02-01"],
[1236.31,2690.27,1117,37711,"shopify | cvr | gm | sls cup | wl - dental mom","2026-01-01"],
[1228.29,3124.56,2217,55948,"shopify | cvr | wl | laurence (legacy)","2026-01-01"],
[1188.03,1869.62,959,36161,"shopify | cvr | gm | tumbler | wl - dental mom","2026-02-01"],
[963.59,0,5367,257206,"amz_traffic_naeiae_20251223","2026-01-01"],
[948.90,3097.77,1604,74253,"shopify | cvr | asc campaign (legacy)","2026-01-01"],
[786.00,1732.66,403,38857,"⭐️ shopify | conversion | 2025","2026-01-01"],
[684.36,1152.89,489,23117,"shopify | cvr | gm | stainless","2026-02-01"],
[677.58,436.28,585,30030,"shopify | cvr | love&care","2026-02-01"],
[672.73,2111.93,819,30126,"shopify | cvr | wl | laurence (legacy)","2026-02-01"],
[653.34,9468.90,1221,50552,"shopify | cvr | asc campaign (legacy)","2026-02-01"],
[604.87,0,2522,139866,"amz_traffic_cha&mom_20260123","2026-02-01"],
[599.70,0,10167,79354,"target | traffic | alpremio","2026-02-01"],
[526.29,60.00,313,72071,"pavbgk_kasdgf_roi_pl_lol1_pro93_gh2r52zg","2026-01-01"],
[517.76,134.70,4017,139585,"target | traffic | alpremio_image","2026-02-01"],
[516.32,1012.22,464,14717,"shopify | cvr | gm | sls cup | wl - dental mom","2026-02-01"],
[505.89,679.75,397,23933,"general | cvr| love&care | bundles","2026-02-01"],
[499.85,1486.17,455,22065,"shopify | cvr | gm | stainless","2026-01-01"],
[491.61,996.77,535,15153,"shopify | cvr | alpremio","2026-02-01"],
[413.42,208.14,244,22141,"shopify_chealsea_wl_cm_202601","2026-01-01"],
[357.19,203.51,229,13390,"general | cvr | love&care | wls","2026-02-01"],
[325.91,1202.71,378,22253,"shopify_cvr_newyear_20260101","2026-01-01"],
[322.15,583.16,185,23852,"shopify_cvr_cm_20251202","2026-01-01"],
[312.19,687.08,144,20126,"shopify | cvr | cm | lotion","2026-01-01"],
[295.84,0,5181,35437,"target | traffic | alpremio","2026-01-01"],
[290.05,0,1590,137315,"amz_traffic_cha&mom_20260123","2026-01-01"],
[275.07,499.70,425,8573,"shopify | cvr | alpremio","2026-01-01"],
[216.89,368.52,147,6440,"shopify | cvr | gm | stainless straw","2026-02-01"],
[188.22,415.24,118,4347,"shopify | cvr | alpremio_2","2026-02-01"],
[158.29,175.77,84,5749,"shopify_lauren_wl_cm_202601","2026-01-01"],
[103.78,269.07,61,5675,"shopify | cvr | cm | lotion","2026-02-01"],
[48.50,0,265,19482,"target | traffic | alpremio_image","2026-01-01"],
[0,0,0,0,"shopify_cvr_earlyholiday_20251205","2026-01-01"],
], [{"facebookads_ad_platform_and_device.raw.spend":44410.92,"facebookads_ad_platform_and_device.raw.purchases_conversion_value":61169.89,"facebookads_ad_platform_and_device.raw.clicks":239784,"facebookads_ad_platform_and_device.raw.impressions":3922704}])

# === Q7: Google Ads by Campaign ===
C7 = ["googleads_campaign_and_device.raw.cost","googleads_campaign_and_device.raw.conversion_value","googleads_campaign_and_device.raw.clicks","googleads_campaign_and_device.raw.impressions","campaign","date"]
save("q7_google_ads_campaign.json", C7, [
[9121.10,17326.03,7281,741356,"onzenna | pmax","2026-01-01"],
[5089.86,8076.46,4586,419804,"onzenna | pmax","2026-02-01"],
[2726.44,1641.00,1048,17895,"onzenna | tumbler | pmax","2026-02-01"],
[1996.12,3980.38,1195,40900,"onzenna | tumbler | pmax","2026-01-01"],
], [{"googleads_campaign_and_device.raw.cost":18933.52,"googleads_campaign_and_device.raw.conversion_value":31023.88,"googleads_campaign_and_device.raw.clicks":14110,"googleads_campaign_and_device.raw.impressions":1219955}])

# === Q8: TikTok Ads by Campaign ===
C8 = ["tiktokads_campaign_and_platform.raw.spend","tiktokads_campaign_and_platform.raw.purchases_conversion_value","tiktokads_campaign_and_platform.raw.clicks","tiktokads_campaign_and_platform.raw.impressions","campaign","date"]
save("q8_tiktok_ads_campaign.json", C8, [
[0,0,0,0,"amazon traffic","2026-01-01"],
[0,0,0,0,"ugc | spark","2026-01-01"],
], [{"tiktokads_campaign_and_platform.raw.spend":0,"tiktokads_campaign_and_platform.raw.purchases_conversion_value":0,"tiktokads_campaign_and_platform.raw.clicks":0,"tiktokads_campaign_and_platform.raw.impressions":0}])

print("Q5-Q8 saved successfully!")
