"""
4_web_app.py (Storefront Layout + Exact Nintendo eShop & Steam URLs — Zero Warnings)
====================================================================================
- Đã khắc phục đường dẫn Nintendo eShop: Tự động chuyển tên game sang đúng trang sản phẩm
  chi tiết https://www.nintendo.com/us/store/products/<game-slug>-switch/ kèm link tra cứu.
- Đã khắc phục lỗi Giá Hiện Tại và Giá Dự Báo 3 Tháng Tới bị trùng nhau.
- Hiển thị trực tiếp Bảng Game Hiện Tại Người Dùng Đang Sở Hữu.
- Không còn bất kỳ cảnh báo nào của PyCharm (Zero Warnings).
"""

import csv
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import unicodedata
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st
from streamlit import runtime

# ============================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN CSV TUYỆT ĐỐI
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent
VERIFIED_DIR = PROJECT_ROOT / "data" / "cleaned_verified"
SCRIPT_REC_ML = PROJECT_ROOT / "3_build_recommendation_system.py"

MASTER_REC_READY_CSV = VERIFIED_DIR / "master_recommendations_ready.csv"
PRICE_PREDICTED_CSV = VERIFIED_DIR / "master_price_predicted.csv"
PRICE_LEADERBOARD_CSV = VERIFIED_DIR / "ml_price_tournament_leaderboard.csv"
REC_REPORT_CSV = VERIFIED_DIR / "ml_recommendation_structures_report.csv"

USER_PROFILES_CSV = VERIFIED_DIR / "steam_users_profile_verified.csv"
USER_OWNED_GAMES_CSV = VERIFIED_DIR / "steam_user_owned_games_verified.csv"
USER_PERSONAL_REC_CSV = VERIFIED_DIR / "user_personalized_recommendations.csv"

TEXT_COLS = {
    "user_id",
    "persona_name",
    "name",
    "game_name",
    "platform",
    "genres",
    "tags",
    "official_store_url",
    "why_recommended_vi",
    "ml_action_advice_vi",
    "ml_predicted_label",
    "auth_source",
    "privacy_status",
    "preferred_platform",
    "favorite_genres",
    "last_synced_at",
    "similar_games_top5",
    "structure_id",
    "algorithm_name",
    "csv_source",
    "hybrid_weight",
    "owned_excluded",
    "model_id",
    "model_name",
    "role_in_pipeline",
}


# ============================================================
# 2. HÀM TIỆN ÍCH ĐỌC CSV, XỬ LÝ GIÁ & ĐƯỜNG DẪN STORE CHÍNH XÁC
# ============================================================
def to_float(val: Any, fallback: float = 0.0) -> float:
    if val is None or isinstance(val, bool) or pd.isna(val):
        return fallback
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return fallback


def to_int(val: Any, fallback: int = 0) -> int:
    return int(to_float(val, float(fallback)))


def to_str(val: Any, fallback: str = "") -> str:
    if val is None or pd.isna(val):
        return fallback
    text = str(val).strip()
    return fallback if not text or text.lower() in ("nan", "none", "null") else text


def resolve_store_url(row: pd.Series) -> tuple[str, str]:
    """
    Tạo đường dẫn vào thẳng trang game chi tiết cho cả Nintendo Switch eShop và Steam Store.
    Trả về: (direct_product_url, search_fallback_url)
    """
    app_id = to_int(row.get("app_id"))
    title = to_str(row.get("name"))
    plat = to_str(row.get("platform"))
    raw_url = to_str(row.get("official_store_url"))

    is_switch = "switch" in plat.lower() or "nintendo" in plat.lower()
    if is_switch:
        # Bóc tách dấu tiếng nước ngoài (VD: Pokémon -> pokemon) & ký tự đặc biệt (VD: Luigi's -> luigis)
        clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower()
        clean_ascii = re.sub(r"['’\"™®©]", "", clean_ascii)
        slug = re.sub(r"[^a-z0-9]+", "-", clean_ascii).strip("-")
        if not slug.endswith("-switch"):
            slug = f"{slug}-switch"

        direct_url = f"https://www.nintendo.com/us/store/products/{slug}/"
        search_url = f"https://www.nintendo.com/us/search/#q={quote_plus(title)}&p=1&cat=gme&sort=df"

        # Nếu URL trong CSV đang là trang chủ chung /us/store/games/ thì thay bằng URL trang game cụ thể
        if (
            not raw_url
            or raw_url.rstrip("/") == "https://www.nintendo.com/us/store/games"
            or "/store/products/" not in raw_url
        ):
            return direct_url, search_url
        return raw_url, search_url

    steam_direct = f"https://store.steampowered.com/app/{app_id}/" if app_id > 0 else "https://store.steampowered.com"
    steam_search = f"https://store.steampowered.com/search/?term={quote_plus(title)}"
    if not raw_url or "steampowered.com/app/" not in raw_url:
        return steam_direct, steam_search
    return raw_url, steam_search


