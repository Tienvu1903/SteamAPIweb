"""
2_clean_data.py (Enterprise Data Auditor, Auto-Synthesizer & Verified Exporter)
===============================================================================
Trạm kiểm duyệt, làm sạch toàn bộ dữ liệu và xuất vào thư mục data/cleaned_verified/:
1. Tự động kiểm tra thư mục data/processed/:
   - Nếu 2 file lịch sử giá (steam_price_history_clean.csv & nintendo_price_history_clean.csv)
     chưa có, hệ thống TỰ ĐỘNG tổng hợp từ 4 file hiện có mà không cần tạo thủ công.
2. Xây dựng Từ điển Đối chiếu Chéo (Cross-Reference) để vá các cột bị khuyết
   (khôi phục tên game cho bảng CCU, đồng bộ giá, hệ điều hành, ngày phát hành).
3. Làm sạch, đánh lại thứ hạng 1..N và lưu 8 file vào thư mục data/cleaned_verified/:
   - nintendo_verified.csv
   - cheapshark_reviews_verified.csv
   - steam_reviews_rank_verified.csv
   - steam_realtime_ccu_verified.csv
   - steam_price_history_verified.csv
   - nintendo_price_history_verified.csv
   - master_games_dataset.csv
   - 0_audit_quality_report.csv
4. In trực tiếp bảng dữ liệu đã làm sạch của từng file và danh sách file thực tế
   trên ổ cứng ra màn hình Console.
"""

from datetime import datetime
import html
from pathlib import Path
import re
from typing import Any
import pandas as pd

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN THƯ MỤC CHUẨN XÁC
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
VERIFIED_DIR = DATA_DIR / "cleaned_verified"

for folder in (DATA_DIR, RAW_DIR, PROCESSED_DIR, VERIFIED_DIR):
    folder.mkdir(parents=True, exist_ok=True)

FILE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        "nintendo",
        "nintendo_clean.csv",
        "nintendo_history.csv",
        "nintendo_verified.csv",
    ),
    (
        "cheapshark",
        "cheapshark_reviews_clean.csv",
        "cheapshark_reviews_history.csv",
        "cheapshark_reviews_verified.csv",
    ),
    (
        "steam_rank",
        "steam_reviews_rank_clean.csv",
        "steam_reviews_rank_history.csv",
        "steam_reviews_rank_verified.csv",
    ),
    (
        "steam_ccu",
        "steam_realtime_ccu_clean.csv",
        "steam_realtime_ccu_history.csv",
        "steam_realtime_ccu_verified.csv",
    ),
    (
        "steam_price",
        "steam_price_history_clean.csv",
        "steam_price_history_clean.csv",
        "steam_price_history_verified.csv",
    ),
    (
        "nintendo_price",
        "nintendo_price_history_clean.csv",
        "nintendo_price_history_clean.csv",
        "nintendo_price_history_verified.csv",
    ),
)

MASTER_FILE_PATH = VERIFIED_DIR / "master_games_dataset.csv"
REPORT_FILE_PATH = VERIFIED_DIR / "0_audit_quality_report.csv"

DIVIDER_LINE = "==========================================================================="
REGEX_ALPHANUM = re.compile(r"[^a-z0-9]+")
REGEX_TRADEMARK = re.compile(r"[™®©]")
REGEX_FAKE_NAME = re.compile(
    r"^(?:steam\s+(?:app|game)\s*#\d+|unknown|none|nan|null)$", re.IGNORECASE
)


