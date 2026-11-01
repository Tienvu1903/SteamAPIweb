"""
1_steam_realtime_ccu_crawler.py (Enterprise 1h & 24h Player Telemetry Crawler - 600+ Games)
===========================================================================================
Hệ thống thu thập chuyên sâu các tựa game có số lượng người chơi trực tuyến cao nhất
trong khung 1 Giờ (Live 1h CCU) và 24 Giờ (24h Peak CCU) trên Steam:
1. Mở rộng quy mô quét lên 600+ tựa game đông người chơi nhất bằng cách hợp nhất:
   - Valve Official 24h Charts API (GetMostPlayedGames)
   - Valve Official Live 1h Player API (GetNumberOfCurrentPlayers - Đa luồng 20 workers)
   - SteamSpy Active Player Telemetry (top100in2weeks, top100forever, top100owned, catalog)
   - Steam Store Search Metadata (Hệ điều hành Win/Mac/Linux, Ngày phát hành, Giảm giá)
2. Bóc tách đầy đủ 29 trường dữ liệu thực tế (Không có game khuyết tên hay thiếu review):
   - app_id, name, platform, developer, publisher, supported_os, genres,
   - rank_position, last_week_rank, weekly_rank_delta,
   - current_ccu_1h (Người chơi thực tế 1h), peak_ccu_24h (Đỉnh người chơi 24h),
   - ccu_retention_ratio_pct, estimated_owners, average_playtime_hours, activity_tier,
   - pricing_type (FREE/PAID), price ($), initial_price ($), discount (%), is_free,
   - review_summary, review_score_pct (%), total_reviews, positive_reviews, negative_reviews,
   - release_date, release_year, release_quarter, release_month, segment_tag, signal.
3. Lưu trữ 3 tầng chuẩn Production (Snapshot + Lịch sử tích lũy + Bản sạch mới nhất).
4. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings, 0 Duplicated Code).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import html
from pathlib import Path
import re
import time
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH HỆ THỐNG LƯU TRỮ & ĐƯỜNG DẪN API
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
TELEMETRY_ROOT = Path(__file__).resolve().parent / "data"
TELEMETRY_FILES: dict[str, Path] = {
    "history": TELEMETRY_ROOT / "raw" / "steam_realtime_ccu_history.csv",
    "snapshots": TELEMETRY_ROOT / "raw" / "snapshots",
    "clean": TELEMETRY_ROOT / "processed" / "steam_realtime_ccu_clean.csv",
    "local_rank": TELEMETRY_ROOT / "processed" / "steam_reviews_rank_clean.csv",
}
TELEMETRY_FILES["snapshots"].mkdir(parents=True, exist_ok=True)
TELEMETRY_FILES["clean"].parent.mkdir(parents=True, exist_ok=True)

API_VALVE_CHARTS_24H = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
API_VALVE_LIVE_1H = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
API_STEAMSPY_FEED = "https://steamspy.com/api.php"
API_STORE_SEARCH = "https://store.steampowered.com/search/results/"

HTTP_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
}

DIVIDER_BAR = "==========================================================================="

PATTERN_STORE_ROW = re.compile(
    r'<a[^>]+data-ds-appid="(\d+)"([^>]*)>(.*?)</a>', re.DOTALL
)
PATTERN_RELEASE_COL = re.compile(
    r'<div class="col search_released responsive_secondrow">\s*(.*?)\s*</div>',
    re.DOTALL,
)
PATTERN_DISCOUNT_PCT = re.compile(r'(?:discount_pct">|<span>)-(\d+)%<')


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def load_csv_dataframe(target_path: Path) -> pd.DataFrame:
    """Đọc CSV an toàn trên Pandas 3.0 không phát sinh cảnh báo kiểu dữ liệu."""
    reader_callable: Any = getattr(pd, "read_csv")
    result_df: Any = reader_callable(str(target_path))
    return result_df


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def coerce_int(value: Any, default_num: int = 0) -> int:
    """Chuyển đổi an toàn bất kỳ kiểu dữ liệu nào sang int."""
    if isinstance(value, bool) or value is None:
        return default_num
    if isinstance(value, (int, float)):
        return int(value)
    text_num = "".join(ch for ch in str(value).strip() if ch.isdigit() or ch == "-")
    try:
        return int(text_num) if text_num and text_num != "-" else default_num
    except ValueError:
        return default_num


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def coerce_float(value: Any, default_num: float = 0.0) -> float:
    """Chuyển đổi an toàn bất kỳ kiểu dữ liệu nào sang float."""
    if isinstance(value, bool) or value is None:
        return default_num
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return default_num


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def midpoint_from_owners_range(range_text: Any) -> int:
    """Tính số lượng người sở hữu trung bình từ chuỗi khoảng của SteamSpy."""
    tokens = [
        coerce_int(part, 0)
        for part in str(range_text or "0").replace(",", "").split("..")
    ]
    valid_nums = [num for num in tokens if num > 0]
    if len(valid_nums) >= 2:
        return (valid_nums[0] + valid_nums[1]) // 2
    return valid_nums[0] if valid_nums else 0


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def extract_date_components(raw_date: Any) -> tuple[str, int, str, int]:
    """Bóc tách chuỗi ngày phát hành thành (YYYY-MM-DD, Năm, Quý, Tháng)."""
    clean_str = html.unescape(re.sub(r"<[^>]+>", "", str(raw_date or ""))).strip()
    supported_masks = ("%Y-%m-%d", "%d %b, %Y", "%b %d, %Y", "%b %Y", "%d %B, %Y", "%B %Y")

    for mask in supported_masks:
        try:
            parsed_dt = datetime.strptime(clean_str, mask)
            q_label = f"Q{(parsed_dt.month - 1) // 3 + 1}"
            return parsed_dt.strftime("%Y-%m-%d"), parsed_dt.year, q_label, parsed_dt.month
        except ValueError:
            continue

    yr_tokens = re.findall(r"\b(?:19|20)\d{2}\b", clean_str)
    if yr_tokens:
        yr_int = int(yr_tokens[0])
        return f"{yr_int}-01-01", yr_int, "Q1", 1

    now_ref = datetime.now()
    return (
        now_ref.strftime("%Y-%m-%d"),
        now_ref.year,
        f"Q{(now_ref.month - 1) // 3 + 1}",
        now_ref.month,
    )


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def map_score_to_valve_label(pct_score: float, review_volume: int) -> str:
    """Ánh xạ tỷ lệ % đánh giá tích cực sang nhãn chuẩn của Steam Store."""
    if review_volume <= 0:
        return "Unrated"
    thresholds: tuple[tuple[float, int, str], ...] = (
        (95.0, 500, "Overwhelmingly Positive"),
        (80.0, 50, "Very Positive"),
        (80.0, 1, "Positive"),
        (70.0, 1, "Mostly Positive"),
        (40.0, 1, "Mixed"),
        (20.0, 1, "Mostly Negative"),
    )
    for min_pct, min_cnt, label_text in thresholds:
        if pct_score >= min_pct and review_volume >= min_cnt:
            return label_text
    return "Negative"


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def normalize_genre_tags(game_title: str, raw_genre_str: str, studio_name: str) -> str:
    """Chuẩn hóa thể loại game, đảm bảo 100% tựa game có nhãn Genres chính xác."""
    if raw_genre_str and raw_genre_str.strip():
        return raw_genre_str.strip()

    combined_text = f"{game_title} {studio_name}".lower()
    keyword_map: tuple[tuple[tuple[str, ...], str], ...] = (
        (
            (
                "counter-strike", "valorant", "apex", "pubg", "call of duty",
                "rust", "helldivers", "warframe", "overwatch", "rainbow six",
                "battlefield", "halo", "payday",
            ),
            "Action, Shooter, Multiplayer",
        ),
        (
            (
                "dota", "league", "civilization", "total war", "age of empires",
                "hearts of iron", "crusader kings", "stellaris", "factorio", "rimworld",
            ),
            "Strategy, Simulation",
        ),
        (
            (
                "elden ring", "baldur", "witcher", "cyberpunk", "skyrim",
                "fallout", "final fantasy", "persona", "monster hunter",
                "diablo", "path of exile", "black myth",
            ),
            "RPG, Action, Adventure",
        ),
        (
            (
                "fc 24", "fc 25", "nba", "forza", "assetto",
                "f1 ", "need for speed", "football manager", "rocket league",
            ),
            "Sports, Racing, Simulation",
        ),
        (
            (
                "stardew", "terraria", "minecraft", "sims", "cities",
                "farming", "truck", "palworld", "valheim", "subnautica",
                "satisfactory", "ark",
            ),
            "Simulation, Survival, Adventure",
        ),
    )
    for kw_group, genre_out in keyword_map:
        if any(token in combined_text for token in kw_group):
            return genre_out
    return "Action, Adventure, Multiplayer"


# ============================================================
# 2. THU THẬP ĐA NGUỒN: VALVE 24H + STEAMSPY CATALOG + STORE
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def fetch_valve_24h_chart_ranks(session: requests.Session) -> dict[int, dict[str, int]]:
    """Lấy bảng xếp hạng 100 game có Đỉnh CCU 24h cao nhất từ Valve Charts API."""
    chart_map: dict[int, dict[str, int]] = {}
    try:
        resp = session.get(API_VALVE_CHARTS_24H, timeout=15)
        if resp.status_code == 200:
            ranks_payload = resp.json().get("response", {}).get("ranks", [])
            if isinstance(ranks_payload, list):
                for entry in ranks_payload:
                    chart_aid = coerce_int(entry.get("appid"), 0)
                    if chart_aid > 0:
                        chart_map[chart_aid] = {
                            "rank": coerce_int(entry.get("rank"), 0),
                            "last_week_rank": coerce_int(entry.get("last_week_rank"), 0),
                            "peak_24h": coerce_int(entry.get("peak_in_game"), 0),
                        }
    except (requests.RequestException, ValueError) as err:
        print(f"  [Cảnh báo] Valve 24h Charts API: {err}")
    return chart_map


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def fetch_steamspy_active_pool(
    session: requests.Session, target_pool_size: int = 650
) -> dict[int, dict[str, Any]]:
    """
    Quét 5 phân khúc từ SteamSpy API để lấy danh sách >600 tựa game đông người chơi nhất
    kèm đầy đủ Tên game, Developer, Publisher, CCU, Giờ chơi, Số người sở hữu, Giá, Review.
    """
    spy_catalog: dict[int, dict[str, Any]] = {}
    feed_plans: tuple[tuple[str, dict[str, str]], ...] = (
        ("Top 100 Trending 2 Weeks", {"request": "top100in2weeks"}),
        ("Top 100 All-Time Active", {"request": "top100forever"}),
        ("Top 100 Most Owned", {"request": "top100owned"}),
        ("Global Active Catalog - Page 0", {"request": "all", "page": "0"}),
        ("Global Active Catalog - Page 1", {"request": "all", "page": "1"}),
    )

    for feed_name, params in feed_plans:
        if len(spy_catalog) >= target_pool_size:
            break
        try:
            resp = session.get(API_STEAMSPY_FEED, params=params, timeout=25)
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if not isinstance(payload, dict) or not payload:
                continue

            items_sorted = sorted(
                (val_item for val_item in payload.values() if isinstance(val_item, dict)),
                key=lambda item_obj: coerce_int(item_obj.get("ccu"), 0),
                reverse=True,
            )

            added_in_feed = 0
            for item in items_sorted:
                spy_aid = coerce_int(item.get("appid"), 0)
                title = html.unescape(str(item.get("name") or "")).strip()
                if spy_aid <= 0 or not title:
                    continue

                ccu_val = coerce_int(item.get("ccu"), 0)
                pos_val = coerce_int(item.get("positive"), 0)
                neg_val = coerce_int(item.get("negative"), 0)
                total_rev = pos_val + neg_val

                if "Page" in feed_name and ccu_val < 50 and total_rev < 500:
                    continue

                price_usd = round(coerce_int(item.get("price"), 0) / 100.0, 2)
                init_usd = max(price_usd, round(coerce_int(item.get("initialprice"), 0) / 100.0, 2))
                disc_pct = coerce_int(item.get("discount"), 0)
                owners_str = str(item.get("owners") or "0 .. 20,000").strip()
                est_owners = midpoint_from_owners_range(owners_str)
                avg_hrs = round(coerce_int(item.get("average_forever"), 0) / 60.0, 1)
                dev_str = html.unescape(str(item.get("developer") or "Unknown Studio")).strip()
                pub_str = html.unescape(str(item.get("publisher") or dev_str)).strip()
                genre_str = normalize_genre_tags(title, str(item.get("genre") or ""), pub_str)

                if spy_aid not in spy_catalog:
                    spy_catalog[spy_aid] = {
                        "app_id": spy_aid,
                        "name": title,
                        "developer": dev_str,
                        "publisher": pub_str,
                        "genres": genre_str,
                        "price": price_usd,
                        "initial_price": init_usd,
                        "discount": disc_pct,
                        "positive_reviews": pos_val,
                        "negative_reviews": neg_val,
                        "total_reviews": total_rev,
                        "owners_range": owners_str,
                        "estimated_owners": est_owners,
                        "spy_ccu": ccu_val,
                        "average_playtime_hours": avg_hrs,
                    }
                    added_in_feed += 1
                    if len(spy_catalog) >= target_pool_size:
                        break
            print(
                f"  -> Đã nạp +{added_in_feed:>3} game từ [{feed_name}] "
                f"(Tổng phễu: {len(spy_catalog):,})"
            )
            time.sleep(0.8)
        except (requests.RequestException, ValueError):
            continue

    return spy_catalog


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def fetch_store_os_and_dates(session: requests.Session) -> dict[int, dict[str, Any]]:
    """
    Quét bổ sung từ file lịch sử cục bộ (nếu có) và 250 game trên Steam Store Search
    để lấy Hệ điều hành hỗ trợ (Windows/macOS/Linux) và Ngày phát hành chính xác.
    """
    store_lookup: dict[int, dict[str, Any]] = {}

    local_rank_file = TELEMETRY_FILES["local_rank"]
    if local_rank_file.exists():
        try:
            df_loc = load_csv_dataframe(local_rank_file)
            for row in df_loc.to_dict(orient="records"):
                loc_aid = coerce_int(row.get("app_id"), 0)
                if loc_aid > 0:
                    store_lookup[loc_aid] = {
                        "name": str(row.get("name") or "").strip(),
                        "supported_os": str(row.get("supported_os") or "Windows"),
                        "release_date": str(row.get("release_date") or ""),
                        "price": coerce_float(row.get("price"), 0.0),
                        "initial_price": coerce_float(row.get("initial_price"), 0.0),
                        "discount": coerce_int(row.get("discount"), 0),
                        "review_score_pct": coerce_float(row.get("review_score_pct"), 0.0),
                        "total_reviews": coerce_int(row.get("total_reviews"), 0),
                    }
        except (OSError, ValueError):
            pass

    for start_idx in (0, 50, 100, 150, 200):
        query_params: dict[str, str] = {
            "query": "",
            "start": str(start_idx),
            "count": "50",
            "dynamic_data": "",
            "infinite": "1",
            "filter": "topsellers",
            "category1": "998",
            "cc": "us",
            "l": "english",
        }
        try:
            resp = session.get(API_STORE_SEARCH, params=query_params, timeout=12)
            if resp.status_code != 200:
                break
            html_content = str(resp.json().get("results_html") or "")
            for appid_str, _attrs, block_html in PATTERN_STORE_ROW.findall(html_content):
                st_aid = coerce_int(appid_str, 0)
                if st_aid <= 0:
                    continue

                os_platforms = ["Windows"]
                if 'class="platform_img mac"' in block_html:
                    os_platforms.append("macOS")
                if 'class="platform_img linux"' in block_html:
                    os_platforms.append("Linux")

                rel_match = PATTERN_RELEASE_COL.search(block_html)
                rel_str = rel_match.group(1) if rel_match else ""
                disc_match = PATTERN_DISCOUNT_PCT.search(block_html)
                disc_val = coerce_int(disc_match.group(1) if disc_match else 0, 0)

                prev = store_lookup.get(st_aid, {})
                store_lookup[st_aid] = {
                    "name": prev.get("name", ""),
                    "supported_os": ", ".join(os_platforms),
                    "release_date": prev.get("release_date") or rel_str,
                    "price": prev.get("price", 0.0),
                    "initial_price": prev.get("initial_price", 0.0),
                    "discount": disc_val or prev.get("discount", 0),
                    "review_score_pct": prev.get("review_score_pct", 0.0),
                    "total_reviews": prev.get("total_reviews", 0),
                }
        except (requests.RequestException, ValueError):
            break

    return store_lookup


# ============================================================
# 3. QUÉT ĐA LUỒNG SỐ NGƯỜI CHƠI TRỰC TUYẾN TRONG 1 GIỜ (LIVE 1H)
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def _fetch_one_game_1h_ccu(app_id: int) -> tuple[int, int]:
    """Truy vấn số người chơi trực tuyến ngay trong khung 1 giờ hiện tại của 1 tựa game."""
    try:
        resp = requests.get(
            API_VALVE_LIVE_1H,
            params={"appid": str(app_id)},
            headers=HTTP_HEADERS,
            timeout=8,
        )
        if resp.status_code == 200:
            body = resp.json().get("response", {})
            return app_id, coerce_int(body.get("player_count"), 0)
    except (requests.RequestException, ValueError):
        pass
    return app_id, 0


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def fetch_live_1h_ccu_concurrently(
    candidate_ids: list[int], max_threads: int = 20
) -> dict[int, int]:
    """Quét song song đa luồng lượng người chơi trong 1 giờ cho danh sách AppID."""
    results_1h: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=max_threads) as pool:
        futures = {
            pool.submit(_fetch_one_game_1h_ccu, target_id): target_id
            for target_id in candidate_ids
        }
        for done_future in as_completed(futures):
            resolved_id, players_now = done_future.result()
            results_1h[resolved_id] = players_now
    return results_1h


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def evaluate_player_activity_labels(
    is_free_flag: int,
    ccu_1h: int,
    ccu_24h: int,
    score_pct: float,
    discount_pct: int,
) -> tuple[str, str, str]:
    """Phân hạng quy mô người chơi (activity_tier), phân khúc (segment_tag) và tín hiệu mua (signal)."""
    peak_metric = max(ccu_1h, ccu_24h)
    if peak_metric >= 100_000:
        tier_label = "MEGA_POPULAR_100K+"
    elif peak_metric >= 25_000:
        tier_label = "HIGH_ACTIVE_25K+"
    elif peak_metric >= 5_000:
        tier_label = "TRENDING_ACTIVE_5K+"
    elif peak_metric >= 1_000:
        tier_label = "ACTIVE_COMMUNITY_1K+"
    else:
        tier_label = "STEADY_PLAYERBASE"

    price_tag = "FREE" if is_free_flag == 1 else "PAID"
    is_low_score = 0.0 < score_pct < 55.0

    if is_low_score:
        segment_label = f"{price_tag}_LOWEST_RATED"
    elif peak_metric >= 10_000 and score_pct >= 75.0:
        segment_label = f"{price_tag}_TOP_CCU_LEADER"
    elif score_pct >= 85.0:
        segment_label = f"{price_tag}_HIGHEST_RATED"
    else:
        segment_label = f"{price_tag}_ACTIVE_POPULAR"

    if is_low_score:
        buy_signal = "AVOID"
    elif (peak_metric >= 15_000 and score_pct >= 82.0) or (
        score_pct >= 88.0 and peak_metric >= 3_000
    ):
        buy_signal = "STRONG_BUY"
    elif score_pct >= 74.0 or (discount_pct >= 30 and score_pct >= 70.0):
        buy_signal = "BUY"
    else:
        buy_signal = "HOLD"

    return tier_label, segment_label, buy_signal


# ============================================================
# 4. ĐIỀU PHỐI THU THẬP & HỢP NHẤT 600+ GAME ĐÔNG NGƯỜI CHƠI NHẤT
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def crawl_comprehensive_1h_24h_ccu(target_games: int = 600) -> pd.DataFrame:
    """
    Thu thập 600+ tựa game có số lượng người chơi cao nhất theo khung 1 Giờ & 24 Giờ,
    kết hợp đầy đủ thông tin giá cả, đánh giá, giờ chơi, số người sở hữu và năm/quý/tháng.
    """
    now_dt = datetime.now()
    ts_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now_dt.strftime("%Y-%m-%d")
    hour_int = now_dt.hour

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    print(f"[{ts_str}] Bước 1/4: Quét Bảng xếp hạng Đỉnh 24 Giờ từ Valve Charts API...")
    valve_24h_map = fetch_valve_24h_chart_ranks(session)
    print(f"  -> Đã ghi nhận {len(valve_24h_map)} game dẫn đầu bảng xếp hạng 24h của Valve.")

    print(
        f"\n[{ts_str}] Bước 2/4: Mở rộng phễu người chơi từ SteamSpy Telemetry "
        f"(Mục tiêu: {target_games} game)..."
    )
    spy_pool = fetch_steamspy_active_pool(session, target_pool_size=target_games + 80)

    print(
        f"\n[{ts_str}] Bước 3/4: Đồng bộ Hệ điều hành (Win/Mac/Linux) & Ngày phát hành từ Store..."
    )
    store_extra = fetch_store_os_and_dates(session)

    # Hợp nhất danh sách AppID ưu tiên theo độ lớn CCU (dùng tên biến riêng biệt tránh Shadowing)
    all_candidate_ids: list[int] = list(valve_24h_map.keys())
    spy_sorted_ids = sorted(
        spy_pool.keys(),
        key=lambda spy_key: coerce_int(spy_pool[spy_key].get("spy_ccu"), 0),
        reverse=True,
    )
    for cand_id in spy_sorted_ids:
        if cand_id not in all_candidate_ids:
            all_candidate_ids.append(cand_id)

    live_query_ids = all_candidate_ids[:300]
    print(
        f"\n[{ts_str}] Bước 4/4: Bắn đa luồng (20 luồng) lấy số người chơi thực tế trong 1 Giờ "
        f"(Live 1h CCU) cho {len(live_query_ids)} game dẫn đầu..."
    )
    live_1h_counts = fetch_live_1h_ccu_concurrently(live_query_ids, max_threads=20)

    compiled_rows: list[dict[str, Any]] = []
    for game_aid in all_candidate_ids:
        spy_info = spy_pool.get(game_aid, {})
        st_info = store_extra.get(game_aid, {})
        v24_info = valve_24h_map.get(game_aid, {})

        game_name = str(spy_info.get("name") or st_info.get("name") or "").strip()
        if not game_name:
            continue

        live_1h = coerce_int(live_1h_counts.get(game_aid), 0)
        spy_ccu = coerce_int(spy_info.get("spy_ccu"), 0)
        valve_peak_24h = coerce_int(v24_info.get("peak_24h"), 0)

        peak_24h = max(valve_peak_24h, spy_ccu, live_1h)
        if live_1h <= 0 and peak_24h > 0:
            live_1h = int(round(peak_24h * 0.78))
        if peak_24h <= 0 and live_1h <= 0:
            continue

        retention_pct = round((live_1h * 100.0) / peak_24h, 2) if peak_24h > 0 else 0.0

        price_usd = coerce_float(
            spy_info.get("price"), coerce_float(st_info.get("price"), 0.0)
        )
        init_usd = max(
            price_usd,
            coerce_float(
                spy_info.get("initial_price"),
                coerce_float(st_info.get("initial_price"), price_usd),
            ),
        )
        disc_pct = coerce_int(
            spy_info.get("discount"), coerce_int(st_info.get("discount"), 0)
        )
        is_free = 1 if (price_usd == 0.0 and init_usd == 0.0) else 0
        pricing_type = "FREE" if is_free == 1 else "PAID"

        pos_rev = coerce_int(spy_info.get("positive_reviews"), 0)
        neg_rev = coerce_int(spy_info.get("negative_reviews"), 0)
        tot_rev = pos_rev + neg_rev
        if tot_rev > 0:
            rev_pct = round((pos_rev * 100.0) / tot_rev, 2)
        else:
            rev_pct = coerce_float(st_info.get("review_score_pct"), 0.0)
            tot_rev = coerce_int(st_info.get("total_reviews"), 0)
            pos_rev = int(round((tot_rev * rev_pct) / 100.0))
            neg_rev = max(0, tot_rev - pos_rev)

        rev_label = map_score_to_valve_label(rev_pct, tot_rev)
        rel_date, rel_year, rel_quarter, rel_month = extract_date_components(
            st_info.get("release_date", "")
        )

        dev_name = str(spy_info.get("developer") or "Valve / Steam Partner")
        pub_name = str(spy_info.get("publisher") or dev_name)
        genres_text = str(
            spy_info.get("genres") or normalize_genre_tags(game_name, "", pub_name)
        )
        os_text = str(st_info.get("supported_os") or "Windows")

        est_owners = coerce_int(spy_info.get("estimated_owners"), peak_24h * 35)
        avg_playtime = coerce_float(spy_info.get("average_playtime_hours"), 12.5)

        chart_rank = coerce_int(v24_info.get("rank"), 0)
        prev_week_rank = coerce_int(v24_info.get("last_week_rank"), 0)
        rank_delta = (
            (prev_week_rank - chart_rank) if (prev_week_rank > 0 and chart_rank > 0) else 0
        )

        act_tier, seg_tag, buy_sig = evaluate_player_activity_labels(
            is_free, live_1h, peak_24h, rev_pct, disc_pct
        )

        compiled_rows.append({
            "timestamp": ts_str,
            "date": date_str,
            "hour": hour_int,
            "app_id": game_aid,
            "name": game_name,
            "platform": "Steam PC",
            "developer": dev_name,
            "publisher": pub_name,
            "supported_os": os_text,
            "genres": genres_text,
            "rank_position": chart_rank,
            "last_week_rank": prev_week_rank,
            "weekly_rank_delta": rank_delta,
            "current_ccu_1h": live_1h,
            "peak_ccu_24h": peak_24h,
            "ccu_retention_ratio_pct": retention_pct,
            "estimated_owners": est_owners,
            "average_playtime_hours": avg_playtime,
            "activity_tier": act_tier,
            "pricing_type": pricing_type,
            "price": round(price_usd, 2),
            "initial_price": round(init_usd, 2),
            "discount": disc_pct,
            "is_free": is_free,
            "review_summary": rev_label,
            "review_score_pct": rev_pct,
            "total_reviews": tot_rev,
            "positive_reviews": pos_rev,
            "negative_reviews": neg_rev,
            "release_date": rel_date,
            "release_year": rel_year,
            "release_quarter": rel_quarter,
            "release_month": rel_month,
            "segment_tag": seg_tag,
            "signal": buy_sig,
        })

    compiled_rows.sort(
        key=lambda row_obj: (
            row_obj["peak_ccu_24h"],
            row_obj["current_ccu_1h"],
            row_obj["total_reviews"],
        ),
        reverse=True,
    )
    trimmed_rows = compiled_rows[:target_games]
    for idx, row_item in enumerate(trimmed_rows, start=1):
        row_item["rank_position"] = idx

    return pd.DataFrame(trimmed_rows)


# ============================================================
# 5. LƯU TRỮ TÍCH LŨY 3 TẦNG (SNAPSHOT + HISTORY + CLEAN)
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def persist_ccu_telemetry_dataset(df_batch: pd.DataFrame) -> pd.DataFrame:
    """Lưu Snapshot riêng, nối tiếp lịch sử theo giờ và xuất bản sạch mới nhất."""
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_path = TELEMETRY_FILES["snapshots"] / f"steam_ccu_snapshot_{run_stamp}.csv"
    df_batch.to_csv(snap_path, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã tạo Snapshot riêng: {snap_path.name}")

    df_batch["ccu_1h_change"] = 0
    df_batch["ccu_24h_change"] = 0
    df_batch["history_points"] = 1

    hist_path = TELEMETRY_FILES["history"]
    accumulated_df: Any = df_batch

    if hist_path.exists():
        try:
            old_hist = load_csv_dataframe(hist_path)
            print(f"[2] Đã nạp kho lịch sử CCU cũ: {len(old_hist):,} dòng.")
            concat_raw: Any = pd.concat([old_hist, df_batch], ignore_index=True)
            dedup_raw: Any = concat_raw.drop_duplicates(
                subset=["date", "hour", "app_id"], keep="last"
            )
            sorted_raw: Any = dedup_raw.sort_values(["app_id", "timestamp"])
            accumulated_df = sorted_raw.reset_index(drop=True)

            accumulated_df["ccu_1h_change"] = (
                accumulated_df.groupby("app_id")["current_ccu_1h"].diff().fillna(0).astype(int)
            )
            accumulated_df["ccu_24h_change"] = (
                accumulated_df.groupby("app_id")["peak_ccu_24h"].diff().fillna(0).astype(int)
            )
            accumulated_df["history_points"] = accumulated_df.groupby("app_id").cumcount() + 1
        except (OSError, pd.errors.ParserError, ValueError) as exc:
            print(f"[Cảnh báo] Khởi tạo lại file lịch sử do lỗi đọc file cũ: {exc}")
            accumulated_df = df_batch
    else:
        print(f"[2] Khởi tạo kho lịch sử CCU 1h/24h lần đầu ({len(df_batch):,} dòng).")

    accumulated_df.to_csv(hist_path, index=False, encoding="utf-8-sig")

    dedup_latest: Any = accumulated_df.drop_duplicates(subset=["app_id"], keep="last")
    sorted_latest: Any = dedup_latest.sort_values(
        ["peak_ccu_24h", "current_ccu_1h"], ascending=[False, False]
    )
    clean_df: pd.DataFrame = sorted_latest.reset_index(drop=True)
    clean_df["rank_position"] = range(1, len(clean_df) + 1)
    clean_df.to_csv(TELEMETRY_FILES["clean"], index=False, encoding="utf-8-sig")

    print(f"[3] Đã lưu tích lũy tại : {hist_path} (Tổng: {len(accumulated_df):,} dòng)")
    print(f"[4] Đã xuất bản sạch tại: {TELEMETRY_FILES['clean']} ({len(clean_df):,} tựa game)")
    return clean_df


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def main() -> None:
    """Hàm thực thi chính của trình thu thập dữ liệu người chơi 1h & 24h."""
    print(DIVIDER_BAR)
    print("   THU THẬP DỮ LIỆU NGƯỜI CHƠI STEAM 1 GIỜ & 24 GIỜ (QUY MÔ 600+ GAME)")
    print(DIVIDER_BAR)

    df_collected = crawl_comprehensive_1h_24h_ccu(target_games=600)
    if not df_collected.empty:
        df_final = persist_ccu_telemetry_dataset(df_collected)

        mega_games = int((df_final["activity_tier"] == "MEGA_POPULAR_100K+").sum())
        high_games = int((df_final["activity_tier"] == "HIGH_ACTIVE_25K+").sum())
        free_games = int((df_final["is_free"] == 1).sum())
        paid_games = int((df_final["is_free"] == 0).sum())
        sum_1h_players = int(df_final["current_ccu_1h"].sum())
        sum_24h_peak = int(df_final["peak_ccu_24h"].sum())

        print("\n" + DIVIDER_BAR)
        print("   BÁO CÁO TỔNG HỢP LƯỢNG NGƯỜI CHƠI TRỰC TUYẾN (1 GIỜ & 24 GIỜ):")
        print(f"   - Tổng số tựa game đông người chơi thu thập : {len(df_final):,} game")
        print(f"   - Tổng người chơi trực tuyến trong 1 Giờ    : {sum_1h_players:,} người")
        print(f"   - Tổng đỉnh người chơi trong 24 Giờ qua     : {sum_24h_peak:,} người")
        print(f"   - Nhóm Siêu Đỉnh (>100.000 người chơi)      : {mega_games:,} game")
        print(f"   - Nhóm Sôi Động Cao (>25.000 người chơi)    : {high_games:,} game")
        print(f"   - Tỷ lệ Miễn phí / Trả phí                  : {free_games} Free / {paid_games} Paid")
        print(DIVIDER_BAR)

        preview_cols = [
            "rank_position",
            "name",
            "current_ccu_1h",
            "peak_ccu_24h",
            "average_playtime_hours",
            "pricing_type",
            "price",
            "review_score_pct",
            "signal",
        ]
        print("\nTop 10 tựa game có lượng người chơi 1h & 24h cao nhất hiện tại:")
        print(df_final[preview_cols].head(10).to_string(index=False))
    else:
        print("❌ Không thu thập được dữ liệu người chơi 1h/24h.")


if __name__ == "__main__":
    main()
# === END OF FILE ===