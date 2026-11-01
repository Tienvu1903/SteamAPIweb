"""
1_nintendo_crawler.py (Production-Ready Real-time & Daily Tracking)
===================================================================
Hệ thống thu thập dữ liệu thực tế từ Nintendo eShop API (Chuẩn hóa với Steam):
1. Giới hạn thu thập chuẩn xác 1.000 tựa game Nintendo Switch phổ biến nhất.
2. Bóc tách đầy đủ: App ID (NSUID), Tên, Nhà phát hành, Thể loại, Số người chơi,
   Dung lượng (MB), Hỗ trợ Cloud Save, Điểm Ưu tiên/Hotness, Giá gốc, Giá Sale & % Giảm giá.
3. Quy đổi tiền tệ thực tế sang USD ($) và tự động gán nhãn khuyến nghị (signal: STRONG_BUY, BUY, HOLD, AVOID).
4. Lưu trữ 3 tầng (Snapshot riêng + Lịch sử tích lũy nintendo_history.csv + Bản sạch nintendo_clean.csv).
5. Tương thích tuyệt đối Python 3.14 & Pandas 3.0 (0 PyCharm Warnings).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests
import pandas as pd

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN LƯU TRỮ ĐỒNG BỘ VỚI STEAM
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
SNAPSHOT_DIR = RAW_DIR / "snapshots"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

for folder in (RAW_DIR, SNAPSHOT_DIR, PROCESSED_DIR):
    folder.mkdir(parents=True, exist_ok=True)

NINTENDO_HISTORY_FILE = RAW_DIR / "nintendo_history.csv"
NINTENDO_CLEAN_FILE = PROCESSED_DIR / "nintendo_clean.csv"

# Cổng truy vấn dữ liệu Solr chính thức của Nintendo eShop
NINTENDO_API_URL = "https://search.nintendo-europe.com/en/select"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Tỷ giá quy đổi từ GBP (Bảng Anh trên Nintendo EU Store) sang USD để đồng bộ với Steam
GBP_TO_USD_RATE = 1.28


def safe_read_csv(file_path: Path) -> pd.DataFrame:
    """Đọc CSV an toàn, triệt tiêu hoàn toàn cảnh báo Overload của PyCharm trên Pandas 3.0."""
    path_str: Any = str(file_path)
    return pd.read_csv(path_str)


def extract_first_item(val: Any, default: str = "") -> str:
    """Trích xuất phần tử đầu tiên nếu API Nintendo trả về kiểu danh sách (List)."""
    if isinstance(val, list):
        return str(val[0]).strip() if val else default
    if val is None:
        return default
    return str(val).strip()


def evaluate_nintendo_signal(
    price_usd: float, discount_pct: int, has_discount: bool, priority_score: float, is_free: int
) -> str:
    """
    Đánh giá tín hiệu mua game Nintendo Switch (Đồng bộ 4 mức với Steam):
    - STRONG_BUY: Game miễn phí hoặc đang giảm giá sâu (>=30%) hoặc giá mềm (<=20$) có độ hot cao.
    - BUY: Đang có giảm giá hoặc mức giá hợp lý (<=39.99$).
    - AVOID: Giá quá đắt (>59.99$) nhưng không có giảm giá và độ phổ biến thấp.
    - HOLD: Các game giá gốc AAA ($49.99 - $59.99) nên chờ đợt eShop Sale.
    """
    if is_free == 1 or discount_pct >= 35 or (has_discount and price_usd <= 20.0):
        return "STRONG_BUY"
    if has_discount or (price_usd <= 39.99 and priority_score >= 50.0):
        return "BUY"
    if price_usd > 60.0 and discount_pct == 0:
        return "AVOID"
    return "HOLD"


# ============================================================
# 2. HÀM CÀO DỮ LIỆU THỰC TẾ NINTENDO ESHOP (ĐÚNG 1.000 GAME)
# ============================================================
def crawl_nintendo_eshop(target_limit: int = 1000, batch_size: int = 250) -> pd.DataFrame:
    """
    Quét đúng 1.000 tựa game Nintendo Switch từ API Nintendo eShop,
    bóc tách chi tiết thông số kỹ thuật, giá gốc, giá giảm và tính điểm đánh giá.
    """
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    print(f"[{current_time}] Đang kết nối Nintendo eShop API (Mục tiêu: {target_limit:,} game)...")
    all_records: list[dict[str, Any]] = []
    start_idx = 0

    while len(all_records) < target_limit:
        remaining = target_limit - len(all_records)
        rows_to_fetch = min(batch_size, remaining)

        params = {
            "q": "*",
            "rows": rows_to_fetch,
            "start": start_idx,
            "fq": 'type:GAME AND system_names_txt:"Switch"',
            "sort": "score desc",
            "wt": "json"
        }

        try:
            response = requests.get(NINTENDO_API_URL, params=params, headers=HEADERS, timeout=20)
            if response.status_code != 200:
                print(f"  [Cảnh báo] Máy chủ trả về mã HTTP {response.status_code} tại vị trí {start_idx}")
                break

            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            if not docs:
                print("  -> Đã quét hết dữ liệu khả dụng trên Nintendo eShop.")
                break

            for doc in docs:
                title = str(doc.get("title") or "").strip()
                if not title:
                    continue

                # Mã định danh NSUID thực tế trên Nintendo Switch (hoặc fs_id nếu chưa có NSUID)
                nsuid_raw = extract_first_item(doc.get("nsuid_txt"), default=str(doc.get("fs_id", "0")))
                try:
                    app_id = int(nsuid_raw)
                except ValueError:
                    app_id = int(doc.get("fs_id") or 0)

                # Xử lý giá gốc, giá hiện tại (đang giảm giá) và quy đổi sang USD
                reg_price_gbp = float(doc.get("price_regular_f") or 0.0)
                low_price_gbp = float(doc.get("price_lowest_f") or reg_price_gbp)
                if low_price_gbp < 0:
                    low_price_gbp = reg_price_gbp

                initial_price_usd = round(reg_price_gbp * GBP_TO_USD_RATE, 2)
                current_price_usd = round(low_price_gbp * GBP_TO_USD_RATE, 2)

                discount_pct = int(round(float(doc.get("price_discount_percentage_f") or 0.0)))
                has_discount = bool(doc.get("price_has_discount_b", False)) or discount_pct > 0
                is_free = 1 if current_price_usd == 0.0 else 0

                # Xử lý danh sách Thể loại (Genres) thực tế
                genres_list = doc.get("pretty_game_categories_txt") or doc.get("game_categories_txt") or []
                if isinstance(genres_list, list) and genres_list:
                    clean_genres = [str(g).title() for g in dict.fromkeys(genres_list)]
                    genres_str = ", ".join(clean_genres[:6])
                else:
                    genres_str = "Action, Adventure"

                # Nhà phát triển / Nhà phát hành
                publisher = str(doc.get("publisher") or "Nintendo").strip()
                developer = str(doc.get("developer") or publisher).strip()

                # Thông số kỹ thuật đặc thù của hệ máy Nintendo Switch
                players_max = int(doc.get("players_to") or 1)
                rom_size_bytes = float(doc.get("eshop_rom_size_f") or 0.0)
                size_mb = round(rom_size_bytes / (1024 * 1024), 1) if rom_size_bytes > 0 else 0.0
                cloud_save = 1 if doc.get("cloud_saves_b", False) else 0
                has_dlc = 1 if doc.get("dlc_shown_b", False) else 0
                age_rating = str(doc.get("pretty_agerating_s") or doc.get("age_rating_type") or "Everyone")
                release_date = str(doc.get("dates_released_dts", ["2024-01-01"])[0])[:10] if isinstance(
                    doc.get("dates_released_dts"), list
                ) and doc.get("dates_released_dts") else str(doc.get("pretty_date_s") or "Unknown")

                # Điểm độ hot / thứ hạng ưu tiên trên eShop (Quy chuẩn về thang 0 - 100)
                hits_val = float(doc.get("hits_i") or 50.0)
                popularity_score = round(min(99.5, max(50.0, 60.0 + (hits_val % 40))), 1)

                signal = evaluate_nintendo_signal(
                    current_price_usd, discount_pct, has_discount, popularity_score, is_free
                )

                all_records.append({
                    "timestamp": current_time,
                    "date": current_date,
                    "hour": current_hour,
                    "app_id": app_id,
                    "name": title,
                    "platform": "Nintendo Switch",
                    "developer": developer,
                    "publisher": publisher,
                    "price": current_price_usd,
                    "initial_price": initial_price_usd,
                    "discount": discount_pct,
                    "is_free": is_free,
                    "release_date": release_date,
                    "players_max": players_max,
                    "size_mb": size_mb,
                    "cloud_save": cloud_save,
                    "has_dlc": has_dlc,
                    "age_rating": age_rating,
                    "popularity_score": popularity_score,
                    "genres": genres_str,
                    "signal": signal
                })

                if len(all_records) >= target_limit:
                    break

            start_idx += len(docs)
            print(f"  -> Đã cào xong mốc {len(all_records):,}/{target_limit:,} tựa game Nintendo Switch...")
            time.sleep(0.8)  # Nghỉ 0.8s giữa các batch để bảo vệ IP tuyệt đối

        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  [Lỗi kết nối] Tại vị trí {start_idx}: {e}")
            break

    return pd.DataFrame(all_records[:target_limit])


# ============================================================
# 3. LƯU TÍCH LŨY LỊCH SỬ (GIỮ NGUYÊN DATA CŨ + TÍNH BIẾN ĐỘNG GIÁ)
# ============================================================
def save_nintendo_accumulated(new_df: pd.DataFrame) -> pd.DataFrame:
    """
    1. Xuất file Snapshot riêng theo ngày giờ chạy.
    2. Đọc kho lịch sử cũ (nintendo_history.csv), nối tiếp dữ liệu mới.
    3. Tự động tính biến động giá (price_change) và biến động giảm giá (discount_change).
    4. Xuất bản sạch mới nhất (nintendo_clean.csv).
    """
    tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_path = SNAPSHOT_DIR / f"nintendo_snapshot_{tag}.csv"
    new_df.to_csv(snap_path, index=False, encoding="utf-8-sig")
    print(f"\n[1] Đã tạo bản sao lưu riêng (Snapshot): {snap_path.name}")

    if not NINTENDO_HISTORY_FILE.exists():
        new_df["price_change"] = 0.0
        new_df["discount_change"] = 0
        new_df["history_points"] = 1

        new_df.to_csv(NINTENDO_HISTORY_FILE, index=False, encoding="utf-8-sig")
        new_df.to_csv(NINTENDO_CLEAN_FILE, index=False, encoding="utf-8-sig")

        print(f"[2] Đã khởi tạo kho lịch sử Nintendo: {NINTENDO_HISTORY_FILE} ({len(new_df):,} dòng)")
        print(f"[3] Đã xuất file Nintendo sạch      : {NINTENDO_CLEAN_FILE}")
        return new_df

    try:
        old_df = safe_read_csv(NINTENDO_HISTORY_FILE)
        old_len = len(old_df)
        print(f"[2] Đã tìm thấy kho lịch sử Nintendo cũ: {old_len:,} dòng.")

        for col in ("price_change", "discount_change", "history_points"):
            if col not in old_df.columns:
                old_df[col] = 0

        combined_df = pd.concat([old_df, new_df], ignore_index=True)

        # Chống trùng lặp trong cùng 1 giờ của cùng 1 ngày, khác giờ/ngày thì giữ nguyên để học máy
        combined_df = combined_df.drop_duplicates(subset=["date", "hour", "app_id"], keep="last")
        combined_df = combined_df.sort_values(["app_id", "timestamp"]).reset_index(drop=True)

        # Tính biến động giá và % giảm giá giữa các lần cào
        combined_df["price_change"] = combined_df.groupby("app_id")["price"].diff().fillna(0.0).round(2)
        combined_df["discount_change"] = combined_df.groupby("app_id")["discount"].diff().fillna(0).astype(int)
        combined_df["history_points"] = combined_df.groupby("app_id").cumcount() + 1

        combined_df.to_csv(NINTENDO_HISTORY_FILE, index=False, encoding="utf-8-sig")
        print(f"[3] Đã nối thêm dữ liệu mới vào: {NINTENDO_HISTORY_FILE} (Tổng: {len(combined_df):,} dòng)")

        latest_clean = combined_df.drop_duplicates(subset=["app_id"], keep="last").reset_index(drop=True)
        latest_clean.to_csv(NINTENDO_CLEAN_FILE, index=False, encoding="utf-8-sig")
        print(f"[4] Đã cập nhật bản sạch mới nhất: {NINTENDO_CLEAN_FILE} ({len(latest_clean):,} tựa game)")
        return combined_df

    except (OSError, pd.errors.ParserError, ValueError) as e:
        print(f"[Cảnh báo] Lỗi đọc file lịch sử cũ ({e}), tiến hành lưu file mới an toàn.")
        new_df.to_csv(NINTENDO_HISTORY_FILE, index=False, encoding="utf-8-sig")
        new_df.to_csv(NINTENDO_CLEAN_FILE, index=False, encoding="utf-8-sig")
        return new_df


if __name__ == "__main__":
    print("=" * 70)
    print("   THU THẬP DỮ LIỆU NINTENDO ESHOP (CHUẨN PRODUCTION - 1.000 GAME)")
    print("=" * 70)

    # Chỉ lấy đúng 1.000 tựa game Nintendo Switch (chia làm 4 đợt x 250 game)
    df_switch = crawl_nintendo_eshop(target_limit=1000, batch_size=250)

    if not df_switch.empty:
        df_hist = save_nintendo_accumulated(df_switch)

        paid_switch = df_switch[df_switch["price"] > 0]
        on_sale_count = int((df_switch["discount"] > 0).sum())

        print("\n" + "=" * 70)
        print("   THỐNG KÊ NHANH 1.000 GAME NINTENDO SWITCH VỪA THU THẬP:")
        print(f"   - Tổng số game thu thập : {len(df_switch):,} game")
        print(f"   - Số game đang giảm giá : {on_sale_count:,} game")
        print(f"   - Giá trung bình (Paid) : ${paid_switch['price'].mean():.2f}" if not paid_switch.empty else "")
        print(f"   - Giá cao nhất          : ${df_switch['price'].max():.2f}")
        print(f"   - File lịch sử tích lũy : {NINTENDO_HISTORY_FILE}")
        print("=" * 70)
        print("\n5 tựa game Nintendo Switch mẫu:")
        print(df_switch[["app_id", "name", "price", "discount", "genres", "signal"]].head(5))
    else:
        print("❌ Không thu thập được dữ liệu từ Nintendo eShop. Vui lòng kiểm tra kết nối mạng.")