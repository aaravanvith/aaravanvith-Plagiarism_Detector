"""Create additive repository tables without altering legacy report data.

Run from ``backend`` with ``python scripts/migrate.py``. SQLAlchemy's
``create_all`` only creates missing tables, so existing SQLite data is kept.
"""
from app.database import init_db


if __name__ == "__main__":
    init_db()
    print("Database schema is up to date.")
