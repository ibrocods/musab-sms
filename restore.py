import shutil
import sys
import datetime
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "db.sqlite3"

if len(sys.argv) != 2:
    print("Usage: python restore.py backups\\db_YYYYMMDD_HHMMSS.sqlite3")
    sys.exit(1)

backup = pathlib.Path(sys.argv[1])
if not backup.exists():
    print(f"Backup not found: {backup}")
    sys.exit(1)

# Keep a copy of the current database before overwriting it
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
safety = BASE / "backups" / f"before_restore_{stamp}.sqlite3"
if DB.exists():
    shutil.copy2(DB, safety)
    print(f"Current database saved to {safety}")

shutil.copy2(backup, DB)
print(f"Restored from {backup}")