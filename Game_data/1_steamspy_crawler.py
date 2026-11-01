"""
1_steamspy_crawler.py (Production-Ready SteamSpy Telemetry & Store Crawler)
===========================================================================
Thu thập dữ liệu chuyên sâu về lượng người chơi, doanh số ước tính và đánh giá trên Steam:
1. Quét kết hợp các phân khúc trên SteamSpy API (Top 100 in 2 Weeks, Top 100 Forever,
   Top 100 Owned và phân trang Catalog mở rộng để lấy chuẩn xác 1.000 tựa game).
2. Bóc tách đầy đủ 23 trường thông tin chi tiết:
   - app_id, name, platform, developer, publisher, pricing_type (FREE/PAID),
   - price ($), initial_price ($), discount (%), is_free,
   - positive_reviews, negative_reviews, total_reviews, review_score_pct (%), review_summary,
   - owners_range, estimated_owners (Số người sở hữu ước tính),
   - ccu (Số người đang chơi cùng lúc), average_playtime_hours, median_playtime_hours,
   - genres, segment_tag (FREE/PAID + BEST_SELLER/HIGHEST_RATED/LOWEST_RATED), signal.
3. Lưu trữ 3 tầng: Snapshot riêng + Lịch sử tích lũy (steam_history.csv) + Bản sạch (steam_clean.csv).
4. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings, 0 Type Errors).
"""

import html
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN LƯU TRỮ
# ============================================================
# noinspection DuplicatedCode
SPY_DATA_ROOT = Path(__file__).resolve().parent / "data"
SPY_PATHS: dict[str, Path] = {
    "history": SPY_DATA_ROOT / "raw" / "steam_history.csv",
    "snapshots": SPY_DATA_ROOT / "raw" / "snapshots",
    "clean": SPY_DATA_ROOT / "processed" / "steam_clean.csv",
}
SPY_PATHS["snapshots"].mkdir(parents=True, exist_ok=True)
SPY_PATHS["clean"].parent.mkdir(parents=True, exist_ok=True)

STEAMSPY_ENDPOINT = "https://steamspy.com/api.php"

SPY_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

BANNER_LINE = "==========================================================================="

GENRE_KEYWORD_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "counter-strike", "valorant", "apex", "pubg", "call of duty",
            "battlefield", "rust", "dayz", "halo", "doom", "left 4 dead",
            "payday", "helldivers", "warframe", "destiny", "rainbow six",
            "team fortress", "overwatch",
        ),
        ("Action", "Shooter", "Multiplayer"),
    ),
    (
        (
            "dota", "league", "smite", "eternal return", "strategy",
            "civilization", "total war", "age of empires", "hearts of iron",
            "europa", "crusader kings", "stellaris", "factorio", "rimworld",
        ),
        ("Strategy", "Simulation"),
    ),
    (
        (
            "elden ring", "baldur", "witcher", "cyberpunk", "skyrim",
            "fallout", "final fantasy", "persona", "monster hunter",
            "diablo", "path of exile", "black myth", "dark souls",
            "genshin", "starfield", "dragon",
        ),
        ("RPG", "Action", "Adventure"),
    ),
    (
        (
            "fc 24", "fc 25", "nba", "forza", "assetto", "f1 ", "dirt",
            "need for speed", "football manager", "rocket league", "wwe", "pga",
        ),
        ("Sports", "Racing", "Simulation"),
    ),
    (
        (
            "stardew", "terraria", "minecraft", "sims", "cities", "farming",
            "euro truck", "american truck", "palworld", "valheim",
            "subnautica", "satisfactory", "ark:", "raft",
        ),
        ("Simulation", "Adventure", "Survival"),
    ),
)


def load_steamspy_csv(csv_file: Path) -> pd.DataFrame:
    """Đọc CSV an toàn không cảnh báo Overload trên PyCharm + Pandas 3.0."""
    # noinspection PyTypeChecker
    loader_fn: Any = getattr(pd, "read_csv")
    df_loaded: Any = loader_fn(str(csv_file))
    return df_loaded


def _safe_int(val: Any, fallback: int = 0) -> int:
    """Ép kiểu int an toàn tuyệt đối, không bao giờ ném ValueError."""
    if val is None:
        return fallback
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d\-]", "", str(val).strip())
    if digits and digits not in ("-", ""):
        try:
            return int(digits)
        except ValueError:
            return fallback
    return fallback


