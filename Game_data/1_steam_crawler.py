"""
1_steam_crawler.py
==================
BƯỚC 1: THU THẬP DỮ LIỆU STEAM API & LƯU TRỮ TÍCH LŨY LỊCH SỬ (TIME-SERIES STORAGE)
- Cào dữ liệu thực tế từ SteamSpy API (~1.000+ tựa game mỗi lần chạy).
- Giữ nguyên 100% dữ liệu cũ: Đọc kho lịch sử cũ -> Nối thêm dữ liệu mới -> Lưu tích lũy.
- Tự động tạo bản sao lưu (Snapshot) theo từng ngày chạy trong data/raw/snapshots/.
- Tự động tính toán độ chênh lệch với dữ liệu cũ (ccu_change, price_change, review_growth)
  để làm đặc trưng chuỗi thời gian cho Machine Learning ở bước sau.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH THƯ MỤC LƯU TRỮ DỮ LIỆU
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
SNAPSHOT_DIR = RAW_DIR / "snapshots"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"

for folder in (RAW_DIR, SNAPSHOT_DIR, PROCESSED_DIR, ANALYSIS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# File lưu tích lũy toàn bộ lịch sử từ các lần cào (Dùng để train ML chuỗi thời gian)
HISTORY_FILE = RAW_DIR / "steam_history.csv"
# File dữ liệu đã xử lý kèm biến động so với lần cũ
CLEAN_FILE = PROCESSED_DIR / "steam_clean.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def safe_read_csv(file_path: Path) -> pd.DataFrame:
    """Đọc file CSV an toàn, không bị cảnh báo Overload trên PyCharm + Pandas 3.0."""
    path_str: Any = str(file_path)
    return pd.read_csv(path_str)


def parse_owners(owners_str: str) -> int:
    """Chuyển chuỗi khoảng sở hữu '1,000,000 .. 2,000,000' thành con số trung bình (1500000)."""
    try:
        clean_str = str(owners_str).replace(",", "")
        parts = clean_str.split("..")
        if len(parts) == 2:
            low = int(parts[0].strip())
            high = int(parts[1].strip())
            return (low + high) // 2
        return 0
    except (ValueError, TypeError, IndexError):
        return 0


def fetch_app_tags(app_id: int | str) -> str:
    """Lấy danh sách Tags/Thể loại thực tế từ API chi tiết của từng game."""
    url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            tags_dict = data.get("tags", {})
            if isinstance(tags_dict, dict) and tags_dict:
                top_tags = list(tags_dict.keys())[:6]
                return ", ".join(top_tags)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return ""


def generate_inferred_tags(price: float, ccu: int, avg_playtime: int, pos_ratio: float) -> str:
    """Gán nhãn thể loại đặc trưng dựa trên thông số thực tế của game."""
    tags = []
    if price == 0:
        tags.append("Free to Play")
    elif price >= 40:
        tags.append("AAA")
    else:
        tags.append("Indie")

    if ccu >= 10000:
        tags.extend(["Multiplayer", "Competitive", "Co-op"])
    elif ccu >= 1000:
        tags.extend(["Action", "Multiplayer"])
    else:
        tags.extend(["Singleplayer", "Adventure"])

    if avg_playtime >= 1200:
        tags.extend(["RPG", "Strategy", "Simulation"])
    elif avg_playtime >= 300:
        tags.extend(["Action", "Open World"])
    else:
        tags.extend(["Casual", "Arcade"])

    if pos_ratio >= 90:
        tags.append("Masterpiece")

    unique_tags = list(dict.fromkeys(tags))
    return ", ".join(unique_tags[:6])


def evaluate_game_signal(price: float, review_pct: float, discount: int, ccu: int) -> str:
    """Đánh giá tín hiệu mua game (STRONG_BUY, BUY, HOLD, AVOID)."""
    if review_pct >= 85 and (discount >= 30 or price <= 15.0 or ccu >= 5000):
        return "STRONG_BUY"
    if review_pct >= 75 and price <= 39.99:
        return "BUY"
    if review_pct < 55 and price > 10.0:
        return "AVOID"
    return "HOLD"


# ============================================================
# 2. HÀM CÀO DỮ LIỆU TỪ STEAMSPY API
# ============================================================
def crawl_steam_api(max_pages: int = 1, enrich_top_n: int = 20) -> pd.DataFrame:
    """Kết nối SteamSpy API và thu thập dữ liệu game hiện tại."""
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    print(f"[{current_time}] Đang kết nối SteamSpy API để cào dữ liệu mới...")
    raw_games: dict[str, dict[str, Any]] = {}

    endpoints = [
        ("Top 100 Trending (2 tuần)", "https://steamspy.com/api.php?request=top100in2weeks"),
        ("Top 100 Most Played", "https://steamspy.com/api.php?request=top100forever"),
    ]

    for label, url in endpoints:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    raw_games.update(data)
                    print(f"  -> Đã tải {len(data)} game từ bảng: {label}")
            time.sleep(1)
        except (requests.RequestException, ValueError) as e:
            print(f"  [Cảnh báo] Không tải được {label}: {e}")

    for page in range(max_pages):
        url = f"https://steamspy.com/api.php?request=all&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    raw_games.update(data)
                    print(f"  -> Đã tải thêm trang {page + 1}/{max_pages} (Tổng cộng: {len(raw_games)} game)")
            time.sleep(1)
        except (requests.RequestException, ValueError) as e:
            print(f"  [Cảnh báo] Lỗi tải trang {page + 1}: {e}")

    records = []
    game_items = list(raw_games.items())
    print(f"[*] Đang bóc tách và xử lý {len(game_items)} tựa game...")

    for idx, (appid, details) in enumerate(game_items, 1):
        name = str(details.get("name") or "").strip()
        if not name:
            continue

        try:
            price = float(details.get("price") or 0) / 100.0
            initial_price = float(details.get("initialprice") or 0) / 100.0
            discount = int(details.get("discount") or 0)
        except (ValueError, TypeError):
            price, initial_price, discount = 0.0, 0.0, 0

        pos = int(details.get("positive") or 0)
        neg = int(details.get("negative") or 0)
        total_reviews = pos + neg
        review_score_pct = round((pos / total_reviews) * 100, 2) if total_reviews > 0 else 0.0

        owners_raw = str(details.get("owners") or "0 .. 0")
        owners_est = parse_owners(owners_raw)
        ccu = int(details.get("ccu") or 0)
        avg_playtime = int(details.get("average_forever") or 0)
        playtime_hours = round(avg_playtime / 60.0, 1)

        if idx <= enrich_top_n:
            fetched_tags = fetch_app_tags(appid)
            tags_str = fetched_tags if fetched_tags else generate_inferred_tags(
                price, ccu, avg_playtime, review_score_pct
            )
            if idx % 10 == 0:
                print(f"  -> Đã lấy Tags chi tiết cho {idx}/{enrich_top_n} game đầu...")
            time.sleep(0.25)
        else:
            tags_str = generate_inferred_tags(price, ccu, avg_playtime, review_score_pct)

        signal = evaluate_game_signal(price, review_score_pct, discount, ccu)

        records.append({
            "timestamp": current_time,
            "date": current_date,
            "hour": current_hour,
            "app_id": int(appid),
            "name": name,
            "developer": str(details.get("developer") or "Unknown"),
            "publisher": str(details.get("publisher") or "Unknown"),
            "price": round(price, 2),
            "initial_price": round(initial_price, 2),
            "discount": discount,
            "is_free": 1 if price == 0 else 0,
            "owners_range": owners_raw,
            "owners_est": owners_est,
            "ccu": ccu,
            "positive": pos,
            "negative": neg,
            "total_reviews": total_reviews,
            "review_score_pct": review_score_pct,
            "avg_playtime_hours": playtime_hours,
            "genres": tags_str,
            "signal": signal
        })

    return pd.DataFrame(records)


# ============================================================
# 3. HÀM LƯU TRỮ TÍCH LŨY (KHÔNG BAO GIỜ MẤT DỮ LIỆU CŨ)
# ============================================================
def save_accumulated_data(new_df: pd.DataFrame) -> pd.DataFrame:
    """
    1. Lưu 1 bản Snapshot riêng cho ngày hôm nay.
    2. Đọc dữ liệu cũ trong steam_history.csv, ghép nối (Append) với dữ liệu mới.
    3. Tính toán sự thay đổi (ccu_change, price_change, review_growth) giữa lần cào trước và lần này.
    4. Lưu ra steam_history.csv (lịch sử đầy đủ) và steam_clean.csv (dữ liệu đã làm giàu).
    """
    today_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_file = SNAPSHOT_DIR / f"steam_snapshot_{today_tag}.csv"
    new_df.to_csv(snapshot_file, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã tạo bản sao lưu riêng (Snapshot): {snapshot_file.name}")

    # Kiểm tra xem đã có dữ liệu lịch sử cũ chưa
    if not HISTORY_FILE.exists():
        # Lần chạy đầu tiên: Khởi tạo các cột biến động bằng 0
        new_df["ccu_change"] = 0
        new_df["price_change"] = 0.0
        new_df["review_growth"] = 0
        new_df["history_Points"] = 1

        new_df.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
        new_df.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")

        print(f"[2] Khởi tạo kho lịch sử lần đầu: {HISTORY_FILE}")
        print(f"    -> Số bản ghi đã lưu: {len(new_df):,} dòng")
        return new_df

    # Nếu đã có dữ liệu cũ: Đọc lên và ghép nối
    try:
        old_df = safe_read_csv(HISTORY_FILE)
        old_count = len(old_df)
        print(f"[2] Đã tìm thấy kho dữ liệu cũ gồm: {old_count:,} bản ghi.")

        # Đảm bảo đủ cột trước khi ghép
        for col in ("ccu_change", "price_change", "review_growth", "history_Points"):
            if col not in old_df.columns:
                old_df[col] = 0

        # Ghép dữ liệu cũ + mới
        combined_df = pd.concat([old_df, new_df], ignore_index=True)

        # Nếu cào nhiều lần trong cùng 1 giờ của cùng 1 ngày thì giữ bản mới nhất của giờ đó,
        # nhưng khác giờ hoặc khác ngày thì GIỮ NGUYÊN 100% để tích lũy lịch sử cho Machine Learning
        combined_df = combined_df.drop_duplicates(subset=["date", "hour", "app_id"], keep="last")
        combined_df = combined_df.sort_values(["app_id", "timestamp"]).reset_index(drop=True)

        # Tính toán biến động thực tế so với lần cào liền trước của từng game
        combined_df["ccu_change"] = combined_df.groupby("app_id")["ccu"].diff().fillna(0).astype(int)
        combined_df["price_change"] = combined_df.groupby("app_id")["price"].diff().fillna(0.0).round(2)
        combined_df["review_growth"] = combined_df.groupby("app_id")["total_reviews"].diff().fillna(0).astype(int)
        combined_df["history_Points"] = combined_df.groupby("app_id").cumcount() + 1

        # Lưu toàn bộ lịch sử tích lũy lại vào steam_history.csv
        combined_df.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
        print(f"[3] Đã nối thêm dữ liệu mới vào kho lịch sử: {HISTORY_FILE}")
        print(f"    -> Từ {old_count:,} dòng cũ => Tăng lên {len(combined_df):,} dòng tích lũy!")

        # Lấy trạng thái mới nhất của từng game (kèm các chỉ số biến động vừa tính) lưu ra steam_clean.csv
        latest_clean_df = combined_df.drop_duplicates(subset=["app_id"], keep="last").sort_values(
            "ccu", ascending=False
        ).reset_index(drop=True)
        latest_clean_df.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")
        print(f"[4] Đã cập nhật bản sạch mới nhất: {CLEAN_FILE} ({len(latest_clean_df):,} tựa game)")

        return combined_df

    except (OSError, pd.errors.ParserError, ValueError) as e:
        print(f"[Cảnh báo] Lỗi đọc file lịch sử cũ ({e}), hệ thống lưu file mới an toàn.")
        new_df.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
        new_df.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")
        return new_df


if __name__ == "__main__":
    print("=" * 70)
    print("   BƯỚC 1: CÀO DỮ LIỆU STEAM & LƯU TÍCH LŨY LỊCH SỬ (KHÔNG MẤT DATA CŨ)")
    print("=" * 70)

    df_new = crawl_steam_api(max_pages=1, enrich_top_n=20)

    if not df_new.empty:
        df_history = save_accumulated_data(df_new)

        print("\n" + "=" * 70)
        print("   KIỂM TRA KHO DỮ LIỆU ĐÃ LƯU TRÊN Ổ CỨNG:")
        print(f"   📁 File lịch sử tích lũy : {HISTORY_FILE}")
        print(f"      -> Tổng số bản ghi    : {len(df_history):,} dòng")
        print(f"      -> Số mốc thời gian   : {df_history['timestamp'].nunique()} lần cào")
        print(f"   📁 File dữ liệu sạch     : {CLEAN_FILE}")
        print(f"   📁 Thư mục Snapshot      : {SNAPSHOT_DIR}")
        print("=" * 70)
        print("\n5 dòng dữ liệu mẫu vừa lưu:")
        print(df_history[["timestamp", "name", "price", "ccu", "ccu_change", "signal"]].tail(5))
    else:
        print("❌ Không lấy được dữ liệu từ API. Hãy kiểm tra lại kết nối Internet.")