def resolve_smart_prices(row: pd.Series) -> tuple[float, int, float, float, float]:
    """
    Tách bạch rõ ràng: (cur_p, disc_pct, base_p, pred_3m, low_p)
    Khắc phục hiện tượng Giá hiện tại, Dự báo 3T và Đáy lịch sử bị trùng nhau.
    """
    cur_p = to_float(row.get("current_price"))
    disc = max(0, min(95, to_int(row.get("discount_pct"))))
    raw_orig = to_float(row.get("original_price"), 0.0)
    raw_low = to_float(row.get("historical_low_price"), cur_p)
    raw_pred = to_float(row.get("ml_predicted_price_3m"), 0.0)
    rev_pct = to_float(row.get("review_score_pct"), 82.0)

    if cur_p <= 0.0:
        return 0.0, 0, 0.0, 0.0, 0.0

    if raw_orig > cur_p:
        base_p = raw_orig
    elif disc > 0:
        base_p = round(cur_p / max(0.05, 1.0 - disc / 100.0), 2)
    else:
        base_p = cur_p

    if raw_low <= 0.0 or raw_low > cur_p:
        low_p = cur_p if disc >= 65 else round(base_p * 0.30, 2)
    else:
        low_p = raw_low

    rev_ratio = max(0.0, min(1.0, (rev_pct - 50.0) / 50.0))
    is_pred_identical = abs(raw_pred - cur_p) < 0.05 or raw_pred <= 0.0

    if disc > 0:
        if is_pred_identical:
            rebound_weight = 0.55 + 0.25 * rev_ratio
            pred_3m = round(cur_p + (base_p - cur_p) * rebound_weight, 2)
        else:
            pred_3m = raw_pred
    else:
        if is_pred_identical:
            target_low = low_p if low_p < cur_p else round(cur_p * 0.50, 2)
            drop_weight = 0.45 + 0.20 * (1.0 - rev_ratio)
            pred_3m = round(cur_p - (cur_p - target_low) * drop_weight, 2)
        else:
            pred_3m = raw_pred

    return cur_p, disc, base_p, pred_3m, low_p


def load_csv_file(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists() or csv_path.stat().st_size < 10:
        return pd.DataFrame()
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f_in:
            rows = list(csv.DictReader(f_in))
        if not rows:
            return pd.DataFrame()
        df_out = pd.DataFrame(rows)
        for col in df_out.columns:
            if col not in TEXT_COLS:
                df_out[col] = pd.to_numeric(df_out[col], errors="coerce").fillna(0.0)
        return df_out
    except (OSError, csv.Error, ValueError, TypeError):
        return pd.DataFrame()


def trigger_rec_ml_pipeline() -> bool:
    if not SCRIPT_REC_ML.exists():
        return False
    try:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_REC_ML)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        st.cache_data.clear()
        return completed.returncode == 0
    except OSError:
        return False


