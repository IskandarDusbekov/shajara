# e-Shajara'ni VPS'ga joylash

Bu qo'llanma Ubuntu serverga, **boshqa sayt allaqachon ishlab turgan** holatda
e-Shajara'ni qo'shish uchun. Eski saytning sozlamalariga tegilmaydi: nginx
so'ralgan domenga qarab qaysi saytni ochishni o'zi ajratadi, e-Shajara esa port
emas, socket fayl orqali ishlaydi — portlar to'qnashmaydi.

Yakuniy tuzilma:

```
/srv/e-shajara/            ← loyiha (git clone)
├── .env                   ← maxfiy sozlamalar (chmod 600)
├── db.sqlite3             ← ma'lumotlar bazasi
├── media/                 ← yuklangan rasmlar
├── staticfiles/           ← collectstatic natijasi
├── backups/               ← kunlik zaxira nusxalar
├── venv/                  ← Python muhiti
└── deploy/                ← shu papka
nginx  ──(unix socket /run/e-shajara/gunicorn.sock)──>  gunicorn (3 worker)
```

Buyruqlar `sudo` huquqli foydalanuvchi bilan bajariladi.

---

## 0. Serverni tekshirish

```bash
lsb_release -a               # Ubuntu versiyasi
python3 --version            # 3.12 yoki yangi bo'lishi SHART (Django 6)
sudo ss -tlnp | grep -E ':80 |:443 '   # 80/443 portni kim egallagan: nginx yoki apache2
free -h && df -h /
```

- **Ubuntu 24.04** — Python 3.12 bor, davom eting.
- **Ubuntu 22.04** — Python 3.10, yangisini o'rnating:
  ```bash
  sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
  sudo apt install -y python3.12 python3.12-venv python3.12-dev
  ```
  va quyida `python3` o'rniga `python3.12` yozing.
- 80-portda **apache2** tursa — 9-bo'limning oxiridagi «Apache bo'lsa» qismini o'qing.

## 1. Domenni serverga yo'naltirish

Domen sotuvchisining DNS panelida:

| Turi | Nomi | Qiymati |
|---|---|---|
| A | `@` (e-shajara.uz) | server IP manzili |
| A | `www` | server IP manzili |

Tekshirish (bir necha daqiqadan bir necha soatgacha vaqt oladi):
```bash
dig +short e-shajara.uz
dig +short www.e-shajara.uz
```

## 2. Kerakli paketlar

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev build-essential \
    nginx certbot python3-certbot-nginx fonts-dejavu-core
```

`fonts-dejavu-core` — PDF kitobdagi o'zbekcha harflar (ʻ ʼ) to'g'ri chiqishi uchun.
Nginx allaqachon o'rnatilgan bo'lsa, apt uni qayta o'rnatmaydi va eski saytga tegmaydi.

## 3. Alohida foydalanuvchi va kod

Sayt o'z foydalanuvchisi nomidan ishlaydi — eski sayt fayllariga kira olmaydi.

```bash
sudo adduser --system --group --no-create-home --home /srv/e-shajara eshajara
sudo mkdir -p /srv/e-shajara
sudo chown eshajara:eshajara /srv/e-shajara
sudo chmod 755 /srv/e-shajara

sudo -u eshajara git clone https://github.com/IskandarDusbekov/shajara.git /srv/e-shajara
```

> Repozitoriy **yopiq (private)** bo'lsa, GitHub'da *Settings → Developer settings →
> Personal access tokens* orqali faqat o'qish huquqli token yarating va
> `https://<TOKEN>@github.com/IskandarDusbekov/shajara.git` ko'rinishida clone qiling.

## 4. Python muhiti

```bash
cd /srv/e-shajara
sudo -u eshajara python3 -m venv venv
sudo -u eshajara venv/bin/pip install --upgrade pip
sudo -u eshajara venv/bin/pip install -r requirements.txt
sudo chmod +x deploy/*.sh
```

## 5. `.env` sozlamalari

```bash
sudo -u eshajara cp .env.example .env
sudo chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # chiqqan kalitni nusxalang
sudo -u eshajara nano .env
```

Kamida shularni to'ldiring:

