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

    def test_postgres_connection_errors_do_not_fall_back_to_sqlite(self):
        with patch("database.DATABASE_URL", "postgresql://example.invalid/db"):
            with patch("database.psycopg.connect", side_effect=RuntimeError("connection failed")):
                with patch("database.sqlite3.connect") as sqlite_connect:
                    with self.assertRaisesRegex(RuntimeError, "connection failed"):
                        get_db()
                    sqlite_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
