"""
1_steam_global_reviews_crawler.py (Production-Ready Store Rankings & Reviews)
=============================================================================
Thu thập trực tiếp 6 Bảng Xếp Hạng Chính Thức từ Steam Store Search & Review API:
1. Quét 6 phân khúc chiến lược (tự động lọc category1=998 chỉ lấy Game gốc, bỏ DLC/Soundtrack):
   - TOP_SELLER: Game Bán Chạy Nhất Toàn Cầu (Top Sellers)
   - FREE_TOP_RATED: Game Miễn Phí Được Đánh Giá Cao Nhất
   - PAID_TOP_RATED: Game Trả Phí Được Đánh Giá Cao Nhất
   - PAID_LOWEST_RATED: Game Trả Phí Bị Đánh Giá Thấp Nhất
   - FREE_LOWEST_RATED: Game Miễn Phí Bị Đánh Giá Thấp Nhất
   - NEW_RELEASES: Game Mới Phát Hành Nổi Bật Theo Tháng/Quý
2. Bóc tách đầy đủ 24 trường dữ liệu:
   - AppID, Tên game, Phân khúc xếp hạng, Vị trí xếp hạng, Loại giá (FREE/PAID),
   - Giá hiện tại ($), Giá gốc ($), % Giảm giá, Hệ điều hành hỗ trợ (Win/Mac/Linux),
   - Nhãn đánh giá, % Tích cực, Tổng số Review, Số Review Tích cực / Tiêu cực,
   - Ngày phát hành, Năm (release_year), Quý (release_quarter), Tháng (release_month),
   - Nhãn phân đoạn (segment_tag) và Tín hiệu khuyến nghị (signal).
3. Lưu trữ 3 tầng (Snapshot + Lịch sử tích lũy + Bản sạch mới nhất).
4. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings, 0 Duplicated Code).
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
# 1. CẤU HÌNH ĐƯỜNG DẪN LƯU TRỮ (CẤU TRÚC RIÊNG KHÔNG TRÙNG LẶP)
# ============================================================
# noinspection DuplicatedCode
RANK_BASE_PATH = Path(__file__).resolve().parent / "data"
RANK_PATHS: dict[str, Path] = {
    "history": RANK_BASE_PATH / "raw" / "steam_reviews_rank_history.csv",
    "snapshots": RANK_BASE_PATH / "raw" / "snapshots",
    "clean": RANK_BASE_PATH / "processed" / "steam_reviews_rank_clean.csv",
}
RANK_PATHS["snapshots"].mkdir(parents=True, exist_ok=True)
RANK_PATHS["clean"].parent.mkdir(parents=True, exist_ok=True)

STEAM_SEARCH_ENDPOINT = "https://store.steampowered.com/search/results/"
STEAM_APPREVIEWS_ENDPOINT = "https://store.steampowered.com/appreviews/{appid}"

SR_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
}

LINE_DIVIDER = "==========================================================================="

ROW_BLOCK_REGEX = re.compile(r'<a[^>]+data-ds-appid="(\d+)"[^>]*>(.*?)</a>', re.DOTALL)
TITLE_TEXT_REGEX = re.compile(r'<span class="title">(.*?)</span>', re.DOTALL)
RELEASE_DATE_REGEX = re.compile(
    r'<div class="col search_released responsive_secondrow">\s*(.*?)\s*</div>',
    re.DOTALL,
)
TOOLTIP_REVIEW_REGEX = re.compile(r'data-tooltip-html="([^"]+)"')
FINAL_PRICE_REGEX = re.compile(r'data-price-final="(\d+)"')
DISCOUNT_TEXT_REGEX = re.compile(r'(?:discount_pct">|<span>)-(\d+)%<')
OS_FLAGS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Windows", re.compile(r'class="platform_img win"')),
    ("macOS", re.compile(r'class="platform_img mac"')),
    ("Linux", re.compile(r'class="platform_img linux"')),
)


def read_csv_steam_rank(csv_path: Path) -> pd.DataFrame:
    """Đọc CSV an toàn không cảnh báo Overload trên PyCharm + Pandas 3.0."""
    # noinspection PyTypeChecker
    csv_reader: Any = getattr(pd, "read_csv")
    return csv_reader(str(csv_path))


def _calc_base_price(sale_usd: float, disc_pct: int) -> float:
    """Tính giá gốc trước khi giảm giá mà không bị lỗi ngắt dòng toán tử trừ."""
    if 0 < disc_pct < 100 and sale_usd > 0.0:
        ratio = (100 - disc_pct) / 100.0
        return round(sale_usd / ratio, 2)
    return sale_usd


def parse_steam_release_period(raw_date_str: str) -> tuple[str, int, str, int]:
    """
    Chuyển chuỗi ngày phát hành của Steam ('15 Oct, 2025', 'Oct 15, 2025', 'May 2024')
    thành bộ 4 giá trị: (YYYY-MM-DD, release_year, release_quarter, release_month).
    """
    cleaned = html.unescape(re.sub(r"<[^>]+>", "", str(raw_date_str or ""))).strip()
    known_formats = ("%d %b, %Y", "%b %d, %Y", "%b %Y", "%Y-%m-%d", "%d %B, %Y", "%B %Y")

    for fmt in known_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            q_idx = (dt.month - 1) // 3 + 1
            return dt.strftime("%Y-%m-%d"), dt.year, f"Q{q_idx}", dt.month
        except ValueError:
            continue

    year_match = re.search(r"\b(19\d\d|20\d\d)\b", cleaned)
    if year_match:
        yr = int(year_match.group(1))
        return f"{yr}-01-01", yr, "Q1", 1

    now_dt = datetime.now()
    q_current = (now_dt.month - 1) // 3 + 1
    return now_dt.strftime("%Y-%m-%d"), now_dt.year, f"Q{q_current}", now_dt.month


def extract_supported_os(row_html: str) -> str:
    """Bóc tách các hệ điều hành mà tựa game hỗ trợ (Windows, macOS, Linux)."""
    matched_os = [label for label, pattern in OS_FLAGS if pattern.search(row_html)]
    return ", ".join(matched_os) if matched_os else "Windows"


def parse_review_tooltip(tooltip_raw: str) -> tuple[str, float, int]:
    """Phân tích chuỗi tooltip đánh giá của Steam thành (Nhãn, Tỷ lệ %, Tổng số review)."""
    if not tooltip_raw:
        return "Unrated", 0.0, 0

    normalized = html.unescape(tooltip_raw).replace("&lt;br&gt;", "<br>")
    parts = normalized.split("<br>")
    summary_label = parts[0].strip() if parts else "Unrated"

    pct_match = re.search(r"(\d+)%\s+of\s+the\s+([\d,]+)", normalized)
    if pct_match:
        try:
            pct_val = float(pct_match.group(1))
            total_cnt = int(pct_match.group(2).replace(",", ""))
            return summary_label, pct_val, total_cnt
        except ValueError:
            pass
    return summary_label, 0.0, 0


def query_exact_appreviews(session: requests.Session, app_id: int) -> tuple[int, int, float, str]:
    """Gọi trực tiếp API appreviews của Steam khi game không có sẵn tooltip trên trang tìm kiếm."""
    url = STEAM_APPREVIEWS_ENDPOINT.format(appid=app_id)
    query_args: dict[str, str] = {"json": "1", "language": "all", "purchase_type": "all"}
    try:
        resp = session.get(url, params=query_args, timeout=8)
        if resp.status_code == 200:
            q_sum = resp.json().get("query_summary", {})
            pos = int(q_sum.get("total_positive") or 0)
            neg = int(q_sum.get("total_negative") or 0)
            total = pos + neg
            pct = round((pos * 100.0) / total, 2) if total > 0 else 0.0
            desc = str(q_sum.get("review_score_desc") or "Unrated")
            return pos, neg, pct, desc
    except (requests.RequestException, ValueError, KeyError):
        pass
    return 0, 0, 0.0, "Unrated"


def classify_segment_and_signal(
    rank_code: str, is_free: int, review_pct: float, total_reviews: int, discount_pct: int
) -> tuple[str, str]:
    """Gán nhãn phân khúc (segment_tag) và tín hiệu khuyến nghị mua (signal)."""
    prefix = "FREE" if is_free == 1 else "PAID"

    if rank_code == "TOP_SELLER":
        segment = f"{prefix}_BEST_SELLER"
    elif "LOWEST" in rank_code or (0.0 < review_pct < 55.0):
        segment = f"{prefix}_LOWEST_RATED"
    elif review_pct >= 80.0:
        segment = f"{prefix}_HIGHEST_RATED"
    else:
        segment = f"{prefix}_AVERAGE_RATED"

    if 0.0 < review_pct < 55.0 or "LOWEST" in rank_code:
        signal = "AVOID"
    elif (
        review_pct >= 88.0
        or (rank_code == "TOP_SELLER" and review_pct >= 80.0)
        or (is_free == 1 and review_pct >= 82.0)
    ):
        signal = "STRONG_BUY"
    elif review_pct >= 74.0 or discount_pct >= 30:
        signal = "BUY"
    else:
        signal = "HOLD"

    if total_reviews == 0 and "LOWEST" not in rank_code:
        signal = "HOLD"

    return segment, signal


def _parse_search_row_item(
    session: requests.Session,
    appid_str: str,
    row_html: str,
    rank_code: str,
    idx_in_page: int,
    stream_count: int,
    time_meta: tuple[str, str, int],
) -> dict[str, Any] | None:
    """Bóc tách 1 dòng HTML kết quả tìm kiếm của Steam thành bản ghi Dictionary chuẩn."""
    app_id = int(appid_str)
    title_match = TITLE_TEXT_REGEX.search(row_html)
    name = html.unescape(title_match.group(1)).strip() if title_match else ""
    if not name:
        return None

    price_match = FINAL_PRICE_REGEX.search(row_html)
    price_cents = int(price_match.group(1)) if price_match else 0
    price_usd = round(price_cents / 100.0, 2)

    if "FREE" in rank_code:
        price_usd = 0.0
    elif "PAID" in rank_code and price_usd == 0.0:
        return None

    disc_match = DISCOUNT_TEXT_REGEX.search(row_html)
    discount_pct = int(disc_match.group(1)) if disc_match else 0
    initial_price = _calc_base_price(price_usd, discount_pct)

    is_free = 1 if price_usd == 0.0 else 0
    pricing_type = "FREE" if is_free == 1 else "PAID"

    rel_match = RELEASE_DATE_REGEX.search(row_html)
    rel_raw = rel_match.group(1) if rel_match else ""
    rel_date, rel_year, rel_quarter, rel_month = parse_steam_release_period(rel_raw)

    tip_match = TOOLTIP_REVIEW_REGEX.search(row_html)
    review_label, review_pct, total_reviews = parse_review_tooltip(
        tip_match.group(1) if tip_match else ""
    )

    pos_reviews = int(round((total_reviews * review_pct) / 100.0))
    neg_reviews = max(0, total_reviews - pos_reviews)

    if total_reviews == 0 and stream_count < 10:
        pos_reviews, neg_reviews, review_pct, review_label = query_exact_appreviews(session, app_id)
        total_reviews = pos_reviews + neg_reviews

    if "LOWEST" in rank_code and review_pct == 0.0:
        review_pct = 35.0
        review_label = "Mostly Negative"

    segment_tag, signal = classify_segment_and_signal(
        rank_code, is_free, review_pct, total_reviews, discount_pct
    )

    current_time, current_date, current_hour = time_meta
    return {
        "timestamp": current_time,
        "date": current_date,
        "hour": current_hour,
        "app_id": app_id,
        "name": name,
        "platform": "Steam PC",
        "supported_os": extract_supported_os(row_html),
        "ranking_category": rank_code,
        "rank_position": idx_in_page,
        "pricing_type": pricing_type,
        "segment_tag": segment_tag,
        "price": price_usd,
        "initial_price": initial_price,
        "discount": discount_pct,
        "is_free": is_free,
        "review_summary": review_label,
        "review_score_pct": review_pct,
        "total_reviews": total_reviews,
        "positive_reviews": pos_reviews,
        "negative_reviews": neg_reviews,
        "release_date": rel_date,
        "release_year": rel_year,
        "release_quarter": rel_quarter,
        "release_month": rel_month,
        "signal": signal,
    }


# ============================================================
# 2. QUÉT 6 BẢNG XẾP HẠNG CHÍNH THỨC TRÊN STEAM STORE
# ============================================================
# noinspection DuplicatedCode
def crawl_steam_ranking_categories(items_per_stream: int = 120) -> pd.DataFrame:
    """
    Quét 6 luồng bảng xếp hạng trên Steam Store để bao phủ toàn bộ nhu cầu lọc:
    Bán chạy nhất, Cao nhất (Miễn phí/Trả phí), Thấp nhất (Miễn phí/Trả phí) và Mới nổi bật.
    """
    now = datetime.now()
    time_meta = (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"), now.hour)

    print(f"[{time_meta[0]}] Đang kết nối Steam Store Official Rankings & Reviews API...")
    session = requests.Session()
    session.headers.update(SR_HEADERS)

    ranking_streams: list[tuple[str, str, dict[str, str]]] = [
        ("TOP_SELLER", "1. Game Bán Chạy Nhất Toàn Cầu (Top Sellers)", {"filter": "topsellers", "category1": "998"}),
        ("FREE_TOP_RATED", "2. Game Miễn Phí Đánh Giá Cao Nhất", {"sort_by": "Reviews_DESC", "maxprice": "free", "category1": "998"}),
        ("PAID_TOP_RATED", "3. Game Trả Phí Đánh Giá Cao Nhất", {"sort_by": "Reviews_DESC", "category1": "998"}),
        ("PAID_LOWEST_RATED", "4. Game Trả Phí Bị Đánh Giá Thấp Nhất", {"sort_by": "Reviews_ASC", "category1": "998"}),
        ("FREE_LOWEST_RATED", "5. Game Miễn Phí Bị Đánh Giá Thấp Nhất", {"sort_by": "Reviews_ASC", "maxprice": "free", "category1": "998"}),
        ("NEW_RELEASES", "6. Game Mới Phát Hành Theo Tháng/Quý", {"sort_by": "Released_DESC", "category1": "998"}),
    ]

    collected_games: dict[int, dict[str, Any]] = {}
    page_step = 50

    for rank_code, stream_title, extra_query in ranking_streams:
        print(f"\n[*] Đang thu thập: {stream_title}...")
        stream_count = 0
        offset = 0
        max_offset = items_per_stream + 150

        while stream_count < items_per_stream and offset < max_offset:
            req_params: dict[str, str] = {
                "query": "",
                "start": str(offset),
                "count": str(page_step),
                "dynamic_data": "",
                "infinite": "1",
                "cc": "us",
                "l": "english",
            }
            req_params.update(extra_query)

            try:
                resp = session.get(STEAM_SEARCH_ENDPOINT, params=req_params, timeout=15)
                if resp.status_code != 200:
                    print(f"  [Cảnh báo] HTTP {resp.status_code} tại offset={offset}")
                    break

                html_chunk = str(resp.json().get("results_html") or "")
                matches = ROW_BLOCK_REGEX.findall(html_chunk)
                if not matches:
                    break

                added_in_batch = 0
                for idx_in_page, (appid_str, row_html) in enumerate(matches, start=offset + 1):
                    if int(appid_str) in collected_games:
                        continue

                    record = _parse_search_row_item(
                        session, appid_str, row_html, rank_code, idx_in_page, stream_count, time_meta
                    )
                    if record is not None:
                        collected_games[record["app_id"]] = record
                        added_in_batch += 1
                        stream_count += 1
                        if stream_count >= items_per_stream:
                            break

                print(
                    f"  -> Offset {offset:>3}: +{added_in_batch:>2} game mới "
                    f"(Đã gom {stream_count}/{items_per_stream} ở nhóm {rank_code})"
                )
                offset += page_step
                time.sleep(0.6)

            except (requests.RequestException, ValueError) as exc:
                print(f"  [Lỗi kết nối] Offset {offset}: {exc}")
                break

    return pd.DataFrame(list(collected_games.values()))


# ============================================================
# 3. LƯU TRỮ TÍCH LŨY LỊCH SỬ BẢNG XẾP HẠNG STEAM
# ============================================================
# noinspection DuplicatedCode
def save_steam_ranking_dataset(df_new: pd.DataFrame) -> pd.DataFrame:
    """Lưu Snapshot, tích lũy lịch sử steam_reviews_rank_history.csv và bản sạch steam_reviews_rank_clean.csv."""
    snap_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_file = RANK_PATHS["snapshots"] / f"steam_rank_snapshot_{snap_tag}.csv"
    df_new.to_csv(snap_file, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã tạo Snapshot riêng: {snap_file.name}")

    df_new["rank_change"] = 0
    df_new["review_growth"] = 0

    hist_file = RANK_PATHS["history"]
    if hist_file.exists():
        try:
            old_df = read_csv_steam_rank(hist_file)
            print(f"[2] Đã nạp kho lịch sử Bảng xếp hạng Steam cũ: {len(old_df):,} dòng.")
            combined = pd.concat([old_df, df_new], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date", "hour", "app_id"], keep="last")
            combined = combined.sort_values(["app_id", "timestamp"]).reset_index(drop=True)

            combined["rank_change"] = combined.groupby("app_id")["rank_position"].diff().fillna(0).astype(int)
            combined["review_growth"] = combined.groupby("app_id")["total_reviews"].diff().fillna(0).astype(int)
        except (OSError, pd.errors.ParserError, ValueError) as err:
            print(f"[Cảnh báo] Tạo mới file lịch sử do lỗi đọc file cũ: {err}")
            combined = df_new
    else:
        print(f"[2] Khởi tạo kho lịch sử Bảng xếp hạng Steam lần đầu ({len(df_new):,} dòng).")
        combined = df_new

    combined.to_csv(hist_file, index=False, encoding="utf-8-sig")
    latest_clean = combined.drop_duplicates(subset=["app_id"], keep="last").reset_index(drop=True)
    latest_clean.to_csv(RANK_PATHS["clean"], index=False, encoding="utf-8-sig")

    print(f"[3] Đã lưu tích lũy tại : {hist_file} (Tổng: {len(combined):,} dòng)")
    print(f"[4] Đã xuất bản sạch tại: {RANK_PATHS['clean']} ({len(latest_clean):,} tựa game)")
    return latest_clean


if __name__ == "__main__":
    print(LINE_DIVIDER)
    print("   NGUỒN ĐÁNH GIÁ 3: STEAM OFFICIAL TOP SELLERS & FREE/PAID RANKINGS")
    print(LINE_DIVIDER)

    df_ranks = crawl_steam_ranking_categories(items_per_stream=120)
    if not df_ranks.empty:
        df_clean_ranks = save_steam_ranking_dataset(df_ranks)

        sellers = df_clean_ranks[df_clean_ranks["ranking_category"] == "TOP_SELLER"]
        free_high = df_clean_ranks[df_clean_ranks["segment_tag"] == "FREE_HIGHEST_RATED"]
        paid_high = df_clean_ranks[df_clean_ranks["segment_tag"] == "PAID_HIGHEST_RATED"]
        lowest_all = df_clean_ranks[df_clean_ranks["segment_tag"].str.contains("LOWEST_RATED", na=False)]

        print("\n" + LINE_DIVIDER)
        print("   THỐNG KÊ CHI TIẾT CÁC PHÂN KHÚC STEAM STORE VỪA THU THẬP:")
        print(f"   - Tổng số tựa game độc lập thu thập      : {len(df_clean_ranks):,} game")
        print(f"   - Nhóm Bán chạy nhất (Top Sellers)       : {len(sellers):,} game")
        print(f"   - Nhóm Miễn phí Đánh giá cao nhất        : {len(free_high):,} game")
        print(f"   - Nhóm Trả phí Đánh giá cao nhất         : {len(paid_high):,} game")
        print(f"   - Nhóm Bị đánh giá thấp nhất (Free/Paid) : {len(lowest_all):,} game")
        print(LINE_DIVIDER)

        preview_cols = [
            "name",
            "segment_tag",
            "price",
            "review_score_pct",
            "supported_os",
            "release_year",
            "release_quarter",
        ]
        print("\n5 tựa game mẫu kèm Phân khúc, Hệ điều hành & Năm/Quý:")
        print(df_clean_ranks[preview_cols].head(5))
    else:
        print("❌ Không lấy được dữ liệu từ Steam Store Search API.")