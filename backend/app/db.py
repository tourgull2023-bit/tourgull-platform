"""Shared database engine and metadata for the Tourgull modular monolith."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    """Read credentials at runtime; never commit them to source control."""
    return os.environ['DATABASE_URL']


def create_db_engine():
    return create_engine(database_url(), pool_pre_ping=True)
