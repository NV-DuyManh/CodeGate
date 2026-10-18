"""Exercise model registration in fresh interpreters after separating SQL types."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("first_module", ["analysis", "testing", "policy", "repository", "pull_request"])
def test_model_import_order_preserves_mapping_and_json_types(first_module):
    script = f"""
import importlib
importlib.import_module('codegate.database.models.{first_module}')
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import configure_mappers
from codegate.database.base import Base
from codegate.database.types import JSONType
from codegate.database.models.analysis import JSONType as LegacyJSONType
configure_mappers()
assert LegacyJSONType is JSONType
assert JSONType().compile(dialect=postgresql.dialect()) == 'JSONB'
assert JSONType().compile(dialect=sqlite.dialect()) == 'JSON'
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
assert 'analysis_runs' in Base.metadata.tables
assert 'test_runs' in Base.metadata.tables
Base.metadata.drop_all(engine)
engine.dispose()
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, timeout=30)
