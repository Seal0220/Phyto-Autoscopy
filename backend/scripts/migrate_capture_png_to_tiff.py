"""Convert indexed capture PNGs to lossless TIFF without deleting originals.

Run with no flags for a read-only plan. Stop the backend before --apply.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from _bootstrap import bootstrap

bootstrap()

from app.hardware.cameras.camera_image import encode_lossless_image  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_NAMES = ("metadata.csv", "record.log.csv")
MODE_INDEX_NAMES = ("metadata.csv", "mode.log.csv")


def _inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def _record_directory(raw_path: str, captures_root: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        resolved = path.resolve()
    elif len(path.parts) >= 3 and path.parts[:2] == ("data", "captures"):
        resolved = (captures_root / Path(*path.parts[2:])).resolve()
    else:
        resolved = (PROJECT_ROOT / path).resolve()
    if not _inside(captures_root, resolved):
        raise ValueError(f"Record outside captures directory: {resolved}")
    return resolved


def _resolve_capture(record_dir: Path, value: object) -> Path | None:
    text = str(value or "").strip()
    if not text or Path(text).suffix.lower() != ".png":
        return None
    candidate = Path(text)
    result = (candidate if candidate.is_absolute() else record_dir / candidate).resolve()
    if not _inside(record_dir, result):
        raise ValueError(f"Capture path leaves its record: {text}")
    return result


def _csv_paths(record_dir: Path) -> list[Path]:
    paths = [record_dir / name for name in INDEX_NAMES]
    modes_dir = record_dir / "modes"
    if modes_dir.is_dir():
        for mode_dir in modes_dir.iterdir():
            if mode_dir.is_dir():
                paths.extend(mode_dir / name for name in MODE_INDEX_NAMES)
    return [path for path in paths if path.is_file()]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def _render_csv(path: Path, record_dir: Path, converted: set[Path]) -> bytes | None:
    fields, rows = _read_csv(path)
    changed = False
    for row in rows:
        image_path = _resolve_capture(record_dir, row.get("file_path"))
        if image_path not in converted:
            continue
        old_value = str(row["file_path"])
        row["file_path"] = str(Path(old_value).with_suffix(".tiff"))
        if "image_name" in fields and row.get("image_name"):
            row["image_name"] = Path(str(row["image_name"])).with_suffix(".tiff").name
        changed = True
    if not changed:
        return None
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    # StorageService writes BOM for mode indexes and capture logs.
    prefix = "\ufeff" if path.name != "metadata.csv" or path.parent != record_dir else ""
    return (prefix + output.getvalue()).encode("utf-8")


def _update_image_patterns(value: object) -> tuple[object, bool]:
    if isinstance(value, dict):
        result = {}
        changed = False
        for key, item in value.items():
            if key == "image_pattern" and isinstance(item, str) and item.endswith(".png"):
                result[key] = item[:-4] + ".tiff"
                changed = True
            else:
                result[key], nested = _update_image_patterns(item)
                changed |= nested
        return result, changed
    if isinstance(value, list):
        items = []
        changed = False
        for item in value:
            updated, nested = _update_image_patterns(item)
            items.append(updated)
            changed |= nested
        return items, changed
    return value, False


def _render_config(path: Path) -> bytes | None:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    updated, changed = _update_image_patterns(payload)
    if not changed:
        return None
    return (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _decode(path: Path):
    import cv2
    import numpy as np

    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Image could not be decoded: {path}")
    return image


def _convert_image(source: Path) -> None:
    import cv2
    import numpy as np

    destination = source.with_suffix(".tiff")
    original = _decode(source)
    if destination.exists():
        converted = _decode(destination)
    else:
        encoded = encode_lossless_image(original, cv2_module=cv2)
        # Decode in memory before writing to catch an unsupported TIFF encoder.
        converted = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if converted is None or not np.array_equal(original, converted):
        raise ValueError(f"TIFF pixels differ from PNG: {source}")
    if destination.exists():
        return
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _capture_rows(connection: sqlite3.Connection, captures_root: Path) -> list[sqlite3.Row]:
    rows = connection.execute(
        """SELECT captures.id, captures.record_id, captures.file_path,
                  records.record_path
           FROM captures JOIN records USING (record_id)
           WHERE captures.status = 'success' AND lower(captures.file_path) LIKE '%.png'"""
    ).fetchall()
    for row in rows:
        _record_directory(row["record_path"], captures_root)
    return rows


def _plan(
    connection: sqlite3.Connection,
    captures_root: Path,
) -> tuple[set[Path], list[sqlite3.Row], dict[Path, Path]]:
    database_rows = _capture_rows(connection, captures_root)
    record_dirs = set()
    for path in captures_root.iterdir():
        if path.is_dir() and (path / "metadata.csv").is_file():
            resolved = path.resolve()
            if not _inside(captures_root, resolved):
                raise ValueError(f"Record link leaves captures directory: {path}")
            record_dirs.add(resolved)
    for row in database_rows:
        record_dirs.add(_record_directory(row["record_path"], captures_root))
    images: set[Path] = set()
    owner: dict[Path, Path] = {}
    for record_dir in record_dirs:
        for index_path in _csv_paths(record_dir):
            _, rows = _read_csv(index_path)
            for row in rows:
                path = _resolve_capture(record_dir, row.get("file_path"))
                if path is not None and str(row.get("status", "success")).lower() == "success":
                    images.add(path)
                    owner[path] = record_dir
    for row in database_rows:
        record_dir = _record_directory(row["record_path"], captures_root)
        path = _resolve_capture(record_dir, row["file_path"])
        if path is not None:
            images.add(path)
            owner[path] = record_dir
    for path in images:
        if not path.is_file():
            raise FileNotFoundError(f"Indexed PNG does not exist: {path}")
    return images, database_rows, owner


def _stage_file(path: Path, contents: bytes) -> Path:
    staged = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    staged.write_bytes(contents)
    return staged


def migrate(data_root: Path, *, apply: bool) -> None:
    data_root = data_root.resolve()
    captures_root = (data_root / "captures").resolve()
    database_path = data_root / "database" / "phyto_autoscopy.sqlite3"
    if not captures_root.is_dir() or not database_path.is_file():
        raise FileNotFoundError("Capture directory or SQLite database is missing")

    connection_target = (
        database_path.as_uri() + "?mode=ro"
        if not apply else str(database_path)
    )
    with sqlite3.connect(
        connection_target,
        timeout=1,
        isolation_level=None,
        uri=not apply,
    ) as connection:
        connection.row_factory = sqlite3.Row
        images, database_rows, owner = _plan(connection, captures_root)
        print(f"Indexed PNGs: {len(images)}; SQLite rows: {len(database_rows)}")
        if not images:
            return
        existing_bytes = sum(path.stat().st_size for path in images)
        print(f"PNG bytes: {existing_bytes:,}; originals will be retained")
        if not apply:
            print("Dry run only. Stop backend and rerun with --apply to convert.")
            return

        missing_tiffs = [path for path in images if not path.with_suffix(".tiff").exists()]
        free_bytes = shutil.disk_usage(data_root).free
        estimated_bytes = sum(path.stat().st_size for path in missing_tiffs) * 2
        if free_bytes < estimated_bytes:
            raise OSError(
                f"Not enough free space for TIFF copies and backup: need roughly "
                f"{estimated_bytes:,} bytes; available {free_bytes:,}"
            )

        backup_dir = data_root / "migration-backups" / (
            "png-to-tiff-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        backup_dir.mkdir(parents=True)
        with sqlite3.connect(backup_dir / database_path.name) as backup:
            connection.backup(backup)
        print(f"Backup: {backup_dir}")

        # Keep the exclusive transaction throughout conversion: no live writer may
        # change indexes between the plan and the SQLite/CSV switch.
        connection.execute("BEGIN EXCLUSIVE")
        staged_files: dict[Path, Path] = {}
        replaced_files: list[Path] = []
        try:
            converted: set[Path] = set()
            for number, source in enumerate(sorted(images), start=1):
                _convert_image(source)
                converted.add(source)
                if number % 100 == 0 or number == len(images):
                    print(f"Verified {number}/{len(images)} TIFF images")

            for record_dir in sorted(set(owner.values())):
                for path in _csv_paths(record_dir):
                    contents = _render_csv(path, record_dir, converted)
                    if contents is not None:
                        staged_files[path] = _stage_file(path, contents)
                config_paths = [record_dir / "config.json"]
                modes_dir = record_dir / "modes"
                if modes_dir.is_dir():
                    config_paths.extend(modes_dir.glob("*/config.json"))
                for path in config_paths:
                    if path.is_file():
                        contents = _render_config(path)
                        if contents is not None:
                            staged_files[path] = _stage_file(path, contents)

            for row in database_rows:
                record_dir = _record_directory(row["record_path"], captures_root)
                source = _resolve_capture(record_dir, row["file_path"])
                if source not in converted:
                    continue
                updated_path = str(Path(row["file_path"]).with_suffix(".tiff"))
                cursor = connection.execute(
                    "UPDATE captures SET file_path=? WHERE id=? AND file_path=?",
                    (updated_path, row["id"], row["file_path"]),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Capture row changed during migration: {row['id']}")

            for path in staged_files:
                relative = path.relative_to(captures_root)
                backup_path = backup_dir / "captures" / relative
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_path)
            for path, staged in staged_files.items():
                staged.replace(path)
                replaced_files.append(path)
            connection.commit()
        except Exception:
            connection.rollback()
            for path in replaced_files:
                backup_path = backup_dir / "captures" / path.relative_to(captures_root)
                shutil.copy2(backup_path, path)
            raise
        finally:
            for staged in staged_files.values():
                staged.unlink(missing_ok=True)

        print(f"Done: {len(images)} PNGs indexed as TIFF; originals and backup retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root", type=Path, default=PROJECT_ROOT / "data",
        help="Project data directory containing captures/ and database/",
    )
    parser.add_argument("--apply", action="store_true", help="Perform conversion")
    args = parser.parse_args()
    migrate(args.data_root, apply=args.apply)