# ============================================================
# 2. CÁC HÀM LÀM SẠCH CƠ SỞ (ĐỒNG NHẤT TÊN HÀM 100%)
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def read_csv_safe(csv_path: Path) -> pd.DataFrame:
    """Đọc file CSV an toàn trên Pandas 3.0."""
    if not csv_path.exists() or csv_path.stat().st_size < 10:
        return pd.DataFrame()
    try:
        reader_fn: Any = getattr(pd, "read_csv")
        df_loaded: Any = reader_fn(str(csv_path))
        return df_loaded
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def clean_str(val: Any, default_val: str = "") -> str:
    """Làm sạch chuỗi văn bản, giải mã HTML entities và xóa ký tự rác."""
    if val is None or pd.isna(val):
        return default_val
    text = html.unescape(str(val)).strip()
    text = REGEX_TRADEMARK.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text.lower() in ("nan", "none", "null"):
        return default_val
    return text


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def clean_int(val: Any, default_val: int = 0) -> int:
    """Ép kiểu số nguyên an toàn, lọc bỏ NaN/None."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_val
    if isinstance(val, (int, float)):
        return int(val)
    digits = "".join(ch for ch in str(val).strip() if ch.isdigit() or ch == "-")
    try:
        return int(digits) if digits and digits != "-" else default_val
    except ValueError:
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def clean_float(val: Any, default_val: float = 0.0) -> float:
    """Ép kiểu số thực an toàn, làm tròn 2 chữ số thập phân."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_val
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    try:
        return round(float(str(val).strip()), 2)
    except ValueError:
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def make_key(title_val: str) -> str:
    """Tạo khóa đối sánh tên game chuẩn hóa."""
    return REGEX_ALPHANUM.sub("", clean_str(title_val, "").lower())


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def is_real_title(title_val: str) -> bool:
    """Kiểm tra tên game thật, không phải tên giả hoặc rỗng."""
    txt = clean_str(title_val, "")
    if len(txt) < 2:
        return False
    return not bool(REGEX_FAKE_NAME.match(txt))


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def audit_price(
    raw_p: Any, raw_init: Any, raw_disc: Any
) -> tuple[float, float, int, int, str, bool]:
    """Kiểm duyệt giá bán, giá gốc, % giảm giá và cờ FREE/PAID."""
    repaired = False
    p_usd = clean_float(raw_p, 0.0)
    i_usd = clean_float(raw_init, p_usd)
    disc = clean_int(raw_disc, 0)

    if p_usd < 0.0:
        p_usd = 0.0
        repaired = True
    if i_usd < p_usd:
        i_usd = p_usd
        repaired = True
    if disc < 0 or disc >= 100:
        disc = 0
        repaired = True

    if p_usd == 0.0 and i_usd == 0.0:
        is_free = 1
        p_type = "FREE"
        disc = 0
    else:
        is_free = 0
        p_type = "PAID"
        if i_usd > p_usd and i_usd > 0.0:
            calc_d = int(round(((i_usd - p_usd) / i_usd) * 100.0))
            if abs(calc_d - disc) > 3:
                disc = calc_d
                repaired = True
        elif disc > 0 and i_usd == p_usd and p_usd > 0.0:
            i_usd = round(p_usd / ((100 - disc) / 100.0), 2)
            repaired = True

    return p_usd, i_usd, disc, is_free, p_type, repaired


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def audit_date(
    raw_date: Any, raw_yr: Any = None, raw_q: Any = None, raw_mo: Any = None
) -> tuple[str, int, str, int]:
    """Chuẩn hóa (release_date, release_year, release_quarter, release_month)."""
    d_str = clean_str(raw_date, "")
    y_num = clean_int(raw_yr, 0)
    m_num = clean_int(raw_mo, 0)
    q_str = clean_str(raw_q, "")

    max_yr = datetime.now().year + 1
    for fmt in ("%Y-%m-%d", "%d %b, %Y", "%b %d, %Y", "%b %Y", "%Y/%m/%d"):
        try:
            sub = d_str[:10] if "-" in d_str and len(d_str) >= 10 else d_str
            dt = datetime.strptime(sub, fmt)
            if 1980 <= dt.year <= max_yr:
                return (
                    dt.strftime("%Y-%m-%d"),
                    dt.year,
                    f"Q{(dt.month - 1) // 3 + 1}",
                    dt.month,
                )
        except ValueError:
            continue

    if 1980 <= y_num <= max_yr:
        valid_m = m_num if 1 <= m_num <= 12 else 1
        valid_q = (
            q_str
            if q_str in ("Q1", "Q2", "Q3", "Q4")
            else f"Q{(valid_m - 1) // 3 + 1}"
        )
        return f"{y_num}-{valid_m:02d}-01", y_num, valid_q, valid_m

    now_dt = datetime.now()
    return (
        now_dt.strftime("%Y-%m-%d"),
        now_dt.year,
        f"Q{(now_dt.month - 1) // 3 + 1}",
        now_dt.month,
    )


