"""Load Sepolia UniverseProxy replicas from OrionConfig whitelist."""

from __future__ import annotations

from web3 import Web3

from owney.types import ReplicaProxy

_ZERO = "0x0000000000000000000000000000000000000000"

_MAINNET_SOURCE_ABI = [
    {
        "inputs": [],
        "name": "mainnetSource",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

_NAME_ABI = [
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def load_whitelisted_proxies(*, warn_on_duplicate: bool = True) -> list[ReplicaProxy]:
    """Walk OrionConfig whitelist and resolve mainnetSource() + name() per twin."""
    from orion_finance_sdk_py import OrionConfig

    config = OrionConfig()
    results: list[ReplicaProxy] = []

    for asset in config.whitelisted_assets:
        sepolia = Web3.to_checksum_address(asset)
        try:
            twin = config.w3.eth.contract(address=sepolia, abi=_MAINNET_SOURCE_ABI + _NAME_ABI)
            mainnet = twin.functions.mainnetSource().call()
        except Exception:
            continue

        if not mainnet or Web3.to_checksum_address(mainnet) == _ZERO:
            continue

        try:
            name = twin.functions.name().call()
        except Exception:
            name = f"{sepolia[:10]}…"

        results.append(
            ReplicaProxy(
                sepolia_proxy=sepolia,
                mainnet_source=Web3.to_checksum_address(mainnet).lower(),
                name=str(name),
            )
        )

    seen: dict[str, ReplicaProxy] = {}
    for entry in results:
        if entry.mainnet_source in seen:
            if warn_on_duplicate:
                kept = seen[entry.mainnet_source]
                print(
                    f"Duplicate mainnetSource {entry.mainnet_source[:10]}… ({entry.name}) - "
                    f"keeping first replica, skipping {entry.sepolia_proxy[:10]}…"
                )
                _ = kept
            continue
        seen[entry.mainnet_source] = entry

    return list(seen.values())
