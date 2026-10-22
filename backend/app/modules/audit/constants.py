"""Audit constants (Data Model §4.18, D-12)."""

from __future__ import annotations

from enum import StrEnum

TABLE_NAME = "audit_event"


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"


# Column limits, shared by the model, the migration and the input schema.
ENTITY_TYPE_MAX = 64
ENTITY_ID_MAX = 128
EVENT_TYPE_MAX = 64
ACTOR_TYPE_MAX = 32
ACTOR_ID_MAX = 128
CORRELATION_ID_MAX = 64
REASON_CODE_MAX = 64
DETAILS_REFERENCE_MAX = 512
DETAILS_MAX_KEYS = 32
DETAILS_MAX_STRING = 256
