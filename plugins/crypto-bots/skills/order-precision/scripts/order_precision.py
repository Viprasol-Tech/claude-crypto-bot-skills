#!/usr/bin/env python3
"""Make orders pass exchange precision filters before you send them.

Part of claude-crypto-bot-skills by Viprasol Tech Private Limited.

Rounds price to the tick size and quantity to the step size with Decimal
arithmetic (never floats), then checks minimum/maximum quantity and minimum
notional. Filters can be given on the command line or read from a Binance
`exchangeInfo` JSON (PRICE_FILTER, LOT_SIZE, MARKET_LOT_SIZE, NOTIONAL /
MIN_NOTIONAL). Standard library only. Run ``python order_precision.py --self-test``.

  python order_precision.py --side BUY --price 64123.456 --qty 0.0012345 \
      --tick 0.01 --step 0.00001 --min-qty 0.00001 --min-notional 5
  python order_precision.py --exchange-info exchangeInfo.json --symbol BTCUSDT \
      --side SELL --price 64123.456 --qty 0.0012345
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation


def fmt(d: Decimal | None) -> str:
    """Plain decimal string, never exponent notation (exchanges reject 1E-8)."""
    if d is None:
        return "-"
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


@dataclass
class Filters:
    tick: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    step: Decimal | None = None
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    market_step: Decimal | None = None
    market_min_qty: Decimal | None = None
    market_max_qty: Decimal | None = None
    min_notional: Decimal | None = None
    max_notional: Decimal | None = None
    apply_min_to_market: bool = True
    apply_max_to_market: bool = False


@dataclass
class Result:
    price: str | None
    qty: str
    notional: str | None
    ok: bool
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def dec(value: str | float | int | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        value = repr(value)
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if not d.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    return d


def snap(value: Decimal, step: Decimal, rounding: str) -> Decimal:
    """Round value to a multiple of step; keeps the step's number of decimals."""
    if step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=rounding)
    return (units * step).quantize(step.normalize()) if step.normalize().as_tuple().exponent < 0 else units * step


def from_binance(exchange_info: dict, symbol: str) -> Filters:
    for s in exchange_info.get("symbols", []):
        if s.get("symbol") == symbol:
            f = Filters()
            for flt in s.get("filters", []):
                t = flt.get("filterType")
                if t == "PRICE_FILTER":
                    f.tick, f.min_price, f.max_price = dec(flt.get("tickSize")), dec(flt.get("minPrice")), dec(flt.get("maxPrice"))
                elif t == "LOT_SIZE":
                    f.step, f.min_qty, f.max_qty = dec(flt.get("stepSize")), dec(flt.get("minQty")), dec(flt.get("maxQty"))
                elif t == "MARKET_LOT_SIZE":
                    f.market_step, f.market_min_qty, f.market_max_qty = (
                        dec(flt.get("stepSize")), dec(flt.get("minQty")), dec(flt.get("maxQty")))
                elif t == "NOTIONAL":
                    f.min_notional, f.max_notional = dec(flt.get("minNotional")), dec(flt.get("maxNotional"))
                    f.apply_min_to_market = bool(flt.get("applyMinToMarket", True))
                    f.apply_max_to_market = bool(flt.get("applyMaxToMarket", False))
                elif t == "MIN_NOTIONAL":
                    f.min_notional = dec(flt.get("minNotional"))
                    f.apply_min_to_market = bool(flt.get("applyToMarket", True))
            # zero means "disabled" in Binance filters
            for name in ("tick", "min_price", "max_price", "step", "min_qty", "max_qty", "market_step",
                         "market_min_qty", "market_max_qty", "max_notional"):
                if getattr(f, name) == 0:
                    setattr(f, name, None)
            return f
    raise ValueError(f"symbol {symbol!r} not found in exchangeInfo")


def prepare(side: str, qty: Decimal, price: Decimal | None, f: Filters, market: bool = False) -> Result:
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if qty <= 0 or (price is not None and price <= 0):
        raise ValueError("qty and price must be positive")
    problems, notes = [], []

    p = price
    if p is not None and f.tick:
        # Round so the order is never more aggressive than asked: buys down, sells up.
        p = snap(p, f.tick, ROUND_FLOOR if side == "BUY" else ROUND_CEILING)
        if p != price:
            notes.append(f"price rounded {'down' if side == 'BUY' else 'up'} to tick {fmt(f.tick)}: {fmt(price)} -> {fmt(p)}")
    if p is not None and f.min_price and p < f.min_price:
        problems.append(f"price {fmt(p)} below minPrice {fmt(f.min_price)}")
    if p is not None and f.max_price and p > f.max_price:
        problems.append(f"price {fmt(p)} above maxPrice {fmt(f.max_price)}")

    step = (f.market_step or f.step) if market else f.step
    q = qty
    if step:
        q = snap(qty, step, ROUND_FLOOR)  # never round quantity up into more size or risk
        if q != qty:
            notes.append(f"qty rounded down to step {fmt(step)}: {fmt(qty)} -> {fmt(q)}")
    min_q = (f.market_min_qty or f.min_qty) if market else f.min_qty
    if min_q and q < min_q:
        problems.append(f"qty {fmt(q)} below minQty {fmt(min_q)}")
    max_q = (f.market_max_qty or f.max_qty) if market else f.max_qty
    if max_q and q > max_q:
        problems.append(f"qty {fmt(q)} above maxQty {fmt(max_q)}")
    if q <= 0:
        problems.append("qty rounds to zero")

    notional = p * q if p is not None else None
    check_min = f.min_notional and (not market or f.apply_min_to_market)
    if notional is not None and f.max_notional and (not market or f.apply_max_to_market) and notional > f.max_notional:
        problems.append(f"notional {fmt(notional)} above maxNotional {fmt(f.max_notional)}")
    if notional is not None and check_min and notional < f.min_notional:
        need = (f.min_notional / p)
        if step:
            need = snap(need, step, ROUND_CEILING)
        problems.append(f"notional {fmt(notional)} below minNotional {fmt(f.min_notional)} (need qty >= {fmt(need)})")
    if market and price is None:
        notes.append("market order: check minNotional against the current price (MARKET orders use an average price)")
    return Result(price=fmt(p) if p is not None else None, qty=fmt(q),
                  notional=fmt(notional.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)) if notional is not None else None,
                  ok=not problems, problems=problems, notes=notes)


