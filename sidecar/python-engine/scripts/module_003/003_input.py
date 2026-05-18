from __future__ import annotations

import streamlit as st

FILL_OPTIONS = ["藍色", "紅色", "綠色", "黑色", "橙色", "紫色"]
BG_OPTIONS = ["白色", "淺灰", "深色"]
FIT_MAX_GAP_PX = 20


def render_input() -> dict:
    mode = st.radio(
        "生成模式",
        ["不規則邊框", "藍框貼合測試"],
        index=1,
        horizontal=True,
        help="不規則邊框：生成可控粗糙度的填色邊框。藍框貼合測試：生成藍色矩形框 + 黑色邊緣，用於 frame_fit_score 分析。",
    )

    if mode == "藍框貼合測試":
        return _render_fit_test_input()

    # ── 不規則邊框模式 ─────────────────────────────────────────
    # ── 影像規格 ──────────────────────────────────────────────
    st.subheader(":material/image: 影像規格")

    col1, col2 = st.columns(2)
    with col1:
        width = st.slider("寬度 (px)", 100, 800, 400, step=10)
    with col2:
        height = st.slider("高度 (px)", 100, 600, 250, step=10)

    col3, col4 = st.columns(2)
    with col3:
        fill_color = st.selectbox("填色", FILL_OPTIONS, index=FILL_OPTIONS.index("黑色"))
    with col4:
        bg_color = st.selectbox("背景色", BG_OPTIONS, index=0)

    st.divider()

    # ── 邊緣生成 ──────────────────────────────────────────────
    st.subheader(":material/texture: 邊緣生成")

    # 左欄：左邊粗糙度；右欄：label + symmetry checkbox 並排，下方 slider 或提示
    col5, col6 = st.columns(2)
    with col5:
        left_roughness = st.slider("左邊粗糙度", 0, 80, 15, help="0 = 平整，80 = 極度不規則")
    with col6:
        # nested columns：讓「右邊粗糙度」label 與 checkbox 視覺上同一行
        label_col, check_col = st.columns([3, 2])
        with label_col:
            st.markdown("**右邊粗糙度**")
        with check_col:
            symmetry = st.checkbox("同左", value=False, help="勾選後右邊鏡射左邊", key="symmetry")
        if symmetry:
            right_roughness = left_roughness
            st.caption(f"鏡射左側：{left_roughness}")
        else:
            right_roughness = st.slider(
                "右邊粗糙度",
                0, 80, 15,
                label_visibility="collapsed",
            )

    # frequency / intensity 配對成 2 欄一行
    col7, col8 = st.columns(2)
    with col7:
        frequency = st.slider(
            "凹凸頻率",
            min_value=1,
            max_value=200,
            value=5,
            help="低 = 少個大波浪，高 = 多個細密鋸齒（100+ 為超高頻）",
        )
    with col8:
        intensity = st.slider(
            "縮進強度 (%)",
            min_value=1,
            max_value=49,
            value=33,
            help="凹凸最深能咬進寬度的百分比（1% = 幾乎不縮，49% = 快咬到中心）",
        )

    # seed 在邊緣生成 section 底部全寬
    seed = st.slider("隨機種子", 0, 99, 0, help="相同種子 + 相同參數 → 相同形狀")

    return {
        "mode": "不規則邊框",
        "width": width,
        "height": height,
        "left_roughness": left_roughness,
        "right_roughness": right_roughness,
        "frequency": frequency,
        "intensity": intensity,
        "symmetry": symmetry,
        "fill_color": fill_color,
        "bg_color": bg_color,
        "seed": seed,
    }


def _render_fit_test_input() -> dict:
    # ── 影像規格 ──────────────────────────────────────────────
    st.subheader(":material/image: 影像規格")
    col1, col2 = st.columns(2)
    with col1:
        width = st.slider("寬度 (px)", 200, 800, 400, step=10, key="fit_width")
    with col2:
        height = st.slider("高度 (px)", 100, 600, 250, step=10, key="fit_height")

    col3, col4 = st.columns(2)
    with col3:
        frame_margin = st.slider(
            "黑邊寬度 (px)",
            min_value=20, max_value=150, value=50,
            help="黑色區塊從圖像邊緣往內延伸的基準寬度，同時決定藍框位置",
            key="fit_frame_margin",
        )
    with col4:
        frame_thickness = st.slider(
            "藍框粗細 (px)", min_value=1, max_value=10, value=3,
            key="fit_frame_thickness",
        )

    st.divider()

    # ── 鋸齒邊緣 ──────────────────────────────────────────────
    st.subheader(":material/texture: 鋸齒邊緣")

    col5, col6 = st.columns(2)
    with col5:
        roughness = st.slider("粗糙度", 0, 80, 40, help="0=平整, 80=極度不規則", key="fit_roughness")
    with col6:
        label_col, check_col = st.columns([3, 2])
        with label_col:
            st.markdown("**右邊粗糙度**")
        with check_col:
            symmetry = st.checkbox("同左", value=True, key="fit_symmetry")
        if symmetry:
            right_roughness = roughness
            st.caption(f"鏡射左側：{roughness}")
        else:
            right_roughness = st.slider(
                "右邊粗糙度", 0, 80, 15,
                label_visibility="collapsed", key="fit_right_roughness",
            )

    col7, col8, col9 = st.columns(3)
    with col7:
        frequency = st.slider("凹凸頻率", 1, 200, 5, key="fit_frequency")
    with col8:
        intensity = st.slider(
            "鋸齒深度 (%)", 1, 49, 40,
            help="貼合偏移為 0 時鋸齒深度會歸零；越接近 -1 或 1，鋸齒越接近此設定。",
            key="fit_intensity",
        )
    with col9:
        seed = st.slider("隨機種子", 0, 99, 0, key="fit_seed")

    st.divider()

    # ── 貼合偏移 ──────────────────────────────────────────────
    st.subheader(":material/rule: 貼合偏移")
    fit_offset_score = st.slider(
        "貼合偏移",
        min_value=-1.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        format="%.2f",
        help="-1.00 = 內縮極不重合；0.00 = 完美重合；1.00 = 外突極不重合。",
        key="fit_offset_score",
    )
    offset_px = int(round(fit_offset_score * FIT_MAX_GAP_PX))
    direction = "內縮" if offset_px < 0 else ("外突" if offset_px > 0 else "重合")
    left_offset = offset_px
    right_offset = offset_px
    st.metric("對應邊緣偏移", f"{offset_px:+d}px（{direction}）")

    return {
        "mode":            "藍框貼合測試",
        "width":           width,
        "height":          height,
        "frame_margin":    frame_margin,
        "frame_thickness": frame_thickness,
        "left_offset":     left_offset,
        "right_offset":    right_offset,
        "fit_offset_score": fit_offset_score,
        "fit_gap_px":      abs(offset_px),
        "fit_direction":   direction,
        "roughness":       roughness,
        "right_roughness": right_roughness,
        "frequency":       frequency,
        "intensity":       intensity,
        "seed":            seed,
    }
