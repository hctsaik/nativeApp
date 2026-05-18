from __future__ import annotations

import base64
import hashlib

import streamlit.components.v1 as components

# ── lightbox overlay injected once into the parent Streamlit page ────────────
_LIGHTBOX_SETUP = """<script>
(function(){
  try {
    var P = window.parent;
    if (P.__cimLbReady) return;
    P.__cimLbReady = true;

    // styles
    var s = P.document.createElement('style');
    s.textContent = [
      '#cim-lb{display:none;position:fixed;top:0;left:0;right:0;bottom:0;',
      'background:rgba(0,0,0,.88);z-index:2147483647;',
      'align-items:center;justify-content:center;cursor:zoom-out;}',
      '#cim-lb.open{display:flex;}',
      '#cim-lb img{max-width:92vw;max-height:92vh;border-radius:8px;',
      'box-shadow:0 20px 60px rgba(0,0,0,.6);object-fit:contain;}',
      '#cim-lb .x{position:fixed;top:16px;right:22px;color:rgba(255,255,255,.8);',
      'font-size:32px;line-height:1;cursor:pointer;user-select:none;font-family:sans-serif;}'
    ].join('');
    P.document.head.appendChild(s);

    // overlay div
    var d = P.document.createElement('div');
    d.id = 'cim-lb';
    d.innerHTML = '<span class="x">&#x2715;</span><img id="cim-lb-img"/>';
    P.document.body.appendChild(d);
    d.onclick = function(){ d.classList.remove('open'); };

    // message listener
    P.addEventListener('message', function(e){
      if (e.data && e.data.type === 'cim:open'){
        P.document.getElementById('cim-lb-img').src = e.data.src;
        d.classList.add('open');
      }
    });
  } catch(err){ /* cross-origin fallback – silently skip */ }
})();
</script>"""

# Layout constants (px)
_THUMB_H   = 72
_PREVIEW_H = 110
_DL_H      = 32
_IFRAME_H  = _THUMB_H + 6 + _PREVIEW_H + 6 + _DL_H + 4


def render_image_preview(
    image_bytes: bytes | None,
    filename: str = "image.png",
    thumb_width: int = _THUMB_H,
    key: str = "",
) -> None:
    """Image widget with:
    - Hover thumbnail  → preview appears below (_PREVIEW_H px).
    - Click thumbnail  → lightbox overlay centered on screen (click to close).
    - 🖼️ 下載          → HTML <a download> (Electron-compatible).
    """
    if not image_bytes:
        components.html(
            "<p style='margin:0;font-size:12px;color:#9ca3af'>無影像</p>",
            height=20, scrolling=False,
        )
        return

    # inject lightbox once per page into the parent Streamlit document
    components.html(_LIGHTBOX_SETUP, height=0, scrolling=False)

    b64     = base64.b64encode(image_bytes).decode("ascii")
    safe_fn = (filename or "image.png").replace('"', "").replace("'", "")
    tw      = thumb_width
    ph      = _PREVIEW_H

    html = f"""<!DOCTYPE html>
<html><head>
<style>
  *{{box-sizing:border-box;}}
  body{{margin:0;padding:2px 2px 0;background:transparent;
       font-family:system-ui,sans-serif;overflow:hidden;}}

  /* thumbnail */
  .thumb-box{{
    width:{tw}px;height:{tw}px;
    display:flex;align-items:center;justify-content:center;
    cursor:zoom-in;
  }}
  .thumb{{
    max-width:100%;max-height:100%;width:auto;height:auto;
    border-radius:4px;border:1px solid #d1d5db;
    transition:box-shadow .15s ease;
  }}
  .wrap:hover .thumb{{box-shadow:0 0 0 2px #6366f1;}}

  /* hover preview below */
  .preview-slot{{
    height:{ph}px;margin-top:6px;
    display:flex;align-items:flex-start;
  }}
  .preview{{
    visibility:hidden;
    max-width:100%;max-height:{ph}px;
    width:auto;height:auto;object-fit:contain;
    border-radius:4px;border:2px solid #6366f1;
    box-shadow:0 4px 16px rgba(0,0,0,.38);
  }}
  .wrap:hover .preview{{visibility:visible;}}

  /* download */
  .dl{{
    display:inline-flex;align-items:center;gap:4px;
    margin-top:6px;padding:5px 10px;
    background:#4f46e5;color:#fff;
    border-radius:5px;text-decoration:none;
    font-size:12px;font-weight:600;white-space:nowrap;
  }}
  .dl:hover{{background:#4338ca;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="thumb-box">
    <img class="thumb" id="thumb"
         src="data:image/png;base64,{b64}"
         title="點擊在畫面中央放大"/>
  </div>
  <div class="preview-slot">
    <img class="preview" src="data:image/png;base64,{b64}"/>
  </div>
  <a class="dl"
     href="data:image/png;base64,{b64}"
     download="{safe_fn}">🖼️ 下載</a>
</div>
<script>
document.getElementById('thumb').addEventListener('click', function(){{
  window.parent.postMessage({{
    type: 'cim:open',
    src:  'data:image/png;base64,{b64}'
  }}, '*');
}});
</script>
</body></html>"""

    components.html(html, height=_IFRAME_H, scrolling=False)
