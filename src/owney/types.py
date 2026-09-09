"""Shared types for Owney keeper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OwneyDenomination = Literal["usdc", "weth"]


@dataclass(frozen=True)
class ReplicaProxy:
    sepolia_proxy: str
    mainnet_source: str
    name: str
