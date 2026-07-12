import sqlite3
import glob
import os
import sys

def dump_sqlite_to_file(db_path, out_path):
    conn = sqlite3.connect(db_path)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()

def main():
    os.makedirs("backups/sqlite_dumps", exist_ok=True)
    patterns = ["data/*.sqlite3", "data/*.db"]
    found = False
    for pattern in patterns:
        for db in glob.glob(pattern):
            found = True
            base = os.path.basename(db)
            out = os.path.join("backups/sqlite_dumps", f"{base}.sql")
            print(f"Exporting {db} -> {out}")
            dump_sqlite_to_file(db, out)
    if not found:
        print("No SQLite files found in data/ (patterns: data/*.sqlite3, data/*.db)")

if __name__ == "__main__":
    main()
