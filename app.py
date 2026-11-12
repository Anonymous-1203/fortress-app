import streamlit as st
import pandas as pd
import yfinance as yf
import unicodedata
import json
import os

st.set_page_config(page_title="Fortress Value Investor", layout="wide")

st.title("◆株式投資 高配当シミュレーター β版◆")
st.write("")

st.markdown("""
<style>
@media (min-width: 769px) {
    .st-key-mobile_selector_area,
    .st-key-mobile_search_area {
        display: none !important;
    }
}
@media (max-width: 768px) {
    [data-testid="stDataFrame"],
    .st-key-del_selected_btn,
    .st-key-list_header_area,
    .st-key-pc_search_area,
    .st-key-pc_title_area {
        display: none !important;
    }
}
</style>
""", unsafe_allow_html=True)

# 最大監視銘柄数の設定
MAX_WATCH_LIST = 50
DEFAULT_WATCH_LIST = ["7011", "7202", "8306", "5401", "7201", "4980", "2914", "8001", "9104", "8411"]
DEFAULT_YOC = 5.0

# --- URLパラメータへの自動保存関数 ---
def sync_url_params():
    st.query_params["codes"] = ",".join(st.session_state.watch_list)
    if "target_yoc_val" in st.session_state:
        st.query_params["yoc"] = f"{st.session_state.target_yoc_val:.1f}"

# --- 文字列の正規化 ---
def normalize_text(text):
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize('NFKC', text).lower().strip()

# --- ローカルJSON（jpx_master.json）のロード ---
@st.cache_data(ttl=86400)
def load_jpx_official_master():
    json_path = "jpx_master.json"
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if len(data) > 0 else None
    except Exception:
        return None

JAPANESE_MASTER = load_jpx_official_master()

if JAPANESE_MASTER is None:
    st.error("⚠️ 銘柄マスターファイル `jpx_master.json` が見つかりません。")
    st.info("ターミナルで `python generate_jpx_master.py` を実行してください。")
    st.stop()

JAPANESE_NAMES = {code: info["name"] if isinstance(info, dict) else info for code, info in JAPANESE_MASTER.items()}

# --- セッション状態の初期化（URLパラメータ優先復元） ---
if "watch_list" not in st.session_state:
    if "codes" in st.query_params:
        parsed = [c.strip() for c in st.query_params["codes"].split(",") if c.strip().isdigit() and len(c.strip()) == 4]
        unique_codes = list(dict.fromkeys(parsed))[:MAX_WATCH_LIST]
        st.session_state.watch_list = unique_codes if unique_codes else list(DEFAULT_WATCH_LIST)
    else:
        st.session_state.watch_list = list(DEFAULT_WATCH_LIST)

if "target_yoc_val" not in st.session_state:
    if "yoc" in st.query_params:
        try:
            st.session_state.target_yoc_val = max(3.0, min(10.0, round(float(st.query_params["yoc"]), 1)))
        except ValueError:
            st.session_state.target_yoc_val = DEFAULT_YOC
    else:
        st.session_state.target_yoc_val = DEFAULT_YOC

if "focused_code" not in st.session_state:
    st.session_state.focused_code = st.session_state.watch_list[0] if st.session_state.watch_list else "7011"

sync_url_params()

# --- あいまい銘柄検索 ---
def search_ticker_candidates(query_str):
    norm_query = normalize_text(query_str)
    if not norm_query:
        return []
    
    candidates = {}
    if norm_query.isdigit() and len(norm_query) == 4:
        name = JAPANESE_NAMES.get(norm_query, f"東証銘柄 {norm_query}")
        candidates[norm_query] = f"{norm_query} {name}"
        return list(candidates.values())

    count = 0
    for code, name in JAPANESE_NAMES.items():
        norm_name = normalize_text(name)
        if norm_query in norm_name or norm_query in code:
            candidates[code] = f"{code} {name}"
            count += 1
            if count >= 30:
                break
                
    return list(candidates.values())

