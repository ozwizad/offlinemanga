# 🚀 Manga Downloader - Server Deployment

## ✅ Hazır! Servera deploy etmeye hazır!

---

## 🎯 Deployment Seçenekleri

### **Seçenek 1: Render.com (ÖNERİLEN - En Kolay)**

1. **[render.com](https://render.com)** hesabı aç (GitHub ile giriş yap)

2. **New → Web Service** tıkla

3. GitHub'dan repo seç veya **"Public Git Repository"** seç:
   - Bu dosyaları GitHub'a yükle
   - Repo URL'ini yapıştır

4. **Ayarlar:**
   ```
   Name: manga-downloader
   Environment: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
   ```

5. **"Create Web Service"** → 2-3 dakikada hazır!

6. **URL alacaksınız:** `https://manga-downloader-xxx.onrender.com`

---

### **Seçenek 2: Railway.app**

1. **[railway.app](https://railway.app)** hesabı aç

2. **"New Project"** → **"Deploy from GitHub repo"**

3. Repo'yu seç

4. Railway otomatik algılar, deploy eder!

5. **URL:** `https://manga-downloader-production.up.railway.app`

---

### **Seçenek 3: Heroku**

1. **[heroku.com](https://heroku.com)** hesabı aç

2. **"New" → "Create new app"**

3. App ismi ver: `manga-downloader`

4. **Deploy:**
   ```bash
   heroku login
   heroku git:remote -a manga-downloader
   git push heroku main
   ```

5. **URL:** `https://manga-downloader.herokuapp.com`

---

## 📁 Dosyalar Deploy İçin Hazır

```
manga-server/
├── app.py              ← Flask backend (Selenium YOK)
├── requirements.txt    ← Python bağımlılıkları
├── Procfile           ← Deployment komutu
└── README.md          ← Bu dosya
```

---

## 🎮 Nasıl Kullanılır (Deploy Sonrası)

1. **URL'i aç:** `https://your-app.render.com`
2. **Manga linki yapıştır**
3. **Chapter seç**
4. **PDF indir!**

### 📱 **Mobilden:**
- Tarayıcıyı aç
- URL'i gir
- Kullan!

### 💻 **PC'den:**
- Aynı şekilde!

---

## ✅ Avantajlar

- ✅ **7/24 çalışır**
- ✅ **Kurulum yok**
- ✅ **Ücretsiz** (aylık limitle)
- ✅ **Mobil uyumlu**
- ✅ **Hızlı** (sunucu güçlü)
- ✅ **Paylaşılabilir** (link paylaş)
- ✅ **Selenium YOK** (daha basit)

---

## ⚠️ Limitler (Ücretsiz Plan)

### **Render.com:**
- ✅ 750 saat/ay
- ✅ 512MB RAM
- ⚠️ 15 dakika hareketsizlikten sonra uyur (ilk istek 30 saniye sürer)

### **Railway.app:**
- ✅ $5 ücretsiz kredi/ay
- ✅ 512MB RAM
- ✅ Sürekli çalışır (uyumaz)

### **Heroku:**
- ⚠️ Ücretsiz plan kaldırıldı ($7/ay)

---

## 🔧 Güncelleme

Deploy ettikten sonra güncelleme yapmak isterseniz:

1. Kodu düzenle
2. GitHub'a push et
3. Render/Railway otomatik günceller!

---

## 🐛 Sorun Giderme

### "Application error"
- Logs'u kontrol et
- `requirements.txt` eksik olabilir

### "Chapter bulunamadı"
- Bazı siteler JS kullanıyor
- MangaDex gibi basit siteler dene

### "PDF oluşturulamadı"
- RAM limiti dolmuş olabilir
- Daha az chapter seç

---

## 📊 Test Linkleri

### MangaDex (En İyi):
```
https://mangadex.org/title/...
```

### Manganato:
```
https://chapmanganato.to/manga-...
```

### Asura Scans (Deneysel):
```
https://asuracomic.net/series/...
```

---

## 🎯 Sonraki Adım

1. **Şimdi:** Render.com'a deploy et
2. **Test et:** Link gönder, chapter seç
3. **Paylaş:** Arkadaşlarınla link paylaş
4. **Kullan:** 7/24 her yerden erişim!

---

**Sorular?** 
Render.com hesabı açtınız mı? Birlikte deploy edelim! 🚀
