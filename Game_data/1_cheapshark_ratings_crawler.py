# noinspection DuplicatedCode
"""
1_cheapshark_ratings_crawler.py (Production-Ready Review & Deal Aggregator - Source 2)
======================================================================================
Thu thập dữ liệu đánh giá chéo Metacritic + Steam User Ratings + Độ bán chạy từ CheapShark API:
1. Quét 4 phân khúc rõ rệt:
   - Game được đánh giá Metacritic cao nhất (Highest Metacritic Score)
   - Game được người chơi đánh giá cao nhất (Highest Steam User Rating)
   - Game bị đánh giá thấp nhất / tệ nhất (Lowest Rated Games - chiều tăng dần)
   - Game bán chạy & Deal hot nhất hiện tại (Best Selling / Top Deal Rating)
2. Trích xuất thực tế: Steam AppID, Tên game, Giá bán ($), Giá gốc ($), % Giảm giá,
   Điểm Metacritic (0-100), Điểm Steam Rating (0-100%), Tổng lượt Review, Nhãn đánh giá,
   Ngày phát hành kèm Năm (release_year), Quý (release_quarter), Tháng (release_month).
3. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN LƯU TRỮ
# ============================================================
CS_ROOT = Path(__file__).resolve().parent
CS_RAW_DIR = CS_ROOT / "data" / "raw"
CS_SNAP_DIR = CS_RAW_DIR / "snapshots"
CS_PROC_DIR = CS_ROOT / "data" / "processed"

for _folder in (CS_RAW_DIR, CS_SNAP_DIR, CS_PROC_DIR):
    _folder.mkdir(parents=True, exist_ok=True)

CS_HISTORY_CSV = CS_RAW_DIR / "cheapshark_reviews_history.csv"
CS_CLEAN_CSV = CS_PROC_DIR / "cheapshark_reviews_clean.csv"

CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"

CS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

LINE_SEP = "========================================================================"


def load_csv_cheapshark(csv_file: Path) -> pd.DataFrame:
    """Đọc CSV an toàn không cảnh báo Overload trên PyCharm + Pandas 3.0."""
    # noinspection PyTypeChecker
    loader: Any = getattr(pd, "read_csv")
    return loader(str(csv_file))


def convert_unix_to_period(unix_ts: Any) -> tuple[str, int, str, int]:
    """Chuyển Unix Timestamp phát hành của CheapShark sang (YYYY-MM-DD, Năm, Quý, Tháng)."""
    try:
        ts_val = int(unix_ts or 0)
        if ts_val > 0:
            dt_val = datetime.fromtimestamp(ts_val)
            q_str = f"Q{(dt_val.month - 1) // 3 + 1}"
            return dt_val.strftime("%Y-%m-%d"), dt_val.year, q_str, dt_val.month
    except (ValueError, TypeError, OSError):
        pass
    now_dt = datetime.now()
    return now_dt.strftime("%Y-%m-%d"), now_dt.year, f"Q{(now_dt.month - 1) // 3 + 1}", now_dt.month


def evaluate_combined_quality(
    metacritic: int, steam_pct: int, steam_count: int, sale_price: float, deal_score: float
) -> tuple[str, str]:
    """
    Phân nhóm chất lượng đánh giá (review_tier) và tín hiệu mua (signal):
    - TOP_RATED_MASTERPIECE: Metacritic >= 85 hoặc Steam Rating >= 90%
    - BEST_SELLER_HIGH_VALUE: Deal Rating >= 8.0 và đánh giá >= 75%
    - MIXED_AVERAGE: Đánh giá trung bình (55% - 74%)
    - LOWEST_RATED_POOR: Đánh giá thấp (< 55% hoặc Metacritic < 55)
    """
    effective_score = steam_pct if steam_pct > 0 else metacritic
    if metacritic >= 85 or (steam_pct >= 90 and steam_count >= 500):
        return "TOP_RATED_MASTERPIECE", "STRONG_BUY"
    if effective_score >= 75 and (deal_score >= 8.0 or sale_price <= 19.99):
        return "BEST_SELLER_HIGH_VALUE", "BUY"
    if 0 < effective_score < 55 or (0 < metacritic < 55):
        return "LOWEST_RATED_POOR", "AVOID"
    return "MIXED_AVERAGE", "HOLD"


# ============================================================
# 2. QUÉT DỮ LIỆU METACRITIC + STEAM REVIEWS TỪ CHEAPSHARK API
# ============================================================
def crawl_cheapshark_reviews(target_limit: int = 800) -> pd.DataFrame:
    """
    Quét 4 chiều dữ liệu trên CheapShark (StoreID=1 là Steam chính thức):
    - Chiều 1: Điểm Metacritic cao nhất (sortBy=Metacritic, desc=0)
    - Chiều 2: Điểm người dùng Steam cao nhất (sortBy=Reviews, desc=0)
    - Chiều 3: Game bị đánh giá thấp nhất / Tệ nhất (sortBy=Reviews, desc=1 - đảo chiều)
    - Chiều 4: Game đang bán chạy / Deal hot nhất (sortBy=Deal Rating, desc=0)
    """
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    print(f"[{current_time}] Đang kết nối CheapShark & Metacritic Aggregator API...")
    session = requests.Session()
    session.headers.update(CS_HEADERS)

    records_by_key: dict[str, dict[str, Any]] = {}

    # Mỗi trang trả về tối đa 60 game
    crawl_modes = [
        ("Metacritic Cao Nhất (Critic Top Rated)", "Metacritic", 0, 4),
        ("Người Chơi Đánh Giá Cao Nhất (User Top Rated)", "Reviews", 0, 5),
        ("Game Đánh Giá Thấp Nhất (Lowest Rated Games)", "Reviews", 1, 4),
        ("Game Bán Chạy & Deal Hot Nhất (Best Sellers)", "Deal Rating", 0, 4),
    ]

    for mode_label, sort_field, desc_flag, max_pages in crawl_modes:
        if len(records_by_key) >= target_limit:
            break

        print(f"\n[*] Đang thu thập phân khúc: {mode_label}...")
        for page_num in range(max_pages):
            if len(records_by_key) >= target_limit:
                break

            # Ép kiểu toàn bộ giá trị sang str để không bị PyCharm báo lỗi kiểu dữ liệu _VT
            params: dict[str, str] = {
                "storeID": "1",
                "pageSize": "60",
                "pageNumber": str(page_num),
                "sortBy": str(sort_field),
                "desc": str(desc_flag),
            }

            try:
                resp = session.get(CHEAPSHARK_DEALS_URL, params=params, timeout=15)
                if resp.status_code != 200:
                    print(f"  [Cảnh báo] HTTP {resp.status_code} tại trang {page_num + 1}")
                    break

                deals = resp.json()
                if not isinstance(deals, list) or not deals:
                    break

                added_cnt = 0
                for d in deals:
                    if not isinstance(d, dict):
                        continue

                    title = str(d.get("title") or "").strip()
                    steam_app_id = int(d.get("steamAppID") or 0)
                    game_id = str(d.get("gameID") or "")
                    unique_key = (
                        f"{steam_app_id}_{title.lower()}"
                        if steam_app_id > 0
                        else f"{game_id}_{title.lower()}"
                    )

                    if not title or unique_key in records_by_key:
                        continue

                    sale_price = round(float(d.get("salePrice") or 0.0), 2)
                    normal_price = round(float(d.get("normalPrice") or sale_price), 2)
                    savings_pct = int(round(float(d.get("savings") or 0.0)))
                    is_free = 1 if sale_price == 0.0 else 0

                    metacritic_score = int(d.get("metacriticScore") or 0)
                    steam_rating_pct = int(d.get("steamRatingPercent") or 0)
                    steam_rating_count = int(d.get("steamRatingCount") or 0)
                    steam_rating_text = str(d.get("steamRatingText") or "Unrated").strip()
                    deal_rating = round(float(d.get("dealRating") or 0.0), 2)

                    rel_date, rel_year, rel_quarter, rel_month = convert_unix_to_period(
                        d.get("releaseDate")
                    )
                    review_tier, signal = evaluate_combined_quality(
                        metacritic_score, steam_rating_pct, steam_rating_count, sale_price, deal_rating
                    )

                    if metacritic_score > 0 and steam_rating_pct > 0:
                        combined_score = round((metacritic_score + steam_rating_pct) / 2.0, 2)
                    else:
                        combined_score = float(max(metacritic_score, steam_rating_pct))

                    records_by_key[unique_key] = {
                        "timestamp": current_time,
                        "date": current_date,
                        "hour": current_hour,
                        "app_id": steam_app_id,
                        "cheapshark_game_id": int(game_id) if game_id.isdigit() else 0,
                        "name": title,
                        "price": sale_price,
                        "initial_price": normal_price,
                        "discount": savings_pct,
                        "is_free": is_free,
                        "metacritic_score": metacritic_score,
                        "steam_rating_pct": steam_rating_pct,
                        "steam_rating_count": steam_rating_count,
                        "steam_rating_text": steam_rating_text,
                        "combined_score": combined_score,
                        "deal_rating_score": deal_rating,
                        "release_date": rel_date,
                        "release_year": rel_year,
                        "release_quarter": rel_quarter,
                        "release_month": rel_month,
                        "review_tier": review_tier,
                        "signal": signal,
                    }
                    added_cnt += 1

                print(
                    f"  -> Trang {page_num + 1}/{max_pages}: +{added_cnt:>2} game mới "
                    f"(Tổng tích lũy: {len(records_by_key):,}/{target_limit:,})"
                )
                time.sleep(0.6)

            except (requests.RequestException, ValueError) as err:
                print(f"  [Lỗi kết nối] Trang {page_num + 1}: {err}")
                break

    return pd.DataFrame(list(records_by_key.values())[:target_limit])


# ============================================================
# 3. LƯU TRỮ TÍCH LŨY LỊCH SỬ CHEAPSHARK & METACRITIC
# ============================================================
def save_cheapshark_dataset(df_in: pd.DataFrame) -> pd.DataFrame:
    """Lưu Snapshot, tích lũy lịch sử cheapshark_reviews_history.csv và bản sạch cheapshark_reviews_clean.csv."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_file = CS_SNAP_DIR / f"cheapshark_snapshot_{run_id}.csv"
    df_in.to_csv(snap_file, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã lưu Snapshot riêng: {snap_file.name}")

    df_in["price_change"] = 0.0
    df_in["rating_count_growth"] = 0

    if CS_HISTORY_CSV.exists():
        try:
            old_df = load_csv_cheapshark(CS_HISTORY_CSV)
            print(f"[2] Đã nạp kho lịch sử CheapShark cũ: {len(old_df):,} dòng.")
            merged = pd.concat([old_df, df_in], ignore_index=True)
            merged = merged.drop_duplicates(subset=["date", "hour", "name"], keep="last")
            merged = merged.sort_values(["name", "timestamp"]).reset_index(drop=True)

            merged["price_change"] = merged.groupby("name")["price"].diff().fillna(0.0).round(2)
            merged["rating_count_growth"] = (
                merged.groupby("name")["steam_rating_count"].diff().fillna(0).astype(int)
            )
        except (OSError, pd.errors.ParserError, ValueError) as exc:
            print(f"[Cảnh báo] Khởi tạo lại file lịch sử do lỗi đọc file cũ: {exc}")
            merged = df_in
    else:
        print(f"[2] Khởi tạo kho lịch sử CheapShark & Metacritic lần đầu ({len(df_in):,} dòng).")
        merged = df_in

    merged.to_csv(CS_HISTORY_CSV, index=False, encoding="utf-8-sig")
    clean_df = (
        merged.drop_duplicates(subset=["name"], keep="last")
        .sort_values("combined_score", ascending=False)
        .reset_index(drop=True)
    )
    clean_df.to_csv(CS_CLEAN_CSV, index=False, encoding="utf-8-sig")

    print(f"[3] Đã lưu tích lũy tại : {CS_HISTORY_CSV} (Tổng: {len(merged):,} dòng)")
    print(f"[4] Đã xuất bản sạch tại: {CS_CLEAN_CSV} ({len(clean_df):,} tựa game)")
    return clean_df


if __name__ == "__main__":
    print(LINE_SEP)
    print("   NGUỒN ĐÁNH GIÁ 2: CHEAPSHARK & METACRITIC AGGREGATOR API")
    print(LINE_SEP)

    df_cs = crawl_cheapshark_reviews(target_limit=800)
    if not df_cs.empty:
        df_cs_clean = save_cheapshark_dataset(df_cs)
        lowest_games = df_cs_clean[df_cs_clean["review_tier"] == "LOWEST_RATED_POOR"]
        masterpieces = df_cs_clean[df_cs_clean["review_tier"] == "TOP_RATED_MASTERPIECE"]

        print("\n" + LINE_SEP)
        print("   THỐNG KÊ DỮ LIỆU METACRITIC & STEAM RATINGS VỪA THU THẬP:")
        print(f"   - Tổng số tựa game thu thập       : {len(df_cs_clean):,} game")
        print(f"   - Số game Đỉnh cao (Masterpiece)  : {len(masterpieces):,} game")
        print(f"   - Số game Đánh giá thấp (Poor)    : {len(lowest_games):,} game")
        print(LINE_SEP)

        print("\nTop 3 game điểm cao nhất:")
        top_cols = ["name", "price", "metacritic_score", "steam_rating_pct", "release_year", "review_tier"]
        print(df_cs_clean[top_cols].head(3))

        if not lowest_games.empty:
            print("\nTop 3 game bị đánh giá thấp nhất (để lọc tránh mua):")
            low_cols = ["name", "price", "metacritic_score", "steam_rating_pct", "steam_rating_text", "review_tier"]
            print(lowest_games[low_cols].tail(3))
    else:
        print("❌ Không lấy được dữ liệu từ CheapShark API.")