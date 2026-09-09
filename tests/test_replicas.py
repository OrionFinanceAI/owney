"""Unit tests for mainnet → Sepolia replica mapping + idle fallback."""

from __future__ import annotations

from owney.replicas import (
    build_mainnet_source_lookup,
    map_mainnet_order_intent,
    resolve_submission_intent,
)
from owney.types import ReplicaProxy

MAINNET_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MAINNET_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
MAINNET_C = "0xcccccccccccccccccccccccccccccccccccccccc"
MAINNET_D = "0xdddddddddddddddddddddddddddddddddddddddd"
PROXY_A = "0x1111111111111111111111111111111111111111"
PROXY_B = "0x2222222222222222222222222222222222222222"
PROXY_IDLE = "0x3333333333333333333333333333333333333333"
USDC_MAINNET = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

SAMPLE_PROXIES = [
    ReplicaProxy(sepolia_proxy=PROXY_A, mainnet_source=MAINNET_A, name="Product A"),
    ReplicaProxy(sepolia_proxy=PROXY_B, mainnet_source=MAINNET_B, name="Product B"),
    ReplicaProxy(sepolia_proxy=PROXY_IDLE, mainnet_source=USDC_MAINNET.lower(), name="USDC"),
]


def test_build_mainnet_source_lookup_keys_lowercase() -> None:
    lookup = build_mainnet_source_lookup(SAMPLE_PROXIES)
    assert lookup[MAINNET_A].sepolia_proxy == PROXY_A
    assert lookup[MAINNET_A.lower()].sepolia_proxy == PROXY_A


def test_maps_all_addresses_to_sepolia_proxies() -> None:
    result = map_mainnet_order_intent(SAMPLE_PROXIES, {MAINNET_A: 40, MAINNET_B: 60})
    assert result.unmapped_addresses == []
    assert result.unmapped_weight == 0
    assert result.sepolia_intent[PROXY_A] == 40
    assert result.sepolia_intent[PROXY_B] == 60


def test_aggregates_when_two_mainnet_keys_share_replica() -> None:
    proxies = [
        ReplicaProxy(sepolia_proxy=PROXY_A, mainnet_source=MAINNET_A, name="A1"),
        ReplicaProxy(sepolia_proxy=PROXY_A, mainnet_source=MAINNET_B, name="A2"),
    ]
    result = map_mainnet_order_intent(proxies, {MAINNET_A: 25, MAINNET_B: 75})
    assert result.unmapped_addresses == []
    assert result.sepolia_intent[PROXY_A] == 100


def test_collects_unmapped_without_dropping_mapped() -> None:
    result = map_mainnet_order_intent(SAMPLE_PROXIES, {MAINNET_A: 50, MAINNET_C: 50})
    assert result.unmapped_addresses == [MAINNET_C]
    assert result.unmapped_weight == 50
    assert result.sepolia_intent[PROXY_A] == 50


def test_matches_checksummed_mainnet_keys_case_insensitively() -> None:
    checksummed = "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"
    result = map_mainnet_order_intent(SAMPLE_PROXIES, {checksummed: 100})
    assert result.unmapped_addresses == []
    assert result.sepolia_intent[PROXY_A] == 100


def test_resolve_all_mapped() -> None:
    result = resolve_submission_intent(
        denomination="usdc",
        proxies=SAMPLE_PROXIES,
        mainnet_intent={MAINNET_A: 33.34, MAINNET_B: 66.66},
    )
    assert result.used_fallback is False
    assert result.unmapped_addresses == []
    assert result.order_intent[PROXY_A] == 33.34
    assert result.order_intent[PROXY_B] == 66.66


def test_resolve_parks_unmapped_on_idle() -> None:
    result = resolve_submission_intent(
        denomination="usdc",
        proxies=SAMPLE_PROXIES,
        mainnet_intent={
            MAINNET_A: 66.73,
            MAINNET_B: 8.73,
            MAINNET_C: 11.32,
            MAINNET_D: 13.22,
        },
    )
    assert result.used_fallback is True
    assert result.unmapped_addresses == [MAINNET_C, MAINNET_D]
    assert abs(result.unmapped_weight - 24.54) < 1e-9
    assert result.order_intent[PROXY_A] == 66.73
    assert result.order_intent[PROXY_B] == 8.73
    assert abs(result.order_intent[PROXY_IDLE] - 24.54) < 1e-9


def test_resolve_parks_100_percent_on_idle() -> None:
    result = resolve_submission_intent(
        denomination="usdc",
        proxies=SAMPLE_PROXIES,
        mainnet_intent={MAINNET_C: 100},
    )
    assert result.used_fallback is True
    assert result.order_intent == {PROXY_IDLE: 100}


def test_resolve_idle_override_for_weth() -> None:
    weth_idle = ReplicaProxy(
        sepolia_proxy=PROXY_IDLE,
        mainnet_source="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        name="WETH",
    )
    result = resolve_submission_intent(
        denomination="weth",
        proxies=[
            ReplicaProxy(sepolia_proxy=PROXY_A, mainnet_source=MAINNET_A, name="Product A"),
            weth_idle,
        ],
        mainnet_intent={MAINNET_C: 100},
        idle_replica=weth_idle,
    )
    assert result.used_fallback is True
    assert result.order_intent == {PROXY_IDLE: 100}
