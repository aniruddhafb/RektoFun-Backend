"""Utility functions for data serialization and coercion."""

from datetime import datetime
from uuid import UUID


def serialize_payload(data: dict) -> dict:
    """Convert datetime and UUID objects to strings for JSON serialization."""
    result = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, UUID):
            result[key] = str(value)
        else:
            result[key] = value
    return result
