"""Resolve idle USDC / WETH UniverseProxy replicas (fallback parking only)."""

from __future__ import annotations

import os
import re

from web3 import Web3

from owney.types import OwneyDenomination, ReplicaProxy

USDC_NAME = re.compile(r"usdc", re.I)
WETH_NAME = re.compile(r"weth|wrapped\s*ether", re.I)
USDC_EXACT = re.compile(r"^usdc$", re.I)
WETH_EXACT = re.compile(r"^(weth|wrapped\s*ether)$", re.I)

# Ethereum mainnet USDC / WETH
USDC_MAINNET_SOURCE = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH_MAINNET_SOURCE = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


def _find_by_exact_name(proxies: list[ReplicaProxy], exact: re.Pattern[str]) -> ReplicaProxy | None:
    matches = [p for p in proxies if exact.match(p.name.strip())]
    return matches[0] if len(matches) == 1 else None


def _find_proxy_for_token(
    proxies: list[ReplicaProxy],
    *,
    token_env: str,
    mainnet_env: str,
    default_mainnet_source: str,
    exact_name: re.Pattern[str],
    fuzzy_name: re.Pattern[str],
    label: str,
    short_label: str,
) -> ReplicaProxy:
    env_token = os.getenv(token_env, "").strip()
    if env_token:
        if not Web3.is_address(env_token):
            raise ValueError(f"{token_env} invalid: {env_token}")
        addr = Web3.to_checksum_address(env_token).lower()
        for proxy in proxies:
            if proxy.sepolia_proxy.lower() == addr:
                return proxy
        raise ValueError(f"{token_env} {env_token} not in OrionConfig whitelist")

    mainnet_override = os.getenv(mainnet_env, "").strip().lower()
    if mainnet_override:
        for proxy in proxies:
            if proxy.mainnet_source.lower() == mainnet_override:
                return proxy
        raise ValueError(f"{mainnet_env} {mainnet_override} not in OrionConfig whitelist")

    default_mainnet = default_mainnet_source.lower()
    for proxy in proxies:
        if proxy.mainnet_source.lower() == default_mainnet:
            return proxy

    exact = _find_by_exact_name(proxies, exact_name)
    if exact is not None:
        return exact

    matches = [p for p in proxies if fuzzy_name.search(p.name)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        listing = ", ".join(f"{p.name} ({p.sepolia_proxy})" for p in matches)
        raise ValueError(
            f"Multiple {short_label} replicas on whitelist - set {mainnet_env} or {token_env}: {listing}"
        )

    listing = "; ".join(f"{p.name}: {p.sepolia_proxy}" for p in proxies) or "(none)"
    raise ValueError(
        f"No {label} replica on whitelist (exact name or mainnet {default_mainnet_source}). "
        f"Set {token_env} or {mainnet_env}. Proxies: {listing}"
    )


def find_usdc_proxy(proxies: list[ReplicaProxy]) -> ReplicaProxy:
    return _find_proxy_for_token(
        proxies,
        token_env="OWNEY_USDC_TOKEN",
        mainnet_env="OWNEY_USDC_MAINNET_SOURCE",
        default_mainnet_source=USDC_MAINNET_SOURCE,
        exact_name=USDC_EXACT,
        fuzzy_name=USDC_NAME,
        label="USDC",
        short_label="USDC",
    )


def find_weth_proxy(proxies: list[ReplicaProxy]) -> ReplicaProxy:
    return _find_proxy_for_token(
        proxies,
        token_env="OWNEY_WETH_TOKEN",
        mainnet_env="OWNEY_WETH_MAINNET_SOURCE",
        default_mainnet_source=WETH_MAINNET_SOURCE,
        exact_name=WETH_EXACT,
        fuzzy_name=WETH_NAME,
        label="Wrapped Ether",
        short_label="wETH",
    )


def find_idle_replica(proxies: list[ReplicaProxy], denomination: OwneyDenomination) -> ReplicaProxy:
    return find_usdc_proxy(proxies) if denomination == "usdc" else find_weth_proxy(proxies)


def print_proxy_table(proxies: list[ReplicaProxy], *, network: str, orion_config: str) -> None:
    print(
        "OrionConfig whitelist",
        {"network": network, "orion_config": orion_config, "proxies": len(proxies)},
    )
    print("UniverseProxy replicas:")
    for proxy in proxies:
        print(f"  {proxy.name}\t{proxy.mainnet_source}\t{proxy.sepolia_proxy}")