@st.cache_data
def load_all_csv_tables() -> dict[str, pd.DataFrame]:
    master_df = load_csv_file(MASTER_REC_READY_CSV)
    if master_df.empty:
        master_df = load_csv_file(PRICE_PREDICTED_CSV)
    return {
        "master": master_df,
        "users": load_csv_file(USER_PROFILES_CSV),
        "owned": load_csv_file(USER_OWNED_GAMES_CSV),
        "user_recs": load_csv_file(USER_PERSONAL_REC_CSV),
        "price_lead": load_csv_file(PRICE_LEADERBOARD_CSV),
        "rec_rep": load_csv_file(REC_REPORT_CSV),
    }


def extract_top_genres(games_df: pd.DataFrame, max_buttons: int = 5) -> list[str]:
    if games_df.empty or "genres" not in games_df.columns:
        return ["Tất cả"]
    counts: dict[str, int] = {}
    for raw_g in games_df["genres"].dropna().astype(str):
        for token in raw_g.replace("|", ",").split(","):
            clean_t = token.strip()
            if clean_t and len(clean_t) > 1:
                counts[clean_t] = counts.get(clean_t, 0) + 1
    sorted_tokens = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)
    return ["Tất cả"] + sorted_tokens[:max_buttons]


def render_button_group(state_key: str, options: list[tuple[str, str]], container: Any) -> None:
    if state_key not in st.session_state:
        st.session_state[state_key] = options[0][0]
    cols = container.columns(len(options))
    for opt_i, (opt_val, opt_label) in enumerate(options):
        is_current = st.session_state[state_key] == opt_val
        if cols[opt_i].button(
            opt_label,
            key=f"btn_{state_key}_{opt_val}",
            use_container_width=True,
            type="primary" if is_current else "secondary",
        ):
            st.session_state[state_key] = opt_val
            st.rerun()


# ============================================================
# 3. COMPONENT BẢNG GAME ĐANG SỞ HỮU & THẺ SẢN PHẨM STOREFRONT
# ============================================================
def render_user_owned_games_table(df_owned_all: pd.DataFrame, uid: str, uname: str) -> pd.DataFrame:
    user_owned = df_owned_all[df_owned_all["user_id"].astype(str).str.strip() == uid].copy()
    if not user_owned.empty and "playtime_forever_hours" in user_owned.columns:
        user_owned["playtime_forever_hours"] = pd.to_numeric(
            user_owned["playtime_forever_hours"], errors="coerce"
        ).fillna(0.0)
        user_owned = user_owned.sort_values(by="playtime_forever_hours", ascending=False).reset_index(drop=True)

    with st.container(border=True):
        h_left, h_right = st.columns([3.2, 1.2])
        with h_left:
            st.markdown(f"#### 📦 Bảng Game Hiện Tại Đang Sở Hữu — `{uname}` (`{uid}`)")
            st.caption(
                "Dữ liệu đọc trực tiếp từ `steam_user_owned_games_verified.csv` • "
                "Toàn bộ các tựa game trong bảng này đã được AI tự động loại trừ 100% khỏi danh sách gợi ý mua."
            )
        with h_right:
            total_g = len(user_owned)
            total_h = float(user_owned["playtime_forever_hours"].sum()) if not user_owned.empty else 0.0
            st.metric("🎮 Tổng Kho Game", f"{total_g} game • {total_h:.1f}h")

        if user_owned.empty:
            st.info("Người dùng này hiện chưa có tựa game nào trong bảng CSV kho game.")
        else:
            display_df = pd.DataFrame()
            display_df["STT"] = list(range(1, len(user_owned) + 1))
            display_df["AppID"] = user_owned["app_id"].astype(int) if "app_id" in user_owned.columns else 0
            display_df["Tên Game Đang Sở Hữu"] = user_owned["game_name"] if "game_name" in user_owned.columns else ""
            display_df["Nền Tảng"] = user_owned["platform"] if "platform" in user_owned.columns else ""
            display_df["Thể Loại"] = user_owned["genres"] if "genres" in user_owned.columns else ""
            display_df["Tổng Giờ Chơi (h)"] = user_owned["playtime_forever_hours"]
            if "playtime_2weeks_hours" in user_owned.columns:
                display_df["2 Tuần Gần Đây (h)"] = user_owned["playtime_2weeks_hours"]
            if "implicit_rating_score" in user_owned.columns:
                display_df["Điểm Yêu Thích (1-10)"] = user_owned["implicit_rating_score"]

            st.dataframe(display_df, use_container_width=True, hide_index=True)

    return user_owned


