"""Shared validator infrastructure: robust parser + end-to-end client."""

from validator_core.client import ClientConfig, ValidateResult, validate_items
from validator_core.parser import ValidatorParseResult, parse_validator_response

__all__ = [
    "ClientConfig",
    "ValidateResult",
    "ValidatorParseResult",
    "parse_validator_response",
    "validate_items",
]
