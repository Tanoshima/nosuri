"""Shared pytest fixtures."""
from __future__ import annotations

import os

import psycopg2
import pytest


@pytest.fixture
def pg_conn():
    """Open a connection to the dev DB and roll back every test."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    conn = psycopg2.connect(url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
