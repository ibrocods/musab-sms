import sqlite3
import datetime
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "db.sqlite3"
BACKUP_DIR = BASE / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
dest = BACKUP_DIR / f"db_{stamp}.sqlite3"

# sqlite3's backup() makes a consistent copy, even if the server is running
with sqlite3.connect(DB) as src, sqlite3.connect(dest) as dst:
    src.backup(dst)

print(f"Backup saved to {dest}")