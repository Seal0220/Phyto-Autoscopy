from __future__ import annotations

from _bootstrap import bootstrap

bootstrap()

from app.core.config import load_settings
from app.database.connection import Database
from app.database.schema import initialize_schema


def main() -> None:
    settings = load_settings()
    database = Database(settings.paths.database_path)
    initialize_schema(database)
    database.close()
    print(f"Initialized {settings.paths.database_path}")


if __name__ == "__main__":
    main()
