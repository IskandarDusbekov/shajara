#!/usr/bin/env bash
# e-Shajara'ni GitHub'dagi oxirgi versiyaga yangilash.
# Ishlatish (serverda):  sudo /srv/e-shajara/deploy/update.sh
set -euo pipefail

APP_DIR=/srv/e-shajara
APP_USER=eshajara
SERVICE=e-shajara

as_app() { sudo -u "$APP_USER" -H bash -c "cd $APP_DIR && $*"; }

echo "==> Yangilanishdan oldin zaxira nusxa"
as_app "deploy/backup.sh"

echo "==> Kodni tortish"
as_app "git pull --ff-only"

echo "==> Kutubxonalar"
as_app "venv/bin/pip install --quiet -r requirements.txt"

echo "==> Ma'lumotlar bazasi migratsiyalari"
as_app "DJANGO_DEBUG=0 venv/bin/python manage.py migrate --noinput"

echo "==> Statik fayllar"
as_app "DJANGO_DEBUG=0 venv/bin/python manage.py collectstatic --noinput --verbosity 0"

echo "==> Tekshiruv"
as_app "DJANGO_DEBUG=0 venv/bin/python manage.py check --deploy --fail-level ERROR"

echo "==> Qayta ishga tushirish"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager --lines=0 status "$SERVICE"
echo "Tayyor."
