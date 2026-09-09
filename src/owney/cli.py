"""CLI entrypoints for Owney keepers."""

from __future__ import annotations

import sys

import typer

from owney.keeper import KeeperFailure, list_proxies, log_keeper_fail, run_keeper

app = typer.Typer(
    name="owney",
    help="Owney USDC/WETH Orion strategist keeper",
    no_args_is_help=True,
)


def _run(asset: str) -> None:
    try:
        run_keeper(asset=asset)
    except KeeperFailure:
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001
        log_keeper_fail("fatal", {"message": str(exc) or type(exc).__name__})
        raise SystemExit(1) from exc


@app.command("usdc")
def usdc() -> None:
    """Run Owney USDC denomination keeper."""
    _run("usdc")


@app.command("weth")
def weth() -> None:
    """Run Owney WETH denomination keeper."""
    _run("weth")


@app.command("list-proxies")
def list_proxies_cmd() -> None:
    """Print OrionConfig UniverseProxy whitelist (mainnet ↔ Sepolia)."""
    try:
        list_proxies()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    app()