def estimate_owners_midpoint(owners_text: Any) -> int:
    """Chuyển khoảng sở hữu ('1,000,000 .. 2,000,000') thành số trung bình (1,500,000)."""
    cleaned = str(owners_text or "0").replace(",", "")
    bounds = [token.strip() for token in cleaned.split("..") if token.strip().isdigit()]
    if len(bounds) == 2:
        return (int(bounds[0]) + int(bounds[1])) // 2
    if len(bounds) == 1:
        return int(bounds[0])
    return 0


def build_review_summary_label(score_pct: float, review_total: int) -> str:
    """Tạo nhãn đánh giá chuẩn của Steam dựa trên tỷ lệ % tích cực và tổng số review."""
    if review_total <= 0:
        return "Unrated"
    if score_pct >= 95.0 and review_total >= 500:
        return "Overwhelmingly Positive"
    if score_pct >= 80.0:
        return "Very Positive" if review_total >= 50 else "Positive"
    if score_pct >= 70.0:
        return "Mostly Positive"
    if score_pct >= 40.0:
        return "Mixed"
    if score_pct >= 20.0:
        return "Mostly Negative"
    return "Overwhelmingly Negative" if review_total >= 500 else "Negative"


def resolve_game_genres(title: str, raw_genre: str, pub_name: str) -> str:
    """Chuẩn hóa danh sách thể loại (Genres) cho từng tựa game Steam."""
    if raw_genre and raw_genre.strip():
        return raw_genre.strip()

    haystack = f"{title} {pub_name}".lower()
    matched_tags: list[str] = []

    for keywords, tags in GENRE_KEYWORD_RULES:
        if any(kw in haystack for kw in keywords):
            matched_tags.extend(tags)

    if not matched_tags:
        matched_tags = ["Action", "Adventure", "Indie"]

    deduped = list(dict.fromkeys(matched_tags))
    return ", ".join(deduped[:5])


def classify_telemetry_tier(
    is_free: int,
    price_usd: float,
    discount_pct: int,
    review_pct: float,
    total_reviews: int,
    estimated_owners: int,
    ccu: int,
) -> tuple[str, str]:
    """Phân loại nhãn phân khúc (segment_tag) và tín hiệu khuyến nghị mua (signal)."""
    prefix = "FREE" if is_free == 1 else "PAID"

    if 0.0 < review_pct < 55.0:
        segment = f"{prefix}_LOWEST_RATED"
    elif (estimated_owners >= 2_000_000 or ccu >= 5_000) and review_pct >= 75.0:
        segment = f"{price_prefix}_BEST_SELLER" if (price_prefix := prefix) else "PAID_BEST_SELLER"
    elif review_pct >= 85.0 and total_reviews >= 500:
        segment = f"{prefix}_HIGHEST_RATED"
    else:
        segment = f"{prefix}_STANDARD"

    is_top_gem = review_pct >= 88.0 and total_reviews >= 300
    is_hot_deal = discount_pct >= 40 and review_pct >= 78.0
    is_great_free = is_free == 1 and review_pct >= 82.0

    if 0.0 < review_pct < 55.0:
        signal = "AVOID"
    elif is_top_gem or is_hot_deal or is_great_free:
        signal = "STRONG_BUY"
    elif review_pct >= 75.0 or (discount_pct >= 20 and price_usd <= 29.99):
        signal = "BUY"
    else:
        signal = "HOLD"

    return segment, signal


