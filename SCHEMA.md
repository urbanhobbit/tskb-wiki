# TSKB Haftalık Görünüm Wiki Şeması

## Alan
**TSKB Ekonomik Araştırmalar — Haftalık Görünüm** — Türkiye Sınai Kalkınma Bankası (TSKB) Ekonomik Araştırmalar departmanı tarafından her hafta yayımlanan "Haftalık Görünüm" raporlarının arşivi ve wiki altyapısı.

## Kurallar
- **Dosya adları:** `haftalik-gorunum-YYYYMMDD.md` (küçük harf, tireli)
- **PDF adları:** `haftalik-gorunum-YYYYMMDD.pdf`
- **Her sayfa YAML frontmatter ile başlar**
- **[[wikilink]]** kullan — entity/concept sayfalarına bağlantı ver
- **Her işlem log.md'ye kaydedilir**

## Klasör Yapısı
```
tskb-wiki/
├── raw/
│   ├── pdfs/          # Orijinal PDF dosyaları
│   └── articles/      # Markdown wiki makaleleri
├── concepts/          # Ekonomi kavram sayfaları
├── entities/          # Kurum/kuruluş sayfaları
├── assets/            # Görseller
├── scripts/           # Otomasyon scriptleri
├── index.md           # Sayfa kataloğu
├── log.md             # İşlem geçmişi
├── SCHEMA.md          # Bu dosya
└── README.md          # Kurulum talimatları
```

## Etiketler
- `#haftalik-gorunum` — Haftalık Görünüm raporu
- `#tskb` — TSKB
- `#ekonomi` — Ekonomi
- `#turkiye-ekonomisi` — Türkiye ekonomisi
- `#kuresel-ekonomi` — Küresel ekonomi
- `#para-politikasi` — Para politikası
- `#enflasyon` — Enflasyon
- `#petrol` — Petrol/enerji
- `#piyasalar` — Finansal piyasalar
- `#veri-takvimi` — Ekonomik veri takvimi
