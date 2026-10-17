"""Create a consistent SQLite backup. Does not copy keys or overwrite existing files.

Usage: .venv/Scripts/python scripts/backup_pilot.py PATH_TO_NEW_BACKUP.db
Store the field-encryption key separately in the operator's protected secret store.
Restore only with all website/worker processes stopped; verify on an isolated instance first.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sme_copilot.config import get_settings  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def backup(destination):
    url = make_url(get_settings().db_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Use your database provider's native backup for non-SQLite deployments")
    source = Path(url.database).resolve()
    target = Path(destination).resolve()
    if target.exists() or source == target:
        raise ValueError("Choose a new backup filename; existing files will not be overwritten")
    if not source.is_file() or not target.parent.is_dir():
        raise ValueError("The source database and destination directory must already exist")
    # Exclusive creation also protects against another operator choosing the same file.
    with target.open("xb"):
        pass
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity check failed")
    except Exception:
        target.unlink(missing_ok=True)  # only the new file exclusively created above
        raise
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    print(backup(parser.parse_args().destination))
