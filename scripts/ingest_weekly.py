#!/usr/bin/env python3
"""
TSKB Haftalık Görünüm — PDF'den Wiki Makalesi Üretme Scripti

Kullanım:
  python3 scripts/ingest_weekly.py                  # Bugünün tarihini dene
  python3 scripts/ingest_weekly.py --date 20260713  # Belirli bir tarih
  python3 scripts/ingest_weekly.py --pdf path.pdf   # Doğrudan PDF yolu

Çıktı:
  - raw/pdfs/haftalik-gorunum-YYYYMMDD.pdf
  - raw/articles/haftalik-gorunum-YYYYMMDD.md
  - index.md ve log.md güncellenir
"""

import os
import sys
import re
import argparse
import subprocess
import json
from datetime import datetime, date, timedelta
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent
PDFS_DIR = WIKI_DIR / "raw" / "pdfs"
ARTICLES_DIR = WIKI_DIR / "raw" / "articles"
SCRIPTS_DIR = WIKI_DIR / "scripts"

BASE_URL = "https://www.tskb.com.tr/uploads/file/haftalik-gorunum-{date}.pdf"


def parse_args():
    parser = argparse.ArgumentParser(description="TSKB Haftalık Görünüm Wiki Alımı")
    parser.add_argument("--date", help="Tarih YYYYMMDD formatında (varsayılan: bugün)")
    parser.add_argument("--pdf", help="Doğrudan PDF dosya yolu")
    parser.add_argument("--force", action="store_true", help="Var olanı tekrar indir")
    parser.add_argument("--verbose", action="store_true", help="Rapor zaten varsa bile çıktı üret (manuel kullanım)")
    return parser.parse_args()


def get_date_and_url(args):
    """Belirtilen tarih/URL'yi çözümle"""
    if args.pdf:
        path = Path(args.pdf)
        if not path.exists():
            print(f"HATA: PDF dosyası bulunamadı: {args.pdf}")
            sys.exit(1)
        # Dosya adından tarih çıkar
        m = re.search(r'(\d{8})', path.name)
        if m:
            date_str = m.group(1)
        else:
            date_str = datetime.now().strftime("%Y%m%d")
        return date_str, path, None
    
    date_str = args.date or datetime.now().strftime("%Y%m%d")
    url = BASE_URL.format(date=date_str)
    pdf_path = PDFS_DIR / f"haftalik-gorunum-{date_str}.pdf"
    return date_str, pdf_path, url


def download_pdf(pdf_path, url, force=False):
    """PDF'yi indir (yoksa veya --force ile)"""
    if pdf_path.exists() and not force:
        print(f"✓ PDF zaten var: {pdf_path.name} ({pdf_path.stat().st_size} bytes)")
        return True
    
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"↓ İndiriliyor: {url}")
    
    result = subprocess.run(
        ["curl", "-sL", "-o", str(pdf_path), "-w", "%{http_code}", url],
        capture_output=True, text=True, timeout=60
    )
    
    http_code = result.stdout.strip()
    if http_code != "200":
        print(f"✗ İndirme başarısız: HTTP {http_code}")
        if pdf_path.exists():
            pdf_path.unlink()
        return False
    
    size = pdf_path.stat().st_size
    print(f"✓ İndirildi: {pdf_path.name} ({size} bytes)")
    return True


def extract_text_from_pdf(pdf_path):
    """PDF'ten temiz Markdown çıkar — öncelik anydoc (Firecrawl, tablolar korunur),
    anydoc yoksa pdftotext yedeğine düş."""
    try:
        import anydoc
        md = anydoc.to_markdown(str(pdf_path))
        if md and len(md.strip()) > 50:
            return md
    except Exception:
        pass
    # Yedek: pdftotext
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=30
    )
    raw_text = result.stdout
    
    # Satır bazında temizlik
    lines = raw_text.split('\n')
    cleaned = []
    for line in lines:
        # Grafik/formül satırlarını temizle (çok fazla boşluk içeren satırlar)
        # Layout korunsun ama aşırı boşluklu satırları ayıkla
        stripped = line.strip()
        if stripped.startswith('\f'):
            stripped = stripped[1:].strip()
        
        # Boş veya sadece grafik elementi olan satırları atla
        if not stripped:
            cleaned.append('')
            continue
        
        cleaned.append(stripped)
    
    return '\n'.join(cleaned)


