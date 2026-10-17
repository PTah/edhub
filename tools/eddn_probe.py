#!/usr/bin/env python3
# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:25:42
"""Пробник живого EDDN: какие схемы и события идут в фиде (без внешних пакетов).

  python3 tools/eddn_probe.py [tcp://eddn.edcd.io:9500] [--count 200] [--system HIP 36601]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import eddn, zmtp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint", nargs="?", default=eddn.DEFAULT_ENDPOINT)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--system", help="показать сообщения по системе")
    args = parser.parse_args()

    subscriber = zmtp.ZmtpSubscriber(args.endpoint, timeout=args.seconds)
    subscriber.connect()
    print(f"подключено к {args.endpoint}")

    schemas: collections.Counter = collections.Counter()
    events: collections.Counter = collections.Counter()
    printed = 0
    deadline = time.time() + args.seconds
    received = 0
    try:
        while received < args.count and time.time() < deadline:
            raw = subscriber.recv()
            if raw is None:
                break
            received += 1
            envelope = eddn.decode_message(raw)
            if not envelope:
                continue
            schemas[envelope.get("$schemaRef", "?")] += 1
            message = envelope.get("message") or {}
            event = message.get("event") or "?"
            events[event] += 1
            if args.system and printed < 3:
                if message.get("StarSystem") == args.system or message.get("SystemName") == args.system:
                    printed += 1
                    print("---")
                    print(json.dumps(message, ensure_ascii=False)[:600])
    finally:
        subscriber.close()

    print(f"\nсообщений: {received}")
    print("схемы:")
    for ref, count in schemas.most_common():
        print(f"  {count:4} {ref}")
    print("события:")
    for event, count in events.most_common(15):
        print(f"  {count:4} {event}")
    return 0 if received else 1


if __name__ == "__main__":
    sys.exit(main())
