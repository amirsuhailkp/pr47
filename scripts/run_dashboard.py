"""Runs the read-only web dashboard (dashboard/app.py).

Usage:
    python -m scripts.run_dashboard                 # 0.0.0.0:8080
    python -m scripts.run_dashboard --port 8090

On Azure: this binds 0.0.0.0 so it's reachable on the VM's public IP, per your
choice to skip auth/tunneling. You'll also need to allow the port through the VM's
Network Security Group (Azure Portal -> VM -> Networking -> add an inbound rule for
this port) — the OS listening on it isn't enough by itself.

This is a second, independent process from scripts/run_service.py — it does not read
its state, and running it costs a little extra idle RAM (a small FastAPI/uvicorn
process) alongside the existing service. On a 1 GiB VM that's fine, but if you ever
add real weight to this (auth, caching, more routes), keep an eye on `free -h`.
"""
from __future__ import annotations

import argparse

import uvicorn


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DataBroker dashboard.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, log_level="info")