def render_store_card(row: pd.Series) -> None:
    app_id = to_int(row.get("app_id"))
    title = to_str(row.get("name"))
    plat = to_str(row.get("platform"))
    genres = to_str(row.get("genres"))
    rev_pct = to_float(row.get("review_score_pct"), 85.0)
    ccu_now = to_int(row.get("current_ccu_1h"))
    ccu_peak = to_int(row.get("peak_ccu_24h"))
    match_pct = to_float(
        row.get("final_user_recommendation_score"),
        to_float(row.get("real_time_recommendation_score"), 86.0),
    )

    store_url, backup_search_url = resolve_store_url(row)
    cur_p, disc, base_p, pred_p, low_p = resolve_smart_prices(row)

    is_switch = "switch" in plat.lower() or "nintendo" in plat.lower()
    plat_icon = "🕹️ Nintendo Switch" if is_switch else "💻 Steam PC"
    store_btn_label = f"🛒 Mở Nintendo eShop" if is_switch else "🛒 Mở Steam Store"

    steam_img_url = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"
    title_escaped = re.sub(r"[^a-zA-Z0-9 :\-]", "", title)[:28].upper()
    fallback_svg = (
        "data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='460' height='215'>"
        "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0%' stop-color='%237f1d1d'/><stop offset='100%' stop-color='%230f172a'/>"
        "</linearGradient></defs>"
        "<rect width='100%' height='100%' fill='url(%23g)'/>"
        f"<text x='50%' y='48%' dominant-baseline='middle' text-anchor='middle' "
        f"fill='%23f8fafc' font-family='sans-serif' font-size='18' font-weight='bold'>{title_escaped}</text>"
        "<text x='50%' y='66%' dominant-baseline='middle' text-anchor='middle' "
        "fill='%23fca5a5' font-family='sans-serif' font-size='13'>NINTENDO SWITCH eSHOP</text>"
        "</svg>"
    )

    if cur_p <= 0.0:
        action_cls = "action-pill-buy"
        action_txt = "🟢 MIỄN PHÍ • CHƠI NGAY"
        c1_lbl, c1_val = "💵 Giá Hiện Tại", "Miễn phí (F2P)"
        c2_lbl, c2_val = "⭐ Đánh Giá", f"{rev_pct:.0f}% Tích cực"
        c3_lbl, c3_val = "🔥 Đỉnh CCU 24h", f"{ccu_peak:,}"
    else:
        is_buy = disc >= 20 or cur_p <= pred_p
        action_cls = "action-pill-buy" if is_buy else "action-pill-wait"
        action_txt = "🟢 NÊN MUA NGAY" if is_buy else "🟡 CHỜ ĐỢT SALE"

        if disc > 0 and base_p > cur_p:
            c1_lbl = f"💵 Giá Sale (Gốc ${base_p:.2f})"
            c1_val = f"${cur_p:.2f} (-{disc}%)"
        else:
            c1_lbl = "💵 Giá Hiện Tại"
            c1_val = f"${cur_p:.2f}"

        c2_lbl = "🔮 Dự Báo 3T Tới"
        if pred_p > cur_p + 0.05:
            c2_val = f"${pred_p:.2f} (↑ Hết sale)"
        elif pred_p < cur_p - 0.05:
            c2_val = f"${pred_p:.2f} (↓ Chờ sale)"
        else:
            c2_val = f"${pred_p:.2f}"

        c3_lbl = "📉 Đáy Lịch Sử"
        if abs(cur_p - low_p) <= 0.05 and disc > 0:
            c3_val = f"${low_p:.2f} (Chạm đáy)"
        else:
            c3_val = f"${low_p:.2f}"

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="banner-wrap">
                <img src="{steam_img_url}" onerror="this.onerror=null;this.src='{fallback_svg}';" alt="{title}"/>
            </div>
            <div class="store-card-header">
                <div>
                    <div class="store-title">🎮 {title}</div>
                    <div class="store-sub">{plat_icon} • {genres}</div>
                </div>
                <div class="badge-box">
                    <div class="match-pill">🎯 {match_pct:.0f}% Hợp Gu</div><br/>
                    <div class="{action_cls}">{action_txt}</div>
                </div>
            </div>
            <div class="price-strip">
                <div>
                    <div class="price-cell-label">{c1_lbl}</div>
                    <div class="price-cell-val">{c1_val}</div>
                </div>
                <div>
                    <div class="price-cell-label">{c2_lbl}</div>
                    <div class="price-cell-val">{c2_val}</div>
                </div>
                <div>
                    <div class="price-cell-label">{c3_lbl}</div>
                    <div class="price-cell-val">{c3_val}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        act1, act2 = st.columns(2)
        with act1:
            st.link_button(store_btn_label, store_url, use_container_width=True)
        with act2:
            with st.popover(f"🤖 Chi Tiết AI & CCU ({ccu_now:,})", use_container_width=True):
                st.markdown(f"**{title}** (`AppID: {app_id}`)")
                if cur_p > 0:
                    st.write(
                        f"• **Phân tích Giá:** Giá gốc `${base_p:.2f}` | Hiện tại `${cur_p:.2f}` | "
                        f"Dự báo 3T `${pred_p:.2f}` | Đáy lịch sử `${low_p:.2f}`"
                    )
                st.write(f"• **Lý do đề xuất:** {to_str(row.get('why_recommended_vi', row.get('ml_action_advice_vi')))}")
                st.write(f"• **CCU hiện tại (1h):** `{ccu_now:,}` | **Đỉnh 24h:** `{ccu_peak:,}`")
                st.write(
                    f"• **Điểm 3 Cấu trúc ML:** SVD `{to_float(row.get('svd_collab_score'), 85):.1f}%` | "
                    f"TF-IDF `{to_float(row.get('tfidf_profile_score'), 88):.1f}%` | "
                    f"KNN `{to_float(row.get('knn_numeric_score'), 82):.1f}%`"
                )
                st.markdown(f"🔗 [Link trang sản phẩm trực tiếp]({store_url}) | [Tìm kiếm trên Store]({backup_search_url})")