def split_pages(raw_text):
    """anydoc Markdown'ında \f (sayfa sonu) yoktur — bölümleri başlıklardan böl.
    Her Markdown başlığı (#/##/###) bir 'sayfa'/bölüm gibi ele alınır."""
    parts = re.split(r'\n(?=#{1,3}\s)', raw_text)
    return [p for p in parts if p.strip()]


def is_bullet(s):
    """Markdown ('- ') ve geleneksel (•) madde işaretlerini tanı."""
    s2 = s.strip()
    return s2.startswith('•') or s2.startswith('- ') or s2.startswith('* ')


def parse_sections(raw_text):
    """Metni bölümlere ayır - sayfa başlıklarına göre"""
    sections = {}
    current_section = "Giriş"
    current_lines = []
    
    # Sayfa başlığı kalıpları (PDF'deki başlık yapısına göre)
    section_patterns = [
        r'ABD enflasyonu.*bilançoları.*Hürmüz Boğazı',
        r'Ödemeler dengesi.*bütçe.*Fitch',
        r'KISALTMALAR',
    ]
    
    lines = raw_text.split('\n')
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append('')
            continue
        
        # Yeni bölüm başlangıcı mı?
        is_new_section = False
        for section_title in [
            "KISALTMALAR",
            "SORUMLULUK REDDİ BEYANI"
        ]:
            if section_title in stripped.upper():
                if current_lines:
                    sections[current_section] = current_lines
                current_section = stripped
                current_lines = []
                is_new_section = True
                break
        
        if not is_new_section:
            # Formül/veri satırlarını (nokta/boşluk pattern) temizle
            # Örn: grafik eksenlerini filtrele
            if re.match(r'^[\d,\-.\s]{30,}$', stripped):
                continue
            current_lines.append(stripped)
    
    if current_lines:
        sections[current_section] = current_lines
    
    return sections


def extract_headers_and_bullets(text):
    """Ana başlıkları ve madde işaretlerini ayıkla"""
    lines = text.split('\n')
    headers = []
    bullets = []
    data_tables = []
    
    current_section = None
    
    for line in lines:
        s = line.strip()
        if not s:
            continue
        
        # Kalın/başlık görünümlü satırlar (büyük harf ağırlıklı, kısa)
        if s.startswith('•') or s.startswith('-') or s.startswith('*'):
            bullets.append(s)
        elif re.match(r'^\d+\s', s):  # Tarih listesi
            data_tables.append(s)
        elif 'Hazine' in s or 'İhale' in s or 'TL' in s:
            data_tables.append(s)
        elif 'Kaynak:' in s:
            continue  # Kaynak satırlarını atla
        else:
            # Tablo verisi olabilir mi?
            if re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', s) or re.search(r'\d+\.\d+,\d+', s):
                data_tables.append(s)
            elif s not in ['Haftalık', 'Yılbaşından Beri']:
                headers.append(s)
    
    return headers, bullets, data_tables


TR_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}

def tr_date(dt):
    """Tarihi Türkçe formatla: '13 Temmuz 2026'"""
    return f"{dt.day} {TR_MONTHS[dt.month]} {dt.year}"

