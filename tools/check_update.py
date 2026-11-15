# Created by nc.ai 1.2.15 on Papasha 2026-11-15 11:18:13
import sys

sys.path.insert(0, ".")
from edhud import __version__, update

print("code version:", __version__)
print("install kind:", update.install_kind())
try:
    tag, notes, url, assets = update.fetch_release()
    print("latest tag:", tag)
    print("url:", url)
    for a in assets:
        print(f"  asset: {a.name}  {a.size} bytes")
except Exception as exc:  # noqa: BLE001
    print("fetch_release FAILED:", type(exc).__name__, exc)

info = update.check()
print()
print("available:", info.available, "| current:", info.current, "| latest:", info.latest)
print("asset:", info.asset_name)
print("error:", info.error or "-")