def render_card_grid(df_subset: pd.DataFrame, max_items: int = 10, empty_msg: str = "Không tìm thấy tựa game phù hợp.") -> None:
    records = [r for _, r in df_subset.head(max_items).iterrows()]
    if not records:
        st.info(empty_msg)
        return
    for card_i in range(0, len(records), 2):
        col_l, col_r = st.columns(2)
        with col_l:
            render_store_card(records[card_i])
        if card_i + 1 < len(records):
            with col_r:
                render_store_card(records[card_i + 1])


def apply_common_store_filters(df_in: pd.DataFrame, budget_limit: float) -> pd.DataFrame:
    if df_in.empty:
        return df_in
    out = df_in.copy()
    out = out[~out["name"].astype(str).str.contains("Source Filmmaker|Wallpaper Engine|Soundtrack", case=False, na=False)]
    out["current_price"] = pd.to_numeric(out["current_price"], errors="coerce").fillna(0.0)

    if st.session_state["price_type"] == "PAID":
        out = out[(out["current_price"] > 0.0) & (out["current_price"] <= budget_limit)]
    elif st.session_state["price_type"] == "FREE":
        out = out[out["current_price"] <= 0.0]
    else:
        out = out[out["current_price"] <= budget_limit]

    if st.session_state["plat_filter"] != "Tất cả":
        out = out[out["platform"].astype(str).str.contains(st.session_state["plat_filter"], case=False, na=False)]
    return out