def _self_test() -> None:
    f = Filters(tick=Decimal("0.01"), step=Decimal("0.00001"), min_qty=Decimal("0.00001"), min_notional=Decimal("5"))
    r = prepare("BUY", Decimal("0.0012345"), Decimal("64123.456"), f)
    assert r.ok and r.price == "64123.45" and r.qty == "0.00123", r
    s = prepare("SELL", Decimal("0.0012345"), Decimal("64123.451"), f)
    assert s.price == "64123.46" and s.qty == "0.00123"
    small = prepare("BUY", Decimal("0.00005"), Decimal("64000"), f)
    assert not small.ok and "need qty >= 0.00008" in small.problems[0], small
    assert snap(Decimal("0.3"), Decimal("0.1"), ROUND_FLOOR) == Decimal("0.3")       # no float drift
    assert snap(Decimal("1.23456"), Decimal("0.001"), ROUND_FLOOR) == Decimal("1.234")
    assert snap(Decimal("12345"), Decimal("10"), ROUND_FLOOR) == Decimal("12340")
    info = {"symbols": [{"symbol": "ETHUSDT", "filters": [
        {"filterType": "PRICE_FILTER", "minPrice": "0.01000000", "maxPrice": "1000000.00000000", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "minQty": "0.00010000", "maxQty": "9000.00000000", "stepSize": "0.00010000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000", "applyMinToMarket": True},
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.00000000", "maxQty": "1000.0", "stepSize": "0.00000000"}]}]}
    fe = from_binance(info, "ETHUSDT")
    assert fe.tick == Decimal("0.01") and fe.step == Decimal("0.0001") and fe.min_notional == Decimal("5")
    assert fe.market_step is None   # 0 = disabled -> falls back to LOT_SIZE
    e = prepare("BUY", Decimal("0.123456"), Decimal("3456.789"), fe)
    assert e.ok and e.qty == "0.1234" and e.price == "3456.78", e
    tiny = prepare("BUY", Decimal("5.123456789"), Decimal("0.00000099123"),
                   Filters(tick=Decimal("0.00000001"), step=Decimal("0.00000001")))
    assert tiny.price == "0.00000099" and tiny.qty == "5.12345678" and "E" not in tiny.price + tiny.qty, tiny
    big = prepare("SELL", Decimal("50"), Decimal("100"), Filters(tick=Decimal("1"), step=Decimal("10"), min_notional=Decimal("100")))
    assert big.qty == "50" and big.notional == "5000" and "E" not in big.notional, big
    assert fmt(Decimal("1E-8")) == "0.00000001" and fmt(Decimal("5E+3")) == "5000"
    m = prepare("BUY", Decimal("2000"), None, fe, market=True)
    assert not m.ok and "maxQty 1000" in m.problems[0], m.problems
    for bad in (lambda: prepare("HOLD", Decimal(1), None, f), lambda: prepare("BUY", Decimal(0), None, f),
                lambda: from_binance(info, "XRPUSDT"), lambda: dec("nan")):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("must reject")
    print("order_precision self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Round and check orders against exchange precision filters")
    ap.add_argument("--side", choices=["BUY", "SELL", "buy", "sell"])
    ap.add_argument("--qty")
    ap.add_argument("--price", help="Omit for market orders")
    ap.add_argument("--market", action="store_true", help="Use MARKET_LOT_SIZE when present")
    ap.add_argument("--tick")
    ap.add_argument("--step")
    ap.add_argument("--min-qty")
    ap.add_argument("--max-qty")
    ap.add_argument("--min-notional")
    ap.add_argument("--exchange-info", help="Binance exchangeInfo JSON file")
    ap.add_argument("--symbol", help="Symbol to read from --exchange-info")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if not (a.side and a.qty):
        ap.error("--side and --qty are required (or use --self-test)")
    try:
        if a.exchange_info:
            if not a.symbol:
                ap.error("--symbol is required with --exchange-info")
            with open(a.exchange_info, encoding="utf-8") as fh:
                f = from_binance(json.load(fh), a.symbol.upper())
        else:
            f = Filters(tick=dec(a.tick), step=dec(a.step), min_qty=dec(a.min_qty), max_qty=dec(a.max_qty),
                        min_notional=dec(a.min_notional))
        r = prepare(a.side, dec(a.qty), dec(a.price), f, a.market)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ArithmeticError:
        print("error: number out of range for these filters", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(asdict(r), indent=2))
    else:
        print(f"price     {r.price or 'MARKET'}\nqty       {r.qty}\nnotional  {r.notional or '-'}\nstatus    {'OK' if r.ok else 'WILL BE REJECTED'}")
        for n in r.notes:
            print(f"note: {n}")
        for p in r.problems:
            print(f"problem: {p}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
