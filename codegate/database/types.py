"""Shared SQL types without dependencies on ORM model modules."""

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import JSON


class JSONType(JSON):
    """Use JSONB on PostgreSQL and JSON on other database engines."""


@compiles(JSONType, "postgresql")
def compile_json_type(type_, compiler, **kwargs):
    return "JSONB"