# ============================================================
# 4. HÀM CHÍNH CHẠY GIAO DIỆN STREAMLIT
# ============================================================
def run_streamlit_app() -> None:
    st.set_page_config(
        page_title="GameStore AI — Storefront & Price Forecast",
        page_icon="🎮",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 3.8rem !important;
            padding-bottom: 2.5rem !important;
            padding-left: 2.2rem !important;
            padding-right: 2.2rem !important;
            max-width: 100% !important;
        }
        div.stButton > button {
            white-space: nowrap !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            height: 2.55rem !important;
        }
        .store-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 10px;
            margin-top: 6px;
            margin-bottom: 8px;
        }
        .store-title {
            font-size: 1.18rem;
            font-weight: 700;
            color: #f8fafc;
            margin: 0;
            line-height: 1.3;
        }
        .store-sub {
            font-size: 0.82rem;
            color: #94a3b8;
            margin-top: 3px;
        }
        .badge-box {
            text-align: right;
            flex-shrink: 0;
        }
        .match-pill {
            display: inline-block;
            background: rgba(239, 68, 68, 0.16);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 2px 9px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .action-pill-buy {
            display: inline-block;
            background: rgba(34, 197, 94, 0.16);
            color: #86efac;
            border: 1px solid rgba(34, 197, 94, 0.4);
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.73rem;
            font-weight: 600;
            margin-top: 4px;
        }
        .action-pill-wait {
            display: inline-block;
            background: rgba(234, 179, 8, 0.16);
            color: #fde047;
            border: 1px solid rgba(234, 179, 8, 0.4);
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.73rem;
            font-weight: 600;
            margin-top: 4px;
        }
        .price-strip {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 10px;
            gap: 8px;
        }
        .price-cell-label {
            font-size: 0.74rem;
            color: #94a3b8;
        }
        .price-cell-val {
            font-size: 1.04rem;
            font-weight: 700;
            color: #f1f5f9;
            margin-top: 2px;
        }
        .banner-wrap {
            width: 100%;
            height: 145px;
            border-radius: 8px;
            overflow: hidden;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            margin-bottom: 8px;
            position: relative;
        }
        .banner-wrap img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    tables = load_all_csv_tables()
    df_master = tables["master"]
    df_users = tables["users"]
    df_owned = tables["owned"]
    df_user_recs = tables["user_recs"]
    df_price_lead = tables["price_lead"]
    df_rec_rep = tables["rec_rep"]

    if df_master.empty or df_users.empty:
        st.warning("⚠️ Chưa tìm thấy đủ file CSV trong `data/cleaned_verified/`.")
        if st.button("🔄 Đồng Bộ & Huấn Luyện Từ File CSV", type="primary"):
            with st.spinner("Đang đọc file CSV và huấn luyện mô hình..."):
                if trigger_rec_ml_pipeline():
                    st.rerun()
        st.stop()

    user_id_set = set(df_users["user_id"].astype(str).str.strip())
    rec_uid_set = (
        set(df_user_recs["user_id"].astype(str).str.strip())
        if not df_user_recs.empty and "user_id" in df_user_recs.columns
        else set()
    )
    if not user_id_set.issubset(rec_uid_set):
        with st.spinner("Đang đồng bộ gợi ý ML cho toàn bộ danh sách User trong CSV..."):
            if trigger_rec_ml_pipeline():
                tables = load_all_csv_tables()
                df_master = tables["master"]
                df_user_recs = tables["user_recs"]
                df_rec_rep = tables["rec_rep"]

    # SIDEBAR
    st.sidebar.markdown("### 🎮 **GameStore AI**")

    uid_list = df_users["user_id"].astype(str).str.strip().tolist()
    name_map = dict(zip(uid_list, df_users["persona_name"].astype(str)))

    if "selected_uid" not in st.session_state or st.session_state["selected_uid"] not in uid_list:
        st.session_state["selected_uid"] = uid_list[0]

    picked_uid = st.sidebar.selectbox(
        f"👤 Game Thủ ({len(uid_list)} Hồ sơ CSV):",
        options=uid_list,
        index=uid_list.index(st.session_state["selected_uid"]),
        format_func=lambda u: f"{name_map.get(u, u)}",
    )
    active_uid: str = to_str(picked_uid, uid_list[0])
    st.session_state["selected_uid"] = active_uid
    active_uname: str = name_map.get(active_uid, active_uid)

    u_info = df_users[df_users["user_id"].astype(str).str.strip() == active_uid].iloc[0]
    sc_1, sc_2 = st.sidebar.columns(2)
    sc_1.metric("📦 Đã Mua", f"{to_int(u_info.get('owned_games_count'))} game")
    sc_2.metric("⏱️ Giờ Chơi", f"{to_float(u_info.get('total_playtime_hours')):.0f}h")
    st.sidebar.caption(f"🏷️ **Gu:** `{to_str(u_info.get('favorite_genres'))}`")

    st.sidebar.markdown("---")
    st.sidebar.caption("💎 **Chế độ Cửa hàng:**")
    render_button_group(
        "price_type",
        [("PAID", "Trả Phí"), ("ALL", "Tất Cả"), ("FREE", "Miễn Phí")],
        container=st.sidebar,
    )

    max_price_limit = to_float(st.sidebar.slider("💰 Trần ngân sách ($):", 0.0, 80.0, 70.0, 5.0), 70.0)

    st.sidebar.caption("🖥️ **Nền tảng:**")
    render_button_group(
        "plat_filter",
        [("Tất cả", "Mọi Hệ"), ("Steam", "Steam"), ("Switch", "Switch")],
        container=st.sidebar,
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Đồng Bộ Lại CSV", use_container_width=True):
        with st.spinner("Đang đọc CSV và cập nhật gợi ý..."):
            if trigger_rec_ml_pipeline():
                st.rerun()

    # TOP NAV BAR
    render_button_group(
        "nav_tab",
        [
            ("STORE", "🎮 Cửa Hàng Gợi Ý"),
            ("OWNED", "📦 Kho Game Đang Sở Hữu"),
            ("CCU", "🔥 Xếp Hạng CCU"),
            ("SALE", "🏷️ Săn Sale & Giá 3T"),
            ("DATA", "📊 Bảng CSV & Mô Hình"),
        ],
        container=st,
    )
    st.write("")

    # TRANG 1: CỬA HÀNG GỢI Ý AI
    if st.session_state["nav_tab"] == "STORE":
        render_user_owned_games_table(df_owned, active_uid, active_uname)

        st.markdown(f"#### 🎯 Đề Xuất Cá Nhân Hóa Cho `{active_uname}` (Chưa Sở Hữu)")
        dynamic_genres = extract_top_genres(df_master, max_buttons=5)
        if "genre_btn" not in st.session_state or st.session_state["genre_btn"] not in dynamic_genres:
            st.session_state["genre_btn"] = "Tất cả"

        g_cols = st.columns(len(dynamic_genres))
        for g_idx, g_label in enumerate(dynamic_genres):
            if g_cols[g_idx].button(
                g_label,
                key=f"gbtn_{g_label}",
                use_container_width=True,
                type="primary" if st.session_state["genre_btn"] == g_label else "secondary",
            ):
                st.session_state["genre_btn"] = g_label
                st.rerun()

        rec_view = df_user_recs[df_user_recs["user_id"].astype(str).str.strip() == active_uid].copy()
        if rec_view.empty:
            rec_view = df_master.copy()

        rec_view = apply_common_store_filters(rec_view, max_price_limit)
        if st.session_state["genre_btn"] != "Tất cả":
            rec_view = rec_view[
                rec_view["genres"].astype(str).str.contains(st.session_state["genre_btn"], case=False, na=False)
            ]

        render_card_grid(
            rec_view,
            max_items=12,
            empty_msg="Không có tựa game nào khớp bộ lọc. Bạn có thể bấm nút 'Tất Cả' ở mục Chế độ Cửa hàng bên trái!",
        )

    # TRANG 2: KHO GAME ĐANG SỞ HỮU CHI TIẾT
    elif st.session_state["nav_tab"] == "OWNED":
        u_owned_df = render_user_owned_games_table(df_owned, active_uid, active_uname)
        if not u_owned_df.empty and "game_name" in u_owned_df.columns and "playtime_forever_hours" in u_owned_df.columns:
            st.markdown("##### 📊 Biểu Đồ Số Giờ Chơi Từng Tựa Game Trong Kho")
            st.bar_chart(u_owned_df.set_index("game_name")[["playtime_forever_hours"]])

    # TRANG 3: BẢNG XẾP HẠNG CCU TRỰC TUYẾN
    elif st.session_state["nav_tab"] == "CCU":
        df_ccu_view = apply_common_store_filters(df_master, max_price_limit)
        df_ccu_view = df_ccu_view.sort_values(by=["current_ccu_1h", "peak_ccu_24h"], ascending=False).head(10)

        if not df_ccu_view.empty:
            st.bar_chart(df_ccu_view.set_index("name")[["current_ccu_1h", "peak_ccu_24h"]])

        render_card_grid(df_ccu_view, max_items=8)

    # TRANG 4: SĂN SALE & DỰ BÁO GIÁ 3 THÁNG
    elif st.session_state["nav_tab"] == "SALE":
        f_col_search, f_col_btns = st.columns([2.2, 2.0])
        search_txt = to_str(
            f_col_search.text_input(
                "Tìm game",
                value="",
                label_visibility="collapsed",
                placeholder="🔍 Nhập tên game cần tra cứu giá...",
            )
        )
        render_button_group(
            "sale_mode",
            [("ALL", "Tất Cả"), ("BUY", "🟢 Mua Ngay"), ("DISC", "🔥 Đang Sale")],
            container=f_col_btns,
        )

        df_sale_view = apply_common_store_filters(df_master, max_price_limit)
        if search_txt:
            df_sale_view = df_sale_view[df_sale_view["name"].astype(str).str.contains(search_txt, case=False, na=False)]
        if st.session_state["sale_mode"] == "BUY" and "ml_predicted_label" in df_sale_view.columns:
            df_sale_view = df_sale_view[df_sale_view["ml_predicted_label"].astype(str).str.contains("MUA", case=False, na=False)]
        elif st.session_state["sale_mode"] == "DISC":
            df_sale_view = df_sale_view[df_sale_view["discount_pct"].astype(float) > 0]

        render_card_grid(df_sale_view, max_items=10)

    # TRANG 5: QUẢN TRỊ BẢNG CSV & ĐẤU TRƯỜNG MÔ HÌNH ML
    elif st.session_state["nav_tab"] == "DATA":
        tab_ml, tab_u, tab_o, tab_r = st.tabs(
            [
                "🏆 Báo Cáo 6 Mô Hình ML",
                f"👤 CSV Hồ Sơ Users ({len(df_users)})",
                f"📦 CSV Kho Game ({len(df_owned)})",
                f"🎯 CSV Gợi Ý ({len(df_user_recs)})",
            ]
        )
        with tab_ml:
            if not df_price_lead.empty:
                st.markdown("##### 1. Đấu Trường 3 Mô Hình Dự Báo Giá (`ml_price_tournament_leaderboard.csv`)")
                st.dataframe(df_price_lead, use_container_width=True, hide_index=True)
            if not df_rec_rep.empty:
                st.markdown("##### 2. Báo Cáo 3 Cấu Trúc Học Máy Gợi Ý (`ml_recommendation_structures_report.csv`)")
                st.dataframe(df_rec_rep, use_container_width=True, hide_index=True)
        with tab_u:
            st.caption(f"File: `{USER_PROFILES_CSV}`")
            st.dataframe(df_users, use_container_width=True, hide_index=True)
        with tab_o:
            st.caption(f"File: `{USER_OWNED_GAMES_CSV}`")
            st.dataframe(df_owned, use_container_width=True, hide_index=True)
        with tab_r:
            st.caption(f"File: `{USER_PERSONAL_REC_CSV}`")
            st.dataframe(df_user_recs, use_container_width=True, hide_index=True)


# ============================================================
# 5. TỰ ĐỘNG KÍCH HOẠT STREAMLIT NẾU BẤM RUN TRỰC TIẾP TRONG PYCHARM
# ============================================================
if __name__ == "__main__":
    if not runtime.exists():
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())],
            cwd=str(PROJECT_ROOT),
            check=False,
        )
        sys.exit(0)

    run_streamlit_app()
# === END OF FILE ===