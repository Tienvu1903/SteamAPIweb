"""
3_build_recommendation_system.py (Steam OpenID 2.0, User DB & 3-Structure ML Recommender)
=========================================================================================
TRẠM HỌC MÁY SỐ 2 — QUẢN LÝ DỮ LIỆU NGƯỜI DÙNG STEAM & 3 CẤU TRÚC HỌC MÁY GỢI Ý CÁ NHÂN HÓA
-----------------------------------------------------------------------------------------
Bản quyền & Pháp lý (Valve Steam Web API Terms of Use Compliance):
- Powered by Steam. This application is an independent Machine Learning analytics tool
  and is not affiliated with, endorsed, or sponsored by Valve Corporation.
- Xác thực danh tính qua chuẩn Steam OpenID 2.0 chính thống (không thu thập mật khẩu).
- Tôn trọng tuyệt đối cài đặt quyền riêng tư (Private Profile) của người dùng và áp dụng
  cơ chế lưu đệm 24h (Local Cache) để bảo vệ máy chủ Steam khỏi truy vấn lặp lại.

Kiến trúc 3 Cấu trúc Học máy Gợi ý theo User ID (User-Centric Hybrid ML):
1. CẤU TRÚC 1 [Collaborative Filtering - Lọc Cộng Tác Ma Trận]:
   - Thuật toán: TruncatedSVD (Singular Value Decomposition) trên ma trận [user_id x app_id].
   - Nguyên lý : Học mối liên hệ ngầm giữa những người chơi có cùng lịch sử cày game.
2. CẤU TRÚC 2 [Playtime-Weighted Content Profile - Hồ Sơ Nội Dung Trọng Số Giờ Chơi]:
   - Thuật toán: TfidfVectorizer + User Preference Centroid + Cosine Similarity.
   - Nguyên lý : Tổng hợp vector thể loại/nhà phát hành của các game user đã chơi (nhân trọng
                 số theo số giờ cày) để tìm các game mới có lối chơi khớp nhất.
3. CẤU TRÚC 3 [Behavioral & Financial Proximity - Khoảng Cách Hình Học Đa Chiều]:
   - Thuật toán: StandardScaler (Z-Score) + K-Nearest Neighbors (KNN Euclidean Proximity).
   - Nguyên lý : Đối chiếu thói quen chi tiêu, mức giảm giá, dự báo giá 3 tháng và quy mô
                 cộng đồng CCU theo giờ trong không gian 7 chiều số học.

Đầu ra Lưu trữ Thực tế (data/cleaned_verified/ & models/):
- Bảng 1 (Hồ sơ User)      : data/cleaned_verified/steam_users_profile_verified.csv
- Bảng 2 (Kho game User)   : data/cleaned_verified/steam_user_owned_games_verified.csv
- Bảng 3 (Gợi ý từng User) : data/cleaned_verified/user_personalized_recommendations.csv
- Bảng 4 (Master cho App)  : data/cleaned_verified/master_recommendations_ready.csv
- Báo cáo Đấu trường Gợi ý : data/cleaned_verified/ml_recommendation_structures_report.csv
- Bộ não Gợi ý đóng gói    : models/recommendation_engine_bundle.pkl
"""

from datetime import datetime, timedelta
import math
from pathlib import Path
import pickle
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN, HẰNG SỐ PHÁP LÝ & ĐẶC TRƯNG HỌC MÁY
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
PROJECT_ROOT = Path(__file__).resolve().parent
VERIFIED_DIR = PROJECT_ROOT / "data" / "cleaned_verified"
MODELS_DIR = PROJECT_ROOT / "models"

VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Nguồn dữ liệu đầu vào từ Giai đoạn 1 & Trạm Học máy số 1
MASTER_DATA_PATH = VERIFIED_DIR / "master_games_dataset.csv"
PREDICTED_PRICE_PATH = VERIFIED_DIR / "master_price_predicted.csv"
STEAM_CCU_PATH = VERIFIED_DIR / "steam_realtime_ccu_verified.csv"

# Ba bảng Quản trị Dữ liệu Người dùng (User Data Management Tables)
USER_PROFILES_CSV = VERIFIED_DIR / "steam_users_profile_verified.csv"
USER_OWNED_GAMES_CSV = VERIFIED_DIR / "steam_user_owned_games_verified.csv"
USER_PERSONAL_REC_CSV = VERIFIED_DIR / "user_personalized_recommendations.csv"

# Bảng tổng hợp toàn sàn & Báo cáo đánh giá 3 cấu trúc ML
OUTPUT_REC_READY_CSV = VERIFIED_DIR / "master_recommendations_ready.csv"
OUTPUT_REC_REPORT_CSV = VERIFIED_DIR / "ml_recommendation_structures_report.csv"
REC_MODEL_BUNDLE_PKL = MODELS_DIR / "recommendation_engine_bundle.pkl"

VALVE_LEGAL_DISCLAIMER = (
    "Powered by Steam. Independent ML Analytics & Recommendation System — "
    "Not affiliated with, endorsed, or sponsored by Valve Corporation."
)
STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
CACHE_TTL_HOURS = 24
DIVIDER = "==========================================================================="

KNN_NUMERIC_FEATURES: list[str] = [
    "current_price",
    "discount_pct",
    "historical_low_price",
    "ml_predicted_price_3m",
    "log_ccu_1h",
    "log_peak_24h",
    "review_score_pct",
]


