"""STS2AIMCP game bridge normalization and HTTP MCP client."""

from __future__ import annotations

from spiremind.bridge.client import PROTOCOL, MCPEnvironment, probe_bridge
from spiremind.bridge.normalize import norm_id, normalize

__all__ = ["MCPEnvironment", "PROTOCOL", "norm_id", "normalize", "probe_bridge"]