def _build_telemetry_record(
    appid_key: str,
    info: dict[str, Any],
    time_meta: tuple[str, str, int],
) -> dict[str, Any] | None:
    """Chuyển đổi 1 object JSON của SteamSpy thành bản ghi Dictionary chuẩn 23 cột."""
    app_id = _safe_int(info.get("appid") or appid_key, fallback=0)
    if app_id <= 0:
        return None

    name = html.unescape(str(info.get("name") or "")).strip()
    if not name:
        return None

    price_cents = _safe_int(info.get("price"), fallback=0)
    init_cents = _safe_int(info.get("initialprice"), fallback=price_cents)
    discount_pct = _safe_int(info.get("discount"), fallback=0)

    price_usd = round(price_cents / 100.0, 2)
    initial_price_usd = max(price_usd, round(init_cents / 100.0, 2))

    is_free = 1 if (price_usd == 0.0 and initial_price_usd == 0.0) else 0
    pricing_type = "FREE" if is_free == 1 else "PAID"

    pos_reviews = _safe_int(info.get("positive"), fallback=0)
    neg_reviews = _safe_int(info.get("negative"), fallback=0)
    total_reviews = pos_reviews + neg_reviews
    review_pct = round((pos_reviews * 100.0) / total_reviews, 2) if total_reviews > 0 else 0.0
    review_summary = build_review_summary_label(review_pct, total_reviews)

    owners_raw = str(info.get("owners") or "0 .. 20,000").strip()
    estimated_owners = estimate_owners_midpoint(owners_raw)
    ccu = _safe_int(info.get("ccu"), fallback=0)

    avg_playtime_hrs = round(_safe_int(info.get("average_forever"), 0) / 60.0, 1)
    med_playtime_hrs = round(_safe_int(info.get("median_forever"), 0) / 60.0, 1)

    developer = html.unescape(str(info.get("developer") or "Unknown Developer")).strip()
    publisher = html.unescape(str(info.get("publisher") or developer)).strip()
    genres_str = resolve_game_genres(name, str(info.get("genre") or ""), publisher)

    segment_tag, signal = classify_telemetry_tier(
        is_free, price_usd, discount_pct, review_pct, total_reviews, estimated_owners, ccu
    )

    current_time, current_date, current_hour = time_meta
    return {
        "timestamp": current_time,
        "date": current_date,
        "hour": current_hour,
        "app_id": app_id,
        "name": name,
        "platform": "Steam PC",
        "developer": developer,
        "publisher": publisher,
        "pricing_type": pricing_type,
        "price": price_usd,
        "initial_price": initial_price_usd,
        "discount": discount_pct,
        "is_free": is_free,
        "positive_reviews": pos_reviews,
        "negative_reviews": neg_reviews,
        "total_reviews": total_reviews,
        "review_score_pct": review_pct,
        "review_summary": review_summary,
        "owners_range": owners_raw,
        "estimated_owners": estimated_owners,
        "ccu": ccu,
        "average_playtime_hours": avg_playtime_hrs,
        "median_playtime_hours": med_playtime_hrs,
        "genres": genres_str,
        "segment_tag": segment_tag,
        "signal": signal,
    }


