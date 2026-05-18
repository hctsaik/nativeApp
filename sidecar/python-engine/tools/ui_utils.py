from __future__ import annotations

import base64
import uuid
from pathlib import Path

import cv2
import numpy as np
import streamlit.components.v1 as components


def show_image(
    source: np.ndarray | Path | str,
    caption: str = "",
    height: int = 480,
) -> None:
    """Responsive image with click-to-enlarge lightbox.

    source: RGB ndarray, or a file path (Path / str).
    caption: optional label shown below the thumbnail.
    height: initial iframe height (px); JS resizes to actual content after load.
    """
    if isinstance(source, np.ndarray):
        bgr = cv2.cvtColor(source, cv2.COLOR_RGB2BGR) if source.ndim == 3 else source
        _, buf = cv2.imencode(".png", bgr)
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    else:
        b64 = base64.b64encode(Path(source).read_bytes()).decode("ascii")

    uid = uuid.uuid4().hex[:8]
    cap_html = f'<p class="cap">{caption}</p>' if caption else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ overflow: hidden; background: transparent; }}
.wrap {{ cursor: zoom-in; position: relative; display: block; line-height: 0; }}
.wrap img.thumb {{ max-width: 100%; height: auto; display: block; border-radius: 4px; }}
.hint {{
  position: absolute; bottom: 6px; right: 8px;
  background: rgba(0,0,0,.6); color: #fff;
  font-size: 11px; padding: 2px 7px; border-radius: 3px;
  opacity: 0; transition: opacity .15s; pointer-events: none; line-height: 1.5;
}}
.wrap:hover .hint {{ opacity: 1; }}
.cap {{ color: #555; font-size: 12px; margin-top: 6px; line-height: 1.4; }}
.ov {{
  display: none; position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.88); cursor: zoom-out;
  align-items: center; justify-content: center;
}}
.ov.open {{ display: flex; }}
.ov-img {{ max-width: 96vw; max-height: 96vh; object-fit: contain; border-radius: 4px; cursor: default; }}
.close-btn {{
  position: fixed; top: 12px; right: 16px; color: #fff;
  font-size: 20px; cursor: pointer; line-height: 1;
  background: rgba(0,0,0,.45); border-radius: 50%;
  width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
}}
</style>
</head><body>
<div class="wrap" onclick="document.getElementById('ov{uid}').classList.add('open')">
  <img class="thumb" id="thumb{uid}" src="data:image/png;base64,{b64}"/>
  <span class="hint">&#128269; 放大</span>
</div>
{cap_html}
<div id="ov{uid}" class="ov" onclick="this.classList.remove('open')">
  <div class="close-btn" onclick="event.stopPropagation();document.getElementById('ov{uid}').classList.remove('open')">&#10005;</div>
  <img class="ov-img" src="data:image/png;base64,{b64}" onclick="event.stopPropagation()"/>
</div>
<script>
  var thumb = document.getElementById('thumb{uid}');
  function autoResize() {{
    var h = document.body.scrollHeight + 4;
    window.parent.postMessage({{ type: 'streamlit:setFrameHeight', height: h }}, '*');
  }}
  thumb.addEventListener('load', autoResize);
  if (thumb.complete) autoResize();
</script>
</body></html>"""

    components.html(html, height=height, scrolling=False)
