from __future__ import annotations

from app.core.config import load_settings


def main() -> None:
    settings = load_settings()
    print(settings.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
