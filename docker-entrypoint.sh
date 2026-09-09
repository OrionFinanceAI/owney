#!/usr/bin/env sh
set -e

case "$1" in
  owney:usdc|usdc)
    export OWNEY_ASSET=usdc
    exec python -m owney usdc
    ;;
  owney:weth|weth)
    export OWNEY_ASSET=weth
    exec python -m owney weth
    ;;
  list-proxies)
    exec python -m owney list-proxies
    ;;
  *)
    echo "usage: owney:usdc | owney:weth | list-proxies" >&2
    exit 1
    ;;
esac
