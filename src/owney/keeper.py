"""Owney keeper - Zyfai simulateBestPositions → map → submit_intent."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

from dotenv import load_dotenv
from eth_account import Account

_PK_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

from owney.asset import (
    optional_owney_vault_address,
    require_owney_vault_address,
    resolve_owney_denomination,
    simulate_token_for_denomination,
)
from owney.proxies import load_whitelisted_proxies
from owney.replicas import resolve_submission_intent
from owney.tokens import find_idle_replica, print_proxy_table
from owney.types import OwneyDenomination, ReplicaProxy
from owney.zyfai_simulate import (
    ETH_MAINNET_CHAIN_ID,
    order_intent_sum,
    positions_for_chain,
    resolve_owney_api_key,
    simulate_mainnet_best_positions,
    simulate_positions_to_order_intent,
)

HARDHAT_DEFAULT_ACCOUNT_0_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)


class KeeperFailure(RuntimeError):
    """Raised after a structured stderr JSON failure line was already emitted."""


def log_keeper_fail(
    reason: str,
    fields: dict[str, Any] | None = None,
    *,
    network: str = "unknown",
) -> None:
    payload = {"event": "owney_keeper_failed", "reason": reason, "network": network}
    if fields:
        payload.update({k: v for k, v in fields.items() if v is not None})
    print(json.dumps(payload), file=sys.stderr)


def _err_message(exc: BaseException) -> str:
    return str(exc) if str(exc) else type(exc).__name__


def _load_env() -> None:
    # Walk up from cwd for .env (same idea as TS loadKeeperEnv).
    load_dotenv(override=False)
    here = os.getcwd()
    for _ in range(4):
        candidate = os.path.join(here, ".env")
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)
            break
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent

    # Alias SEPOLIA_RPC_URL → RPC_URL for the Orion Python SDK.
    if not os.getenv("RPC_URL", "").strip():
        sepolia = os.getenv("SEPOLIA_RPC_URL", "").strip()
        if sepolia:
            os.environ["RPC_URL"] = sepolia


def _bridge_sdk_env(*, vault: str | None, strategist_key: str | None) -> None:
    if vault:
        os.environ["ORION_VAULT_ADDRESS"] = vault
    if strategist_key:
        os.environ["STRATEGIST_PRIVATE_KEY"] = strategist_key


def _percent_intent_to_fractions(order_intent: dict[str, float]) -> dict[str, float]:
    return {addr: weight / 100.0 for addr, weight in order_intent.items()}


def build_mock_mainnet_intent(
    proxies: list[ReplicaProxy],
    denomination: OwneyDenomination,
) -> dict[str, float]:
    print("\nOWNEY_MOCK=1 - synthetic multi-leg mainnet intent")
    try:
        idle = find_idle_replica(proxies, denomination)
        others = [p for p in proxies if p.sepolia_proxy != idle.sepolia_proxy][:3]
        picks = others if others else [idle]
    except Exception:
        picks = proxies[:3]

    if not picks:
        raise ValueError("No proxies to mock weights for")

    weight = int(10000 / len(picks)) / 100
    intent: dict[str, float] = {}
    assigned = 0.0
    for i, proxy in enumerate(picks):
        if i == len(picks) - 1:
            w = round((100 - assigned) * 100) / 100
        else:
            w = weight
        intent[proxy.mainnet_source] = w
        assigned += w
        print(f"   {proxy.name}: {w}% (mainnet {proxy.mainnet_source[:10]}…)")
    return intent


def fetch_mainnet_order_intent(
    denomination: OwneyDenomination,
    proxies: list[ReplicaProxy],
    *,
    mock_mode: bool,
) -> dict[str, float]:
    if mock_mode:
        return build_mock_mainnet_intent(proxies, denomination)

    if not resolve_owney_api_key():
        raise ValueError("Set OWNEY_API_KEY in .env (or OWNEY_MOCK=1)")

    token = simulate_token_for_denomination(denomination)
    params, result = simulate_mainnet_best_positions(token)
    print("simulate params", params)
    positions = positions_for_chain(result, ETH_MAINNET_CHAIN_ID)
    order_intent = simulate_positions_to_order_intent(positions)
    print(
        "mainnet order intent",
        {
            "sum": order_intent_sum(order_intent),
            "legs": len(order_intent),
            "orderIntent": order_intent,
        },
    )
    return order_intent


def run_keeper(*, asset: str | None = None) -> None:
    _load_env()
    denomination = resolve_owney_denomination(asset)
    dry_run = os.getenv("DRY_RUN", "").strip() == "1"
    mock_mode = os.getenv("OWNEY_MOCK", "").strip() == "1"
    network = "sepolia"

    vault_addr = (
        optional_owney_vault_address(denomination)
        if dry_run
        else require_owney_vault_address(denomination)
    )

    pk_raw = os.getenv("OWNEY_STRATEGIST_PRIVATE_KEY", "").strip()
    if pk_raw:
        if not _PK_RE.match(pk_raw):
            raise ValueError(
                "OWNEY_STRATEGIST_PRIVATE_KEY must be a 32-byte hex private key (0x + 64 hex chars)"
            )
        signer_key = pk_raw
        signer_address = Account.from_key(pk_raw).address
    elif dry_run:
        signer_key = HARDHAT_DEFAULT_ACCOUNT_0_KEY
        signer_address = Account.from_key(signer_key).address
    else:
        raise ValueError("OWNEY_STRATEGIST_PRIVATE_KEY is required when not DRY_RUN")

    print(
        "keeper start",
        {
            "denomination": denomination,
            "simulate_token": simulate_token_for_denomination(denomination),
            "network": network,
            "vault": vault_addr or "(none - DRY_RUN)",
            "signer": signer_address,
            "dry_run": dry_run,
            "mock": mock_mode,
        },
    )

    try:
        proxies = load_whitelisted_proxies()
    except Exception as exc:
        log_keeper_fail("fatal", {"message": _err_message(exc)}, network=network)
        raise KeeperFailure(_err_message(exc)) from exc

    if not proxies:
        raise ValueError("No whitelisted UniverseProxy replicas found in OrionConfig")
    print(f"   {len(proxies)} UniverseProxy replicas resolved")

    try:
        mainnet_intent = fetch_mainnet_order_intent(denomination, proxies, mock_mode=mock_mode)
        resolved = resolve_submission_intent(
            denomination=denomination,
            proxies=proxies,
            mainnet_intent=mainnet_intent,
        )
    except Exception as exc:
        log_keeper_fail("portfolio_build_failed", {"message": _err_message(exc)}, network=network)
        raise KeeperFailure(_err_message(exc)) from exc

    if resolved.used_fallback:
        print(
            "fallback: parking unmapped weight on idle replica",
            {
                "denomination": denomination,
                "unmapped": resolved.unmapped_addresses,
                "unmappedWeight": resolved.unmapped_weight,
                "orderIntent": resolved.order_intent,
            },
        )
    else:
        print(
            "mapped sepolia order intent",
            {
                "sum": order_intent_sum(resolved.order_intent),
                "legs": len(resolved.order_intent),
                "orderIntent": resolved.order_intent,
            },
        )

    if dry_run:
        print(
            "submission intent (not sent)",
            {
                "denomination": denomination,
                "vault": vault_addr,
                "fallback": resolved.used_fallback,
                "orderIntent": resolved.order_intent,
            },
        )
        print("run complete", {"dry_run": True})
        return

    assert vault_addr is not None
    _bridge_sdk_env(vault=vault_addr, strategist_key=signer_key)

    from orion_finance_sdk_py import OrionTransparentVault, strategist
    from orion_finance_sdk_py.utils import validate_order

    vault = OrionTransparentVault(contract_address=vault_addr)
    if vault.strategist_address.lower() != signer_address.lower():
        raise ValueError(
            f"Signer {signer_address} is not vault strategist {vault.strategist_address} for {vault_addr}"
        )

    fractions = _percent_intent_to_fractions(resolved.order_intent)
    print(
        "submitting intent",
        {
            "denomination": denomination,
            "vault": vault_addr,
            "fallback": resolved.used_fallback,
            "dry_run": False,
        },
    )

    try:
        scaled = validate_order(fractions)
        result = strategist.submit_intent(scaled, vault_address=vault_addr)
        print(
            "submit success",
            {
                "denomination": denomination,
                "vault": vault_addr,
                "tx_hash": result.tx_hash,
            },
        )
        print("run complete", {"ok": 1})
    except Exception as exc:
        log_keeper_fail(
            "submit_order_intent_failed",
            {"denomination": denomination, "vault": vault_addr, "message": _err_message(exc)},
            network=network,
        )
        raise KeeperFailure(_err_message(exc)) from exc


def list_proxies() -> None:
    _load_env()
    proxies = load_whitelisted_proxies()
    config = os.getenv("ORION_CONFIG_ADDRESS", "").strip() or "(sdk default)"
    print_proxy_table(proxies, network="sepolia", orion_config=config)
