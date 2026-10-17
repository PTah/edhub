#!/usr/bin/env python3
# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:15:02
"""Догрузка системы из EDSM/Spansh и предсказание биологии по чужим данным.

  python3 tools/inspect_remote.py "HIP 36601" [--address 84456968626]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import bio, remote, values  # noqa: E402
from edhud.model import System  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system")
    parser.add_argument("--address", type=int)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    client = remote.RemoteClient(ttl=0.0)
    fetched = client.fetch(args.system, args.address, force=True)
    if fetched is None or not fetched.bodies:
        print("нет данных")
        return 1

    system = System(address=fetched.address, name=fetched.name)
    added = remote.merge_into_system(system, fetched)
    scan_sum, mapped_sum = values.system_totals(system)
    print(f"{fetched.name}: тел {len(system.bodies)} (+{added} из сети), источники {fetched.sources}")
    print(f"наши оценки: скан {values.credits(scan_sum)}, с DSS {values.credits(mapped_sum)}")
    if fetched.estimated_scan_value:
        print(
            f"EDSM: скан {values.credits(fetched.estimated_scan_value)}, "
            f"с картами {values.credits(fetched.estimated_mapped_value or 0)}"
        )

    shown = 0
    for body in sorted(system.bodies.values(), key=lambda b: b.distance_ls):
        if not body.bio_signals:
            continue
        shown += 1
        if shown > args.limit:
            break
        breakdown = values.body_values(body)
        print(f"\n{body.name} · {body.planet_class} · БИО {body.bio_signals} · DSS {'✔' if body.dss_scanned else '✗'}")
        if breakdown:
            print(f"  скан {values.credits(breakdown.scan)} · с DSS {values.credits(breakdown.mapped)}")
        predictions = bio.predict_for_body(body, system, limit=8)
        for prediction in predictions:
            print(f"  ≈ {prediction.label} ({values.credits(prediction.reward)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
