"""Set the current platform role (RBAC identity) — demonstrable role switching.

RBAC is declarative (config/permissions.yaml) and enforced by the runners, but
"who am I" needs an identity source. This writes the default identity file
(config/identity.json) that AuthProvider.get_current_role reads — no env var
plumbing — so an admin can switch between admin/operator/viewer and immediately
see permissions take effect (operators/viewers get fewer tools / no execute).

    python tools/set_role.py viewer
    python tools/set_role.py operator
    python tools/set_role.py admin

In production, point CIM_IDENTITY_FILE at a file your SSO/IdP writes instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth_provider import VALID_ROLES, set_identity  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1 or argv[0] not in VALID_ROLES:
        print(f"用法：python tools/set_role.py <{'|'.join(VALID_ROLES)}>")
        return 2
    path = set_identity(argv[0])
    print(f"✅ 目前角色設為 {argv[0]}（寫入 {path}）。重新整理 portal / 重開工具即生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
