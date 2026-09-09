"""Unit tests for Zyfai simulate helpers."""

from __future__ import annotations

import os

import pytest

from owney.zyfai_simulate import (
    extract_deposit_address,
    resolve_simulate_params,
    simulate_positions_to_order_intent,
)


def _pos(*, protocol: str, pool: str, amount: float, deposit: str) -> dict:
    return {
        "protocol": protocol,
        "pool": pool,
        "amount": amount,
        "simulated_apy": 1,
        "combined_apy": 1,
        "url": "",
        "amount_raw": str(int(round(amount * 1e6))),
        "tvl": 0,
        "liquidity": 0,
        "averageCombinedApy30Days": 1,
        "calldata": [
            {
                "contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "function_name": "approve",
                "parameters": [deposit, "1"],
                "value": "0",
                "description": "approve",
            },
            {
                "contract_address": deposit,
                "function_name": "deposit",
                "parameters": ["1", "<RECEIVER>"],
                "value": "0",
                "description": "deposit",
            },
        ],
    }


def test_extract_deposit_address() -> None:
    p = _pos(
        protocol="Morpho",
        pool="Steakhouse USDC",
        amount=1,
        deposit="0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB",
    )
    assert extract_deposit_address(p) == "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB"


def test_maps_deposit_addresses_to_percents_summing_to_100() -> None:
    a = "0x1111111111111111111111111111111111111111"
    b = "0x2222222222222222222222222222222222222222"
    intent = simulate_positions_to_order_intent(
        [
            _pos(protocol="A", pool="p", amount=2500, deposit=a),
            _pos(protocol="B", pool="p", amount=7500, deposit=b),
        ]
    )
    assert intent[a] == 25
    assert intent[b] == 75
    assert sum(intent.values()) == 100


def test_aggregates_duplicate_product_addresses() -> None:
    a = "0x1111111111111111111111111111111111111111"
    intent = simulate_positions_to_order_intent(
        [
            _pos(protocol="A", pool="p1", amount=40, deposit=a),
            _pos(protocol="A", pool="p2", amount=60, deposit=a),
        ]
    )
    assert intent == {a: 100}


def test_equal_split_rounds_to_100() -> None:
    a = "0x1111111111111111111111111111111111111111"
    b = "0x2222222222222222222222222222222222222222"
    c = "0x3333333333333333333333333333333333333333"
    intent = simulate_positions_to_order_intent(
        [
            _pos(protocol="A", pool="p", amount=3333.333334, deposit=a),
            _pos(protocol="B", pool="p", amount=3333.333333, deposit=b),
            _pos(protocol="C", pool="p", amount=3333.333333, deposit=c),
        ]
    )
    assert sum(intent.values()) == 100


def test_resolve_simulate_params_defaults_aggressive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OWNEY_SIM_STRATEGY", raising=False)
    assert resolve_simulate_params(token="USDC").strategy == "aggressive"


def test_resolve_simulate_params_rejects_bad_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNEY_SIM_STRATEGY", "yolo")
    with pytest.raises(ValueError, match='OWNEY_SIM_STRATEGY must be "conservative" or "aggressive"'):
        resolve_simulate_params(token="USDC")