def create_wiki_article(date_str, pdf_path):
    """PDF içeriğinden wiki makalesi oluştur"""
    
    raw_text = extract_text_from_pdf(pdf_path)
    
    # Parse date
    dt = datetime.strptime(date_str, "%Y%m%d")
    formatted_date = tr_date(dt)
    week_num = dt.isocalendar()[1]
    year = dt.year
    
    # Başlık/metin ayıklama
    headers, bullets, tables = extract_headers_and_bullets(raw_text)
    
    # Ana bölümleri tespit et
    # Sayfa 1: ABD enflasyonu, bilançolar, Hürmüz Boğazı
    # Sayfa 2: Ödemeler dengesi, bütçe, Fitch
    # Sayfa 3: Veri takvimi
    # Sayfa 4: Kısaltmalar
    
    # Bölümleri elle ayır (sayfa sonu karakterleriyle)
    pages = split_pages(raw_text)
    
    body_parts = []
    section_bullets = {"Küresel Görünüm": [], "Türkiye Görünümü": [], "Veri Takvimi": [], "Diğer": []}
    
    current_section = "Küresel Görünüm"
    
    for page_idx, page_text in enumerate(pages):
        if not page_text.strip():
            continue
        
        lines = page_text.strip().split('\n')
        
        # Sayfa başlığını tespit et
        first_lines = [l.strip() for l in lines[:3] if l.strip()]
        full_title = ' '.join(first_lines[:2])
        
        # Bölüm sınıflandırması
        if any(kw in full_title for kw in ['Ödemeler dengesi', 'bütçe', 'Fitch', 'Türkiye', 'TCMB', 'DOLAR/TL']):
            current_section = "Türkiye Görünümü"
        elif any(kw in full_title for kw in ['KISALTMALAR']):
            current_section = "Kısaltmalar"
        elif any(kw in full_title for kw in ['SORUMLULUK']):
            current_section = "Diğer"
        elif any(kw in full_title for kw in ['ABD', 'enflasyon', 'Hürmüz', 'küresel', 'borsa']):
            current_section = "Küresel Görünüm"
        
        # Madde işaretlerini topla
        for line in lines:
            s = line.strip()
            if is_bullet(s):
                # Grafik gürültüsünü temizle
                clean = re.sub(r'\s{10,}', ' ', s)  # Çoklu boşlukları tek boşluğa indir
                clean = clean.strip()
                if len(clean) > 15:  # Çok kısa maddeleri atla
                    if current_section in section_bullets:
                        section_bullets[current_section].append(clean)
                    else:
                        section_bullets["Diğer"].append(clean)
    
    # Wiki makalesini oluştur
    sections_output = []
    
    # Küresel Görünüm
    if section_bullets["Küresel Görünüm"]:
        sections_output.append("## Küresel Görünüm\n")
        for b in section_bullets["Küresel Görünüm"]:
            sections_output.append(f"- {b[1:].strip()}")
        sections_output.append("")
    
    # Türkiye Görünümü  
    if section_bullets["Türkiye Görünümü"]:
        sections_output.append("## Türkiye Görünümü\n")
        for b in section_bullets["Türkiye Görünümü"]:
            sections_output.append(f"- {b[1:].strip()}")
        sections_output.append("")
    
    # Veri Takvimi
    data_timeline = []
    for line in raw_text.split('\n'):
        s = line.strip()
        # Tarih içeren satırları veri takvimi olarak al
        if re.match(r'^\d{1,2}\s', s) and any(month in s for month in ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']):
            data_timeline.append(s)
    
    if data_timeline:
        sections_output.append("## Veri Takvimi\n")
        # Verileri haftanın günlerine göre grupla
        for item in data_timeline[:30]:  # Maksimum 30 satır
            sections_output.append(f"- {item}")
        sections_output.append("")
    
    # Hazine borç ödemeleri
    hazine_lines = []
    in_hazine = False
    for line in raw_text.split('\n'):
        s = line.strip()
        if 'HAZİNE İÇ BORÇ ÖDEME' in s:
            in_hazine = True
            continue
        if in_hazine and 'KISALTMALAR' in s:
            in_hazine = False
            continue
        if in_hazine and s:
            hazine_lines.append(s)
    
    if hazine_lines:
        sections_output.append("## Hazine İç Borç Ödeme Takvimi\n")
        sections_output.append("```")
        for h in hazine_lines:
            sections_output.append(h)
        sections_output.append("```\n")
    
    # Kısaltmalar
    acronyms = []
    in_acronyms = False
    for line in raw_text.split('\n'):
        s = line.strip()
        if 'KISALTMALAR' in s and len(s) < 30:
            in_acronyms = True
            continue
        if in_acronyms:
            if 'SORUMLULUK' in s or not s:
                if 'SORUMLULUK' in s:
                    break
                continue
            acronyms.append(s)
    
    if acronyms:
        sections_output.append("## Kısaltmalar\n")
        for a in acronyms:
            sections_output.append(f"- {a}")
        sections_output.append("")
    
    body = '\n'.join(sections_output)
    
    # Frontmatter
    summary_text = generate_summary(raw_text, date_str)
    summary_for_yaml = summary_text[:500].replace('"', "'").replace('\n', '\\n')
    
    frontmatter = f"""---
title: "TSKB Haftalık Görünüm — {formatted_date}"
date: {dt.strftime('%Y-%m-%d')}
week: {week_num}/{year}
source_url: {BASE_URL.format(date=date_str)}
pdf_file: haftalik-gorunum-{date_str}.pdf
category: tskb-haftalik-gorunum
tags: [tskb, haftalik-gorunum, ekonomi, turkiye-ekonomisi, kuresel-ekonomi]
---

# TSKB Haftalık Görünüm — {formatted_date}

**Tarih:** {formatted_date} | **Hafta:** {week_num}/{year} | **Kaynak:** TSKB Ekonomik Araştırmalar

## 📋 Özet

{summary_text}

---

## Detaylı İçerik

{body}

---

*Bu makale [TSKB Haftalık Görünüm]({BASE_URL.format(date=date_str)}) PDF'sinden otomatik olarak oluşturulmuştur.*
"""
    
    return frontmatter.strip()


def update_index(date_str, title):
    """index.md'yi güncelle"""
    index_path = WIKI_DIR / "index.md"
    
    if index_path.exists():
        content = index_path.read_text(encoding='utf-8')
    else:
        content = """# TSKB Haftalık Görünüm Wiki — Sayfa Kataloğu

## Makaleler

| Tarih | Başlık | PDF |
|-------|--------|-----|

## Kavramlar

## Entity'ler
"""
    
    # Yeni makale satırı
    dt = datetime.strptime(date_str, "%Y%m%d")
    formatted = dt.strftime("%d.%m.%Y")
    article_link = f"[[raw/articles/haftalik-gorunum-{date_str}.md|{formatted}]]"
    pdf_link = f"[PDF](raw/pdfs/haftalik-gorunum-{date_str}.pdf)"
    new_row = f"| {formatted} | {title} | {pdf_link} |"
    
    # Tablodan sonra ekle
    if "|-------|--------|-----|" in content:
        # Sıralı ekle - tarihe göre
        lines = content.split('\n')
        in_table = False
        table_rows = []
        new_lines = []
        header_line = None
        
        for line in lines:
            if "|-------|--------|-----|" in line:
                in_table = True
                new_lines.append(line)
                continue
            if in_table:
                if line.startswith('|') and 'PDF' not in line and 'Tarih' not in line:
                    table_rows.append(line)
                elif not line.startswith('|'):
                    in_table = False
                    # Sort and insert
                    table_rows.append(new_row)
                    table_rows.sort()
                    new_lines.extend(table_rows)
                    new_lines.append(line)
                else:
                    continue
            else:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
    else:
        content += f"\n{new_row}\n"
    
    index_path.write_text(content, encoding='utf-8')
    print(f"✓ index.md güncellendi")


def update_log(date_str, pdf_path):
    """log.md'yi güncelle"""
    log_path = WIKI_DIR / "log.md"
    
    dt = datetime.strptime(date_str, "%Y%m%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    size = pdf_path.stat().st_size if pdf_path.exists() else 0
    
    entry = f"| {now} | {dt.strftime('%d.%m.%Y')} | İndirme + Wiki Makalesi | {size/1024:.0f} KB |"
    
    if log_path.exists():
        content = log_path.read_text(encoding='utf-8')
    else:
        content = """# TSKB Haftalık Görünüm Wiki — İşlem Geçmişi

| Tarih (İşlem) | Rapor Tarihi | İşlem | Boyut |
|---------------|-------------|-------|-------|
"""
    
    # Başlıktan sonra ekle
    if "|-------|-------------|-------|-------|" in content:
        content = content.replace(
            "|-------|-------------|-------|-------|",
            f"|-------|-------------|-------|-------|\n{entry}"
        )
    else:
        content += f"\n{entry}\n"
    
    log_path.write_text(content, encoding='utf-8')
    print(f"✓ log.md güncellendi")


def generate_summary(raw_text, date_str):
    """PDF metninden yapılandırılmış özet çıkar"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    formatted_date = tr_date(dt)
    
    pages = split_pages(raw_text)
    
    # Sayfa başlıklarını topla (öne çıkan başlıklar)
    page_headers = []
    for page_text in pages:
        if not page_text.strip():
            continue
        lines = page_text.strip().split('\n')
        # Temiz başlık satırlarını bul (büyük harf içeren, kısa, grafik etiketi olmayan)
        for line in lines[:6]:
            s = line.strip()
            if not s or len(s) < 15 or '•' in s[:5]:
                continue
            # Markdown tablo satırlarını atla (| ile başlayan) ve başlık işaretlerini temizle
            if s.startswith('|'):
                continue
            s = re.sub(r'^#{1,3}\s*', '', s).strip()
            if not s:
                continue
            # Grafik/formül satırlarını filtrele
            if re.match(r'^[\d,.\s%()x]{10,}$', s):
                continue
            if any(kw in s for kw in ['Haftalık', 'Yılbaşından', 'Şub ', 'Oca ', 'Nis ', 'Mar ', 'May ', 'Haz ', 'Tem ']):
                continue
            # Anlamlı başlık satırı
            if re.search(r'[A-ZÖÜÇĞİŞ]', s) and len(s.split()) >= 2:
                clean = re.sub(r'\s{5,}', ' | ', s).strip()
                page_headers.append(clean)
    
    # Ana temaları topla (sayfa bazında tematik gruplama)
    themes = {"Küresel": [], "Türkiye": [], "Politika": []}
    current_theme = "Küresel"
    
    for page_idx, page_text in enumerate(pages):
        if not page_text.strip():
            continue
        lines = page_text.strip().split('\n')
        first_lines = []
        for l in lines[:6]:
            ls = l.strip()
            if ls.startswith('|') or not ls:
                continue
            first_lines.append(re.sub(r'^#{1,3}\s*', '', ls).strip())
        full_title = ' '.join(first_lines[:4])
        
        # Bölüm sınıflandırması
        if any(kw in full_title for kw in ['Ödemeler dengesi', 'bütçe', 'Fitch', 'Türkiye', 'TCMB', 'DOLAR/TL', 'BORSA İSTANBUL']):
            current_theme = "Türkiye"
        elif any(kw in full_title for kw in ['ABD enflasyonu', 'ABD GETİRİ', 'EMTİA', 'bilanço', 'Hürmüz']):
            current_theme = "Küresel"
        
        # Madde işaretlerini temizle ve birleştir
        for line in lines:
            s = line.strip()
            if is_bullet(s):
                clean = re.sub(r'\s{10,}', ' ', s)
                clean = clean.strip().lstrip('•-* ').strip()
                if len(clean) > 20 and current_theme in themes:
                    themes[current_theme].append(clean)
    
    # Özet metnini oluştur
    summary_parts = []
    summary_parts.append(f"📊 **TSKB Haftalık Görünüm — {formatted_date}**\n")
    
    # 1. Öne Çıkan Başlıklar
    if page_headers:
        summary_parts.append("**🔹 Öne Çıkan Başlıklar:**")
        seen = set()
        for h in page_headers:
            # Yinelenenleri önle
            key = h.split('|')[0][:40]
            if key not in seen and len(seen) < 6:
                seen.add(key)
                summary_parts.append(f"  • {h}")
        summary_parts.append("")
    
    # 2. Küresel Görünüm
    if themes["Küresel"]:
        summary_parts.append("**🌍 Küresel Görünüm:**")
        seen = set()
        for item in themes["Küresel"][:5]:
            clean = re.sub(r'\s+', ' ', item).strip()
            if clean and len(clean) > 25 and clean[:50] not in seen:
                seen.add(clean[:50])
                # PDF'de bölünen cümleleri birleştirmeye çalış
                if clean.endswith(',') or clean.endswith('ve') or clean.endswith('ile'):
                    clean += "…"
                summary_parts.append(f"  • {clean}")
        summary_parts.append("")
    
    # 3. Türkiye Görünümü
    if themes["Türkiye"]:
        summary_parts.append("**🇹🇷 Türkiye Görünümü:**")
        seen = set()
        for item in themes["Türkiye"][:5]:
            clean = re.sub(r'\s+', ' ', item).strip()
            if clean and len(clean) > 25 and clean[:50] not in seen:
                seen.add(clean[:50])
                summary_parts.append(f"  • {clean}")
        summary_parts.append("")
    
    # 4. Veri Takvimi (önemli kalemler)
    data_calendar = []
    for line in raw_text.split('\n'):
        s = line.strip()
        if re.match(r'^\d{1,2}\s', s) and any(month in s for month in 
            ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 
             'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']):
            parts = s.split()
            if len(parts) >= 4:
                data_calendar.append(s)
    
    # Piyasa verileri
    market_data = []
    for page_text in pages[3:12]:  # Sayfa 4-11 arası (veri sayfaları)
        lines = page_text.strip().split('\n')
        for line in lines:
            s = line.strip()
            # Endeks/seviye verisi olan satırları yakala
            if s and len(s) > 20 and re.search(r'[A-ZÖÜÇĞİŞ]{4,}', s) and re.search(r'[\d.,%]+', s):
                if 'Seviye' in s or 'Değişim' in s or 'Getiri' in s:
                    continue
                if any(kw in s for kw in ['Kaynak:', 'Bloomberg']):
                    continue
                clean = re.sub(r'\s{5,}', '  ', s).strip()
                if len(clean) > 30 and '•' not in clean:
                    market_data.append(clean)
    
    if data_calendar:
        summary_parts.append("**📅 Haftanın Önemli Verileri:**")
        for item in data_calendar[:6]:
            # Veri satırını temizle - ilk 4-5 kelimeyi al
            parts = item.split()
            # Sadece tarih + ülke + gösterge kısmını göster (ilk ~5 alan)
            if len(parts) >= 3:
                day = parts[0]
                month = parts[1] if parts[1][0].isupper() else ""
                country = ""
                rest_start = 2
                if month:
                    country = parts[2] if len(parts) > 2 and parts[2][0].isupper() else ""
                    rest_start = 3 if country else 2
                else:
                    country = parts[1] if parts[1][0].isupper() else ""
                    rest_start = 2 if country else 1
                # Göstergeyi ilk birkaç anlamlı kelime
                indicator_parts = []
                for p in parts[rest_start:]:
                    if p.replace(',', '').replace('.', '').replace('-', '').replace('%', '').isdigit():
                        break
                    indicator_parts.append(p)
                    if len(indicator_parts) >= 4:
                        break
                indicator = ' '.join(indicator_parts) if indicator_parts else '...'
                label = f"{day} {month}".strip()
                if country:
                    label += f" - {country}"
                summary_parts.append(f"  • {label} → {indicator}")
        summary_parts.append("")
    
    # 5. Piyasa Verileri (kısa)
    if market_data:
        summary_parts.append("**📈 Piyasa Verileri:**")
        for item in market_data[:4]:
            summary_parts.append(f"  • {item}")
        summary_parts.append("")
    
    return '\n'.join(summary_parts).strip()


def create_concept_entities(raw_text, date_str):
    """Yeni kavram/entity sayfaları oluştur (ihtiyaç halinde)"""
    # Tespit edilen kavramlar
    concepts_found = []
    
    if 'enflasyon' in raw_text.lower():
        concepts_found.append('enflasyon')
    if 'carry trade' in raw_text.lower():
        concepts_found.append('carry-trade')
    if 'volatilite' in raw_text.lower():
        concepts_found.append('volatilite')
    if 'CDS' in raw_text:
        concepts_found.append('cds')
    
    entities_found = []
    if 'TSKB' in raw_text:
        entities_found.append('tskb')
    if 'TCMB' in raw_text or 'Merkez Bankası' in raw_text:
        entities_found.append('tcmb')
    if 'Fed' in raw_text:
        entities_found.append('fed')
    if 'Fitch' in raw_text:
        entities_found.append('fitch')
    if 'NATO' in raw_text:
        entities_found.append('nato')
    
    return concepts_found, entities_found


def git_push(date_str):
    """tskb-wiki repo'sunu GitHub'a push et."""
    try:
        subprocess.run(["git", "-C", str(WIKI_DIR), "add", "-A"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(WIKI_DIR), "commit", "-m", f"feat: haftalik-gorunum {date_str}"],
                       capture_output=True, timeout=30)
        r = subprocess.run(["git", "-C", str(WIKI_DIR), "push"], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    args = parse_args()
    date_str, pdf_path, url = get_date_and_url(args)
    
    # 1. PDF'yi indir
    if url:
        ok = download_pdf(pdf_path, url, force=args.force)
        if not ok:
            # Bugünün raporu henüz yayımlanmamış olabilir — dünü dene
            yesterday = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            date_str = yesterday
            pdf_path = PDFS_DIR / f"haftalik-gorunum-{date_str}.pdf"
            url = BASE_URL.format(date=date_str)
            ok = download_pdf(pdf_path, url, force=args.force)
            if not ok:
                print("✗ Rapor bulunamadı.")
                sys.exit(1)
    
    # 2. Makale zaten var mı? (no_agent cron: yeni rapor yoksa SESSİZ kal — stdout boş = teslim yok)
    article_path = ARTICLES_DIR / f"haftalik-gorunum-{date_str}.md"
    summary_path = ARTICLES_DIR / f"haftalik-gorunum-{date_str}-ozet.txt"
    is_new = not article_path.exists() or args.force
    
    if article_path.exists() and not args.force:
        if not args.verbose:
            return  # cron: yeni içerik yok → çıktı üretme (sessiz)
        print(f"✓ Makale zaten var: {article_path.name}")
        if summary_path.exists():
            summary_text = summary_path.read_text(encoding='utf-8')
        else:
            raw_text = extract_text_from_pdf(pdf_path)
            summary_text = generate_summary(raw_text, date_str)
    else:
        # 3. Wiki makalesi oluştur (anydoc tabanlı)
        raw_text = extract_text_from_pdf(pdf_path)
        article_text = create_wiki_article(date_str, pdf_path)
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        article_path.write_text(article_text, encoding='utf-8')
        print(f"✓ Makale oluşturuldu: {article_path.name}")
        
        # Özeti ayrı dosyaya kaydet
        summary_text = generate_summary(raw_text, date_str)
        summary_path.write_text(summary_text, encoding='utf-8')
        print(f"✓ Özet kaydedildi: {summary_path.name}")
    
    # 4. Index ve log güncelle
    dt = datetime.strptime(date_str, "%Y%m%d")
    title = f"TSKB Haftalık Görünüm — {tr_date(dt)}"
    update_index(date_str, title)
    update_log(date_str, pdf_path)
    
    # 5. Kavram/entity tespiti
    if is_new:
        concepts, entities = create_concept_entities(raw_text, date_str)
        if concepts:
            print(f"  → Tespit edilen kavramlar: {', '.join(concepts)}")
        if entities:
            print(f"  → Tespit edilen entity'ler: {', '.join(entities)}")
    
    # 6. GitHub push (artık script içinde — no_agent cron bunu da halleder)
    if is_new:
        if git_push(date_str):
            print(f"✓ GitHub'a push edildi")
        else:
            print("⚠ Push başarısız (git durumunu kontrol et)")
    
    # 7. Teslim edilecek özet çıktısı (no_agent cron stdout'u doğrudan gönderir)
    print(f"\n✅ **TSKB Haftalık Görünüm — {tr_date(dt)}** hazır (anydoc dönüşümü)\n")
    print(summary_text)
    print(f"\n📄 **PDF:** https://github.com/urbanhobbit/tskb-wiki/blob/main/raw/pdfs/haftalik-gorunum-{date_str}.pdf")
    print(f"📝 **Wiki makalesi:** https://github.com/urbanhobbit/tskb-wiki/blob/main/raw/articles/haftalik-gorunum-{date_str}.md")
    print(f"🔗 **Repo:** https://github.com/urbanhobbit/tskb-wiki")


if __name__ == "__main__":
    main()
