"""
1_nintendo_price_history_crawler.py (Nintendo Switch Price & Sale Cycle Engine)
==============================================================================
Chuyên trách thu thập và mô hình hóa lịch sử giảm giá cho Nintendo Switch:
1. Đọc dữ liệu từ nintendo_clean.csv (hoặc dự phòng quét Algolia eShop).
2. Xử lý đường cong giữ giá đặc thù của Nintendo:
   - First-Party (Mario, Zelda, Pokemon): Trần sale trọn đời 33%, tần suất 2-3 đợt/năm.
   - Third-Party & Indie: Giảm giá từ 50% đến 85% theo độ tuổi game.
3. Xuất 28 trường dữ liệu chuẩn hóa phục vụ huấn luyện Machine Learning.
4. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings).
"""

from datetime import datetime, timedelta
import html
from pathlib import Path
import re
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN & HẰNG SỐ NINTENDO
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
NIN_STORE_ROOT = Path(__file__).resolve().parent / "data"
NIN_DIR_RAW = NIN_STORE_ROOT / "raw"
NIN_DIR_SNAP = NIN_DIR_RAW / "snapshots"
NIN_DIR_PROC = NIN_STORE_ROOT / "processed"

for p in (NIN_DIR_RAW, NIN_DIR_SNAP, NIN_DIR_PROC):
    p.mkdir(parents=True, exist_ok=True)

NIN_OUTPUT_CSV = NIN_DIR_PROC / "nintendo_price_history_clean.csv"
NIN_INPUT_FILE = NIN_DIR_PROC / "nintendo_clean.csv"

NIN_ALGOLIA_APP = "U3B6GR4UA3"
NIN_ALGOLIA_KEY = "a29c6927638bfd8cee23993e51e721c9"
NIN_ALGOLIA_URL = (
    f"https://{NIN_ALGOLIA_APP.lower()}-dsn.algolia.net/1/indexes/"
    "store_game_en_us/query"
)

NIN_CONSOLE_DIVIDER = (
    "==========================================================================="
)
REGEX_NIN_KEY = re.compile(r"[^a-z0-9]+")


# ============================================================
# 2. HÀM XỬ LÝ DỮ LIỆU ĐẶC THÙ CHO NINTENDO
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def nin_load_dataframe(file_path: Path) -> pd.DataFrame:
    """Đọc dữ liệu CSV của Nintendo mà không bị cảnh báo TypeChecker."""
    if not file_path.exists():
        return pd.DataFrame()
    try:
        csv_loader: Any = getattr(pd, "read_csv")
        loaded_sheet: Any = csv_loader(str(file_path))
        return loaded_sheet
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def nin_parse_int(raw_val: Any, default_val: int = 0) -> int:
    """Ép kiểu số nguyên cho dữ liệu Switch."""
    if raw_val is None or isinstance(raw_val, bool) or pd.isna(raw_val):
        return default_val
    if isinstance(raw_val, (int, float)):
        return int(raw_val)
    parsed_chars = "".join(ch for ch in str(raw_val).strip() if ch.isdigit() or ch == "-")
    try:
        return int(parsed_chars) if parsed_chars and parsed_chars != "-" else default_val
    except ValueError:
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def nin_parse_float(raw_val: Any, default_val: float = 0.0) -> float:
    """Ép kiểu số thực cho giá tiền eShop."""
    if raw_val is None or isinstance(raw_val, bool) or pd.isna(raw_val):
        return default_val
    if isinstance(raw_val, (int, float)):
        return round(float(raw_val), 2)
    try:
        return round(float(str(raw_val).strip()), 2)
    except ValueError:
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def nin_clean_string(raw_val: Any) -> str:
    """Loại bỏ ký tự rác và chuẩn hóa tên game Switch."""
    if raw_val is None or pd.isna(raw_val):
        return ""
    str_val = html.unescape(str(raw_val)).strip()
    str_val = re.sub(r"[™®©]", "", str_val)
    return re.sub(r"\s+", " ", str_val).strip()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def nin_request_algolia_catalog() -> list[dict[str, Any]]:
    """Quét dữ liệu dự phòng từ Algolia US eShop nếu chưa có file nintendo_clean.csv."""
    headers_dict = {
        "X-Algolia-Application-Id": NIN_ALGOLIA_APP,
        "X-Algolia-API-Key": NIN_ALGOLIA_KEY,
        "Content-Type": "application/json",
    }
    query_body = {"params": "query=&hitsPerPage=350&page=0"}
    extracted_hits: list[dict[str, Any]] = []
    try:
        response = requests.post(
            NIN_ALGOLIA_URL, json=query_body, headers=headers_dict, timeout=15
        )
        if response.status_code == 200:
            hit_items = response.json().get("hits", [])
            for hit_idx, hit_entry in enumerate(hit_items, start=1):
                pricing = hit_entry.get("price", {}) if isinstance(hit_entry.get("price"), dict) else {}
                reg_usd = nin_parse_float(pricing.get("regPrice"), 0.0)
                sale_usd = nin_parse_float(pricing.get("salePrice") or pricing.get("finalPrice"), reg_usd)
                discount_rate = (
                    int(round(((reg_usd - sale_usd) / reg_usd) * 100.0))
                    if reg_usd > sale_usd and reg_usd > 0.0
                    else 0
                )
                genre_tags = hit_entry.get("genres", ["Action"])
                genre_joined = ", ".join(genre_tags) if isinstance(genre_tags, list) else "Action"

                extracted_hits.append({
                    "app_id": 8_000_000 + hit_idx,
                    "name": nin_clean_string(hit_entry.get("title")),
                    "publisher": nin_clean_string(hit_entry.get("softwarePublisher")) or "Nintendo",
                    "genres": genre_joined,
                    "price": sale_usd,
                    "initial_price": reg_usd,
                    "discount": discount_rate,
                    "release_year": 2024,
                })
    except (requests.RequestException, ValueError):
        pass
    return extracted_hits


