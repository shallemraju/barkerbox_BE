import unittest
from unittest.mock import patch

from database import _PostgresCursor, get_db


class RecordingCursor:
    def __init__(self):
        self.args = None

    def execute(self, *args):
        self.args = args


class DatabaseAdapterTests(unittest.TestCase):
    def test_postgres_cursor_translates_sqlite_placeholders_and_timestamps(self):
        raw_cursor = RecordingCursor()
        cursor = _PostgresCursor(raw_cursor)

        cursor.execute(
            "UPDATE orders SET updated_at = datetime('now') WHERE id = ?",
            ("order-1",),
        )

        self.assertEqual(
            raw_cursor.args,
            ("UPDATE orders SET updated_at = CURRENT_TIMESTAMP::text WHERE id = %s", ("order-1",)),
        )

    def test_unavailable_postgres_driver_falls_back_to_sqlite(self):
        original_import = __import__

        def import_without_psycopg(name, *args, **kwargs):
            if name == "psycopg" or name.startswith("psycopg."):
                raise ImportError("PostgreSQL driver is unavailable")
            return original_import(name, *args, **kwargs)

        with patch("database.DATABASE_URL", "postgresql://example.invalid/db"):
            with patch("database._USE_SQLITE", False):
                with patch("builtins.__import__", side_effect=import_without_psycopg):
                    with patch("database.sqlite3.connect") as sqlite_connect:
                        self.assertIs(get_db(), sqlite_connect.return_value)
                        sqlite_connect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