# --- データ取得関数 ---
@st.cache_data(ttl=900)
def fetch_stock_data(ticker_code):
    try:
        clean_code = ticker_code.strip()
        symbol = f"{clean_code}.T"
        ticker = yf.Ticker(symbol)
        info = ticker.info

        meta = JAPANESE_MASTER.get(clean_code, {})
        name = meta.get("name") if isinstance(meta, dict) else info.get("shortName") or f"銘柄 {clean_code}"
        sector = meta.get("sector", "不明") if isinstance(meta, dict) else "不明"
        market = meta.get("market", "不明") if isinstance(meta, dict) else "不明"

        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0
        bps = info.get("bookValue") or 0
        dps = info.get("dividendRate") or 0
        pbr = info.get("priceToBook") or (price / bps if bps > 0 else 0)

        # ROEの取得（直接取れない場合は EPS ÷ BPS で自動補完）
        raw_roe = info.get("returnOnEquity")
        eps = info.get("trailingEps") or 0
        if raw_roe is not None:
            roe = float(raw_roe * 100)
        elif eps != 0 and bps > 0:
            roe = float((eps / bps) * 100)
        else:
            roe = 0.0

        payout_ratio = float(info.get("payoutRatio", 0) * 100) if info.get("payoutRatio") else 0.0
        current_yield = (dps / price * 100) if price > 0 else 0.0

        return {
            "code": clean_code,
            "name": name,
            "sector": sector,
            "market": market,
            "price": float(price),
            "current_yield": round(current_yield, 2),
            "bps": float(bps),
            "dps": float(dps),
            "roe": round(roe, 1),
            "pbr": float(pbr),
            "payout_ratio": round(payout_ratio, 1)
        }
    except Exception:
        return None

# --- シンプル条件チェック ---
def evaluate_stock_signals(row):
    signals = []
    all_clear = True

    if row["pbr"] < 0.8:
        signals.append(f"✅ **PBR {row['pbr']:.2f}倍**（0.8倍未満・超割安）")
    elif row["pbr"] < 1.0:
        signals.append(f"✅ **PBR {row['pbr']:.2f}倍**（1.0倍割れ・割安）")
    else:
        signals.append(f"⚠️ **PBR {row['pbr']:.2f}倍**（1.0倍以上）")
        all_clear = False

    if row["roe"] >= 8.0:
        signals.append(f"✅ **ROE {row['roe']:.1f}%**（8%以上・高収益）")
    elif row["roe"] >= 5.0:
        signals.append(f"⚠️ **ROE {row['roe']:.1f}%**（標準水準）")
        all_clear = False
    else:
        signals.append(f"🚨 **ROE {row['roe']:.1f}%**（稼ぐ力が弱い）")
        all_clear = False

    if 0 < row["payout_ratio"] <= 50.0:
        signals.append(f"✅ **配当性向 {row['payout_ratio']:.1f}%**（増配・自社株買い余力あり）")
    elif 50.0 < row["payout_ratio"] <= 80.0:
        signals.append(f"⚠️ **配当性向 {row['payout_ratio']:.1f}%**（標準的な配当負担）")
    elif row["payout_ratio"] > 80.0:
        signals.append(f"🚨 **配当性向 {row['payout_ratio']:.1f}%**（高負担・減配リスク注意）")
        all_clear = False
    else:
        signals.append(f"⚪ **配当性向 {row['payout_ratio']:.1f}%**（無配またはデータなし）")
        all_clear = False

    return all_clear, signals

# --- メイン2カラム分割（PC：左＝詳細 / 右＝一覧、スマホ：上＝詳細 / 下＝一覧） ---
col_detail, col_list = st.columns([1, 2.3], gap="large")

# 1. 左カラム上部：目標利回りスライダー（計算前に値確定）
with col_detail:
    st.subheader("🎯 目標 配当利回り / YOC (%)")
    target_yoc = st.slider(
        "目標 配当利回り / YOC (%)",
        min_value=3.0,
        max_value=10.0,
        value=st.session_state.target_yoc_val,
        step=0.1,
        label_visibility="collapsed",
        key="yoc_slider",
        on_change=lambda: (st.session_state.update({"target_yoc_val": st.session_state.yoc_slider}), sync_url_params())
    )
    st.write("")

