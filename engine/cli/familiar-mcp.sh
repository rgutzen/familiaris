#!/usr/bin/env bash
# familiar-mcp.sh — launch the L1 MCP server (journal_search + grep) on
# stdio. A standalone entry point, not a back-end verb: the main
# script is invoked by every harness hook on whatever bare `python3` is first
# on PATH and must stay stdlib-only (journal_index.py's own rule), while this
# server genuinely needs the `mcp` SDK. `uv run --with mcp` keeps that
# dependency out of the hook-latency path entirely.
#
# See ROADMAP.md Track L, L1 and memory/knowledge/system/knowledge/journal-index.md.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --with mcp python3 "$HERE/../context/mcp_server.py"
