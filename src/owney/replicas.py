"""Map Zyfai/Owney mainnet-keyed orderIntent → Sepolia UniverseProxy replicas."""

from __future__ import annotations

from dataclasses import dataclass

from owney.tokens import find_idle_replica
from owney.types import OwneyDenomination, ReplicaProxy


def build_mainnet_source_lookup(proxies: list[ReplicaProxy]) -> dict[str, ReplicaProxy]:
    return {proxy.mainnet_source.lower(): proxy for proxy in proxies}


@dataclass(frozen=True)
class MapMainnetOrderIntentResult:
    sepolia_intent: dict[str, float]
    unmapped_addresses: list[str]
    unmapped_weight: float


def map_mainnet_order_intent(
    proxies: list[ReplicaProxy],
    mainnet_intent: dict[str, float],
) -> MapMainnetOrderIntentResult:
    lookup = build_mainnet_source_lookup(proxies)
    sepolia_intent: dict[str, float] = {}
    unmapped_addresses: list[str] = []
    unmapped_weight = 0.0

    for mainnet_addr, weight in mainnet_intent.items():
        proxy = lookup.get(mainnet_addr.lower())
        if proxy is None:
            unmapped_addresses.append(mainnet_addr)
            unmapped_weight += weight
            continue
        sepolia_intent[proxy.sepolia_proxy] = sepolia_intent.get(proxy.sepolia_proxy, 0.0) + weight

    return MapMainnetOrderIntentResult(
        sepolia_intent=sepolia_intent,
        unmapped_addresses=unmapped_addresses,
        unmapped_weight=unmapped_weight,
    )


@dataclass(frozen=True)
class ResolveSubmissionIntentResult:
    order_intent: dict[str, float]
    used_fallback: bool
    unmapped_addresses: list[str]
    unmapped_weight: float


def resolve_submission_intent(
    *,
    denomination: OwneyDenomination,
    proxies: list[ReplicaProxy],
    mainnet_intent: dict[str, float],
    idle_replica: ReplicaProxy | None = None,
) -> ResolveSubmissionIntentResult:
    mapped = map_mainnet_order_intent(proxies, mainnet_intent)

    if not mapped.unmapped_addresses:
        return ResolveSubmissionIntentResult(
            order_intent=mapped.sepolia_intent,
            used_fallback=False,
            unmapped_addresses=[],
            unmapped_weight=0.0,
        )

    idle = idle_replica if idle_replica is not None else find_idle_replica(proxies, denomination)
    order_intent = dict(mapped.sepolia_intent)
    order_intent[idle.sepolia_proxy] = (
        order_intent.get(idle.sepolia_proxy, 0.0) + mapped.unmapped_weight
    )

    return ResolveSubmissionIntentResult(
        order_intent=order_intent,
        used_fallback=True,
        unmapped_addresses=mapped.unmapped_addresses,
        unmapped_weight=mapped.unmapped_weight,
    )