```
DJANGO_SECRET_KEY=<yuqorida chiqqan kalit>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=e-shajara.uz,www.e-shajara.uz
EMAIL_HOST_USER=<gmail manzil>
EMAIL_HOST_PASSWORD=<gmail app password>
DEFAULT_FROM_EMAIL=e-Shajara <gmail manzil>
```

Saqlash: `Ctrl+O`, `Enter`, chiqish: `Ctrl+X`.

## 6. Baza, statik fayllar, admin

```bash
cd /srv/e-shajara
sudo -u eshajara DJANGO_DEBUG=0 venv/bin/python manage.py migrate
sudo -u eshajara DJANGO_DEBUG=0 venv/bin/python manage.py collectstatic --noinput
sudo -u eshajara mkdir -p media
sudo chmod 600 db.sqlite3

# Boshqaruv paneliga kiradigan hisob (superadmin):
sudo -u eshajara DJANGO_DEBUG=0 venv/bin/python manage.py createsuperuser

# Ixtiyoriy: 3 ta namunaviy tarixiy xarita (Amir Temur, Buyuk ipak yo'li, Bobur)
sudo -u eshajara DJANGO_DEBUG=0 venv/bin/python manage.py seed_maps

# Tekshiruv — ERROR bo'lmasligi kerak (HSTS haqidagi ogohlantirishlar normal)
sudo -u eshajara DJANGO_DEBUG=0 venv/bin/python manage.py check --deploy
```

> ⚠️ `seed_regions` buyrug'ini **serverda ishlatmang** — u sinov uchun 42 ta soxta
> foydalanuvchi va shajara yaratadi.

## 7. Gunicorn servisi

```bash
sudo cp /srv/e-shajara/deploy/e-shajara.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now e-shajara
sudo systemctl status e-shajara          # "active (running)" bo'lishi kerak
ls -l /run/e-shajara/gunicorn.sock       # socket fayl paydo bo'lgan
```

## 8. Nginx

```bash
sudo cp /srv/e-shajara/deploy/nginx-e-shajara.conf /etc/nginx/sites-available/e-shajara
sudo ln -s /etc/nginx/sites-available/e-shajara /etc/nginx/sites-enabled/e-shajara
sudo nginx -t                  # "syntax is ok" va "test is successful"
sudo systemctl reload nginx
```

`reload` eski saytni to'xtatmaydi. Eski sayt ishlayotganini tekshiring:
```bash
curl -I https://ESKI-SAYT-DOMENI
```

## 9. HTTPS (bepul sertifikat)

```bash
sudo certbot --nginx -d e-shajara.uz -d www.e-shajara.uz
```

Email so'raydi, shartlarga rozilik, keyin «redirect» — **2 (Redirect)** ni tanlang.
Sertifikat har 90 kunda o'zi yangilanadi; tekshirish:

```bash
sudo certbot renew --dry-run
```

Brauzerda oching: **https://e-shajara.uz** → ro'yxatdan o'ting, menyudan
**Boshqaruv paneli** (superadmin hisobida) → **https://e-shajara.uz/boshqaruv/**.

Firewall yoqilgan bo'lsa (`sudo ufw status`):
```bash
sudo ufw allow 'Nginx Full'
```

### Apache bo'lsa (80-portni apache2 egallagan)

Ikkinchi veb-server qo'ymang — Apache'ning o'ziga e-Shajara uchun sayt qo'shing:

```bash
sudo a2enmod proxy proxy_http headers ssl rewrite
sudo nano /etc/apache2/sites-available/e-shajara.conf
```
```apache
<VirtualHost *:80>
    ServerName e-shajara.uz
    ServerAlias www.e-shajara.uz
    LimitRequestBody 26214400
    Alias /static/ /srv/e-shajara/staticfiles/
    Alias /media/  /srv/e-shajara/media/
    <Directory /srv/e-shajara/staticfiles> Require all granted </Directory>
    <Directory /srv/e-shajara/media> Require all granted </Directory>
    ProxyPass /static/ !
    ProxyPass /media/ !
    ProxyPass        / unix:/run/e-shajara/gunicorn.sock|http://localhost/ timeout=120
    ProxyPassReverse / unix:/run/e-shajara/gunicorn.sock|http://localhost/
    RequestHeader set X-Forwarded-Proto expr=%{REQUEST_SCHEME}
    RequestHeader set X-Real-IP expr=%{REMOTE_ADDR}
</VirtualHost>
```
```bash
sudo a2ensite e-shajara && sudo apache2ctl configtest && sudo systemctl reload apache2
sudo apt install -y python3-certbot-apache
sudo certbot --apache -d e-shajara.uz -d www.e-shajara.uz
```
(Apache `www-data` guruhida — socket huquqlari shunga mos.)

