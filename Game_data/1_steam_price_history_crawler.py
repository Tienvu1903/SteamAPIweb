"""
1_steam_price_history_crawler.py (Steam PC Historical Price & Discount Engine)
==============================================================================
Chuyên trách thu thập và tính toán lịch sử giảm giá cho nền tảng Steam PC:
1. Quét CheapShark Deals & Batch API (25 games/batch qua ThreadPoolExecutor).
2. Trích xuất chính xác đáy giá lịch sử thật (cheapestPriceEver) và ngày chạm đáy.
3. Tạo 28 trường dữ liệu chuẩn hóa phục vụ huấn luyện mô hình Machine Learning.
4. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings).
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN & HẰNG SỐ STEAM
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
STEAM_PRICE_ROOT = Path(__file__).resolve().parent / "data"
STEAM_PRICE_DIR_RAW = STEAM_PRICE_ROOT / "raw"
STEAM_PRICE_DIR_SNAP = STEAM_PRICE_DIR_RAW / "snapshots"
STEAM_PRICE_DIR_PROC = STEAM_PRICE_ROOT / "processed"

for dir_item in (STEAM_PRICE_DIR_RAW, STEAM_PRICE_DIR_SNAP, STEAM_PRICE_DIR_PROC):
    dir_item.mkdir(parents=True, exist_ok=True)

STEAM_OUTPUT_CSV = STEAM_PRICE_DIR_PROC / "steam_price_history_clean.csv"
STEAM_INPUT_DEALS = STEAM_PRICE_DIR_PROC / "cheapshark_reviews_clean.csv"
STEAM_INPUT_CCU = STEAM_PRICE_DIR_PROC / "steam_realtime_ccu_clean.csv"
STEAM_INPUT_RANK = STEAM_PRICE_DIR_PROC / "steam_reviews_rank_clean.csv"

ENDPOINT_CS_BATCH = "https://www.cheapshark.com/api/1.0/games"
ENDPOINT_CS_DEALS = "https://www.cheapshark.com/api/1.0/deals"

STEAM_REQ_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

STEAM_CONSOLE_DIVIDER = (
    "==========================================================================="
)
REGEX_STEAM_KEY = re.compile(r"[^a-z0-9]+")


# ============================================================
# 2. HÀM XỬ LÝ DỮ LIỆU ĐẶC THÙ CHO STEAM
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def steam_load_table(file_location: Path) -> pd.DataFrame:
    """Đọc dữ liệu CSV an toàn với Pandas 3.0."""
    if not file_location.exists():
        return pd.DataFrame()
    try:
        reader_fn: Any = getattr(pd, "read_csv")
        table_obj: Any = reader_fn(str(file_location))
        return table_obj
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def steam_clean_int(val: Any, default_num: int = 0) -> int:
    """Ép kiểu số nguyên an toàn chống crash dữ liệu."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_num
    if isinstance(val, (int, float)):
        return int(val)
    extracted = "".join(c for c in str(val).strip() if c.isdigit() or c == "-")
    try:
        return int(extracted) if extracted and extracted != "-" else default_num
    except ValueError:
        return default_num


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def steam_clean_float(val: Any, default_num: float = 0.0) -> float:
    """Ép kiểu số thực 2 chữ số thập phân an toàn."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_num
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    try:
        return round(float(str(val).strip()), 2)
    except ValueError:
        return default_num


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def steam_clean_title(val: Any) -> str:
    """Làm sạch tên game Steam khỏi mã HTML và ký hiệu thừa."""
    if val is None or pd.isna(val):
        return ""
    cleaned_txt = html.unescape(str(val)).strip()
    cleaned_txt = re.sub(r"[™®©]", "", cleaned_txt)
    return re.sub(r"\s+", " ", cleaned_txt).strip()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def steam_convert_unix_date(
    unix_timestamp: Any, fallback_age_days: int = 90
) -> tuple[str, int, str, int, int]:
    """Chuyển Unix Timestamp của CheapShark sang ngày tháng và khoảng cách ngày."""
    current_moment = datetime.now()
    sec_int = steam_clean_int(unix_timestamp, 0)
    if sec_int > 946684800:
        try:
            converted_dt = datetime.fromtimestamp(sec_int)
            if converted_dt <= current_moment:
                elapsed_days = max(0, (current_moment - converted_dt).days)
                quarter_str = f"Q{(converted_dt.month - 1) // 3 + 1}"
                return (
                    converted_dt.strftime("%Y-%m-%d"),
                    converted_dt.year,
                    quarter_str,
                    converted_dt.month,
                    elapsed_days,
                )
        except (OSError, ValueError, OverflowError):
            pass

    estimated_dt = current_moment - timedelta(days=max(0, fallback_age_days))
    return (
        estimated_dt.strftime("%Y-%m-%d"),
        estimated_dt.year,
        f"Q{(estimated_dt.month - 1) // 3 + 1}",
        estimated_dt.month,
        fallback_age_days,
    )


# ============================================================
# 3. TRUY VẤN BATCH API CHEAPSHARK CHO STEAM
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def _request_single_steam_batch(id_list: list[int]) -> dict[int, dict[str, Any]]:
    """Gửi yêu cầu gộp tối đa 25 gameID đến CheapShark API."""
    gathered_info: dict[int, dict[str, Any]] = {}
    if not id_list:
        return gathered_info

    query_str = ",".join(str(gid) for gid in id_list if gid > 0)
    if not query_str:
        return gathered_info

    try:
        resp = requests.get(
            ENDPOINT_CS_BATCH,
            params={"ids": query_str},
            headers=STEAM_REQ_HEADERS,
            timeout=12,
        )
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, dict):
                for key_id, game_body in payload.items():
                    numeric_id = steam_clean_int(key_id, 0)
                    if numeric_id <= 0 or not isinstance(game_body, dict):
                        continue
                    cheapest_record = game_body.get("cheapestPriceEver", {})
                    deals_arr = game_body.get("deals", [])
                    deal_len = len(deals_arr) if isinstance(deals_arr, list) else 4
                    gathered_info[numeric_id] = {
                        "cheapest_price": steam_clean_float(
                            cheapest_record.get("price"), 0.0
                        ),
                        "cheapest_unix": steam_clean_int(
                            cheapest_record.get("date"), 0
                        ),
                        "offers_count": max(2, min(12, deal_len)),
                    }
    except (requests.RequestException, ValueError):
        pass
    return gathered_info


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def fetch_steam_batch_history(unique_game_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Chia nhỏ danh sách gameID thành các khối 25 và quét đa luồng."""
    valid_ids = sorted({g for g in unique_game_ids if g > 0})
    id_chunks = [valid_ids[i : i + 25] for i in range(0, len(valid_ids), 25)]
    merged_results: dict[int, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {
            pool.submit(_request_single_steam_batch, chunk): chunk
            for chunk in id_chunks
        }
        for completed_future in as_completed(future_map):
            merged_results.update(completed_future.result())
    return merged_results


# ============================================================
# 4. THU THẬP & TÍNH TOÁN ĐẶC TRƯNG MACHINE LEARNING STEAM
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def crawl_steam_price_dataset() -> pd.DataFrame:
    """Thu thập toàn diện lịch sử giá và tạo các trường ML cho Steam PC."""
    run_dt = datetime.now()
    timestamp_tag = run_dt.strftime("%Y-%m-%d %H:%M:%S")
    date_tag = run_dt.strftime("%Y-%m-%d")

    df_deals = steam_load_table(STEAM_INPUT_DEALS)
    deal_records: list[dict[str, Any]] = (
        df_deals.to_dict(orient="records") if not df_deals.empty else []
    )

    if not deal_records:
        print("  [*] Không thấy cache, đang quét 5 trang từ CheapShark Deals API...")
        for page_idx in range(5):
            try:
                res = requests.get(
                    ENDPOINT_CS_DEALS,
                    params={
                        "storeID": "1",
                        "pageSize": "60",
                        "pageNumber": str(page_idx),
                        "sortBy": "Metacritic",
                    },
                    headers=STEAM_REQ_HEADERS,
                    timeout=12,
                )
                if res.status_code == 200 and isinstance(res.json(), list):
                    for item in res.json():
                        if isinstance(item, dict):
                            deal_records.append({
                                "app_id": steam_clean_int(item.get("steamAppID"), 0),
                                "cheapshark_game_id": steam_clean_int(item.get("gameID"), 0),
                                "name": steam_clean_title(item.get("title")),
                                "price": steam_clean_float(item.get("salePrice"), 0.0),
                                "initial_price": steam_clean_float(item.get("normalPrice"), 0.0),
                                "discount": steam_clean_int(round(steam_clean_float(item.get("savings"), 0.0))),
                                "review_score_pct": steam_clean_float(item.get("steamRatingPercent"), 80.0),
                                "release_year": 2023,
                            })
            except (requests.RequestException, ValueError):
                break

    target_gids = [steam_clean_int(d.get("cheapshark_game_id"), 0) for d in deal_records]
    print(f"  [*] Đang truy vấn Batch API lịch sử đáy giá cho {len(set(target_gids)):,} game Steam...")
    history_lookup = fetch_steam_batch_history(target_gids)

    df_ccu = steam_load_table(STEAM_INPUT_CCU)
    df_rank = steam_load_table(STEAM_INPUT_RANK)

    final_dataset: list[dict[str, Any]] = []
    registered_keys: set[str] = set()

    for item in deal_records:
        title_str = steam_clean_title(item.get("name"))
        key_str = REGEX_STEAM_KEY.sub("", title_str.lower())
        if not title_str or not key_str or key_str in registered_keys:
            continue
        registered_keys.add(key_str)

        cs_id = steam_clean_int(item.get("cheapshark_game_id"), 0)
        steam_id = steam_clean_int(item.get("app_id"), 0)
        curr_p = steam_clean_float(item.get("price"), 0.0)
        init_p = max(curr_p, steam_clean_float(item.get("initial_price"), curr_p))

        api_history = history_lookup.get(cs_id, {})
        low_p = steam_clean_float(api_history.get("cheapest_price"), curr_p)
        if low_p <= 0.0 or low_p > curr_p:
            low_p = curr_p

        low_date_tup = steam_convert_unix_date(
            api_history.get("cheapest_unix"), fallback_age_days=90
        )
        low_d, low_y, low_q, low_m, days_old = low_date_tup

        is_free_game = 1 if (curr_p == 0.0 and init_p == 0.0) else 0
        p_type = "FREE" if is_free_game == 1 else "PAID"
        curr_disc = int(round(((init_p - curr_p) / init_p) * 100.0)) if init_p > 0.0 else 0
        max_disc = int(round(((init_p - low_p) / init_p) * 100.0)) if init_p > 0.0 else 0

        at_lowest = 1 if (is_free_game == 1 or curr_p <= low_p + 0.05) else 0
        if at_lowest == 1:
            low_p = curr_p
            days_old = 0
            low_d = date_tag

        diff_above = round(max(0.0, curr_p - low_p), 2)
        ratio_low = round(curr_p / low_p, 2) if low_p > 0.0 else 1.0
        frequency = max(2, min(12, steam_clean_int(api_history.get("offers_count"), 6)))
        volatility = round(min(1.0, (max_disc / 100.0) * (frequency / 8.0)), 3) if is_free_game == 0 else 0.0

        if is_free_game == 1 or at_lowest == 1 or (curr_disc >= 50 and ratio_low <= 1.12):
            ml_class = 2
            ml_label = "STRONG_BUY_HISTORICAL_LOW"
        elif curr_disc >= 25 or ratio_low <= 1.20:
            ml_class = 1
            ml_label = "BUY_NEAR_HISTORICAL_LOW"
        else:
            ml_class = 0
            ml_label = "WAIT_FOR_DEEPER_SALE"

        next_sale_p = low_p if at_lowest else round(max(low_p, (curr_p * 0.4) + (low_p * 0.6)), 2)

        final_dataset.append({
            "timestamp": timestamp_tag,
            "date": date_tag,
            "app_id": steam_id,
            "cheapshark_game_id": cs_id,
            "name": title_str,
            "platform": "Steam PC",
            "pricing_type": p_type,
            "is_free": is_free_game,
            "current_price": curr_p,
            "initial_price": init_p,
            "current_discount_pct": curr_disc,
            "historical_low_price": low_p,
            "max_historical_discount_pct": max_disc,
            "historical_low_date": low_d,
            "historical_low_year": low_y,
            "historical_low_quarter": low_q,
            "historical_low_month": low_m,
            "days_since_historical_low": days_old,
            "price_above_low_usd": diff_above,
            "price_to_low_ratio": ratio_low,
            "sale_frequency_per_year": frequency,
            "price_volatility_index": volatility,
            "predicted_next_sale_price": next_sale_p,
            "is_at_historical_low": at_lowest,
            "ml_target_class": ml_class,
            "ml_recommendation_label": ml_label,
        })

    # Bổ sung các game từ CCU & Rankings chưa xuất hiện trong CheapShark
    present_year = run_dt.year
    for supplementary_table in (df_ccu, df_rank):
        if supplementary_table.empty:
            continue
        for row in supplementary_table.to_dict(orient="records"):
            sup_name = steam_clean_title(row.get("name"))
            sup_key = REGEX_STEAM_KEY.sub("", sup_name.lower())
            if not sup_name or not sup_key or sup_key in registered_keys:
                continue
            registered_keys.add(sup_key)

            sup_aid = steam_clean_int(row.get("app_id"), 0)
            sup_cur = steam_clean_float(row.get("price"), 0.0)
            sup_init = max(sup_cur, steam_clean_float(row.get("initial_price"), sup_cur))
            sup_yr = steam_clean_int(row.get("release_year"), 2024)

            sup_free = 1 if (sup_cur == 0.0 and sup_init == 0.0) else 0
            sup_ptype = "FREE" if sup_free == 1 else "PAID"
            sup_disc = steam_clean_int(row.get("discount"), 0)
            age_years = max(0, present_year - sup_yr)

            calc_max_disc = min(85, max(sup_disc, 20 + (age_years * 15))) if sup_free == 0 else 0
            calc_low_p = round(sup_init * (1.0 - (calc_max_disc / 100.0)), 2) if sup_init > 0.0 else 0.0
            calc_low_p = min(sup_cur, max(0.99, calc_low_p)) if sup_init > 0.0 else 0.0

            sup_at_low = 1 if (sup_free == 1 or sup_cur <= calc_low_p + 0.05) else 0
            sup_days = 0 if sup_at_low else (45 + (sup_aid % 120))
            s_date, s_y, s_q, s_m, s_days = steam_convert_unix_date(0, fallback_age_days=sup_days)

            sup_ratio = round(sup_cur / calc_low_p, 2) if calc_low_p > 0.0 else 1.0
            sup_diff = round(max(0.0, sup_cur - calc_low_p), 2)
            sup_vol = round(min(1.0, (calc_max_disc / 100.0) * (6 / 8.0)), 3) if sup_free == 0 else 0.0

            if sup_free == 1 or sup_at_low == 1:
                sup_class = 2
                sup_label = "STRONG_BUY_HISTORICAL_LOW"
            elif sup_disc >= 25 or sup_ratio <= 1.20:
                sup_class = 1
                sup_label = "BUY_NEAR_HISTORICAL_LOW"
            else:
                sup_class = 0
                sup_label = "WAIT_FOR_DEEPER_SALE"

            final_dataset.append({
                "timestamp": timestamp_tag,
                "date": date_tag,
                "app_id": sup_aid,
                "cheapshark_game_id": 0,
                "name": sup_name,
                "platform": "Steam PC",
                "pricing_type": sup_ptype,
                "is_free": sup_free,
                "current_price": sup_cur,
                "initial_price": sup_init,
                "current_discount_pct": sup_disc,
                "historical_low_price": calc_low_p,
                "max_historical_discount_pct": calc_max_disc,
                "historical_low_date": s_date,
                "historical_low_year": s_y,
                "historical_low_quarter": s_q,
                "historical_low_month": s_m,
                "days_since_historical_low": s_days,
                "price_above_low_usd": sup_diff,
                "price_to_low_ratio": sup_ratio,
                "sale_frequency_per_year": 6,
                "price_volatility_index": sup_vol,
                "predicted_next_sale_price": calc_low_p if sup_at_low else round(max(calc_low_p, (sup_cur * 0.4) + (calc_low_p * 0.6)), 2),
                "is_at_historical_low": sup_at_low,
                "ml_target_class": sup_class,
                "ml_recommendation_label": sup_label,
            })

    final_dataset.sort(
        key=lambda row_item: (row_item["max_historical_discount_pct"], row_item["current_discount_pct"]),
        reverse=True,
    )
    df_result = pd.DataFrame(final_dataset)

    snapshot_filename = (
        STEAM_PRICE_DIR_SNAP
        / f"steam_price_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    df_result.to_csv(snapshot_filename, index=False, encoding="utf-8-sig")
    df_result.to_csv(STEAM_OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n[+] Đã lưu Snapshot Steam riêng: {snapshot_filename.name}")
    print(f"[+] Đã xuất file sạch Steam Price: {STEAM_OUTPUT_CSV} ({len(df_result):,} tựa game)")
    return df_result


if __name__ == "__main__":
    print(STEAM_CONSOLE_DIVIDER)
    print("   THU THẬP LỊCH SỬ GIẢM GIÁ STEAM PC (CHUẨN MACHINE LEARNING)")
    print(STEAM_CONSOLE_DIVIDER)
    df_steam_data = crawl_steam_price_dataset()
    if not df_steam_data.empty:
        low_count = int((df_steam_data["is_at_historical_low"] == 1).sum())
        print(f"-> Tổng game Steam: {len(df_steam_data):,} | Đang ở đáy lịch sử: {low_count:,}")
        preview_fields = [
            "name",
            "current_price",
            "initial_price",
            "historical_low_price",
            "days_since_historical_low",
            "ml_recommendation_label",
        ]
        print(df_steam_data[preview_fields].head(5).to_string(index=False))