# 2. 右カラム上部：銘柄検索・追加（PC表示用）
with col_list:
    with st.container(key="pc_search_area"):
        search_query = st.text_input("🔍 銘柄検索・追加（企業名や4桁コードを入力）", key="search_query_input", placeholder="例: トヨタ / 7203")

        if search_query:
            found_candidates = search_ticker_candidates(search_query)
            if found_candidates:
                col_s1, col_s2 = st.columns([3, 1])
                with col_s1:
                    selected_cand = st.selectbox(f"👇 該当候補 ({len(found_candidates)}件) から選択", options=found_candidates, key="pc_cand_select")
                with col_s2:
                    st.write("")
                    st.write("")
                    is_full = len(st.session_state.watch_list) >= MAX_WATCH_LIST
                    if st.button("➕ リストに追加", key="pc_add_btn", use_container_width=True, disabled=is_full):
                        target_code = selected_cand.split(" ")[0]
                        if target_code not in st.session_state.watch_list:
                            st.session_state.watch_list.append(target_code)
                            st.session_state.focused_code = target_code
                            sync_url_params()
                            st.success(f"追加しました: {selected_cand}")
                            st.rerun()
                if is_full:
                    st.warning(f"⚠️ 監視リストの上限（{MAX_WATCH_LIST}銘柄）に達しています。不要な銘柄を削除してから追加してください。")

# 3. 全銘柄データの取得と計算
stock_list = []
with st.spinner("監視リストの最新財務データを解析中..."):
    for code in list(st.session_state.watch_list):
        data = fetch_stock_data(code)
        if data and data["price"] > 0:
            stock_list.append(data)

if stock_list:
    df = pd.DataFrame(stock_list)
    df["final_target_price"] = (df["dps"] / (target_yoc / 100)).round(1)
    df["diff_yen"] = (df["final_target_price"] - df["price"]).round(1)
    df["margin_of_safety_%"] = (((df["final_target_price"] - df["price"]) / df["price"]) * 100).round(1)
    df["pbr"] = df["pbr"].round(2)

    df["safety_display"] = df.apply(
        lambda r: "無配" if r["dps"] <= 0 else (
            f"🎯 +{r['margin_of_safety_%']:.1f}% (買いゾーン)" if r["margin_of_safety_%"] >= 0 else f"⏳ {r['margin_of_safety_%']:.1f}% (待機)"
        ),
        axis=1
    )

    eval_results = [evaluate_stock_signals(row) for _, row in df.iterrows()]
    df["all_clear"] = [er[0] for er in eval_results]
    df["signals"] = [er[1] for er in eval_results]

    column_mapping = {
        "code": "銘柄コード",
        "name": "企業名",
        "sector": "業種",
        "price": "現在株価",
        "current_yield": "利回り(%)",
        "pbr": "PBR(倍)",
        "roe": "ROE(%)",
        "payout_ratio": "配当性向(%)",
        "final_target_price": "ターゲット株価",
        "safety_display": "安全域乖離率"
    }

    # 4. 右カラム下部：監視ターゲット一覧テーブル
    with col_list:
        display_cols = list(column_mapping.keys())
        display_df = df[display_cols].rename(columns=column_mapping)

        col_title, col_refresh_btn, col_del_btn = st.columns([2.0, 1.0, 1.0])
        with col_title:
            with st.container(key="list_header_area"):
                st.subheader(f"📊 監視ターゲット一覧 ({len(display_df)} / {MAX_WATCH_LIST} 銘柄)")
        with col_refresh_btn:
            st.write("")
            if st.button("🔄 株価を最新に更新", help="キャッシュをクリアして最新株価を再取得します（通常は15分ごとに自動更新）", use_container_width=True):
                fetch_stock_data.clear()
                st.rerun()

        event = st.dataframe(
            display_df,
            height=550,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode=["multi-row", "single-cell"]
        )

        selected_rows = event.selection.rows
        selected_cells = event.selection.cells

        if selected_cells:
            clicked_row_idx = selected_cells[0][0]
            if 0 <= clicked_row_idx < len(df):
                st.session_state.focused_code = df.iloc[clicked_row_idx]["code"]

        with col_del_btn:
            st.write("")
            btn_label = f"🗑️ 選択した {len(selected_rows)} 件を削除" if selected_rows else "🗑️ チェックした銘柄を削除"
            if st.button(btn_label, key="del_selected_btn", type="primary" if selected_rows else "secondary", disabled=not selected_rows, use_container_width=True):
                codes_to_remove = [df.iloc[idx]["code"] for idx in selected_rows]
                st.session_state.watch_list = [c for c in st.session_state.watch_list if c not in codes_to_remove]
                sync_url_params()
                st.rerun()