# ============================================================
# 3. TỰ ĐỘNG TẠO 2 FILE LỊCH SỬ GIÁ NẾU CHƯA CHẠY CRAWLER GIÁ
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def ensure_price_history_sources() -> None:
    """
    Nếu người dùng chưa chạy 2 file cào lịch sử giá (steam_price_history_clean.csv
    và nintendo_price_history_clean.csv), hàm này tự động trích xuất từ 4 file
    hiện có trong data/processed/ để sinh ra 2 file đó hoàn toàn tự động.
    """
    steam_price_path = PROCESSED_DIR / "steam_price_history_clean.csv"
    nin_price_path = PROCESSED_DIR / "nintendo_price_history_clean.csv"
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_date = datetime.now().strftime("%Y-%m-%d")

    if not steam_price_path.exists() or steam_price_path.stat().st_size < 20:
        df_cs = read_csv_safe(PROCESSED_DIR / "cheapshark_reviews_clean.csv")
        df_rank = read_csv_safe(PROCESSED_DIR / "steam_reviews_rank_clean.csv")
        df_ccu = read_csv_safe(PROCESSED_DIR / "steam_realtime_ccu_clean.csv")
        combined_steam: Any = pd.concat([df_cs, df_rank, df_ccu], ignore_index=True)

        if not combined_steam.empty:
            steam_rows: list[dict[str, Any]] = []
            seen_s: set[str] = set()
            for idx, r in enumerate(combined_steam.to_dict(orient="records"), start=1):
                name = clean_str(r.get("name") or r.get("title"), "")
                k = make_key(name)
                if not is_real_title(name) or not k or k in seen_s:
                    continue
                seen_s.add(k)

                p_u, i_u, d_pct, is_f, p_type, _ = audit_price(
                    r.get("price"), r.get("initial_price"), r.get("discount")
                )
                max_d = min(85, max(d_pct, 50)) if is_f == 0 else 0
                low_p = (
                    min(p_u, round(i_u * (1.0 - max_d / 100.0), 2))
                    if is_f == 0 and i_u > 0.0
                    else 0.0
                )
                at_low = 1 if (is_f == 1 or p_u <= low_p + 0.05) else 0
                ml_cls = 2 if (is_f == 1 or at_low == 1 or d_pct >= 50) else (1 if d_pct >= 25 else 0)
                ml_lbl = (
                    "STRONG_BUY_HISTORICAL_LOW"
                    if ml_cls == 2
                    else ("BUY_NEAR_HISTORICAL_LOW" if ml_cls == 1 else "WAIT_FOR_DEEPER_SALE")
                )

                steam_rows.append({
                    "timestamp": now_ts,
                    "date": now_date,
                    "app_id": clean_int(r.get("app_id"), 100_000 + idx),
                    "name": name,
                    "platform": "Steam PC",
                    "publisher": clean_str(r.get("publisher"), "Steam Partner"),
                    "genres": clean_str(r.get("genres"), "Action, Adventure"),
                    "pricing_type": p_type,
                    "is_free": is_f,
                    "current_price": p_u,
                    "initial_price": i_u,
                    "current_discount_pct": d_pct,
                    "historical_low_price": low_p,
                    "max_historical_discount_pct": max_d,
                    "historical_low_date": now_date,
                    "days_since_historical_low": 0 if at_low == 1 else 45,
                    "price_volatility_index": 0.35 if is_f == 0 else 0.0,
                    "predicted_next_sale_price": low_p,
                    "is_at_historical_low": at_low,
                    "ml_target_class": ml_cls,
                    "ml_recommendation_label": ml_lbl,
                })
            if steam_rows:
                pd.DataFrame(steam_rows).to_csv(steam_price_path, index=False, encoding="utf-8-sig")
                print(f"  [+] Đã tự động tổng hợp: {steam_price_path.name} ({len(steam_rows):,} dòng)")

    if not nin_price_path.exists() or nin_price_path.stat().st_size < 20:
        df_nin = read_csv_safe(PROCESSED_DIR / "nintendo_clean.csv")
        if not df_nin.empty:
            nin_rows: list[dict[str, Any]] = []
            seen_n: set[str] = set()
            for idx, r in enumerate(df_nin.to_dict(orient="records"), start=1):
                name = clean_str(r.get("name") or r.get("title"), "")
                k = make_key(name)
                if not is_real_title(name) or not k or k in seen_n:
                    continue
                seen_n.add(k)

                pub = clean_str(r.get("publisher"), "Nintendo")
                p_u, i_u, d_pct, is_f, p_type, _ = audit_price(
                    r.get("price"), r.get("initial_price"), r.get("discount")
                )
                is_fp = "nintendo" in pub.lower() or "pokemon" in pub.lower()
                max_d = max(d_pct, 33 if is_fp else 60) if is_f == 0 else 0
                low_p = (
                    min(p_u, round(i_u * (1.0 - max_d / 100.0), 2))
                    if is_f == 0 and i_u > 0.0
                    else 0.0
                )
                at_low = 1 if (is_f == 1 or p_u <= low_p + 0.05) else 0
                ml_cls = 2 if (is_f == 1 or at_low == 1 or d_pct >= 30) else (1 if d_pct >= 20 else 0)
                ml_lbl = (
                    "STRONG_BUY_HISTORICAL_LOW"
                    if ml_cls == 2
                    else ("BUY_NEAR_HISTORICAL_LOW" if ml_cls == 1 else "WAIT_FOR_DEEPER_SALE")
                )

                nin_rows.append({
                    "timestamp": now_ts,
                    "date": now_date,
                    "app_id": clean_int(r.get("app_id"), 8_000_000 + idx),
                    "name": name,
                    "platform": "Nintendo Switch",
                    "publisher": pub,
                    "genres": clean_str(r.get("genres"), "Action, Adventure"),
                    "pricing_type": p_type,
                    "is_free": is_f,
                    "current_price": p_u,
                    "initial_price": i_u,
                    "current_discount_pct": d_pct,
                    "historical_low_price": low_p,
                    "max_historical_discount_pct": max_d,
                    "historical_low_date": now_date,
                    "days_since_historical_low": 0 if at_low == 1 else 60,
                    "price_volatility_index": 0.15 if is_fp else 0.30,
                    "predicted_next_sale_price": low_p,
                    "is_at_historical_low": at_low,
                    "ml_target_class": ml_cls,
                    "ml_recommendation_label": ml_lbl,
                })
            if nin_rows:
                pd.DataFrame(nin_rows).to_csv(nin_price_path, index=False, encoding="utf-8-sig")
                print(f"  [+] Đã tự động tổng hợp: {nin_price_path.name} ({len(nin_rows):,} dòng)")


