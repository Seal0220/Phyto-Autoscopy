from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from uuid import uuid4


PATH_KEYS = (
    "captures_dir",
    "snapshots_dir",
    "calibration_dir",
    "analysis_dir",
    "database_path",
    "logs_dir",
    "temp_dir",
)
TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}
REPOSITORY_DATA_DIRECTORIES = (
    "captures",
    "snapshots",
    "calibration",
    "analysis",
    "database",
    "logs",
    "temp",
)


class MoveDataError(RuntimeError):
    pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="完整搬移 Phyto-Autoscopy 資料根目錄。",
    )
    parser.add_argument(
        "target",
        help="新的資料根目錄絕對路徑。",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def load_path_configuration(
    config_path: Path,
) -> tuple[dict, dict[str, Path]]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MoveDataError(f"找不到設定檔：{config_path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise MoveDataError(f"無法讀取設定檔：{error}") from error

    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise MoveDataError("default.json 缺少 paths 設定。")

    resolved: dict[str, Path] = {}
    for key in PATH_KEYS:
        value = paths.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MoveDataError(f"default.json 缺少有效的 {key}。")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise MoveDataError(f"{key} 必須是絕對路徑：{value}")
        resolved[key] = path.resolve()

    return payload, resolved


def configured_data_root(paths: dict[str, Path]) -> Path:
    root = paths["captures_dir"].parent.resolve()
    if root == Path(root.anchor):
        raise MoveDataError("拒絕把磁碟根目錄視為資料根目錄。")

    for key, path in paths.items():
        try:
            path.relative_to(root)
        except ValueError as error:
            raise MoveDataError(
                f"{key} 不在同一個資料根目錄內，無法完整搬移：{path}"
            ) from error
    return root


def validate_target(
    source: Path,
    raw_target: str,
) -> Path:
    target_path = Path(raw_target).expanduser()
    if not target_path.is_absolute():
        raise MoveDataError("--move-data 必須提供絕對路徑。")

    target = target_path.resolve()
    if target == Path(target.anchor):
        raise MoveDataError("拒絕使用磁碟根目錄作為資料根目錄。")
    if target == source:
        raise MoveDataError("指定位置已經是目前的資料根目錄。")

    try:
        target.relative_to(source)
    except ValueError:
        pass
    else:
        raise MoveDataError("目標位置不可位於目前資料根目錄內。")

    try:
        source.relative_to(target)
    except ValueError:
        pass
    else:
        raise MoveDataError("目標位置不可包含目前資料根目錄。")

    return target


def directory_has_user_data(path: Path) -> bool:
    if not path.exists():
        return False
    if not path.is_dir():
        raise MoveDataError(f"目標位置不是資料夾：{path}")

    for item in path.rglob("*"):
        if item.is_file() and item.name != ".gitkeep":
            return True
        if item.is_symlink():
            return True
    return False


def scan_source(source: Path) -> tuple[int, int]:
    if not source.exists() or not source.is_dir():
        raise MoveDataError(f"找不到目前的資料根目錄：{source}")

    file_count = 0
    total_bytes = 0
    for item in source.rglob("*"):
        if item.is_symlink():
            raise MoveDataError(f"資料目錄不可包含符號連結：{item}")
        if not item.is_file():
            continue
        file_count += 1
        total_bytes += item.stat().st_size
    return file_count, total_bytes


def ensure_database_is_idle(database_path: Path) -> None:
    if not database_path.exists():
        return

    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=rw",
            uri=True,
            timeout=0,
        )
        try:
            connection.execute("PRAGMA busy_timeout=0")
            checkpoint = connection.execute(
                "PRAGMA wal_checkpoint(FULL)"
            ).fetchone()
            if checkpoint and checkpoint[0]:
                raise MoveDataError("SQLite 仍在使用中，請先關閉後端服務。")
            connection.execute("BEGIN EXCLUSIVE")
            connection.rollback()
        finally:
            connection.close()
    except MoveDataError:
        raise
    except sqlite3.Error as error:
        raise MoveDataError(
            "無法鎖定 SQLite，請先關閉後端服務再搬移資料。"
        ) from error


def readable_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def copy_data_tree(
    source: Path,
    staging: Path,
    *,
    file_count: int,
    total_bytes: int,
) -> None:
    staging.mkdir(parents=False, exist_ok=False)
    copied_files = 0
    copied_bytes = 0
    last_reported_at = 0.0

    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = staging / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied_files += 1
        copied_bytes += item.stat().st_size

        current_time = time.monotonic()
        if (
            copied_files == file_count
            or current_time - last_reported_at >= 2.0
        ):
            print(
                "搬移進度："
                f"{copied_files}/{file_count} 個檔案，"
                f"{readable_size(copied_bytes)}/{readable_size(total_bytes)}",
                flush=True,
            )
            last_reported_at = current_time

    if copied_files != file_count or copied_bytes != total_bytes:
        raise MoveDataError(
            "搬移期間來源資料發生變動；已保留原資料並取消搬移。"
        )


def replacement_pairs(
    source: Path,
    target: Path,
) -> tuple[tuple[str, str], ...]:
    raw_source = str(source)
    raw_target = str(target)
    candidates = (
        (
            json.dumps(raw_source, ensure_ascii=False)[1:-1],
            json.dumps(raw_target, ensure_ascii=False)[1:-1],
        ),
        (source.as_posix(), target.as_posix()),
        (raw_source, raw_target),
    )
    unique: dict[str, str] = {}
    for old, new in candidates:
        if old and old != new:
            unique[old] = new
    return tuple(
        sorted(
            unique.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def rewrite_text_paths(
    root: Path,
    replacements: tuple[tuple[str, str], ...],
) -> int:
    changed_files = 0
    byte_replacements = tuple(
        (old.encode("utf-8"), new.encode("utf-8"))
        for old, new in replacements
    )

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            original = path.read_bytes()
        except OSError as error:
            raise MoveDataError(f"無法讀取資料檔案：{path}") from error

        updated = original
        for old, new in byte_replacements:
            updated = updated.replace(old, new)
        if updated == original:
            continue

        temporary = path.with_name(f".{path.name}.relocating-{uuid4().hex}")
        try:
            temporary.write_bytes(updated)
            shutil.copystat(path, temporary)
            os.replace(temporary, path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise MoveDataError(f"無法更新資料檔案路徑：{path}") from error
        changed_files += 1

    return changed_files


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def rewrite_sqlite_paths(
    database_path: Path,
    replacements: tuple[tuple[str, str], ...],
) -> int:
    changed_values = 0
    try:
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA busy_timeout=0")
            connection.execute("PRAGMA wal_checkpoint(FULL)")
            connection.execute("BEGIN IMMEDIATE")
            tables = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            for (table_name,) in tables:
                quoted_table = quote_identifier(table_name)
                columns = connection.execute(
                    f"PRAGMA table_info({quoted_table})"
                ).fetchall()
                for column in columns:
                    column_name = column[1]
                    quoted_column = quote_identifier(column_name)
                    for old, new in replacements:
                        cursor = connection.execute(
                            f"""
                            UPDATE {quoted_table}
                            SET {quoted_column}=replace({quoted_column}, ?, ?)
                            WHERE typeof({quoted_column})='text'
                              AND instr({quoted_column}, ?) > 0
                            """,
                            (old, new, old),
                        )
                        changed_values += max(0, cursor.rowcount)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise MoveDataError(f"無法更新 SQLite 內的資料路徑：{database_path}") from error
    return changed_values


def rewrite_data_paths(
    root: Path,
    source: Path,
    target: Path,
) -> tuple[int, int]:
    replacements = replacement_pairs(source, target)
    changed_text_files = rewrite_text_paths(root, replacements)
    changed_database_values = 0
    for database_path in root.rglob("*.sqlite3"):
        changed_database_values += rewrite_sqlite_paths(
            database_path,
            replacements,
        )
    return changed_text_files, changed_database_values


def write_config_atomic(
    config_path: Path,
    payload: dict,
) -> None:
    temporary = config_path.with_name(
        f".{config_path.name}.relocating-{uuid4().hex}"
    )
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copystat(config_path, temporary)
        os.replace(temporary, config_path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise MoveDataError(f"無法更新設定檔：{config_path}") from error


def restore_repository_data_skeleton(project_root: Path) -> None:
    data_root = project_root / "data"
    for name in REPOSITORY_DATA_DIRECTORIES:
        directory = data_root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").touch(exist_ok=True)


def move_data(
    project_root: Path,
    raw_target: str,
) -> None:
    config_path = project_root / "backend" / "config" / "default.json"
    payload, configured_paths = load_path_configuration(config_path)
    source = configured_data_root(configured_paths)
    target = validate_target(source, raw_target)
    if directory_has_user_data(target):
        raise MoveDataError(f"目標資料夾已有資料，拒絕覆蓋：{target}")

    file_count, total_bytes = scan_source(source)
    ensure_database_is_idle(configured_paths["database_path"])

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    free_bytes = shutil.disk_usage(target.parent).free
    required_free_bytes = total_bytes + max(
        64 * 1024 * 1024,
        total_bytes // 20,
    )
    if free_bytes < required_free_bytes:
        raise MoveDataError(
            "目標磁碟空間不足："
            f"需要至少 {readable_size(required_free_bytes)}，"
            f"目前可用 {readable_size(free_bytes)}。"
        )

    staging = target.parent / f".{target.name}.moving-{uuid4().hex}"
    relative_paths = {
        key: path.relative_to(source)
        for key, path in configured_paths.items()
    }
    print(f"目前位置：{source}")
    print(f"目標位置：{target}")
    print(
        f"準備搬移 {file_count} 個檔案，共 {readable_size(total_bytes)}。",
        flush=True,
    )

    finalized = False
    try:
        copy_data_tree(
            source,
            staging,
            file_count=file_count,
            total_bytes=total_bytes,
        )
        changed_files, changed_values = rewrite_data_paths(
            staging,
            source,
            target,
        )
        staging.rename(target)
        finalized = True

        updated_paths = payload["paths"]
        for key, relative in relative_paths.items():
            updated_paths[key] = (target / relative).resolve().as_posix()
        write_config_atomic(config_path, payload)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if finalized and target.exists():
            shutil.rmtree(target, ignore_errors=True)
        raise

    try:
        shutil.rmtree(source)
    except OSError as error:
        raise MoveDataError(
            "新資料位置與設定已完成，但舊資料夾無法刪除："
            f"{source}。請確認新位置可正常使用後手動刪除。"
        ) from error

    if source == (project_root / "data").resolve():
        restore_repository_data_skeleton(project_root)

    print(f"已更新文字資料檔案：{changed_files} 個。")
    print(f"已更新 SQLite 路徑欄位：{changed_values} 筆。")
    print(f"資料已完整移動至：{target}")
    print("請手動重新啟動服務以使用新的資料位置。")


def main() -> int:
    arguments = parse_arguments()
    try:
        move_data(
            arguments.project_root.resolve(),
            arguments.target,
        )
    except MoveDataError as error:
        print(f"搬移失敗：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "搬移已取消；請保留原資料，並刪除目標旁名稱含 .moving- 的暫存資料夾後重試。",
            file=sys.stderr,
        )
        return 130
    except (OSError, ValueError) as error:
        print(f"搬移失敗：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
