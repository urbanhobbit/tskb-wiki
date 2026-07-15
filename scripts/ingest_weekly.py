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
    """PDF'ten temiz metin çıkar (pdftotext ile)"""
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
    pages = raw_text.split('\f')
    
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
            if s.startswith('•'):
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


def main():
    args = parse_args()
    date_str, pdf_path, url = get_date_and_url(args)
    
    print(f"\n=== TSKB Haftalık Görünüm Wiki Alımı ===\n")
    print(f"Tarih: {date_str}")
    
    # 1. PDF'yi indir
    if url:
        ok = download_pdf(pdf_path, url, force=args.force)
        if not ok:
            # Bugünün raporu henüz yayımlanmamış olabilir — dünü dene
            yesterday = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            print(f"  → {date_str} bulunamadı, {yesterday} deneniyor...")
            date_str = yesterday
            pdf_path = PDFS_DIR / f"haftalik-gorunum-{date_str}.pdf"
            url = BASE_URL.format(date=date_str)
            ok = download_pdf(pdf_path, url, force=args.force)
            if not ok:
                print("✗ Rapor bulunamadı.")
                sys.exit(1)
    
    # 2. Makale zaten var mı?
    article_path = ARTICLES_DIR / f"haftalik-gorunum-{date_str}.md"
    if article_path.exists() and not args.force:
        print(f"✓ Makale zaten var: {article_path.name}")
    else:
        # 3. Wiki makalesi oluştur
        article_text = create_wiki_article(date_str, pdf_path)
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        article_path.write_text(article_text, encoding='utf-8')
        print(f"✓ Makale oluşturuldu: {article_path.name}")
    
    # 4. Index ve log güncelle
    dt = datetime.strptime(date_str, "%Y%m%d")
    title = f"TSKB Haftalık Görünüm — {tr_date(dt)}"
    update_index(date_str, title)
    update_log(date_str, pdf_path)
    
    # 5. Kavram/entity tespiti
    raw_text = extract_text_from_pdf(pdf_path)
    concepts, entities = create_concept_entities(raw_text, date_str)
    
    if concepts:
        print(f"  → Tespit edilen kavramlar: {', '.join(concepts)}")
    if entities:
        print(f"  → Tespit edilen entity'ler: {', '.join(entities)}")
    
    print(f"\n✓ İşlem tamam. PDF: {pdf_path.name}, Makale: {article_path.name}\n")


if __name__ == "__main__":
    main()
