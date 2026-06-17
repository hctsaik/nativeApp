"""verify_deppack — 指著一個 dep-pack 資料夾，判斷它的檔案完不完整。

讀資料夾內的 deppack.json 當「應有清單」，逐一比對 wheels/ 內每個 .whl 是否存在、
sha256 與大小相符（並抓出多餘檔）。完整 → exit 0；缺/壞/多 → exit 1 並列出問題，
可直接用在 agent copy 完之後的自我檢查或腳本判斷。

用法：
    py -3.11 tools/verify_deppack.py <dep-pack 資料夾>
    # 例：copy 過來的那一包
    py -3.11 tools/verify_deppack.py D:\incoming\app-lv
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from core import deppack  # noqa: E402

# 此工具會在工廠目標機（可能是 CP950 繁中 console）上跑。emoji 等非 CP950 字元會讓
# print 直接 UnicodeEncodeError 崩潰；用 errors="replace" 當保險，並全程不用 emoji。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print("用法：py -3.11 tools/verify_deppack.py <dep-pack 資料夾>")
        return 2
    pack_dir = Path(argv[0])
    if not pack_dir.is_dir():
        print(f"[不完整] 找不到資料夾：{pack_dir}")
        return 1

    ok, errors = deppack.verify_deppack_dir(pack_dir)
    if ok:
        manifest = deppack.load_manifest(pack_dir / deppack.MANIFEST_FILENAME)
        total_mb = sum(w.size for w in manifest.wheels) / (1024 * 1024)
        print(f"[完整] {pack_dir}")
        print(f"   工具 {manifest.tool_id}，{len(manifest.wheels)} 個 wheel，共 {total_mb:.1f} MB，"
              f"全部存在且 sha256 相符。")
        return 0

    print(f"[不完整] {pack_dir}")
    for e in errors:
        print(f"   - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
