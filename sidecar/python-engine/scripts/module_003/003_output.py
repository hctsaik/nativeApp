from __future__ import annotations

import base64

import streamlit as st


def render_output(result: dict) -> None:
    img_bytes = base64.b64decode(result["image_b64"])

    if result.get("mode") == "藍框貼合測試":
        lo = result.get("left_offset",  0)
        ro = result.get("right_offset", 0)
        def _offset_label(v: int) -> str:
            return f"+{v}px（突出）" if v > 0 else (f"{v}px（內縮）" if v < 0 else "0px（完美）")
        st.metric("貼合偏移", f"{float(result.get('fit_offset_score', 0.0)):.2f}")
        st.caption(
            f"{result['width']} × {result['height']} px　｜　"
            f"黑邊寬度：{result.get('frame_margin')} px　藍框粗細：{result.get('frame_thickness')} px"
        )
        st.caption(
            f"偏差方向：{result.get('fit_direction', '重合')}　偏差量：{result.get('fit_gap_px', 0)} px　｜　"
            f"左偏差：{_offset_label(lo)}　右偏差：{_offset_label(ro)}　｜　"
            f"粗糙度 L{result.get('roughness')}/R{result.get('right_roughness')}　"
            f"頻率：{result.get('frequency')}　深度：{result.get('intensity')}%　種子：{result.get('seed')}"
        )
        fname = f"fit_offset_{float(result.get('fit_offset_score', 0.0)):.2f}_r{result.get('roughness')}_s{result.get('seed')}.png"
    else:
        sym_label = "是" if result.get("symmetry") else "否"
        st.caption(
            f"{result['width']} × {result['height']} px　｜　"
            f"左粗糙度：{result['left_roughness']}　右粗糙度：{result['right_roughness']}　｜　"
            f"頻率：{result['frequency']}　對稱：{sym_label}　｜　"
            f"填色：{result['fill_color']}　背景：{result['bg_color']}　｜　種子：{result['seed']}"
        )
        st.caption(
            f"梯度方向變異：{result.get('gradient_dir_variance', '—')}　｜　"
            f"PSD 高頻能量比：{result.get('psd_energy_ratio', '—')}"
        )
        fname = f"shape_r{result['left_roughness']}-{result['right_roughness']}_f{result['frequency']}_s{result['seed']}.png"

    st.image(img_bytes, use_container_width=False)

    st.download_button(
        label="下載 PNG",
        data=img_bytes,
        file_name=fname,
        mime="image/png",
        icon=":material/download:",
    )
