# GarajHub Bot Deployment Guide

## 🚀 Railway.com da Deploy Qilish (Bot va Web Server)

### 1. Railway.com ga Ro'yxatdan O'tish

- https://railway.app ga o'ting
- GitHub hisobi bilan kirish
- Deploy qilish

### 2. Loyihani Tayyorlash

```bash
# .env faylini yarating
cp .env.example .env

# .env ni to'ldiring:
BOT_TOKEN=your_bot_token
ADMIN_ID=your_admin_id
```

### 3. Railway da Deploy Qilish

1. **New Project** → **GitHub Repo** tanlang
2. Repository tanlang
3. **Add Service** → Environment variables qo'shing:

   - `BOT_TOKEN` = Telegram bot token
   - `ADMIN_ID` = Admin user ID

4. Procfile avtomatik o'qiladi
5. Deploy tugmasini bosing

### 4. Deployment URL olish

- Railway dashboard da domain ko'rinadip
- Bot uchun: Procfile `worker` dinamisini ishlatadi
- Web uchun: Procfile `web` serveri

---

## 🌐 Netlify da Veb Panel Deploy Qilish

**Maslahat:** Netlify faqat static HTML uchun. Flask backend uchun Railway foydalaning.

### 1. Frontend Yaratish (Netlify uchun)

```bash
# public/ papkasini yarating
mkdir -p public

# dashboard.html ni ko'chiring
cp templates/dashboard.html public/

# login.html ni ko'chiring
cp templates/login.html public/
```

### 2. API Endpoint o'zgartirisni

`dashboard.html` va `login.html` da API URLs ni o'zgartiring:

```javascript
// Eski:
fetch('http://localhost:5000/api/stats')

// Yangi (Railway domain):
fetch('https://your-railway-app.up.railway.app/api/stats')
```

### 3. Netlify da Deploy Qilish

1. https://netlify.com ga o'ting
2. **New Site from Git** tanlang
3. GitHub repo tanlang
4. Build settings:
   - **Build command:** `echo "Static site"`
   - **Publish directory:** `public`
5. Deploy tugmasini bosing

---

## 📝 .env Fayli (Local Testing)

```env
BOT_TOKEN=8265294721:AAEWhiYC2zTYxPbFpYYFezZGNzKHUumoplE
ADMIN_ID=7903688837
WEB_SECRET_KEY=garajhub-secret-key-2026
```

## ✅ Test Qilish

```bash
# Local test
python main.py

# Web: http://localhost:5000/admin
# Bot: @GarajHub_uz ga xabar yuboring
```

---

## 🔧 Railway da Masalani Hal Qilish

### Logs ko'rish:

```bash
railway logs
```

### Database va files:

Railway **ephemeral file system** ishlatadi. Persistent data uchun:

- PostgreSQL (Railway Marketplace dan)
- MongoDB (Railway Marketplace dan)

---

## ⚠️ Muhim Eslat

1. **Bot offline bolmay qolish uchun:** Railway da `worker` service ishchi bo'lishi kerak
2. **CORS xatoligi:** Flask app CORS header qo'shing
3. **File upload:** Railway da files saqlana olmaydi - S3/Cloudinary ishlatang
