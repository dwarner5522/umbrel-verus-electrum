# umbrel-verus-electrum

Docker image for the **Verus Electrum Server** umbrelOS app: [ElectrumX for Verus](https://github.com/VerusCoin/electrumx) plus a small status page. It indexes the blockchain of a Verus node (`verusd`) so lite wallets can use your own Electrum server.

## What is in the image

- **ElectrumX**: `VerusCoin/electrumx` at a pinned commit (ElectrumX 1.8.6), with one fix in `patches/verus-hash-v2b2.patch`. Without it the server computes wrong block hashes from block 1,053,660 on (VerusHash 2.2 and PBaaS headers) and cannot follow the current chain.
- **VerusHash**: the native module from `VerusCoin/verushashpy` at a pinned commit, built with `verushash/setup.py` (no `-march=native`, system libsodium). `verushash/arm_compat.py` makes it compile on arm64. It is *not* installed from PyPI: the `verushash` package there is unrelated.
- **`app/supervisor.py`**: runs ElectrumX, restarts it if it exits, and serves the status page, its API and the Umbrel widget. Standard library only.
- **`tests/selftest.py`**: runs during the image build. It checks block hashes and txids for real mainnet blocks from every header generation, on each architecture, so a broken hash module fails the build.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DAEMON_HOST` | required | hostname of the Verus node |
| `DAEMON_RPC_USER` / `DAEMON_RPC_PASS` | required | `verusd` RPC credentials |
| `DAEMON_RPC_PORT` | `27486` | `verusd` RPC port |
| `ELECTRUM_PORT` | `17485` | Electrum TCP port for wallets |
| `CACHE_MB` | `800` | ElectrumX cache size while indexing |
| `DEVICE_DOMAIN_NAME` | none | hostname shown in the connection details |
| `PORT` | `3000` | status page port |

The index lives in `/data/db`. The node must run with `txindex=1` (the Verus default).

The server speaks plain TCP only (Electrum protocol 1.1 to 1.4). It is meant for a home network; put it behind a TLS proxy or VPN before exposing it further.

## Publish

Pushing a `v*` tag runs `.github/workflows/build.yml`, which builds `linux/amd64` and `linux/arm64` and pushes `ghcr.io/<owner>/umbrel-verus-electrum:<tag>`. The workflow summary prints the `image:tag@sha256:digest` reference for the app's `docker-compose.yml`.

## Credits

ElectrumX by Neil Booth and contributors (MIT); Verus support by the Verus developers. The Verus logo is from [VerusCoin/Media-Assets](https://github.com/VerusCoin/Media-Assets) (MIT, © 2020 Max Theyse).