## 10. Kunlik zaxira

```bash
sudo -u eshajara /srv/e-shajara/deploy/backup.sh      # bir marta qo'lda sinab ko'ring
sudo crontab -u eshajara -e
```
Oxiriga qo'shing (har kuni soat 03:30):
```
30 3 * * * /srv/e-shajara/deploy/backup.sh >/dev/null 2>&1
```

Zaxiralar `/srv/e-shajara/backups/` da, 14 kun saqlanadi. Server buzilsa ular ham
yo'qoladi — vaqti-vaqti bilan o'z kompyuteringizga ko'chirib oling:

```bash
# o'z kompyuteringizda:
scp -r USER@SERVER_IP:/srv/e-shajara/backups ./eshajara-backups
```

## 11. Yangilash (kodga o'zgarish kiritgandan keyin)

Kompyuterda `git push`, so'ng serverda:

```bash
sudo /srv/e-shajara/deploy/update.sh
```

Skript: zaxira → `git pull` → kutubxonalar → migratsiya → collectstatic → tekshiruv → qayta ishga tushirish.

## 12. Kompyuterdagi ma'lumotlarni ko'chirish (ixtiyoriy)

Yangi, bo'sh sayt bilan boshlash tavsiya etiladi (lokal bazada sinov hisoblari bor).
Baribir ko'chirmoqchi bo'lsangiz — 6-bo'limdagi `migrate`dan **oldin**:

```bash
# o'z kompyuteringizdan:
scp db.sqlite3 USER@SERVER_IP:/tmp/
scp -r media USER@SERVER_IP:/tmp/

# serverda:
sudo systemctl stop e-shajara 2>/dev/null || true
sudo mv /tmp/db.sqlite3 /srv/e-shajara/db.sqlite3
sudo rm -rf /srv/e-shajara/media && sudo mv /tmp/media /srv/e-shajara/media
sudo chown -R eshajara:eshajara /srv/e-shajara/db.sqlite3 /srv/e-shajara/media
sudo chmod 600 /srv/e-shajara/db.sqlite3
```
So'ng 6-bo'limni davom ettiring (`migrate` yetishmayotgan o'zgarishlarni qo'shadi).

---

## Muammo bo'lsa

| Belgi | Qayerga qarash / yechim |
|---|---|
| **502 Bad Gateway** | `sudo systemctl status e-shajara` va `sudo journalctl -u e-shajara -n 100`. Ko'pincha `.env` xatosi yoki kutubxona o'rnatilmagan. |
| `DJANGO_SECRET_KEY is empty` | `.env` da kalit yo'q yoki fayl `/srv/e-shajara/.env` da emas. |
| **400 Bad Request** | `DJANGO_ALLOWED_HOSTS` da domen yo'q. |
| **403 CSRF verification failed** | https orqali kiring; `DJANGO_CSRF_TRUSTED_ORIGINS` ni bo'sh qoldiring yoki `https://e-shajara.uz` yozing. |
| Dizayn (CSS) yuklanmaydi | `collectstatic` qayta ishga tushiring; `sudo tail /var/log/nginx/e-shajara.error.log`. |
| Rasm yuklashda **413** | nginx faylida `client_max_body_size 25m;` borligini tekshiring. |
| Email kod kelmayapti | `journalctl -u e-shajara` da SMTP xatosi; Gmail uchun oddiy parol emas, **App password** kerak. |
| Sahifalar sekin / xotira | `free -h`; kerak bo'lsa `deploy/gunicorn.conf.py` da `workers = 2`, so'ng `sudo systemctl restart e-shajara`. |

`.env` o'zgartirilgandan keyin har doim: `sudo systemctl restart e-shajara`.
