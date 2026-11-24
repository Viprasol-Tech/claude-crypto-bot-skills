#!/usr/bin/env python3
"""Perpetual futures maths: PnL, funding, margin and liquidation price.

Part of claude-crypto-bot-skills by Viprasol Tech Private Limited.

Formulas follow the exchanges' published help pages (Binance USD-M FAQ,
Bybit UTA help centre) and reproduce their worked examples. Exchanges add
fees, tiers and rounding, so treat results as estimates and keep a buffer.
Standard library only. Run ``python perps_calc.py --self-test`` to check it.

  python perps_calc.py pnl --side long --qty 0.5 --entry 60000 --exit 61500
  python perps_calc.py pnl --side short --qty 100 --entry 50000 --exit 45500 --inverse --contract 100
  python perps_calc.py funding --side long --qty 2 --mark 3500 --rate 0.0001
  python perps_calc.py liq-binance --side long --qty 1 --entry 60000 --wallet 6000 --mmr 0.004 --cum 0
  python perps_calc.py liq-bybit --side long --qty 1 --entry 40000 --leverage 50 --mmr 0.005 \
      --extra-margin 3000 --taker-fee 0.00055
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, getcontext

getcontext().prec = 34


def D(x: str | int | float) -> Decimal:
    try:
        d = Decimal(str(x))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {x!r}") from exc
    if not d.is_finite():
        raise ValueError(f"not a finite number: {x!r}")
    return d


def sign(side: str) -> int:
    s = side.lower()
    if s not in ("long", "short"):
        raise ValueError("side must be long or short")
    return 1 if s == "long" else -1


def pnl_linear(side: str, qty: Decimal, entry: Decimal, exit_: Decimal) -> Decimal:
    """USDT/USDC-margined: side x qty x (exit - entry), in quote currency."""
    return sign(side) * qty * (exit_ - entry)


def pnl_inverse(side: str, contracts: Decimal, contract_size: Decimal, entry: Decimal, exit_: Decimal) -> Decimal:
    """Coin-margined: side x contracts x contract_size x (1/entry - 1/exit), in the base coin."""
    if entry <= 0 or exit_ <= 0:
        raise ValueError("prices must be positive")
    return sign(side) * contracts * contract_size * (1 / entry - 1 / exit_)


def funding_payment(side: str, qty: Decimal, price: Decimal, rate: Decimal) -> Decimal:
    """Cash flow to YOU (negative = you pay). Payment = notional x rate; positive rate: longs pay shorts.
    Binance uses mark price; Hyperliquid uses the oracle price."""
    return -sign(side) * qty * price * rate


def liq_binance(side: str, qty: Decimal, entry: Decimal, wallet: Decimal, mmr: Decimal, cum: Decimal,
                other_mm: Decimal = Decimal(0), other_upnl: Decimal = Decimal(0)) -> Decimal:
    """Binance USD-M one-way mode liquidation price.
    Isolated: wallet = isolated position margin, other_mm = other_upnl = 0.
    Cross: wallet = cross wallet balance, other_* = maintenance margin and unrealised PnL of other positions.
    LP = (WB - TMM1 + UPNL1 + cum - Side*Pos*EP) / (Pos*MMR - Side*Pos)"""
    s = sign(side)
    if qty <= 0 or entry <= 0:
        raise ValueError("qty and entry must be positive")
    if not (0 <= mmr < 1):
        raise ValueError("mmr must be a fraction between 0 and 1, e.g. 0.004")
    denom = qty * mmr - s * qty
    if denom == 0:
        raise ValueError("MMR of 100% makes the formula undefined")
    lp = (wallet - other_mm + other_upnl + cum - s * qty * entry) / denom
    return max(lp, Decimal(0))


def liq_bybit(side: str, qty: Decimal, entry: Decimal, leverage: Decimal, mmr: Decimal,
              extra_margin: Decimal = Decimal(0), mm_deduction: Decimal = Decimal(0),
              taker_fee: Decimal = Decimal(0)) -> Decimal:
    """Bybit UTA isolated-margin liquidation price for USDT/USDC linear contracts."""
    if leverage <= 0 or qty <= 0 or entry <= 0:
        raise ValueError("leverage, qty and entry must be positive")
    if not (0 <= mmr < 1) or not (0 <= taker_fee < 1):
        raise ValueError("mmr and taker fee must be fractions between 0 and 1")
    if sign(side) == 1:
        lp = (entry * qty - entry * qty / leverage - extra_margin / (1 - taker_fee) - mm_deduction) / (qty - qty * mmr)
    else:
        lp = (entry * qty + entry * qty / leverage + extra_margin / (1 + taker_fee) + mm_deduction) / (qty + qty * mmr)
    return max(lp, Decimal(0))


def margins(qty: Decimal, price: Decimal, leverage: Decimal, mmr: Decimal, cum: Decimal = Decimal(0)) -> dict:
    notional = qty * price
    return {"notional": notional, "initial_margin": notional / leverage,
            "maintenance_margin": notional * mmr - cum}


def _q(x: Decimal, places: str = "0.01") -> Decimal:
    return x.quantize(Decimal(places))


def _self_test() -> None:
    # Binance FAQ cross-margin examples (one-way mode)
    eth = liq_binance("long", D("3683.979"), D("1456.84"), D("1535443.01"), D("0.10"), D("135365"),
                      D("71200.81144"), D("-56354.57"))
    assert _q(eth) == D("1153.26"), eth
    btc = liq_binance("long", D("109.488"), D("32481.98"), D("1535443.01"), D("0.025"), D("16300"),
                      D("356512.508"), D("-448192.89"))
    assert _q(btc) == D("26316.89"), btc
    # isolated 10x long: margin 6000 on 60000 notional
    iso = liq_binance("long", D(1), D(60000), D(6000), D("0.004"), D(0))
    assert _q(iso) == D("54216.87"), iso
    short_iso = liq_binance("short", D(1), D(60000), D(6000), D("0.004"), D(0))
    assert short_iso > D(60000)
    # Bybit help-centre examples
    assert _q(liq_bybit("long", D(1), D(40000), D(50), D("0.005"), D(3000), D(0), D("0.00055"))) == D("36380.25")
    assert liq_bybit("short", D(1), D(10000), D(10), D("0.004")).quantize(D("0.0001")) == D("10956.1753")
    # Binance coin-margined example: short 100 x $100 contracts, 50000 -> 45500 = ~0.0198 BTC profit
    inv = pnl_inverse("short", D(100), D(100), D(50000), D(45500))
    assert _q(inv, "0.0001") == D("0.0198"), inv
    assert pnl_linear("long", D("0.5"), D(60000), D(61500)) == D(750)
    assert pnl_linear("short", D(2), D(100), D(90)) == D(20)
    assert funding_payment("long", D(2), D(3500), D("0.0001")) == D("-0.7000")
    assert funding_payment("short", D(2), D(3500), D("0.0001")) == D("0.7000")
    assert funding_payment("long", D(2), D(3500), D("-0.0001")) == D("0.7000")
    m = margins(D("4918.775081"), D(1000), D(10), D("0.10"), D(135365))
    assert _q(m["maintenance_margin"], "0.001") == D("356512.508")
    assert _plain(D(750).quantize(D("0.0001"))) == "750" and _plain(D("-9.6386")) == "-9.6386"
    for bad in (lambda: sign("flat"), lambda: liq_bybit("long", D(1), D(1), D(0), D("0.01")),
                lambda: liq_binance("long", D(1), D(100), D(10), D("1.5"), D(0)),
                lambda: liq_bybit("long", D(1), D(100), D(10), D("0.005"), taker_fee=D("-0.1")),
                lambda: D("inf"), lambda: liq_binance("long", D(1), D(1), D(1), D(1), D(0))):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("must reject")
    print("perps_calc self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Perpetual futures PnL, funding, margin and liquidation price")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pnl")
    p.add_argument("--side", required=True)
    p.add_argument("--qty", required=True, help="Base quantity (linear) or contracts (inverse)")
    p.add_argument("--entry", required=True)
    p.add_argument("--exit", required=True)
    p.add_argument("--inverse", action="store_true", help="Coin-margined contract")
    p.add_argument("--contract", default="1", help="Inverse contract size in USD (e.g. 100 for BTC on Binance COIN-M)")
    f = sub.add_parser("funding")
    f.add_argument("--side", required=True)
    f.add_argument("--qty", required=True)
    f.add_argument("--mark", required=True, help="Mark price (Binance) or oracle price (Hyperliquid)")
    f.add_argument("--rate", required=True, help="Funding rate per interval as a fraction, e.g. 0.0001")
    f.add_argument("--intervals-per-day", default="3", help="3 for 8h, 6 for 4h, 24 for 1h")
    m = sub.add_parser("margin")
    m.add_argument("--qty", required=True)
    m.add_argument("--price", required=True)
    m.add_argument("--leverage", required=True)
    m.add_argument("--mmr", required=True)
    m.add_argument("--cum", default="0", help="Binance maintenance amount for the bracket")
    lb = sub.add_parser("liq-binance", help="Binance USD-M one-way liquidation price")
    lb.add_argument("--side", required=True)
    lb.add_argument("--qty", required=True)
    lb.add_argument("--entry", required=True)
    lb.add_argument("--wallet", required=True, help="Isolated margin, or cross wallet balance")
    lb.add_argument("--mmr", required=True, help="Maintenance margin rate of the bracket, e.g. 0.004")
    lb.add_argument("--cum", default="0", help="Maintenance amount of the bracket")
    lb.add_argument("--other-mm", default="0", help="Cross only: maintenance margin of other positions")
    lb.add_argument("--other-upnl", default="0", help="Cross only: unrealised PnL of other positions")
    ly = sub.add_parser("liq-bybit", help="Bybit isolated linear liquidation price")
    ly.add_argument("--side", required=True)
    ly.add_argument("--qty", required=True)
    ly.add_argument("--entry", required=True)
    ly.add_argument("--leverage", required=True)
    ly.add_argument("--mmr", required=True)
    ly.add_argument("--extra-margin", default="0")
    ly.add_argument("--mm-deduction", default="0")
    ly.add_argument("--taker-fee", default="0")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    try:
        if a.cmd == "pnl":
            out = {"pnl": pnl_inverse(a.side, D(a.qty), D(a.contract), D(a.entry), D(a.exit)) if a.inverse
                   else pnl_linear(a.side, D(a.qty), D(a.entry), D(a.exit)),
                   "unit": "base coin" if a.inverse else "quote currency"}
        elif a.cmd == "funding":
            per = funding_payment(a.side, D(a.qty), D(a.mark), D(a.rate))
            out = {"per_interval": per, "per_day": per * D(a.intervals_per_day),
                   "note": "negative = you pay; positive rate means longs pay shorts"}
        elif a.cmd == "margin":
            out = margins(D(a.qty), D(a.price), D(a.leverage), D(a.mmr), D(a.cum))
        elif a.cmd == "liq-binance":
            lp = liq_binance(a.side, D(a.qty), D(a.entry), D(a.wallet), D(a.mmr), D(a.cum), D(a.other_mm), D(a.other_upnl))
            out = {"liquidation_price": lp, "distance_pct": (lp / D(a.entry) - 1) * 100,
                   "note": "triggered on MARK price; fees and tier changes move it - keep a buffer"}
        elif a.cmd == "liq-bybit":
            lp = liq_bybit(a.side, D(a.qty), D(a.entry), D(a.leverage), D(a.mmr), D(a.extra_margin),
                           D(a.mm_deduction), D(a.taker_fee))
            out = {"liquidation_price": lp, "distance_pct": (lp / D(a.entry) - 1) * 100,
                   "note": "triggered on MARK price; keep a buffer"}
        else:
            ap.print_help()
            return 2
    except (ValueError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        if a.json:
            print(json.dumps({k: _plain(v) if isinstance(v, Decimal) else v for k, v in out.items()}, indent=2))
        else:
            for k, v in out.items():
                print(f"{k:<20}{_plain(v.quantize(Decimal('0.0001'))) if isinstance(v, Decimal) else v}")
    except ArithmeticError as exc:
        print(f"error: result out of range ({exc})", file=sys.stderr)
        return 1
    return 0


def _plain(d: Decimal) -> str:
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


if __name__ == "__main__":
    sys.exit(main())
