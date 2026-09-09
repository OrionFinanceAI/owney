# Owney

Python keeper for Orion **Owney USDC** and **Owney WETH** vaults.

Pipeline:

1. Call Zyfai `simulateBestPositions` for `USDC` or `WETH` (mainnet)
2. Compress deposit addresses → percent weights (sum 100)
3. Map mainnet product addresses → Sepolia `UniverseProxy` replicas
4. Park unmapped weight on the idle USDC/WETH replica
5. Submit via [`orion-finance-sdk-py`](https://github.com/OrionFinanceAI/orion-finance-sdk-py) (`validate_order` → `strategist.submit_intent`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill RPC, vaults, keys, OWNEY_API_KEY
```

For a local editable Orion SDK:

```bash
pip install -e ../orion-finance-sdk-py
pip install -e ".[dev]"
```

## Run

```bash
# Live dry-run (map + print, no submit)
DRY_RUN=1 python -m owney usdc
DRY_RUN=1 python -m owney weth

# Mock whitelist intent (no Zyfai key)
DRY_RUN=1 OWNEY_MOCK=1 python -m owney usdc

# Submit
python -m owney usdc
python -m owney weth

# Debug whitelist
python -m owney list-proxies
```

Or use the `owney` console script after install.

## Docker

```bash
docker build -t owney:latest .
docker run --rm --env-file .env owney:latest owney:usdc
docker run --rm --env-file .env -e DRY_RUN=1 -e OWNEY_MOCK=1 owney:latest owney:weth
```

## Env

| Variable | Required | Notes |
|----------|----------|-------|
| `RPC_URL` | yes | Sepolia RPC (`SEPOLIA_RPC_URL` also accepted) |
| `ORION_CONFIG_ADDRESS` | optional | Defaults inside Orion SDK |
| `OWNEY_USDC_VAULT_ADDRESS` / `OWNEY_WETH_VAULT_ADDRESS` | yes (unless dry-run) | Per denomination |
| `OWNEY_STRATEGIST_PRIVATE_KEY` | yes (unless dry-run) | Bridged to `STRATEGIST_PRIVATE_KEY` for the SDK |
| `OWNEY_API_KEY` | yes (unless `OWNEY_MOCK=1`) | Zyfai API key |
| `DRY_RUN=1` | optional | Print mapped intent only |
| `OWNEY_MOCK=1` | optional | Synthetic multi-leg intent from whitelist |
| `OWNEY_SIM_AMOUNT` | optional | Default `10000` |
| `OWNEY_SIM_STRATEGY` | optional | `aggressive` (default) or `conservative` |
| `OWNEY_SIM_MIN_SPLIT` | optional | Default `1` |

## Tests

```bash
pytest
```