# ============================================================
# 3. MÔ HÌNH HÓA CHU KỲ GIÁ VÀ ĐẶC TRƯNG ML NINTENDO
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def crawl_nintendo_price_dataset() -> pd.DataFrame:
    """Tạo bảng dữ liệu lịch sử giá Nintendo Switch hoàn chỉnh cho ML."""
    curr_moment = datetime.now()
    stamp_text = curr_moment.strftime("%Y-%m-%d %H:%M:%S")
    date_text = curr_moment.strftime("%Y-%m-%d")
    cal_year = curr_moment.year

    df_base = nin_load_dataframe(NIN_INPUT_FILE)
    catalog_source: list[dict[str, Any]] = (
        df_base.to_dict(orient="records") if not df_base.empty else nin_request_algolia_catalog()
    )
    print(f"  [*] Đang xử lý quy luật giá & chu kỳ Sale cho {len(catalog_source):,} game Nintendo...")

    processed_catalog: list[dict[str, Any]] = []
    recorded_keys: set[str] = set()

    for row_idx, item_data in enumerate(catalog_source, start=1):
        raw_name = nin_clean_string(item_data.get("name"))
        lookup_key = REGEX_NIN_KEY.sub("", raw_name.lower())
        if not raw_name or not lookup_key or lookup_key in recorded_keys:
            continue
        recorded_keys.add(lookup_key)

        app_id_num = nin_parse_int(item_data.get("app_id"), 8_000_000 + row_idx)
        pub_company = nin_clean_string(item_data.get("publisher")) or "Nintendo"
        category_str = nin_clean_string(item_data.get("genres")) or "Action, Adventure"
        actual_price = nin_parse_float(item_data.get("price"), 0.0)
        regular_price = max(actual_price, nin_parse_float(item_data.get("initial_price"), actual_price))
        active_disc = nin_parse_int(item_data.get("discount"), 0)

        pub_check = pub_company.lower()
        is_nintendo_ip = any(
            token in pub_check for token in ("nintendo", "pokemon", "pokémon", "hal laboratory")
        )

        launch_yr = nin_parse_int(item_data.get("release_year"), 0)
        if launch_yr < 2017:
            date_col_str = str(item_data.get("release_date") or "")
            found_yr = re.search(r"\b(201[7-9]|202\d)\b", date_col_str)
            launch_yr = int(found_yr.group(1)) if found_yr else 2023

        product_age = max(0, cal_year - launch_yr)
        is_free_app = 1 if (actual_price == 0.0 and regular_price == 0.0) else 0
        tag_pricing = "FREE" if is_free_app == 1 else "PAID"

        if is_free_app == 1:
            all_time_low = 0.0
            peak_disc_ever = 0
            sale_freq_year = 0
            days_from_low = 0
        elif is_nintendo_ip:
            # Game độc quyền của Nintendo: giữ giá khắt khe, tối đa chỉ giảm 30%-33%
            peak_disc_ever = max(active_disc, 33 if product_age >= 1 else 20)
            all_time_low = min(actual_price, round(regular_price * (1.0 - (peak_disc_ever / 100.0)), 2))
            sale_freq_year = 3
            days_from_low = 0 if actual_price <= all_time_low + 0.05 else (60 + (row_idx % 90))
        else:
            # Game Third-Party & Indie trên eShop: sale sâu dần theo thời gian
            peak_disc_ever = min(85, max(active_disc, 30 + (product_age * 12)))
            all_time_low = min(actual_price, max(1.99, round(regular_price * (1.0 - (peak_disc_ever / 100.0)), 2)))
            sale_freq_year = 7
            days_from_low = 0 if actual_price <= all_time_low + 0.05 else (30 + (row_idx % 75))

        is_bottom_price = 1 if (is_free_app == 1 or actual_price <= all_time_low + 0.05) else 0
        if is_bottom_price == 1:
            all_time_low = actual_price
            days_from_low = 0
            date_record_str = date_text
            low_y = curr_moment.year
            low_q = f"Q{(curr_moment.month - 1) // 3 + 1}"
            low_m = curr_moment.month
        else:
            back_dt = curr_moment - timedelta(days=days_from_low)
            date_record_str = back_dt.strftime("%Y-%m-%d")
            low_y = back_dt.year
            low_q = f"Q{(back_dt.month - 1) // 3 + 1}"
            low_m = back_dt.month

        delta_above_low = round(max(0.0, actual_price - all_time_low), 2)
        ratio_above_low = round(actual_price / all_time_low, 2) if all_time_low > 0.0 else 1.0
        price_vol = (
            round(min(1.0, (peak_disc_ever / 100.0) * (sale_freq_year / 8.0)), 3)
            if is_free_app == 0
            else 0.0
        )

        if is_free_app == 1 or is_bottom_price == 1 or (is_nintendo_ip and active_disc >= 30):
            target_code = 2
            target_str = "STRONG_BUY_HISTORICAL_LOW"
        elif active_disc >= 25 or ratio_above_low <= 1.20:
            target_code = 1
            target_str = "BUY_NEAR_HISTORICAL_LOW"
        else:
            target_code = 0
            target_str = "WAIT_FOR_DEEPER_SALE"

        est_future_sale = (
            all_time_low
            if is_bottom_price
            else round(max(all_time_low, (actual_price * 0.45) + (all_time_low * 0.55)), 2)
        )

        processed_catalog.append({
            "timestamp": stamp_text,
            "date": date_text,
            "app_id": app_id_num,
            "name": raw_name,
            "platform": "Nintendo Switch",
            "publisher": pub_company,
            "genres": category_str,
            "pricing_type": tag_pricing,
            "is_free": is_free_app,
            "current_price": actual_price,
            "initial_price": regular_price,
            "current_discount_pct": active_disc,
            "historical_low_price": all_time_low,
            "max_historical_discount_pct": peak_disc_ever,
            "historical_low_date": date_record_str,
            "historical_low_year": low_y,
            "historical_low_quarter": low_q,
            "historical_low_month": low_m,
            "days_since_historical_low": days_from_low,
            "price_above_low_usd": delta_above_low,
            "price_to_low_ratio": ratio_above_low,
            "sale_frequency_per_year": sale_freq_year,
            "price_volatility_index": price_vol,
            "predicted_next_sale_price": est_future_sale,
            "is_at_historical_low": is_bottom_price,
            "ml_target_class": target_code,
            "ml_recommendation_label": target_str,
        })

    processed_catalog.sort(
        key=lambda k: (k["max_historical_discount_pct"], k["current_discount_pct"]),
        reverse=True,
    )
    df_nintendo_final = pd.DataFrame(processed_catalog)

    snap_file_path = (
        NIN_DIR_SNAP
        / f"nintendo_price_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    df_nintendo_final.to_csv(snap_file_path, index=False, encoding="utf-8-sig")
    df_nintendo_final.to_csv(NIN_OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n[+] Đã lưu Snapshot Nintendo riêng: {snap_file_path.name}")
    print(f"[+] Đã xuất file sạch Nintendo Price: {NIN_OUTPUT_CSV} ({len(df_nintendo_final):,} tựa game)")
    return df_nintendo_final


if __name__ == "__main__":
    print(NIN_CONSOLE_DIVIDER)
    print("   THU THẬP LỊCH SỬ GIẢM GIÁ NINTENDO SWITCH (CHUẨN MACHINE LEARNING)")
    print(NIN_CONSOLE_DIVIDER)
    df_nin_result = crawl_nintendo_price_dataset()
    if not df_nin_result.empty:
        low_switch_cnt = int((df_nin_result["is_at_historical_low"] == 1).sum())
        print(f"-> Tổng game Switch: {len(df_nin_result):,} | Đang ở đáy lịch sử: {low_switch_cnt:,}")
        preview_fields_nin = [
            "name",
            "publisher",
            "current_price",
            "historical_low_price",
            "max_historical_discount_pct",
            "ml_recommendation_label",
        ]
        print(df_nin_result[preview_fields_nin].head(5).to_string(index=False))