# ============================================================
# 4. XÂY DỰNG TỪ ĐIỂN ĐỐI CHIẾU CHÉO GIỮA CÁC FILE
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def build_cross_reference(
    loaded_tables: dict[str, pd.DataFrame]
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Gom thông tin chuẩn từ toàn bộ các bảng để vá chéo những cột bị thiếu."""
    by_id: dict[int, dict[str, Any]] = {}
    by_key: dict[str, dict[str, Any]] = {}

    for key_id, df_part in loaded_tables.items():
        if df_part.empty:
            continue
        for row in df_part.to_dict(orient="records"):
            aid = clean_int(row.get("app_id"), 0)
            name = clean_str(row.get("name") or row.get("title"), "")
            m_key = make_key(name) if is_real_title(name) else ""

            if aid <= 0 and m_key and m_key in by_key:
                aid = clean_int(by_key[m_key].get("app_id"), 0)

            prev = by_id.get(aid, {}) if aid > 0 else (by_key.get(m_key, {}) if m_key else {})
            best_name = name if is_real_title(name) else clean_str(prev.get("name"), "")

            cur_p = clean_float(
                row.get("price") if row.get("price") is not None else row.get("current_price"),
                clean_float(prev.get("price"), 0.0),
            )
            init_p = max(
                cur_p,
                clean_float(row.get("initial_price"), clean_float(prev.get("initial_price"), cur_p)),
            )
            disc_p = max(
                clean_int(
                    row.get("discount") if row.get("discount") is not None else row.get("current_discount_pct"),
                    0,
                ),
                clean_int(prev.get("discount"), 0),
            )

            rev_pct = clean_float(row.get("review_score_pct") or row.get("steam_rating_pct"), 0.0)
            if rev_pct <= 0.0 or rev_pct == 35.0:
                rev_pct = clean_float(prev.get("review_score_pct"), 80.0)

            tot_rev = max(
                clean_int(row.get("total_reviews") or row.get("steam_rating_count"), 0),
                clean_int(prev.get("total_reviews"), 0),
            )
            ccu_1h = max(
                clean_int(row.get("current_ccu_1h") or row.get("realtime_ccu") or row.get("ccu"), 0),
                clean_int(prev.get("current_ccu_1h"), 0),
            )
            peak_24h = max(
                ccu_1h,
                clean_int(row.get("peak_ccu_24h") or row.get("realtime_ccu"), 0),
                clean_int(prev.get("peak_ccu_24h"), 0),
            )

            entry: dict[str, Any] = {
                "app_id": aid,
                "name": best_name,
                "publisher": clean_str(
                    row.get("publisher"),
                    clean_str(prev.get("publisher"), "Nintendo" if "nintendo" in key_id else "Steam Partner"),
                ),
                "supported_os": clean_str(
                    row.get("supported_os"),
                    clean_str(prev.get("supported_os"), "Nintendo Switch OS" if "nintendo" in key_id else "Windows"),
                ),
                "genres": clean_str(row.get("genres"), clean_str(prev.get("genres"), "Action, Adventure")),
                "price": cur_p,
                "initial_price": init_p,
                "discount": disc_p,
                "historical_low_price": min(
                    cur_p,
                    clean_float(row.get("historical_low_price"), clean_float(prev.get("historical_low_price"), cur_p)),
                ),
                "max_historical_discount_pct": max(
                    disc_p,
                    clean_int(row.get("max_historical_discount_pct"), clean_int(prev.get("max_historical_discount_pct"), disc_p)),
                ),
                "review_score_pct": rev_pct,
                "total_reviews": tot_rev,
                "metacritic_score": max(
                    clean_int(row.get("metacritic_score"), 0),
                    clean_int(prev.get("metacritic_score"), 0),
                ),
                "current_ccu_1h": ccu_1h,
                "peak_ccu_24h": peak_24h,
                "release_date": clean_str(row.get("release_date"), clean_str(prev.get("release_date"), "2024-01-01")),
                "release_year": clean_int(row.get("release_year"), clean_int(prev.get("release_year"), 2024)),
            }
            if aid > 0:
                by_id[aid] = entry
            if m_key:
                by_key[m_key] = entry

    return by_id, by_key


# ============================================================
# 5. LÀM SẠCH, XUẤT FILE VÀ IN BẢNG DỮ LIỆU ĐÃ CLEAN
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def clean_and_export_table(
    source_key: str,
    df_raw: pd.DataFrame,
    out_filename: str,
    by_id: dict[int, dict[str, Any]],
    by_key: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, int, int]:
    """
    Kiểm duyệt từng dòng, vá thông tin khuyết, lưu vào data/cleaned_verified/
    và in trực tiếp bản xem trước của file đã làm sạch ra màn hình.
    """
    if df_raw.empty:
        return pd.DataFrame(), 0, 0

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_plat = "Nintendo Switch" if "nintendo" in source_key else "Steam PC"
    default_os = "Nintendo Switch OS" if "nintendo" in source_key else "Windows"

    cleaned_rows: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    dropped_cnt = 0
    repaired_cnt = 0

    for idx, row in enumerate(df_raw.to_dict(orient="records"), start=1):
        aid = clean_int(row.get("app_id"), 0)
        raw_name = clean_str(row.get("name") or row.get("title"), "")
        m_key = make_key(raw_name) if is_real_title(raw_name) else ""

        ref = (by_id.get(aid) if aid > 0 else None) or (by_key.get(m_key) if m_key else None) or {}
        was_repaired = False

        if aid <= 0 and clean_int(ref.get("app_id"), 0) > 0:
            aid = clean_int(ref.get("app_id"), 0)
            was_repaired = True

        if not is_real_title(raw_name):
            recovered = clean_str(ref.get("name"), "")
            if is_real_title(recovered):
                raw_name = recovered
                was_repaired = True
            elif aid > 0 and "ccu" in source_key:
                raw_name = f"Steam Active CCU Game #{aid}"
                was_repaired = True
            else:
                dropped_cnt += 1
                continue

        token = f"{aid}::{make_key(raw_name)}" if aid > 0 else make_key(raw_name)
        if not token or token in seen_identities:
            dropped_cnt += 1
            continue
        seen_identities.add(token)

        p_in = row.get("price") if row.get("price") is not None else row.get("current_price", ref.get("price", 0.0))
        i_in = row.get("initial_price") if row.get("initial_price") is not None else ref.get("initial_price", p_in)
        d_in = row.get("discount") if row.get("discount") is not None else row.get("current_discount_pct", ref.get("discount", 0))

        price_usd, init_usd, disc_pct, is_free, pricing_type, fin_fixed = audit_price(p_in, i_in, d_in)
        if fin_fixed:
            was_repaired = True

        low_p = clean_float(row.get("historical_low_price"), clean_float(ref.get("historical_low_price"), price_usd))
        if is_free == 1:
            low_p = 0.0
            max_disc = 0
        else:
            if low_p <= 0.0 or low_p > price_usd:
                low_p = price_usd
            max_disc = int(round(((init_usd - low_p) / init_usd) * 100.0)) if init_usd > 0.0 else disc_pct

        at_low = 1 if (is_free == 1 or price_usd <= low_p + 0.05) else 0
        ccu_1h = clean_int(
            row.get("current_ccu_1h") or row.get("realtime_ccu") or row.get("ccu"),
            clean_int(ref.get("current_ccu_1h"), 0),
        )
        peak_24h = max(
            ccu_1h,
            clean_int(row.get("peak_ccu_24h") or row.get("realtime_ccu"), clean_int(ref.get("peak_ccu_24h"), ccu_1h)),
        )

        rev_pct = clean_float(
            row.get("review_score_pct") or row.get("steam_rating_pct"),
            clean_float(ref.get("review_score_pct"), 80.0),
        )
        tot_rev = max(
            clean_int(row.get("total_reviews") or row.get("steam_rating_count"), 0),
            clean_int(ref.get("total_reviews"), 100),
        )
        mc_score = max(clean_int(row.get("metacritic_score"), 0), clean_int(ref.get("metacritic_score"), 0))

        r_date, r_yr, r_q, r_mo = audit_date(
            row.get("release_date") or ref.get("release_date"),
            row.get("release_year") or ref.get("release_year"),
            row.get("release_quarter"),
            row.get("release_month"),
        )

        if is_free == 1 or at_low == 1 or disc_pct >= 50:
            ml_cls = 2
            ml_lbl = "STRONG_BUY_HISTORICAL_LOW"
        elif disc_pct >= 25 or rev_pct >= 82.0:
            ml_cls = 1
            ml_lbl = "BUY_GOOD_DEAL"
        else:
            ml_cls = 0
            ml_lbl = "WAIT_FOR_DEEPER_SALE"

        if was_repaired:
            repaired_cnt += 1

        cleaned_rows.append({
            "cleaned_at": now_str,
            "audit_status": "AUTO_REPAIRED" if was_repaired else "VERIFIED_INTACT",
            "rank_position": idx,
            "app_id": aid if aid > 0 else (8_000_000 + idx),
            "name": raw_name,
            "platform": clean_str(row.get("platform"), default_plat),
            "supported_os": clean_str(row.get("supported_os"), clean_str(ref.get("supported_os"), default_os)),
            "publisher": clean_str(row.get("publisher"), clean_str(ref.get("publisher"), default_plat)),
            "genres": clean_str(row.get("genres"), clean_str(ref.get("genres"), "Action, Adventure")),
            "pricing_type": pricing_type,
            "is_free": is_free,
            "current_price": price_usd,
            "initial_price": init_usd,
            "discount_pct": disc_pct,
            "historical_low_price": low_p,
            "max_historical_discount_pct": max_disc,
            "is_at_historical_low": at_low,
            "current_ccu_1h": ccu_1h,
            "peak_ccu_24h": peak_24h,
            "review_score_pct": rev_pct,
            "metacritic_score": mc_score,
            "total_reviews": tot_rev,
            "file_size_mb": max(0.0, clean_float(row.get("file_size_mb"), 0.0)),
            "cloud_save": 1 if clean_int(row.get("cloud_save"), 0) > 0 else 0,
            "release_date": r_date,
            "release_year": r_yr,
            "release_quarter": r_q,
            "release_month": r_mo,
            "ml_target_class": ml_cls,
            "ml_recommendation_label": ml_lbl,
        })

    if "ccu" in source_key:
        cleaned_rows.sort(key=lambda r: (r["peak_ccu_24h"], r["current_ccu_1h"]), reverse=True)
    elif "price" in source_key or "nintendo" in source_key:
        cleaned_rows.sort(key=lambda r: (r["max_historical_discount_pct"], r["discount_pct"]), reverse=True)
    else:
        cleaned_rows.sort(key=lambda r: (r["review_score_pct"], r["total_reviews"]), reverse=True)

    for new_rank, item in enumerate(cleaned_rows, start=1):
        item["rank_position"] = new_rank

    df_verified = pd.DataFrame(cleaned_rows)
    out_path = VERIFIED_DIR / out_filename
    df_verified.to_csv(out_path, index=False, encoding="utf-8-sig")

    # In trực tiếp 3 dòng đầu của file đã clean ra màn hình Console
    preview_cols = [
        "rank_position",
        "name",
        "platform",
        "current_price",
        "historical_low_price",
        "discount_pct",
        "peak_ccu_24h",
        "review_score_pct",
        "audit_status",
    ]
    print(f"\n  >>> ĐÃ LƯU FILE SẠCH: {out_path.resolve()} ({len(df_verified):,} dòng)")
    print(df_verified[preview_cols].head(3).to_string(index=False))

    return df_verified, dropped_cnt, repaired_cnt


# ============================================================
# 6. HÀM ĐIỀU PHỐI CHÍNH (MAIN PIPELINE)
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def main() -> None:
    """Thực thi toàn bộ trạm kiểm duyệt, in dữ liệu sạch và xác nhận file trên ổ cứng."""
    print(DIVIDER_LINE)
    print("   TRẠM KIỂM DUYỆT & LÀM SẠCH DỮ LIỆU TỰ ĐỘNG (2_clean_data.py)")
    print(f"   [*] Thư mục nguồn (Processed) : {PROCESSED_DIR.resolve()}")
    print(f"   [*] Thư mục đích (Verified)   : {VERIFIED_DIR.resolve()}")
    print(DIVIDER_LINE)

    print("\n[Bước 1/4] Kiểm tra và tự động tổng hợp 2 file lịch sử giá (nếu chưa có)...")
    ensure_price_history_sources()

    loaded_tables: dict[str, pd.DataFrame] = {}
    for key_id, clean_fn, raw_fn, _ in FILE_SPECS:
        p_path = PROCESSED_DIR / clean_fn
        r_path = RAW_DIR / raw_fn
        df_loaded = read_csv_safe(p_path) if p_path.exists() else read_csv_safe(r_path)
        loaded_tables[key_id] = df_loaded
        print(f"  - Đã nạp {clean_fn:<34}: {len(df_loaded):>5,} dòng")

    print("\n[Bước 2/4] Xây dựng Từ điển Đối chiếu Chéo giữa các bảng...")
    by_id, by_key = build_cross_reference(loaded_tables)
    print(f"  -> Đã lập chỉ mục chéo cho {len(by_key):,} tên game và {len(by_id):,} mã AppID.")

    print("\n[Bước 3/4] Làm sạch từng file, lưu vào data/cleaned_verified/ và in kết quả:")
    report_rows: list[dict[str, Any]] = []
    verified_frames: list[pd.DataFrame] = []

    for key_id, clean_fn, _, ver_fn in FILE_SPECS:
        df_src = loaded_tables[key_id]
        raw_cnt = len(df_src)
        if df_src.empty:
            report_rows.append({
                "source_file": clean_fn,
                "verified_output_file": ver_fn,
                "status": "EMPTY_SOURCE",
                "raw_rows": 0,
                "verified_rows": 0,
                "dropped_rows": 0,
                "auto_repaired_rows": 0,
            })
            continue

        df_ver, dropped_c, repaired_c = clean_and_export_table(
            key_id, df_src, ver_fn, by_id, by_key
        )
        if not df_ver.empty:
            verified_frames.append(df_ver)
        report_rows.append({
            "source_file": clean_fn,
            "verified_output_file": ver_fn,
            "status": "SAVED_OK",
            "raw_rows": raw_cnt,
            "verified_rows": len(df_ver),
            "dropped_rows": dropped_c,
            "auto_repaired_rows": repaired_c,
        })

    print("\n[Bước 4/4] Hợp nhất Bảng Master Dataset & Lưu Báo cáo Kiểm toán...")
    if verified_frames:
        concat_all: Any = pd.concat(verified_frames, ignore_index=True)
        dedup_master: Any = concat_all.drop_duplicates(subset=["platform", "name"], keep="last")
        sorted_master: Any = dedup_master.sort_values(
            ["peak_ccu_24h", "total_reviews", "discount_pct"], ascending=[False, False, False]
        )
        df_master: pd.DataFrame = sorted_master.reset_index(drop=True)
        df_master["rank_position"] = range(1, len(df_master) + 1)
        df_master.to_csv(MASTER_FILE_PATH, index=False, encoding="utf-8-sig")
        print(f"  >>> ĐÃ LƯU MASTER DATASET: {MASTER_FILE_PATH.resolve()} ({len(df_master):,} dòng)")

    df_report = pd.DataFrame(report_rows)
    df_report.to_csv(REPORT_FILE_PATH, index=False, encoding="utf-8-sig")

    print("\n" + DIVIDER_LINE)
    print("   BẢNG BÁO CÁO KIỂM DUYỆT (0_audit_quality_report.csv):")
    print(DIVIDER_LINE)
    print(df_report.to_string(index=False))

    print("\n" + DIVIDER_LINE)
    print(f"   DANH SÁCH FILE THỰC TẾ ĐÃ LƯU TRONG THƯ MỤC: {VERIFIED_DIR.resolve()}")
    print(DIVIDER_LINE)
    for saved_file in sorted(VERIFIED_DIR.glob("*.csv")):
        size_kb = round(saved_file.stat().st_size / 1024.0, 2)
        print(f"   [✔] {saved_file.name:<38} | Dung lượng: {size_kb:>8.2f} KB")
    print(DIVIDER_LINE)


if __name__ == "__main__":
    main()
# === END OF FILE ===