# 5. 左カラム下部：銘柄詳細パネル
    with col_detail:
        # スマホ専用：ドロップダウン切り替え＋削除ボタン
        with st.container(key="mobile_selector_area"):
            detail_options = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
            codes_list = df["code"].tolist()
            current_idx = codes_list.index(st.session_state.focused_code) if st.session_state.focused_code in codes_list else 0

            def on_mobile_select_change():
                st.session_state.focused_code = st.session_state.mobile_stock_select.split(" ")[0]

            col_sel, col_mdel = st.columns([4, 1])
            with col_sel:
                st.selectbox(
                    "表示銘柄を切り替え",
                    options=detail_options,
                    index=current_idx,
                    label_visibility="collapsed",
                    key="mobile_stock_select",
                    on_change=on_mobile_select_change
                )
            with col_mdel:
                if st.button("🗑️", key="mobile_del_btn", help="表示中の銘柄をリストから削除", disabled=len(st.session_state.watch_list) <= 1, use_container_width=True):
                    st.session_state.watch_list = [c for c in st.session_state.watch_list if c != st.session_state.focused_code]
                    st.session_state.focused_code = st.session_state.watch_list[0]
                    sync_url_params()
                    st.rerun()

        # スマホ専用：銘柄検索・追加エリア
        with st.container(key="mobile_search_area"):
            m_query = st.text_input("🔍 銘柄を追加（企業名 / 4桁コード）", key="mobile_search_input", placeholder="例: トヨタ / 7203")
            if m_query:
                m_cands = search_ticker_candidates(m_query)
                if m_cands:
                    m_sel = st.selectbox("候補を選択", options=m_cands, label_visibility="collapsed", key="mobile_cand_select")
                    is_full = len(st.session_state.watch_list) >= MAX_WATCH_LIST
                    if st.button("➕ この銘柄を追加", key="mobile_add_btn", use_container_width=True, disabled=is_full):
                        target_code = m_sel.split(" ")[0]
                        if target_code not in st.session_state.watch_list:
                            st.session_state.watch_list.append(target_code)
                            st.session_state.focused_code = target_code
                            sync_url_params()
                            st.rerun()
            st.divider()

        matched_df = df[df["code"] == st.session_state.focused_code]
        row = matched_df.iloc[0] if not matched_df.empty else df.iloc[0]

        # PC専用：銘柄名見出しのみ表示
        with st.container(key="pc_title_area"):
            st.markdown(f"### **{row['code']} {row['name']}**")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("現在株価", f"{int(row['price']):,} 円")
        with col_m2:
            st.metric("現在利回り", f"{row['current_yield']:.2f} %")

        with st.container(border=True):
            st.metric("🎯 ターゲット株価", f"{row['final_target_price']:,} 円", delta=f"{row['diff_yen']:,} 円")
        
        st.write("📋 **財務・指標チェック:**")
        for sig in row["signals"]:
            st.markdown(sig)
            
        if row['dps'] <= 0:
            st.info("⚪ **【無配銘柄】** 現在の年間配当予想が0円のため、ターゲット株価は算出対象外です。")
        elif row['margin_of_safety_%'] >= 0 and row['all_clear']:
            st.success("🏰 **【鉄壁の狙撃ゾーン】** 目標利回りに到達し、財務指標もすべて健全です。")
        elif row['margin_of_safety_%'] >= 0:
            st.info("⚠️ **【利回り達成・指標確認】** 目標利回りに到達しています。⚠️/🚨の項目を確認してください。")
        else:
            st.warning(f"⏳ **【要待機】** 目標株価まで あと {abs(row['diff_yen']):,} 円 ({abs(row['margin_of_safety_%'])}%) 下落を待ちます。")

        # （既存の黄色い判定メッセージ：st.warning や st.success などのブロックの直下）
        st.write("")
        st.caption("🔗 外部サイトで最新決算・配当予想を確認：")
        code_str = str(row['code'])
        col_link1, col_link2, col_link3 = st.columns(3)
        with col_link1:
            st.link_button("Yahoo!ファイナンス", f"https://finance.yahoo.co.jp/quote/{code_str}.T", use_container_width=True)
        with col_link2:
            st.link_button("株探 (Kabutan)", f"https://kabutan.jp/stock/?code={code_str}", use_container_width=True)
        with col_link3:
            st.link_button("IR BANK", f"https://irbank.net/{code_str}", use_container_width=True)

st.divider()
st.caption("※ 本ツールの財務・配当データは外部API（Yahoo! Finance）を参照しているため、株式分割や決算発表の反映ラグ等により国内証券会社の予想値と差異が生じる場合があります。最終的な投資判断・発注の際は、必ず証券会社の最新情報をご確認ください。")