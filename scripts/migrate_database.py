"""Run the idempotent additive v2 migration and retain a pre-upgrade SQLite backup."""
from config.settings import Settings
from database.store import Database


if __name__ == "__main__":
    settings = Settings()
    database = Database(settings.data_dir / "metadata.sqlite3")
    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    print(f"Database schema is v{version}; preserved {len(database.documents())} indexed documents.")
    print(f"Pre-v2 backup: {database.path.with_name(database.path.stem + '.pre-v2.sqlite3')}")
