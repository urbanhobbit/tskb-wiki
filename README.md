# TSKB Haftalık Görünüm Wiki

**TSKB Ekonomik Araştırmalar** tarafından her hafta yayımlanan **Haftalık Görünüm** raporlarının arşivi ve wiki altyapısı.

## 🔗 Kaynak
Raporlar şu URL'den yayımlanır:
```
https://www.tskb.com.tr/uploads/file/haftalik-gorunum-YYYYMMDD.pdf
```

## 📁 Klasör Yapısı

```
tskb-wiki/
├── raw/pdfs/              # Orijinal PDF'ler
├── raw/articles/           # Markdown wiki makaleleri
├── concepts/               # Ekonomi kavram sayfaları
├── entities/               # Kurum sayfaları (TSKB, TCMB, Fed, vs.)
├── scripts/                # Otomasyon scriptleri
│   └── ingest_weekly.py    # Haftalık PDF çekme + wiki makalesi oluşturma
├── index.md                # Sayfa kataloğu
├── log.md                  # Değişiklik geçmişi
├── SCHEMA.md               # Şema kuralları
└── README.md               # Bu dosya
```

## 🚀 Kullanım

### Manuel
```bash
# Yeni raporu indir
python3 scripts/ingest_weekly.py

# Sadece belirli bir tarih
python3 scripts/ingest_weekly.py --date 20260713
```

### Otomatik (Cron)
Haftada bir Pazartesi 09:00 UTC'de çalışacak şekilde ayarlanmıştır.

## 📊 Mevcut İçerik
| Tür | Adet |
|-----|------|
| PDF | 1 |
| Wiki Makale | 1 |
| Kavram | 0 |
| Entity | 0 |