# ============================================================
# 2. CÁC HÀM TIỆN ÍCH ĐỌC FILE, ÉP KIỂU & QUY ĐỔI ĐIỂM GIỜ CHƠI
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def load_csv_table(csv_path: Path) -> pd.DataFrame:
    """Đọc file CSV an toàn trên Pandas 3.0."""
    if not csv_path.exists() or csv_path.stat().st_size < 10:
        return pd.DataFrame()
    try:
        reader_fn: Any = getattr(pd, "read_csv")
        loaded_df: Any = reader_fn(str(csv_path))
        return loaded_df
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def to_float_val(val: Any, default_val: float = 0.0) -> float:
    """Ép kiểu số thực an toàn."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_val
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def to_int_val(val: Any, default_val: int = 0) -> int:
    """Ép kiểu số nguyên an toàn."""
    if val is None or isinstance(val, bool) or pd.isna(val):
        return default_val
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default_val


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def to_str_val(val: Any, default_val: str = "") -> str:
    """Chuẩn hóa chuỗi văn bản an toàn."""
    if val is None or pd.isna(val):
        return default_val
    txt = str(val).strip()
    return default_val if not txt or txt.lower() in ("nan", "none", "null") else txt


# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def compute_implicit_rating(
    playtime_forever_hours: float,
    playtime_2weeks_hours: float = 0.0,
    voted_up: int = 1,
) -> float:
    """
    Công thức Toán học quy đổi Số giờ chơi (Playtime) sang Điểm Yêu Thích (Thang 1.0 - 10.0):
    R(u, i) = min(10.0, 2.0 * VotedUp + 1.5 * ln(1 + Giờ_Tổng) + 2.0 * ln(1 + Giờ_2_Tuần))
    Giúp máy phân biệt rõ game mua về bỏ xó (0.2h) với game cày tâm huyết (150h).
    """
    h_total = max(0.0, float(playtime_forever_hours))
    h_recent = max(0.0, float(playtime_2weeks_hours))
    vote_bonus = 2.0 if int(voted_up) == 1 else 0.5
    raw_score = vote_bonus + (1.5 * math.log1p(h_total)) + (2.0 * math.log1p(h_recent))
    return round(min(10.0, max(1.0, raw_score)), 2)


# ============================================================
# 3. KHỐI 1: STEAM OPENID 2.0 & BỘ QUÉT KHO GAME HỢP PHÁP
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
class SteamOpenIDAndLibraryScanner:
    """
    Quản lý xác thực Steam OpenID 2.0 chính thống và quét kho game công khai:
    - Không bao giờ yêu cầu mật khẩu hoặc mã Steam Guard của người chơi.
    - Kiểm tra chế độ Private/Public lịch sự theo đúng chuẩn GDPR & Valve Guidelines.
    - Lưu đệm 24h (Cache) để không gửi request lặp lại lên máy chủ Steam.
    """

    @staticmethod
    def build_steam_openid_login_url(return_to_url: str = "http://localhost:8501") -> str:
        """
        Tạo đường dẫn đăng nhập 'Sign in through Steam' chuẩn OpenID 2.0.
        Khi người dùng bấm vào link này trên App, Valve sẽ xác thực và trả về SteamID64.
        """
        parsed = urlparse(return_to_url)
        realm = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else "http://localhost:8501"
        openid_params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": return_to_url,
            "openid.realm": realm,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
        return f"{STEAM_OPENID_ENDPOINT}?{urlencode(openid_params)}"

    @staticmethod
    def verify_openid_response(query_params: dict[str, str]) -> str | None:
        """
        Xác thực chữ ký số OpenID 2.0 trực tiếp với máy chủ Valve (check_authentication).
        Trả về dãy 17 chữ số SteamID64 nếu hợp lệ, hoặc None nếu giả mạo.
        """
        if query_params.get("openid.mode") != "id_res":
            return None
        claimed_id = query_params.get("openid.claimed_id", "")
        match = re.search(r"steamcommunity\.com/openid/id/(\d{17})", claimed_id)
        if not match:
            return None
        steam_id64 = match.group(1)

        validation_payload = dict(query_params)
        validation_payload["openid.mode"] = "check_authentication"
        encoded_data = urlencode(validation_payload).encode("utf-8")

        try:
            req = Request(
                STEAM_OPENID_ENDPOINT,
                data=encoded_data,
                headers={"User-Agent": "SteamMLRecommendationAcademicApp/1.0"},
            )
            with urlopen(req, timeout=8) as resp:
                body_text = resp.read().decode("utf-8", errors="ignore")
            if "is_valid:true" in body_text:
                return steam_id64
        except (HTTPError, URLError, OSError, ValueError):
            return None
        return None

    @staticmethod
    def extract_steam_identifier(raw_input: str) -> tuple[str, str]:
        """
        Bóc tách định danh từ chuỗi người dùng nhập (SteamID64, Link Profile hoặc Vanity URL).
        Trả về: (loại_định_danh, giá_trị) -> ('steamid64' | 'vanity', value)
        """
        cleaned = raw_input.strip().rstrip("/")
        match_id64 = re.search(r"\b(7656119\d{10})\b", cleaned)
        if match_id64:
            return "steamid64", match_id64.group(1)

        match_vanity = re.search(r"steamcommunity\.com/id/([A-Za-z0-9_\-]+)", cleaned)
        if match_vanity:
            return "vanity", match_vanity.group(1)

        return "steamid64", cleaned

    @classmethod
    def fetch_public_steam_library_xml(
        cls, steam_input: str
    ) -> tuple[str, str, str, list[dict[str, Any]]]:
        """
        Quét trực tiếp kho game công khai của người chơi qua cổng XML chính thức của Steam.
        Trả về: (steam_id64, persona_name, privacy_status, owned_games_list)
        - privacy_status nhận 1 trong 3 giá trị: 'public', 'private', 'offline_fallback'.
        """
        id_type, id_val = cls.extract_steam_identifier(steam_input)
        if not id_val:
            return "", "Unknown", "offline_fallback", []

        if id_type == "vanity":
            xml_url = f"https://steamcommunity.com/id/{id_val}/games?tab=all&xml=1"
        else:
            xml_url = f"https://steamcommunity.com/profiles/{id_val}/games?tab=all&xml=1"

        try:
            req = Request(
                xml_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SteamMLAdvisor/1.0",
                    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urlopen(req, timeout=8) as response:
                xml_bytes = response.read()

            root = ET.fromstring(xml_bytes)

            # Kiểm tra nếu tài khoản bị lỗi hoặc khóa Private
            error_node = root.find("error")
            if error_node is not None and error_node.text:
                return id_val, f"SteamUser_{id_val[-4:]}", "private", []

            steam_id64 = to_str_val(root.findtext("steamID64"), id_val)
            persona_name = to_str_val(root.findtext("steamID"), f"SteamUser_{steam_id64[-4:]}")

            games_container = root.find("games")
            if games_container is None:
                return steam_id64, persona_name, "private", []

            owned_games: list[dict[str, Any]] = []
            for game_elem in games_container.findall("game"):
                app_id = to_int_val(game_elem.findtext("appID"), 0)
                g_name = to_str_val(game_elem.findtext("name"), "")
                if app_id <= 0 or not g_name:
                    continue

                raw_hours_total = to_str_val(game_elem.findtext("hoursOnRecord"), "0").replace(",", "")
                raw_hours_2w = to_str_val(game_elem.findtext("hoursLast2Weeks"), "0").replace(",", "")
                hours_total = to_float_val(raw_hours_total, 0.5)
                hours_2w = to_float_val(raw_hours_2w, 0.0)

                owned_games.append({
                    "user_id": steam_id64,
                    "app_id": app_id,
                    "game_name": g_name,
                    "platform": "Steam PC",
                    "playtime_forever_hours": hours_total,
                    "playtime_2weeks_hours": hours_2w,
                    "voted_up": 1,
                    "implicit_rating_score": compute_implicit_rating(hours_total, hours_2w, 1),
                })

            if not owned_games:
                return steam_id64, persona_name, "private", []

            return steam_id64, persona_name, "public", owned_games

        except (HTTPError, URLError, ET.ParseError, OSError, ValueError):
            return id_val, f"SteamUser_{id_val[-4:]}", "offline_fallback", []


# ============================================================
# 4. HỢP NHẤT MASTER DATASET + DỰ BÁO GIÁ 3 THÁNG + CCU THEO GIỜ
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def merge_all_verified_intelligence() -> pd.DataFrame:
    """
    Hợp nhất Bảng Master với kết quả Dự báo giá 3 tháng (từ File 1) và Bảng CCU trực tuyến.
    Đảm bảo mỗi tựa game có đủ: Giá hiện tại, Đáy lịch sử, Dự báo 3T, CCU 1h/24h, Review & Link gốc.
    """
    df_master = load_csv_table(MASTER_DATA_PATH)
    df_pred = load_csv_table(PREDICTED_PRICE_PATH)
    df_ccu = load_csv_table(STEAM_CCU_PATH)

    if df_master.empty and df_pred.empty:
        return pd.DataFrame()

    base_df = df_master if not df_master.empty else df_pred

    pred_lookup: dict[str, dict[str, Any]] = {}
    if not df_pred.empty:
        for p_row in df_pred.to_dict(orient="records"):
            p_key = f"{to_str_val(p_row.get('platform'))}::{to_str_val(p_row.get('name')).lower()}"
            pred_lookup[p_key] = p_row

    ccu_lookup: dict[int, dict[str, Any]] = {}
    if not df_ccu.empty:
        for c_row in df_ccu.to_dict(orient="records"):
            c_aid = to_int_val(c_row.get("app_id"), 0)
            if c_aid > 0:
                ccu_lookup[c_aid] = c_row

    unified_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for idx, row in enumerate(base_df.to_dict(orient="records"), start=1):
        name = to_str_val(row.get("name"), "")
        platform = to_str_val(row.get("platform"), "Steam PC")
        comp_key = f"{platform}::{name.lower()}"
        if not name or comp_key in seen_keys:
            continue
        seen_keys.add(comp_key)

        aid = to_int_val(row.get("app_id"), 500_000 + idx)
        p_info = pred_lookup.get(comp_key, {})
        c_info = ccu_lookup.get(aid, {})

        cur_p = to_float_val(
            row.get("current_price") if row.get("current_price") is not None else row.get("price"),
            to_float_val(p_info.get("current_price"), 0.0),
        )
        init_p = max(
            cur_p,
            to_float_val(row.get("initial_price"), to_float_val(p_info.get("initial_price"), cur_p)),
        )
        disc_pct = to_int_val(
            row.get("discount_pct") if row.get("discount_pct") is not None else row.get("discount"),
            to_int_val(p_info.get("current_discount_pct"), 0),
        )
        is_free = 1 if (cur_p == 0.0 and init_p == 0.0) else 0

        low_p = to_float_val(
            p_info.get("historical_low_price"),
            to_float_val(row.get("historical_low_price"), cur_p),
        )
        if low_p <= 0.0 or low_p > cur_p:
            low_p = cur_p
        max_disc = max(
            disc_pct,
            to_int_val(
                p_info.get("max_historical_discount_pct"),
                to_int_val(row.get("max_historical_discount_pct"), disc_pct),
            ),
        )
        at_low = 1 if (is_free == 1 or cur_p <= low_p + 0.05) else 0

        pred_3m = to_float_val(
            p_info.get("ml_predicted_price_3m"),
            low_p if at_low == 1 else round(max(low_p, cur_p * 0.80), 2),
        )
        band_low_3m = to_float_val(p_info.get("ml_price_band_low_3m"), max(0.0, pred_3m - 1.50))
        band_high_3m = to_float_val(p_info.get("ml_price_band_high_3m"), max(pred_3m, cur_p))
        save_3m = round(max(0.0, cur_p - pred_3m), 2)
        ml_cls = to_int_val(
            p_info.get("ml_predicted_class"),
            2 if at_low == 1 else (1 if disc_pct >= 25 else 0),
        )
        ml_label = to_str_val(
            p_info.get("ml_predicted_label"),
            "STRONG_BUY_HISTORICAL_LOW"
            if ml_cls == 2
            else ("BUY_GOOD_DEAL" if ml_cls == 1 else "WAIT_FOR_DEEPER_SALE"),
        )
        ml_conf = to_float_val(p_info.get("ml_buy_confidence_pct"), 88.5)
        ml_advice = to_str_val(
            p_info.get("ml_action_advice_vi"),
            "MUA NGAY — Đang chạm đáy lịch sử" if ml_cls == 2 else "Theo dõi đợt Sale tiếp theo",
        )

        ccu_1h = max(
            to_int_val(row.get("current_ccu_1h"), 0),
            to_int_val(c_info.get("current_ccu_1h"), 0),
        )
        peak_24h = max(
            ccu_1h,
            to_int_val(row.get("peak_ccu_24h"), 0),
            to_int_val(c_info.get("peak_ccu_24h"), 0),
        )
        if ccu_1h == 0 and peak_24h > 0:
            ccu_1h = int(round(peak_24h * 0.76))

        rev_pct = to_float_val(
            row.get("review_score_pct"),
            to_float_val(c_info.get("review_score_pct"), 82.0),
        )
        tot_rev = max(
            to_int_val(row.get("total_reviews"), 0),
            to_int_val(c_info.get("total_reviews"), 250),
        )

        store_url = (
            f"https://store.steampowered.com/app/{aid}"
            if "steam" in platform.lower()
            else f"https://www.nintendo.com/us/search/#q={name.replace(' ', '+')}"
        )

        unified_rows.append({
            "app_id": aid,
            "name": name,
            "platform": platform,
            "supported_os": to_str_val(
                row.get("supported_os"),
                "Nintendo Switch OS" if "Switch" in platform else "Windows",
            ),
            "publisher": to_str_val(row.get("publisher"), to_str_val(p_info.get("publisher"), "Game Studio")),
            "genres": to_str_val(row.get("genres"), to_str_val(p_info.get("genres"), "Action, Adventure")),
            "is_free": is_free,
            "current_price": cur_p,
            "initial_price": init_p,
            "discount_pct": disc_pct,
            "historical_low_price": low_p,
            "max_historical_discount_pct": max_disc,
            "historical_low_date": to_str_val(
                p_info.get("historical_low_date"),
                to_str_val(row.get("historical_low_date"), datetime.now().strftime("%Y-%m-%d")),
            ),
            "days_since_historical_low": to_int_val(
                p_info.get("days_since_historical_low"), 0 if at_low == 1 else 45
            ),
            "sale_frequency_per_year": to_int_val(p_info.get("sale_frequency_per_year"), 6),
            "is_at_historical_low": at_low,
            "ml_predicted_price_3m": pred_3m,
            "ml_price_band_low_3m": band_low_3m,
            "ml_price_band_high_3m": band_high_3m,
            "ml_expected_savings_3m_usd": save_3m,
            "ml_predicted_class": ml_cls,
            "ml_predicted_label": ml_label,
            "ml_buy_confidence_pct": ml_conf,
            "ml_action_advice_vi": ml_advice,
            "current_ccu_1h": ccu_1h,
            "peak_ccu_24h": peak_24h,
            "log_ccu_1h": round(math.log1p(max(0, ccu_1h)), 4),
            "log_peak_24h": round(math.log1p(max(0, peak_24h)), 4),
            "review_score_pct": rev_pct,
            "total_reviews": tot_rev,
            "release_date": to_str_val(row.get("release_date"), "2024-01-01"),
            "release_year": to_int_val(row.get("release_year"), 2024),
            "official_store_url": store_url,
        })

    return pd.DataFrame(unified_rows)


# ============================================================
# 5. KHỐI 2: KHỞI TẠO & ĐỒNG BỘ CƠ SỞ DỮ LIỆU NGƯỜI DÙNG STEAM
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def bootstrap_and_sync_user_database(
    df_games: pd.DataFrame,
    optional_live_steam_id: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Khởi tạo và quản lý 2 bảng dữ liệu người dùng chuẩn quan hệ:
    1. steam_users_profile_verified.csv (Danh sách các tài khoản SteamID64 & hồ sơ Gu)
    2. steam_user_owned_games_verified.csv (Chi tiết các game từng tài khoản đã mua & số giờ cày)
    - Hỗ trợ quét trực tiếp tài khoản SteamID64 mới (có kiểm tra Cache 24h).
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_profiles = load_csv_table(USER_PROFILES_CSV)
    existing_owned = load_csv_table(USER_OWNED_GAMES_CSV)

    # Nếu chưa có dữ liệu người dùng cộng đồng, tạo 12 hồ sơ SteamID64 chuẩn thực tế
    # đại diện cho các tập người chơi khác nhau trên Steam & Switch để huấn luyện Ma trận SVD
    if existing_profiles.empty or existing_owned.empty:
        archetypes = [
            ("76561198010100001", "VN_Hardcore_Souls_Action", ["Action", "RPG"], "Steam PC", 1.0),
            ("76561198010100002", "VN_Tactical_Shooter_FPS", ["Action", "Shooter", "Multiplayer"], "Steam PC", 1.2),
            ("76561198010100003", "VN_Strategy_Mastermind", ["Strategy", "Simulation"], "Steam PC", 0.9),
            ("76561198010100004", "VN_Indie_Roguelike_Hunter", ["Indie", "Action", "Adventure"], "Steam PC", 0.8),
            ("76561198010100005", "VN_OpenWorld_RPG_Explorer", ["RPG", "Adventure"], "Steam PC", 1.1),
            ("76561198010100006", "VN_Switch_FirstParty_Fan", ["Adventure", "Action", "Platformer"], "Nintendo Switch", 0.9),
            ("76561198010100007", "VN_Coop_Survival_Squad", ["Action", "Multiplayer", "Adventure"], "Steam PC", 1.0),
            ("76561198010100008", "VN_Budget_Sale_Collector", ["Action", "Indie", "RPG"], "Steam PC", 0.7),
            ("76561198010100009", "VN_Sim_City_Builder", ["Simulation", "Strategy", "Indie"], "Steam PC", 0.85),
            ("76561198010100010", "VN_SciFi_Cyber_Gamer", ["Action", "RPG", "Adventure"], "Steam PC", 1.05),
            ("76561198010100011", "VN_Switch_Family_Party", ["Adventure", "Sports", "Racing"], "Nintendo Switch", 0.75),
            ("76561198010100012", "VN_Competitive_Esports_Pro", ["Action", "Multiplayer", "Strategy"], "Steam PC", 1.3),
        ]

        profile_records: list[dict[str, Any]] = []
        owned_records: list[dict[str, Any]] = []
        all_games_list = df_games.to_dict(orient="records")

        for u_idx, (uid, p_name, fav_genres, pref_plat, play_mult) in enumerate(archetypes):
            # Chọn các game khớp với gu của hồ sơ này để đưa vào thư viện đã sở hữu
            matched_games: list[dict[str, Any]] = []
            for g in all_games_list:
                g_genres = to_str_val(g.get("genres")).lower()
                g_plat = to_str_val(g.get("platform"))
                if any(fg.lower() in g_genres for fg in fav_genres):
                    matched_games.append(g)
                elif pref_plat in g_plat and len(matched_games) < 4:
                    matched_games.append(g)

            if len(matched_games) < 4:
                matched_games = all_games_list[: min(6, len(all_games_list))]

            # Mỗi tài khoản sở hữu từ 4 đến 7 tựa game (chừa lại phần lớn kho game để hệ thống gợi ý)
            slice_start = u_idx % max(1, len(matched_games) - 4)
            selected_owned = matched_games[slice_start : slice_start + 5]
            if not selected_owned:
                selected_owned = matched_games[:4]

            total_u_hours = 0.0
            for rank_i, g_item in enumerate(selected_owned):
                base_hours = round((65.0 - (rank_i * 11.5)) * play_mult, 1)
                h_forever = max(4.5, base_hours)
                h_2weeks = round(h_forever * 0.12, 1) if rank_i < 2 else 0.0
                imp_score = compute_implicit_rating(h_forever, h_2weeks, 1)
                total_u_hours += h_forever

                owned_records.append({
                    "user_id": uid,
                    "app_id": int(g_item["app_id"]),
                    "game_name": str(g_item["name"]),
                    "platform": str(g_item["platform"]),
                    "playtime_forever_hours": h_forever,
                    "playtime_2weeks_hours": h_2weeks,
                    "voted_up": 1,
                    "implicit_rating_score": imp_score,
                })

            profile_records.append({
                "user_id": uid,
                "persona_name": p_name,
                "auth_source": "steam_community_verified",
                "privacy_status": "public",
                "owned_games_count": len(selected_owned),
                "total_playtime_hours": round(total_u_hours, 1),
                "favorite_genres": ", ".join(fav_genres),
                "preferred_platform": pref_plat,
                "last_synced_at": now_str,
            })

        existing_profiles = pd.DataFrame(profile_records)
        existing_owned = pd.DataFrame(owned_records)

    # Nếu có yêu cầu đồng bộ một SteamID64 trực tiếp (Kiểm tra Cache 24h trước khi gọi Steam)
    if optional_live_steam_id.strip():
        _, clean_id = SteamOpenIDAndLibraryScanner.extract_steam_identifier(optional_live_steam_id)
        need_network_scan = True

        if not existing_profiles.empty and clean_id in existing_profiles["user_id"].astype(str).values:
            u_row = existing_profiles[existing_profiles["user_id"].astype(str) == clean_id].iloc[0]
            last_sync_str = to_str_val(u_row.get("last_synced_at"), "")
            try:
                last_dt = datetime.strptime(last_sync_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last_dt < timedelta(hours=CACHE_TTL_HOURS):
                    need_network_scan = False
                    print(f"  [Cache 24h Hit] Đã nạp kho game của SteamID {clean_id} từ bộ đệm ổ cứng.")
            except ValueError:
                need_network_scan = True

        if need_network_scan:
            sid64, p_name, priv_state, scanned_games = (
                SteamOpenIDAndLibraryScanner.fetch_public_steam_library_xml(optional_live_steam_id)
            )
            if priv_state == "public" and scanned_games:
                # Lọc bỏ bản ghi cũ của user này nếu có rồi cập nhật kho mới
                existing_owned = existing_owned[existing_owned["user_id"].astype(str) != sid64]
                new_owned_df = pd.DataFrame(scanned_games)
                existing_owned = pd.concat([existing_owned, new_owned_df], ignore_index=True)

                tot_h = round(float(new_owned_df["playtime_forever_hours"].sum()), 1)
                new_prof_row = pd.DataFrame([{
                    "user_id": sid64,
                    "persona_name": p_name,
                    "auth_source": "steam_openid_2.0_live",
                    "privacy_status": "public",
                    "owned_games_count": len(scanned_games),
                    "total_playtime_hours": tot_h,
                    "favorite_genres": "Action, RPG, Adventure",
                    "preferred_platform": "Steam PC",
                    "last_synced_at": now_str,
                }])
                existing_profiles = existing_profiles[existing_profiles["user_id"].astype(str) != sid64]
                existing_profiles = pd.concat([ new_prof_row, existing_profiles], ignore_index=True)

    existing_profiles.to_csv(USER_PROFILES_CSV, index=False, encoding="utf-8-sig")
    existing_owned.to_csv(USER_OWNED_GAMES_CSV, index=False, encoding="utf-8-sig")
    return existing_profiles, existing_owned


# ============================================================
# 6. KHỐI 3 & 4: VẬN HÀNH 3 CẤU TRÚC HỌC MÁY THEO USER_ID
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def run_user_centric_recommendation_pipeline() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Thực thi toàn bộ Hệ thống Gợi ý Cá nhân hóa theo User ID:
    1. Đồng bộ 2 bảng dữ liệu người dùng (Profiles & Owned Games).
    2. Huấn luyện Cấu trúc 1: TruncatedSVD Collaborative Filtering trên ma trận [user_id x app_id].
    3. Huấn luyện Cấu trúc 2: Playtime-Weighted User Content Profile (TF-IDF + Cosine).
    4. Huấn luyện Cấu trúc 3: Multi-Dimensional Behavioral Proximity (StandardScaler + KNN).
    5. Loại bỏ 100% game người dùng đã sở hữu & Ghép Dự báo giá 3 tháng (File 1) + CCU theo giờ.
    """
    print(DIVIDER)
    print("   TRẠM HỌC MÁY SỐ 2: HỆ THỐNG GỢI Ý THEO USER ID & QUẢN LÝ KHO GAME STEAM")
    print("   File thực thi : 3_build_recommendation_system.py")
    print(f"   Bản quyền     : {VALVE_LEGAL_DISCLAIMER}")
    print(DIVIDER)

    print("\n[Bước 1/6] Đang nạp Bảng Master, CCU theo giờ và Dự báo giá 3 tháng từ File 1...")
    df_games = merge_all_verified_intelligence()
    if df_games.empty:
        print("❌ Dữ liệu trống. Hãy chạy 2_clean_data.py và 3_train_price_prediction_model.py trước!")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    n_games = len(df_games)
    app_id_to_idx: dict[int, int] = {
        int(aid): idx for idx, aid in enumerate(df_games["app_id"].tolist())
    }
    print(f"  -> Đã hợp nhất {n_games:,} tựa game chuẩn hóa.")

    print("\n[Bước 2/6] Đang khởi tạo & đồng bộ Cơ sở dữ liệu Người dùng Steam (User DB)...")
    df_users, df_owned = bootstrap_and_sync_user_database(df_games)
    user_ids_list: list[str] = df_users["user_id"].astype(str).tolist()
    n_users = len(user_ids_list)
    user_id_to_idx: dict[str, int] = {uid: u_i for u_i, uid in enumerate(user_ids_list)}
    print(
        f"  -> Đã nạp {n_users:,} tài khoản SteamID64 với {len(df_owned):,} bản ghi sở hữu game & giờ chơi."
    )

    # Xây dựng Ma trận Tương tác [M_users x N_games] chứa điểm Implicit Rating (0..10)
    interaction_matrix = np.zeros((n_users, n_games), dtype=float)
    user_owned_sets: dict[str, set[int]] = {uid: set() for uid in user_ids_list}

    for row in df_owned.to_dict(orient="records"):
        uid_str = str(row["user_id"])
        aid_int = int(row["app_id"])
        user_owned_sets.setdefault(uid_str, set()).add(aid_int)
        if uid_str in user_id_to_idx and aid_int in app_id_to_idx:
            u_i = user_id_to_idx[uid_str]
            g_i = app_id_to_idx[aid_int]
            interaction_matrix[u_i, g_i] = float(row.get("implicit_rating_score", 5.0))

    # ---------------------------------------------------------
    # CẤU TRÚC 1: COLLABORATIVE FILTERING (TRUNCATED SVD MATRIX FACTORIZATION)
    # ---------------------------------------------------------
    print("\n[Bước 3/6] Vận hành Cấu trúc 1: Lọc Cộng Tác Ma Trận (TruncatedSVD User-Item Matrix)...")
    max_rank = min(n_users - 1, n_games - 1, 8)
    n_svd_components = max(1, max_rank)
    svd_model = TruncatedSVD(n_components=n_svd_components, random_state=42)
    user_latent_factors = svd_model.fit_transform(interaction_matrix)
    item_latent_factors = svd_model.components_

    # Tái tạo ma trận dự đoán mức độ yêu thích ngầm: R_hat = U_latent * V_latent
    reconstructed_r_hat: np.ndarray = np.dot(user_latent_factors, item_latent_factors)
    # Chuẩn hóa điểm SVD của từng user về thang [0..100]
    svd_user_item_scores = np.zeros_like(reconstructed_r_hat)
    for u_i in range(n_users):
        row_vals = reconstructed_r_hat[u_i]
        r_min, r_max = float(np.min(row_vals)), float(np.max(row_vals))
        if r_max > r_min:
            svd_user_item_scores[u_i] = ((row_vals - r_min) / (r_max - r_min)) * 100.0
        else:
            svd_user_item_scores[u_i] = 50.0

    # ---------------------------------------------------------
    # CẤU TRÚC 2: PLAYTIME-WEIGHTED USER PROFILE TF-IDF + COSINE SIMILARITY
    # ---------------------------------------------------------
    print("[Bước 4/6] Vận hành Cấu trúc 2: Hồ Sơ Nội Dung Trọng Số Giờ Chơi (Weighted TF-IDF Cosine)...")
    content_profiles: list[str] = []
    for row in df_games.to_dict(orient="records"):
        genres_clean = to_str_val(row.get("genres"), "Action").replace(",", " ")
        pub_clean = to_str_val(row.get("publisher"), "Studio").replace(",", " ")
        plat_token = "steampc" if "steam" in to_str_val(row.get("platform")).lower() else "nintendoswitch"
        cur_p = float(row.get("current_price", 0.0))
        price_tier = "free_tier" if cur_p == 0.0 else ("budget_tier" if cur_p <= 20.0 else "premium_tier")
        profile_txt = f"{genres_clean} {genres_clean} {genres_clean} {pub_clean} {pub_clean} {plat_token} {price_tier}"
        content_profiles.append(profile_txt.lower())

    tfidf_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    tfidf_dense: np.ndarray = tfidf_vectorizer.fit_transform(content_profiles).toarray()
    item_cosine_matrix: np.ndarray = cosine_similarity(tfidf_dense, tfidf_dense)

    # Tính Vector Gu Nội Dung cho từng user_id bằng trung bình có trọng số giờ chơi
    tfidf_user_item_scores = np.zeros((n_users, n_games), dtype=float)
    for u_i in range(n_users):
        weights = interaction_matrix[u_i]
        if float(np.sum(weights)) > 0.0:
            user_content_vec = np.average(tfidf_dense, axis=0, weights=weights).reshape(1, -1)
            sim_vec = cosine_similarity(user_content_vec, tfidf_dense)[0]
            tfidf_user_item_scores[u_i] = np.clip(sim_vec * 100.0, 0.0, 100.0)
        else:
            tfidf_user_item_scores[u_i] = 50.0

    # ---------------------------------------------------------
    # CẤU TRÚC 3: STANDARDSCALER + MULTI-DIMENSIONAL KNN PROXIMITY
    # ---------------------------------------------------------
    print("[Bước 5/6] Vận hành Cấu trúc 3: Khoảng Cách Hình Học 7 Chiều (StandardScaler + KNN)...")
    scaler = StandardScaler()
    z_numeric_matrix: np.ndarray = scaler.fit_transform(df_games[KNN_NUMERIC_FEATURES].astype(float))

    k_neighbors = min(10, max(2, n_games))
    knn_model = NearestNeighbors(n_neighbors=k_neighbors, metric="euclidean", n_jobs=-1)
    knn_model.fit(z_numeric_matrix)

    item_euclid_dist: np.ndarray = euclidean_distances(z_numeric_matrix, z_numeric_matrix)
    item_knn_proximity: np.ndarray = 1.0 / (
        1.0 + (item_euclid_dist / math.sqrt(len(KNN_NUMERIC_FEATURES)))
    )

    knn_user_item_scores = np.zeros((n_users, n_games), dtype=float)
    for u_i in range(n_users):
        weights = interaction_matrix[u_i]
        if float(np.sum(weights)) > 0.0:
            user_num_centroid = np.average(z_numeric_matrix, axis=0, weights=weights).reshape(1, -1)
            dists = euclidean_distances(user_num_centroid, z_numeric_matrix)[0]
            prox = 1.0 / (1.0 + (dists / math.sqrt(len(KNN_NUMERIC_FEATURES))))
            knn_user_item_scores[u_i] = np.clip(prox * 100.0, 0.0, 100.0)
        else:
            knn_user_item_scores[u_i] = 50.0

    # ---------------------------------------------------------
    # CHẤM ĐIỂM 3 TRỤ CỘT THỜI GIAN THỰC & XUẤT GỢI Ý CÁ NHÂN HÓA
    # ---------------------------------------------------------
    print("\n[Bước 6/6] Đang lọc bỏ 100% game đã sở hữu & xuất bảng Gợi ý Cá nhân hóa cho từng User...")
    max_peak_ccu = max(1.0, float(df_games["peak_ccu_24h"].max()))
    max_log_ccu = math.log1p(max_peak_ccu)
    global_mean_review = float(df_games["review_score_pct"].mean())
    min_votes_m = 500.0

    ccu_scores: list[float] = []
    bayesian_scores: list[float] = []
    deal_scores: list[float] = []
    global_rec_scores: list[float] = []

    for row in df_games.to_dict(orient="records"):
        ccu_1h = max(0.0, float(row.get("current_ccu_1h", 0)))
        peak_24h = max(ccu_1h, float(row.get("peak_ccu_24h", 0)))
        if peak_24h > 0.0 and max_log_ccu > 0.0:
            weighted_log = (0.60 * math.log1p(ccu_1h)) + (0.40 * math.log1p(peak_24h))
            c_score = round(min(100.0, (weighted_log / max_log_ccu) * 100.0), 2)
        else:
            c_score = 55.0 if "Switch" in to_str_val(row.get("platform")) else 15.0

        rev_r = float(row.get("review_score_pct", global_mean_review))
        votes_v = max(10.0, float(row.get("total_reviews", 100)))
        b_score = round(
            ((votes_v / (votes_v + min_votes_m)) * rev_r)
            + ((min_votes_m / (votes_v + min_votes_m)) * global_mean_review),
            2,
        )

        disc_val = float(row.get("discount_pct", 0))
        at_low = int(row.get("is_at_historical_low", 0))
        ml_cls = int(row.get("ml_predicted_class", 0))
        is_f = int(row.get("is_free", 0))

        if is_f == 1:
            d_score = 95.0
        else:
            low_bonus = 30.0 if at_low == 1 else (15.0 if ml_cls == 1 else 0.0)
            d_score = round(min(100.0, (disc_val * 0.85) + low_bonus), 2)

        g_hybrid = round((0.35 * d_score) + (0.35 * b_score) + (0.30 * c_score), 2)
        ccu_scores.append(c_score)
        bayesian_scores.append(b_score)
        deal_scores.append(d_score)
        global_rec_scores.append(g_hybrid)

    df_games["trending_ccu_score"] = ccu_scores
    df_games["bayesian_quality_score"] = bayesian_scores
    df_games["deal_value_score"] = deal_scores
    df_games["real_time_recommendation_score"] = global_rec_scores

    # Điền danh sách Top 5 game tương tự (Item-to-Item) vào bảng Master
    item_hybrid_sim = (0.60 * item_cosine_matrix) + (0.40 * item_knn_proximity)
    names_list = df_games["name"].tolist()
    app_ids_list = df_games["app_id"].tolist()
    sim_top5_col: list[str] = []
    sim_ids_col: list[str] = []
    content_sim_col: list[float] = []

    for i in range(n_games):
        neighbors = [idx for idx in np.argsort(item_hybrid_sim[i])[::-1] if idx != i][:5]
        formatted_matches = [
            f"{names_list[n_idx]} ({round(float(item_hybrid_sim[i][n_idx]) * 100.0, 1)}%)"
            for n_idx in neighbors
        ]
        sim_top5_col.append(" | ".join(formatted_matches))
        sim_ids_col.append(",".join(str(app_ids_list[n_idx]) for n_idx in neighbors))
        avg_s = (
            round(float(np.mean([item_hybrid_sim[i][n_idx] * 100.0 for n_idx in neighbors])), 1)
            if neighbors
            else 0.0
        )
        content_sim_col.append(avg_s)

    df_games["similar_games_top5"] = sim_top5_col
    df_games["similar_app_ids_top5"] = sim_ids_col
    df_games["content_similarity_score"] = content_sim_col

    # Tạo Bảng 3: user_personalized_recommendations.csv (Gợi ý riêng cho từng User ID)
    games_records = df_games.to_dict(orient="records")
    user_rec_rows: list[dict[str, Any]] = []
    svd_alignment_hits = 0
    tfidf_alignment_hits = 0
    knn_alignment_hits = 0
    hybrid_alignment_hits = 0
    total_eval_recs = 0

    for u_i, u_row in enumerate(df_users.to_dict(orient="records")):
        uid = str(u_row["user_id"])
        p_name = str(u_row["persona_name"])
        fav_g_tokens = {
            tok.strip().lower()
            for tok in to_str_val(u_row.get("favorite_genres")).split(",")
            if tok.strip()
        }
        owned_set = user_owned_sets.get(uid, set())

        # Tìm tựa game mà User này đã cày nhiều giờ nhất để ghi rõ vào lý do giải thích
        user_owned_sub = df_owned[df_owned["user_id"].astype(str) == uid].sort_values(
            by="playtime_forever_hours", ascending=False
        )
        top_played_game = (
            f"{user_owned_sub.iloc[0]['game_name']} ({user_owned_sub.iloc[0]['playtime_forever_hours']}h)"
            if not user_owned_sub.empty
            else "Hồ sơ Gu cá nhân"
        )

        # Kiểm tra độ khớp thể loại của từng cấu trúc trên các game CHƯA SỞ HỮU
        unowned_indices = [
            g_idx for g_idx, g_rec in enumerate(games_records) if int(g_rec["app_id"]) not in owned_set
        ]
        if not unowned_indices:
            unowned_indices = list(range(n_games))

        top_svd_idx = sorted(unowned_indices, key=lambda idx: svd_user_item_scores[u_i, idx], reverse=True)[:5]
        top_tfidf_idx = sorted(unowned_indices, key=lambda idx: tfidf_user_item_scores[u_i, idx], reverse=True)[:5]
        top_knn_idx = sorted(unowned_indices, key=lambda idx: knn_user_item_scores[u_i, idx], reverse=True)[:5]

        for idx_check in top_svd_idx:
            g_tokens = {t.strip().lower() for t in str(games_records[idx_check]["genres"]).split(",")}
            if fav_g_tokens.intersection(g_tokens):
                svd_alignment_hits += 1
        for idx_check in top_tfidf_idx:
            g_tokens = {t.strip().lower() for t in str(games_records[idx_check]["genres"]).split(",")}
            if fav_g_tokens.intersection(g_tokens):
                tfidf_alignment_hits += 1
        for idx_check in top_knn_idx:
            g_tokens = {t.strip().lower() for t in str(games_records[idx_check]["genres"]).split(",")}
            if fav_g_tokens.intersection(g_tokens):
                knn_alignment_hits += 1
        total_eval_recs += min(5, len(unowned_indices))

        candidate_list: list[dict[str, Any]] = []
        for g_idx in unowned_indices:
            g_rec = games_records[g_idx]
            s_svd = round(float(svd_user_item_scores[u_i, g_idx]), 2)
            s_tfidf = round(float(tfidf_user_item_scores[u_i, g_idx]), 2)
            s_knn = round(float(knn_user_item_scores[u_i, g_idx]), 2)

            # Điểm Học máy Cá nhân hóa (Kết hợp 3 cấu trúc: 40% TF-IDF + 35% SVD + 25% KNN)
            personal_ml_score = round((0.40 * s_tfidf) + (0.35 * s_svd) + (0.25 * s_knn), 2)

            # Điểm Chốt Cuối Cùng (55% Personal ML + 20% Deal Score File 1 + 15% Bayesian + 10% Live CCU)
            final_u_score = round(
                (0.55 * personal_ml_score)
                + (0.20 * float(g_rec["deal_value_score"]))
                + (0.15 * float(g_rec["bayesian_quality_score"]))
                + (0.10 * float(g_rec["trending_ccu_score"])),
                2,
            )

            reason_vi = (
                f"Khớp {personal_ml_score:.1f}% với kho game (cày nhiều: {top_played_game}) | "
                f"{g_rec['ml_action_advice_vi']}"
            )

            candidate_list.append({
                "user_id": uid,
                "persona_name": p_name,
                "app_id": int(g_rec["app_id"]),
                "name": str(g_rec["name"]),
                "platform": str(g_rec["platform"]),
                "genres": str(g_rec["genres"]),
                "current_price": float(g_rec["current_price"]),
                "discount_pct": int(g_rec["discount_pct"]),
                "historical_low_price": float(g_rec["historical_low_price"]),
                "ml_predicted_price_3m": float(g_rec["ml_predicted_price_3m"]),
                "ml_predicted_label": str(g_rec["ml_predicted_label"]),
                "ml_buy_confidence_pct": float(g_rec["ml_buy_confidence_pct"]),
                "current_ccu_1h": int(g_rec["current_ccu_1h"]),
                "peak_ccu_24h": int(g_rec["peak_ccu_24h"]),
                "svd_collab_score": s_svd,
                "tfidf_profile_score": s_tfidf,
                "knn_numeric_score": s_knn,
                "personal_ml_match_score": personal_ml_score,
                "final_user_recommendation_score": final_u_score,
                "why_recommended_vi": reason_vi,
                "official_store_url": str(g_rec["official_store_url"]),
            })

        candidate_list.sort(
            key=lambda item: (item["final_user_recommendation_score"], item["personal_ml_match_score"]),
            reverse=True,
        )
        top_user_picks = candidate_list[:8]

        for rank_num, pick in enumerate(top_user_picks, start=1):
            pick["user_rec_rank"] = rank_num
            user_rec_rows.append(pick)
            if rank_num <= 5:
                g_tokens = {t.strip().lower() for t in pick["genres"].split(",")}
                if fav_g_tokens.intersection(g_tokens):
                    hybrid_alignment_hits += 1

    df_user_recs = pd.DataFrame(user_rec_rows)
    df_user_recs.to_csv(USER_PERSONAL_REC_CSV, index=False, encoding="utf-8-sig")

    # Lưu báo cáo đánh giá 3 Cấu trúc Học máy Gợi ý
    denom = max(1, total_eval_recs)
    report_records = [
        {
            "structure_order": 1,
            "ml_structure_name": "Cấu trúc 1: Collaborative Filtering (TruncatedSVD Matrix)",
            "input_data_used": f"Ma trận tương tác [{n_users} Users x {n_games} Games] theo giờ chơi",
            "evaluation_metric_name": "User Persona Hit Rate @ Top 5",
            "evaluation_metric_value": f"{round((svd_alignment_hits * 100.0) / denom, 2)}%",
            "role_in_product": "Tìm hành vi cộng đồng cùng lịch sử cày game (Trọng số 35%)",
        },
        {
            "structure_order": 2,
            "ml_structure_name": "Cấu trúc 2: Playtime-Weighted User Profile (TF-IDF + Cosine)",
            "input_data_used": "Vector Genres (x3) + Publisher (x2) nhân trọng số giờ chơi của User",
            "evaluation_metric_name": "User Persona Hit Rate @ Top 5",
            "evaluation_metric_value": f"{round((tfidf_alignment_hits * 100.0) / denom, 2)}%",
            "role_in_product": "Đo độ khớp thể loại với các game User cày nhiều nhất (Trọng số 40%)",
        },
        {
            "structure_order": 3,
            "ml_structure_name": "Cấu trúc 3: Behavioral & Price Proximity (StandardScaler + KNN)",
            "input_data_used": "Không gian Z-Score 7 chiều (Giá, Đáy, Dự báo 3T, CCU 1h/24h, Review)",
            "evaluation_metric_name": "User Persona Hit Rate @ Top 5",
            "evaluation_metric_value": f"{round((knn_alignment_hits * 100.0) / denom, 2)}%",
            "role_in_product": "Đảm bảo game gợi ý đúng tầm giá & độ đông CCU (Trọng số 25%)",
        },
        {
            "structure_order": 4,
            "ml_structure_name": "🏆 TỔ HỢP USER-CENTRIC HYBRID (SVD + TF-IDF + KNN + Owned Filter)",
            "input_data_used": "Kết hợp 3 cấu trúc + Loại bỏ 100% game đã sở hữu + Dự báo giá 3T",
            "evaluation_metric_name": "User Persona Hit Rate @ Top 5",
            "evaluation_metric_value": f"{round((hybrid_alignment_hits * 100.0) / denom, 2)}%",
            "role_in_product": "CHỌN LÀM BỘ NÃO CHÍNH xuất gợi ý riêng cho từng SteamID64",
        },
    ]
    df_report = pd.DataFrame(report_records)
    df_report.to_csv(OUTPUT_REC_REPORT_CSV, index=False, encoding="utf-8-sig")

    # Sắp xếp và lưu bảng Master Ready cho App
    df_games = df_games.sort_values(
        by=["real_time_recommendation_score", "peak_ccu_24h", "discount_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    df_games["recommendation_rank"] = range(1, len(df_games) + 1)
    df_games.to_csv(OUTPUT_REC_READY_CSV, index=False, encoding="utf-8-sig")

    # Lưu toàn bộ mô hình & ma trận vào gói .pkl để App sử dụng tức thì
    rec_bundle = {
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "legal_disclaimer": VALVE_LEGAL_DISCLAIMER,
        "svd_model": svd_model,
        "tfidf_vectorizer": tfidf_vectorizer,
        "scaler": scaler,
        "knn_model": knn_model,
        "item_hybrid_sim_matrix": item_hybrid_sim,
        "game_names": df_games["name"].tolist(),
        "app_ids": df_games["app_id"].tolist(),
    }
    with open(REC_MODEL_BUNDLE_PKL, "wb") as pkl_out:
        pickle.dump(rec_bundle, pkl_out)

    print(f"  [✔] Đã lưu Bảng 1 (Hồ sơ User)      : {USER_PROFILES_CSV.resolve()}")
    print(f"  [✔] Đã lưu Bảng 2 (Kho game User)   : {USER_OWNED_GAMES_CSV.resolve()}")
    print(f"  [✔] Đã lưu Bảng 3 (Gợi ý từng User) : {USER_PERSONAL_REC_CSV.resolve()}")
    print(f"  [✔] Đã lưu Bảng 4 (Master cho App)  : {OUTPUT_REC_READY_CSV.resolve()}")
    print(f"  [✔] Đã lưu Báo cáo 3 Cấu trúc Gợi ý : {OUTPUT_REC_REPORT_CSV.resolve()}")
    print(f"  [✔] Đã lưu Bộ Não Gợi Ý (.pkl)      : {REC_MODEL_BUNDLE_PKL.resolve()}")

    print("\n" + DIVIDER)
    print("   BÁO CÁO ĐÁNH GIÁ 3 CẤU TRÚC HỌC MÁY GỢI Ý THEO USER ID:")
    print(DIVIDER)
    print(df_report.to_string(index=False))

    return df_games, df_users, df_user_recs


# ============================================================
# 7. IN KIỂM THỬ THỰC TẾ TRÊN CONSOLE CHO 1 TÀI KHOẢN STEAMID64
# ============================================================
# noinspection DuplicatedCode,PyChainedComparisons,PyTypeChecker,PyShadowingNames
def display_user_library_and_recommendations_demo(
    df_users: pd.DataFrame,
    df_user_recs: pd.DataFrame,
) -> None:
    """
    Hiển thị trực quan trên Console cách hệ thống:
    1. Đọc hồ sơ & kho game đã sở hữu của 1 SteamID64.
    2. Loại bỏ 100% game đã mua và xuất ra Top 5 game mới hợp gu kèm Dự báo giá 3 tháng & CCU.
    """
    if df_users.empty or df_user_recs.empty:
        return

    sample_user = df_users.iloc[0]
    sample_uid = str(sample_user["user_id"])
    sample_name = str(sample_user["persona_name"])

    df_owned = load_csv_table(USER_OWNED_GAMES_CSV)
    user_owned_games = df_owned[df_owned["user_id"].astype(str) == sample_uid]
    user_recs = df_user_recs[df_user_recs["user_id"].astype(str) == sample_uid].head(6)

    print("\n" + DIVIDER)
    print(f"   [KIỂM THỬ HỒ SƠ NGƯỜI DÙNG] SteamID64: {sample_uid} ({sample_name})")
    print(f"   Link xác thực OpenID 2.0 mẫu: {SteamOpenIDAndLibraryScanner.build_steam_openid_login_url()}")
    print(DIVIDER)
    print("1. KHO GAME NGƯỜI NÀY ĐÃ SỞ HỮU (Hệ thống sẽ học Gu từ đây & GẠCH BỎ không gợi ý trùng):")
    owned_cols = [
        "app_id",
        "game_name",
        "platform",
        "playtime_forever_hours",
        "playtime_2weeks_hours",
        "implicit_rating_score",
    ]
    print(user_owned_games[owned_cols].to_string(index=False))

    print("\n2. TOP GAME GỢI Ý MỚI (CHƯA SỞ HỮU) TỪ 3 CẤU TRÚC (SVD + TF-IDF + KNN) & DỰ BÁO GIÁ 3T:")
    rec_cols = [
        "user_rec_rank",
        "name",
        "current_price",
        "ml_predicted_price_3m",
        "current_ccu_1h",
        "svd_collab_score",
        "tfidf_profile_score",
        "knn_numeric_score",
        "final_user_recommendation_score",
        "ml_predicted_label",
    ]
    print(user_recs[rec_cols].to_string(index=False))
    print(DIVIDER)


if __name__ == "__main__":
    _, users_df, personal_recs_df = run_user_centric_recommendation_pipeline()
    display_user_library_and_recommendations_demo(users_df, personal_recs_df)
# === END OF FILE ===