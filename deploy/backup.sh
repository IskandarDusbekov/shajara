#!/usr/bin/env bash
# Kunlik zaxira: ma'lumotlar bazasi (ishlab turgan paytda ham xavfsiz nusxa)
# va foydalanuvchi yuklagan rasmlar. 14 kundan eskisi o'chiriladi.
#
# cron (eshajara foydalanuvchisi):  30 3 * * * /srv/e-shajara/deploy/backup.sh
set -euo pipefail

APP_DIR=/srv/e-shajara
BACKUP_DIR=${BACKUP_DIR:-/srv/e-shajara/backups}
KEEP_DAYS=${KEEP_DAYS:-14}
STAMP=$(date +%Y-%m-%d_%H%M)

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if [ ! -f "$APP_DIR/db.sqlite3" ]; then
  echo "Baza hali yo'q — zaxira o'tkazib yuborildi."
  exit 0
fi

# SQLite'ning o'z backup API'si — yozilayotgan bazadan ham buzilmagan nusxa oladi.
"$APP_DIR/venv/bin/python" - "$APP_DIR/db.sqlite3" "$BACKUP_DIR/db_$STAMP.sqlite3" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
gzip -f "$BACKUP_DIR/db_$STAMP.sqlite3"

if [ -d "$APP_DIR/media" ]; then
  tar -czf "$BACKUP_DIR/media_$STAMP.tar.gz" -C "$APP_DIR" media
fi

find "$BACKUP_DIR" -type f -name 'db_*.sqlite3.gz' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'media_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "Zaxira tayyor: $BACKUP_DIR ($STAMP)"
