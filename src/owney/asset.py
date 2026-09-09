"""Owney denomination (USDC / WETH product lines) and vault env resolution."""

from __future__ import annotations

import os
import re

from web3 import Web3

from owney.types import OwneyDenomination

_VAULT_ENV: dict[OwneyDenomination, str] = {
    "usdc": "OWNEY_USDC_VAULT_ADDRESS",
    "weth": "OWNEY_WETH_VAULT_ADDRESS",
}

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def resolve_owney_denomination(raw: str | None = None) -> OwneyDenomination:
    value = (raw if raw is not None else os.getenv("OWNEY_ASSET", "")).strip().lower()
    if value in ("usdc", "weth"):
        return value  # type: ignore[return-value]
    raise ValueError("OWNEY_ASSET must be usdc or weth")


def simulate_token_for_denomination(denomination: OwneyDenomination) -> str:
    return "USDC" if denomination == "usdc" else "WETH"


def _parse_single_vault_address(raw: str, env_name: str) -> str:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 1:
        raise ValueError(f"{env_name} must be exactly one address")
    addr = parts[0]
    if not _ADDRESS_RE.match(addr):
        raise ValueError(f"{env_name} is not a valid address: {addr}")
    return Web3.to_checksum_address(addr)


def require_owney_vault_address(denomination: OwneyDenomination) -> str:
    env_name = _VAULT_ENV[denomination]
    raw = os.getenv(env_name, "").strip()
    if not raw:
        raise ValueError(f"{env_name} is required")
    return _parse_single_vault_address(raw, env_name)


def optional_owney_vault_address(denomination: OwneyDenomination) -> str | None:
    env_name = _VAULT_ENV[denomination]
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    return _parse_single_vault_address(raw, env_name)
