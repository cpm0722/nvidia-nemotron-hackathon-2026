"""Silence NAT's 0.0.0.0-bind-without-auth warning inside compose.

Every A2A agent binds to 0.0.0.0:PORT so that cross-container DNS on the
ari-net bridge works; authentication is handled by the network boundary
(only e2e's port is published to the host). NAT emits a hardcoded
pydantic warning for this exact config — not actionable in our setup.

This module is auto-imported by Python's `site.py` at interpreter start
because it sits in site-packages, so the logger level is set before NAT's
validator runs.
"""
import logging

logging.getLogger("nat.plugins.a2a.server.front_end_config").setLevel(logging.ERROR)
