"""Zyfai simulateBestPositions helpers - wallet-free proposed pool splits."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from owney.http_retry import resolve_http_timeout_ms, with_owney_retry

ETH_MAINNET_CHAIN_ID = 1
ZYFAI_API_BASE = "https://api.zyf.ai/api/v1"

ZyfaiStrategy = Literal["conservative", "aggressive"]
_ZYFAI_STRATEGIES = frozenset({"conservative", "aggressive"})
_INTERNAL_STRATEGY = {
    "conservative": "safe_strategy",
    "aggressive": "degen_strategy",
}

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def resolve_owney_api_key() -> str:
    return os.getenv("OWNEY_API_KEY", "").strip()


def require_api_key(api_key: str | None = None) -> str:
    key = api_key if api_key is not None else resolve_owney_api_key()
    if not key:
        raise ValueError("OWNEY_API_KEY is required. Set it in .env.")
    return key


@dataclass(frozen=True)
class SimulateParams:
    amount: float
    token: str
    networks: int
    strategy: ZyfaiStrategy
    min_split: int
    protocols: list[str] | None = None
    pools: list[str] | None = None


def resolve_simulate_params(
    *,
    token: str,
    amount: float | None = None,
    strategy: ZyfaiStrategy | None = None,
    min_split: int | None = None,
    networks: int | None = None,
    protocols: list[str] | None = None,
    pools: list[str] | None = None,
) -> SimulateParams:
    if amount is None:
        amount_raw = os.getenv("OWNEY_SIM_AMOUNT", "").strip()
        try:
            parsed = float(amount_raw)
        except ValueError:
            parsed = float("nan")
        amount = parsed if parsed == parsed and parsed > 0 else 10_000.0

    if strategy is None:
        strategy_env = os.getenv("OWNEY_SIM_STRATEGY", "").strip().lower()
        if not strategy_env:
            strategy = "aggressive"
        elif strategy_env in _ZYFAI_STRATEGIES:
            strategy = strategy_env  # type: ignore[assignment]
        else:
            raise ValueError(
                'OWNEY_SIM_STRATEGY must be "conservative" or "aggressive" '
                f'(got "{os.getenv("OWNEY_SIM_STRATEGY")}")'
            )

    if min_split is None:
        min_split_raw = os.getenv("OWNEY_SIM_MIN_SPLIT", "").strip()
        try:
            parsed_split = float(min_split_raw)
        except ValueError:
            parsed_split = float("nan")
        min_split = int(parsed_split) if parsed_split == parsed_split and parsed_split > 0 else 1

    return SimulateParams(
        amount=amount,
        token=token,
        networks=networks if networks is not None else ETH_MAINNET_CHAIN_ID,
        strategy=strategy,
        min_split=min_split,
        protocols=protocols,
        pools=pools,
    )


def _normalize_address(addr: str) -> str:
    a = addr.strip()
    if not _ADDRESS_RE.match(a):
        raise ValueError(f"Invalid product address: {addr}")
    return a


def extract_deposit_address(position: dict[str, Any]) -> str:
    calls = position.get("calldata") or []
    for call in calls:
        if str(call.get("function_name", "")).lower() == "deposit" and call.get("contract_address"):
            return _normalize_address(str(call["contract_address"]))

    for call in reversed(calls):
        if str(call.get("function_name", "")).lower() == "approve":
            continue
        if call.get("contract_address"):
            return _normalize_address(str(call["contract_address"]))

    protocol = position.get("protocol", "?")
    pool = position.get("pool", "?")
    raise ValueError(f"No deposit contract_address in calldata for {protocol}/{pool}")


def _round_percents_to_fixed_sum(entries: list[tuple[str, float]], target: float) -> dict[str, float]:
    scaled = [
        {
            "addr": addr,
            "units": int(pct * 100 + 1e-9),
            "rem": pct * 100 - int(pct * 100 + 1e-9),
            "pct": pct,
        }
        for addr, pct in entries
    ]
    target_units = int(round(target * 100))
    residual = target_units - sum(e["units"] for e in scaled)

    order = sorted(
        range(len(scaled)),
        key=lambda i: (-scaled[i]["rem"], -scaled[i]["units"]),
    )

    oi = 0
    while residual > 0 and order:
        scaled[order[oi % len(order)]]["units"] += 1
        residual -= 1
        oi += 1
    while residual < 0 and order:
        idx = order[oi % len(order)]
        if scaled[idx]["units"] > 0:
            scaled[idx]["units"] -= 1
            residual += 1
        oi += 1

    return {e["addr"]: e["units"] / 100 for e in scaled}


def simulate_positions_to_order_intent(positions: list[dict[str, Any]]) -> dict[str, float]:
    if not positions:
        raise ValueError("simulateBestPositions returned no positions")

    amounts_by_addr: dict[str, float] = {}
    for position in positions:
        addr = extract_deposit_address(position)
        try:
            amount = float(position["amount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid amount for {addr}: {position.get('amount')}") from exc
        if amount != amount or amount < 0:  # NaN or negative
            raise ValueError(f"Invalid amount for {addr}: {position.get('amount')}")
        amounts_by_addr[addr] = amounts_by_addr.get(addr, 0.0) + amount

    total = sum(amounts_by_addr.values())
    if not (total > 0):
        raise ValueError("simulateBestPositions amounts sum to 0")

    entries = [(addr, (100.0 * amount) / total) for addr, amount in amounts_by_addr.items()]
    return _round_percents_to_fixed_sum(entries, 100.0)


def order_intent_sum(order_intent: dict[str, float]) -> float:
    units = sum(round(n * 100) for n in order_intent.values())
    return units / 100


def positions_for_chain(
    result: dict[str, Any],
    chain_id: int = ETH_MAINNET_CHAIN_ID,
) -> list[dict[str, Any]]:
    if not result.get("success"):
        raise ValueError(f"simulateBestPositions failed: {json.dumps(result.get('messages'))}")
    key = str(chain_id)
    data = result.get("data") or {}
    positions = data.get(key)
    if not positions:
        raise ValueError(f"No positions for chain {chain_id} in simulateBestPositions response")
    return list(positions)


def _build_simulate_url(params: SimulateParams) -> str:
    query: list[str] = [
        f"amount={params.amount}",
        f"token={urllib.parse.quote(params.token)}",
        f"networks={params.networks}",
        f"strategy={_INTERNAL_STRATEGY[params.strategy]}",
        f"minSplit={params.min_split}",
    ]
    if params.protocols:
        query.append(f"protocols={urllib.parse.quote(','.join(params.protocols))}")
    if params.pools:
        query.append(f"pools={urllib.parse.quote(','.join(params.pools))}")
    return f"{ZYFAI_API_BASE}/simulate/best-positions?{'&'.join(query)}"


def _http_get_json(url: str, *, api_key: str, timeout_s: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zyfai HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise TimeoutError(f"Zyfai simulateBestPositions timed out after {int(timeout_s * 1000)}ms") from exc
    except Exception as exc:  # noqa: BLE001
        # Normalize socket timeouts that surface as URLError/OSError.
        if "timed out" in str(exc).lower():
            raise TimeoutError(
                f"Zyfai simulateBestPositions timed out after {int(timeout_s * 1000)}ms"
            ) from exc
        raise

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Zyfai simulateBestPositions returned non-object JSON")
    return payload


def simulate_mainnet_best_positions(
    token: str,
    *,
    api_key: str | None = None,
    amount: float | None = None,
    strategy: ZyfaiStrategy | None = None,
    min_split: int | None = None,
) -> tuple[SimulateParams, dict[str, Any]]:
    key = require_api_key(api_key)
    params = resolve_simulate_params(
        token=token,
        amount=amount,
        strategy=strategy,
        min_split=min_split,
    )
    timeout_ms = resolve_http_timeout_ms()
    url = _build_simulate_url(params)

    def _call() -> dict[str, Any]:
        return _http_get_json(url, api_key=key, timeout_s=timeout_ms / 1000)

    result = with_owney_retry(_call)
    return params, result
