#!/usr/bin/env python3
"""Local order book from a REST snapshot + WebSocket diff stream, with gap detection.

Part of claude-crypto-bot-skills by Viprasol Tech Private Limited.

Implements Binance's documented procedures:
  spot    : drop events with u <= lastUpdateId; after that each event must have
            U == previous u + 1, otherwise a gap -> resync from a new snapshot.
  futures : drop events with u < lastUpdateId; the first applied event must have
            U <= lastUpdateId <= u; each later event must have pu == previous u.
Quantities are absolute: a quantity of 0 removes the price level.
Prices and quantities are kept as Decimal strings. Standard library only.

  python book_sync.py replay snapshot.json events.jsonl --mode spot
  python book_sync.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal


class GapError(Exception):
    """Updates were missed: discard the book and resync from a fresh snapshot."""


class LocalBook:
    def __init__(self, mode: str = "spot") -> None:
        if mode not in ("spot", "futures"):
            raise ValueError("mode must be spot or futures")
        self.mode = mode
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_id: int | None = None
        self.synced = False   # True once the first event after the snapshot was applied

    def load_snapshot(self, snap: dict) -> None:
        self.bids = {Decimal(p): Decimal(q) for p, q in snap["bids"] if Decimal(q) != 0}
        self.asks = {Decimal(p): Decimal(q) for p, q in snap["asks"] if Decimal(q) != 0}
        self.last_id = int(snap["lastUpdateId"])
        self.synced = False

    def apply(self, ev: dict) -> bool:
        """Apply one diff event. Returns False if it was older than the book and ignored.
        Raises GapError when an update was missed."""
        if self.last_id is None:
            raise GapError("no snapshot loaded")
        first, last = int(ev["U"]), int(ev["u"])
        if self.mode == "spot":
            if last <= self.last_id:
                return False
            if first > self.last_id + 1:
                raise GapError(f"gap: expected U <= {self.last_id + 1}, got U={first}")
        else:
            if last < self.last_id or (self.synced and last == self.last_id):
                return False  # older or duplicate event
            if not self.synced:
                if not (first <= self.last_id <= last):
                    raise GapError(f"first event must cover lastUpdateId {self.last_id}: U={first} u={last}")
            elif int(ev["pu"]) != self.last_id:
                raise GapError(f"gap: pu={ev['pu']} but previous u={self.last_id}")
        for side, book in (("b", self.bids), ("a", self.asks)):
            for p, q in ev.get(side, []):
                price, qty = Decimal(p), Decimal(q)
                if qty == 0:
                    book.pop(price, None)
                else:
                    book[price] = qty
        self.last_id = last
        self.synced = True
        return True

    def best(self) -> tuple[tuple[Decimal, Decimal] | None, tuple[Decimal, Decimal] | None]:
        bid = max(self.bids.items()) if self.bids else None
        ask = min(self.asks.items()) if self.asks else None
        return bid, ask

    def crossed(self) -> bool:
        bid, ask = self.best()
        return bool(bid and ask and bid[0] >= ask[0])


def _self_test() -> None:
    snap = {"lastUpdateId": 100, "bids": [["99.0", "1"], ["98.5", "2"]], "asks": [["100.0", "1.5"], ["100.5", "3"]]}
    b = LocalBook("spot")
    b.load_snapshot(snap)
    assert b.apply({"U": 90, "u": 100, "b": [], "a": []}) is False          # older: ignored
    assert b.apply({"U": 95, "u": 103, "b": [["99.0", "0"], ["99.2", "4"]], "a": []})
    assert b.best()[0] == (Decimal("99.2"), Decimal("4")) and Decimal("99.0") not in b.bids
    assert b.apply({"U": 104, "u": 104, "b": [], "a": [["100.0", "0"]]})
    assert b.best()[1] == (Decimal("100.5"), Decimal("3"))
    try:
        b.apply({"U": 106, "u": 107, "b": [], "a": []})                      # 105 missed
    except GapError:
        pass
    else:
        raise AssertionError("spot gap not detected")
    f = LocalBook("futures")
    f.load_snapshot(snap)
    assert f.apply({"U": 80, "u": 99, "pu": 79, "b": [], "a": []}) is False
    try:
        f.apply({"U": 101, "u": 105, "pu": 100, "b": [], "a": []})           # does not cover 100
    except GapError:
        pass
    else:
        raise AssertionError("futures first-event rule not enforced")
    f.load_snapshot(snap)
    assert f.apply({"U": 98, "u": 102, "pu": 97, "b": [["101", "1"]], "a": []})
    assert f.crossed()                                                        # 101 bid >= 100 ask
    assert f.apply({"U": 103, "u": 104, "pu": 102, "b": [["101", "0"]], "a": []}) and not f.crossed()
    try:
        f.apply({"U": 106, "u": 107, "pu": 105, "b": [], "a": []})           # pu != 104
    except GapError:
        pass
    else:
        raise AssertionError("futures pu chain not enforced")
    assert f.apply({"U": 103, "u": 104, "pu": 102, "b": [], "a": []}) is False   # duplicate after sync
    try:
        LocalBook("spot").apply({"U": 1, "u": 1})
    except GapError:
        pass
    else:
        raise AssertionError("apply without snapshot accepted")
    print("book_sync self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay a depth snapshot + diff events and check sync rules")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("replay")
    r.add_argument("snapshot", help="JSON from GET /api/v3/depth or /fapi/v1/depth")
    r.add_argument("events", help="JSON lines of depthUpdate events (fields U, u, [pu], b, a)")
    r.add_argument("--mode", choices=["spot", "futures"], default="spot")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if a.cmd != "replay":
        ap.print_help()
        return 2
    try:
        book = LocalBook(a.mode)
        with open(a.snapshot, encoding="utf-8") as fh:
            book.load_snapshot(json.load(fh))
        applied = ignored = 0
        with open(a.events, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                ev = json.loads(line)
                ev = ev.get("data", ev)  # combined-stream wrapper
                if book.apply(ev):
                    applied += 1
                else:
                    ignored += 1
                if book.crossed():
                    print(f"warning: book crossed after event line {n}")
    except GapError as exc:
        print(f"RESYNC NEEDED at event line {n}: {exc}")
        return 3
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    bid, ask = book.best()
    print(f"in sync: {applied} applied, {ignored} ignored, last update id {book.last_id}")
    print(f"best bid {bid[0] if bid else '-'} x {bid[1] if bid else '-'} | best ask {ask[0] if ask else '-'} x {ask[1] if ask else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