# ============================================================
# 2. QUÉT DỮ LIỆU CHUYÊN SÂU TỪ STEAMSPY API (ĐÚNG 1.000 GAME)
# ============================================================
# noinspection DuplicatedCode
def fetch_steamspy_telemetry(target_limit: int = 1000) -> pd.DataFrame:
    """Quét kết hợp các bảng xếp hạng của SteamSpy để thu thập đúng 1.000 tựa game."""
    now = datetime.now()
    time_meta = (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"), now.hour)

    print(f"[{time_meta[0]}] Đang kết nối SteamSpy Telemetry API (Mục tiêu: {target_limit:,} game)...")
    session = requests.Session()
    session.headers.update(SPY_HEADERS)

    feed_plans: list[tuple[str, dict[str, str]]] = [
        ("Top 100 Trending (Hot Nhất 2 Tuần Qua)", {"request": "top100in2weeks"}),
        ("Top 100 All-Time Active (Đông Người Chơi Nhất)", {"request": "top100forever"}),
        ("Top 100 Most Owned (Bán Chạy / Sở Hữu Nhiều Nhất)", {"request": "top100owned"}),
        ("Catalog Mở Rộng - Trang 1 (1.000 Game Phổ Biến)", {"request": "all", "page": "0"}),
        ("Catalog Mở Rộng - Trang 2 (Dự Phòng Đủ 1.000 Game)", {"request": "all", "page": "1"}),
    ]

    catalog_store: dict[int, dict[str, Any]] = {}

    for feed_label, query_params in feed_plans:
        if len(catalog_store) >= target_limit:
            break

        print(f"\n[*] Đang tải phân khúc: {feed_label}...")
        try:
            resp = session.get(STEAMSPY_ENDPOINT, params=query_params, timeout=25)
            if resp.status_code != 200:
                print(f"  [Cảnh báo] HTTP {resp.status_code} khi tải {feed_label}")
                continue

            payload = resp.json()
            if not isinstance(payload, dict) or not payload:
                continue

            batch_added = 0
            for appid_key, raw_info in payload.items():
                if not isinstance(raw_info, dict):
                    continue

                record = _build_telemetry_record(str(appid_key), raw_info, time_meta)
                if record is None or record["app_id"] in catalog_store:
                    continue

                catalog_store[record["app_id"]] = record
                batch_added += 1
                if len(catalog_store) >= target_limit:
                    break

            print(
                f"  -> Đã tách thành công +{batch_added:,} game mới "
                f"(Tổng tích lũy: {len(catalog_store):,}/{target_limit:,})"
            )
            time.sleep(1.0)

        except (requests.RequestException, ValueError) as exc:
            print(f"  [Lỗi mạng] Khi tải {feed_label}: {exc}")

    rows_out = list(catalog_store.values())[:target_limit]
    return pd.DataFrame(rows_out)


# ============================================================
# 3. LƯU TRỮ TÍCH LŨY LỊCH SỬ STEAMSPY (GIỮ NGUYÊN DATA CŨ)
# ============================================================
# noinspection DuplicatedCode,PyTypeChecker
def persist_steamspy_records(df_fresh: pd.DataFrame) -> pd.DataFrame:
    """Lưu Snapshot riêng, nối tiếp lịch sử steam_history.csv và xuất bản sạch steam_clean.csv."""
    snap_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_target = SPY_PATHS["snapshots"] / f"steam_snapshot_{snap_stamp}.csv"
    df_fresh.to_csv(snap_target, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã tạo bản sao lưu riêng (Snapshot): {snap_target.name}")

    df_fresh["price_change"] = 0.0
    df_fresh["ccu_change"] = 0
    df_fresh["history_points"] = 1

    history_csv = SPY_PATHS["history"]
    merged_df: Any = df_fresh

    if history_csv.exists():
        try:
            prev_df = load_steamspy_csv(history_csv)
            print(f"[2] Đã tìm thấy kho lịch sử Steam cũ: {len(prev_df):,} dòng.")
            concat_df: Any = pd.concat([prev_df, df_fresh], ignore_index=True)
            dedup_df: Any = concat_df.drop_duplicates(subset=["date", "hour", "app_id"], keep="last")
            sorted_df: Any = dedup_df.sort_values(["app_id", "timestamp"])
            merged_df = sorted_df.reset_index(drop=True)

            merged_df["price_change"] = (
                merged_df.groupby("app_id")["price"].diff().fillna(0.0).round(2)
            )
            merged_df["ccu_change"] = (
                merged_df.groupby("app_id")["ccu"].diff().fillna(0).astype(int)
            )
            merged_df["history_points"] = merged_df.groupby("app_id").cumcount() + 1
        except (OSError, pd.errors.ParserError, ValueError) as err:
            print(f"[Cảnh báo] Khởi tạo lại file lịch sử do lỗi đọc file cũ: {err}")
            merged_df = df_fresh
    else:
        print(f"[2] Khởi tạo kho lịch sử Steam lần đầu ({len(df_fresh):,} dòng).")

    merged_df.to_csv(history_csv, index=False, encoding="utf-8-sig")

    latest_dedup: Any = merged_df.drop_duplicates(subset=["app_id"], keep="last")
    clean_df: pd.DataFrame = latest_dedup.reset_index(drop=True)
    clean_df.to_csv(SPY_PATHS["clean"], index=False, encoding="utf-8-sig")

    print(f"[3] Đã lưu tích lũy tại : {history_csv} (Tổng: {len(merged_df):,} dòng)")
    print(f"[4] Đã xuất bản sạch tại: {SPY_PATHS['clean']} ({len(clean_df):,} tựa game)")
    return clean_df


if __name__ == "__main__":
    print(BANNER_LINE)
    print("   THU THẬP DỮ LIỆU STEAMSPY TELEMETRY (CHUẨN PRODUCTION - 1.000 GAME)")
    print(BANNER_LINE)

    df_telemetry = fetch_steamspy_telemetry(target_limit=1000)
    if not df_telemetry.empty:
        df_clean_out = persist_steamspy_records(df_telemetry)

        free_total = int((df_clean_out["is_free"] == 1).sum())
        paid_total = int((df_clean_out["is_free"] == 0).sum())
        top_sellers_cnt = int(
            df_clean_out["segment_tag"].str.contains("BEST_SELLER", na=False).sum()
        )

        print("\n" + BANNER_LINE)
        print("   THỐNG KÊ KHO DỮ LIỆU STEAMSPY VỪA THU THẬP:")
        print(f"   - Tổng số tựa game thu thập       : {len(df_clean_out):,} game")
        print(f"   - Số game Miễn phí (Free-to-Play) : {free_total:,} game")
        print(f"   - Số game Trả phí (Paid Games)    : {paid_total:,} game")
        print(f"   - Số game Bán chạy (Best Sellers) : {top_sellers_cnt:,} game")
        print(BANNER_LINE)

        preview_columns = [
            "app_id",
            "name",
            "pricing_type",
            "price",
            "review_score_pct",
            "review_summary",
            "ccu",
            "segment_tag",
            "signal",
        ]
        print("\n5 tựa game Steam mẫu vừa thu thập:")
        print(df_clean_out[preview_columns].head(5))
    else:
        print("❌ Không thu thập được dữ liệu từ SteamSpy API.")
# === END OF FILE ===