"""İddia doğrulama raporu: iskelet üretir ve mekanik denetim yapar (T0, DB'siz).
Biçim: Özet tablo + Kanıtlar + Açık kalanlar (ayarlar/iddia_dogrula.json ornek_raporlar listesindeki raporlar).

Alt komutlar:
  ayar     Birleşik ayarı JSON yazar (eklenti ayarlar/iddia_dogrula.json + proje .claude/orkestra/iddia_dogrula.json).
  iskelet  <iddialar.csv|.md|.txt> --rapor <rapor_dizini>/<konu>_dogrulama_<YYYYMMDD>.md --kanit <calisma_dizini>/<konu>_<YYYYMMDD>/kanit
           Rapor iskeleti + iddia başına kanıt kartı (kanit/<KID>.md; araştırmacı ajan doldurur). Var olan dosyaya yazmaz.
  denetle  <rapor.md> [--iddialar <liste>] [--yasakli <proje dışı kelime listesi>]
           Kontroller: karar etiketi geçerli; KISMEN/ÇÜRÜTÜLDÜ satırında yeni metin var; her kimliğin kanıt bölümü var
           ve içinde kanıt izi (dosya:satır, `kod/nesne`, saat, .csv) var; listedeki her iddia raporda; yer tutucu kalmamış;
           sır/e-posta kalıbı ve yasaklı kelime (ör. çalışan adları; liste proje DIŞINDA tutulur) yok.
           Çıkış: 0 temiz, 1 hata var. Denetçinin mekanik ön elemesidir; içerik doğruluğunu denetçi ayrıca okur.

İddia listesi biçimi: CSV (kolonlar: kid/id/kimlik + iddia/metin) ya da satır başına "K002: metin" / "- K002 — metin".
"""
import argparse, csv, io, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

KARARLAR = ['DOĞRULANDI', 'KISMEN', 'ÇÜRÜTÜLDÜ', 'TEYİT', 'BELİRSİZ']
METIN_ZORUNLU = {'KISMEN', 'ÇÜRÜTÜLDÜ'}
YER_TUTUCU = '⟨doldur⟩'
KID = r'[A-Z]{1,3}-?\d{1,4}[a-z]?'
SATIR_KID = re.compile(rf'^\s*[-*]?\s*\**({KID})\**\s*[:—–-]\s*(.+?)\s*$')
KANIT_IZI = [re.compile(p) for p in (
    r'[\w./\\-]+\.(py|ts|tsx|js|sql|md|yaml|yml|json|csv|txt):\d+',  # dosya:satır
    r'`[^`]{3,}`',                                                   # kod / DB nesnesi / yol
    r'\b\d{1,2}:\d{2}\b',                                            # sorgu saati
    r'\.csv\b', r'\bP\d{2}\b')]                                       # ham çıktı / prod teyit testi
SIR = {
    'parola': re.compile(r"(?i)(password|pwd|passwd)\s*[=:]\s*[\"']?(?!<|\*|\$|%|\{|null|none)[^\s\"',;|]{4,}"),
    'hesap_anahtari': re.compile(r"(?i)account_?key\s*[=:\"']+\s*[A-Za-z0-9+/]{20,}"),
    'auth_token': re.compile(r"(?i)auth_?token[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_.]{12,}"),
    'bearer': re.compile(r'(?i)bearer\s+[A-Za-z0-9\-_.]{20,}'),
    'imza': re.compile(r'(?i)\b(sig|sv|se)=[A-Za-z0-9%]{20,}'),
    'e-posta': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
}


AYAR_AD = 'iddia_dogrula'


def ayar_oku():
    """Eklenti varsayılanı + proje ezmesi (anahtar anahtar). Proje kökü: CLAUDE_PROJECT_DIR ya da çalışma klasörü."""
    kok = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    proje = os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()
    sonuc = {}
    for yol in (os.path.join(kok, 'ayarlar', AYAR_AD + '.json'), os.path.join(proje, '.claude', 'orkestra', AYAR_AD + '.json')):
        try:
            with open(yol, encoding='utf-8-sig') as f:
                d = json.load(f)
            if isinstance(d, dict):
                sonuc.update(d)
        except (OSError, ValueError):
            pass
    return sonuc


def ayar_yaz(a):
    print(json.dumps(ayar_oku(), ensure_ascii=False, indent=2))


def iddialari_oku(yol):
    metin = open(yol, encoding='utf-8-sig').read()
    out = []
    if yol.lower().endswith('.csv'):
        ayrac = max([',', ';', '\t'], key=lambda c: metin.splitlines()[0].count(c))
        for r in csv.DictReader(io.StringIO(metin), delimiter=ayrac):
            k = {a.strip().lower(): (v or '').strip() for a, v in r.items() if a}
            kid = k.get('kid') or k.get('id') or k.get('kimlik')
            iddia = k.get('iddia') or k.get('metin') or k.get('claim') or ''
            if kid:
                out.append((kid, iddia))
    else:
        for satir in metin.splitlines():
            m = SATIR_KID.match(satir)
            if m:
                out.append((m.group(1), m.group(2)))
    kimlikler = [k for k, _ in out]
    tekrar = {k for k in kimlikler if kimlikler.count(k) > 1}
    if tekrar:
        sys.exit(f"Tekrarlanan kimlik: {', '.join(sorted(tekrar))}")
    if not out:
        sys.exit(f"İddia okunamadı: {yol}")
    return out


def iskelet(a):
    iddialar = iddialari_oku(a.liste)
    if os.path.exists(a.rapor):
        sys.exit(f"Var: {a.rapor} (üstüne yazılmaz; yeni tarihli ad ver)")
    os.makedirs(a.kanit, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.rapor)), exist_ok=True)
    y = YER_TUTUCU
    md = [f"# {a.baslik}", "",
          f"**Tarih:** {y} (ölçüm saatleriyle)",
          "**Kaynaklar:**", f"- {y} (DB: kopya mı prod mu; kod deposu ve son commit; belgeler)", "",
          f"**Kapsam:** {len(iddialar)} iddia, kaynak `{a.liste}`.", "",
          "**Kararlar:** DOĞRULANDI / KISMEN (düzeltilmeli) / ÇÜRÜTÜLDÜ / BELİRSİZ (kanıt yetersiz).",
          f"- {y} (çürütülen, metni düzeltilecek, nüans eklenecek maddeler)", "",
          f"**Ham kanıt kartları:** `{a.kanit}`", "",
          "## Özet tablo", "", "| KID | Karar | Önerilen yeni metin (yalnız değişenler) |", "|---|---|---|"]
    md += [f"| {k} | {y} | {y} |" for k, _ in iddialar]
    md += ["", "## Kanıtlar", ""]
    for k, iddia in iddialar:
        md += [f"### {k} — {iddia[:70]}", f"- **İddia:** {iddia}", f"- {y} (dosya:satır, sorgu + saat, CSV yolu; kanıt derecesi kesin/güçlü/hipotez; kopya ise \"bu kopyaya göre\")", ""]
    md += ["## Açık kalanlar", f"- {y}", ""]
    with open(a.rapor, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    for k, iddia in iddialar:
        p = os.path.join(a.kanit, f"{k}.md")
        if os.path.exists(p):
            print(f"atlandı (var): {p}")
            continue
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f"# {k} — kanıt kartı\n\n**İddia:** {iddia}\n\n"
                    "## Kanıt (her satır: kaynak türü | yer | ne gösteriyor)\n"
                    "- kod | `depo/yol/dosya.py:satır` | ...\n- DB | `şema.tablo` + sorgu betiği + saat + ortam (kopya/prod) | ...\n"
                    "- belge | `<belge yolu>.md` §… | ...\n\n"
                    "## Karşı kanıt / iddiayı zayıflatan\n- ...\n\n"
                    "## Ön değerlendirme (araştırmacı; karar değildir)\n- destekliyor / kısmen / çelişiyor / yetersiz — gerekçe\n\n"
                    "## Önerilen yeni metin (gerekirse)\n- ...\n")
    print(f"Rapor iskeleti: {a.rapor}\nKanıt kartları: {a.kanit} ({len(iddialar)} kart)")


def tablo_satirlari(md):
    m = re.search(r'^##\s+Özet tablo\s*$', md, re.M)
    if not m:
        return None
    out = []
    for satir in md[m.end():].splitlines():
        s = satir.strip()
        if s.startswith('## '):
            break
        if not s.startswith('|') or set(s) <= set('|-: '):
            continue
        h = [x.strip() for x in s.strip('|').split('|')]
        if len(h) < 2 or h[0].upper() in ('KID', 'KİMLİK', 'ID'):
            continue
        out.append((h[0].strip('* '), h[1].replace('*', '').strip(), (h[2] if len(h) > 2 else '').strip()))
    return out


def kanit_bolumleri(md):
    """Kanıtlar bölümünü ### başlıklarına böler; kimlik → bölüm metni. Gruplu başlıkta (K109 / K111) **K109:** maddesi tercih edilir."""
    m = re.search(r'^##\s+Kanıtlar\s*$', md, re.M)
    if not m:
        return {}
    govde = md[m.end():]
    son = re.search(r'^##\s+', govde, re.M)
    govde = govde[:son.start()] if son else govde
    out = {}
    for parca in re.split(r'^(?=###\s)', govde, flags=re.M):
        if not parca.startswith('###'):
            continue
        baslik = parca.splitlines()[0]
        for kid in re.findall(KID, baslik.split('—')[0]):
            alt = re.search(rf'^\s*-\s*\*\*{re.escape(kid)}:?\*\*:?(.*?)(?=^\s*-\s*\*\*{KID}:?\*\*|\Z)', parca, re.M | re.S)
            out[kid] = alt.group(0) if alt else parca
    return out


def denetle(a):
    md = open(a.rapor, encoding='utf-8').read()
    hatalar, uyarilar = [], []
    satirlar = tablo_satirlari(md)
    if satirlar is None:
        hatalar.append("'## Özet tablo' bölümü yok")
        satirlar = []
    bolumler = kanit_bolumleri(md)
    if not bolumler:
        hatalar.append("'## Kanıtlar' bölümü yok ya da ### başlığı yok")
    sayac = {}
    for kid, karar, metin in satirlar:
        if karar not in KARARLAR:
            hatalar.append(f"{kid}: geçersiz karar '{karar}' (geçerli: {', '.join(KARARLAR)})")
            continue
        sayac[karar] = sayac.get(karar, 0) + 1
        if karar in METIN_ZORUNLU and metin in ('', '—', '-', YER_TUTUCU):
            hatalar.append(f"{kid}: {karar} ama önerilen yeni metin boş")
        b = bolumler.get(kid)
        if b is None:
            hatalar.append(f"{kid}: Kanıtlar'da başlığı yok")
        elif not any(p.search(b) for p in KANIT_IZI):
            hatalar.append(f"{kid}: kanıt bölümünde iz yok (dosya:satır, `nesne`, saat ya da .csv)")
    tablodaki = [k for k, _, _ in satirlar]
    for k in {k for k in tablodaki if tablodaki.count(k) > 1}:
        hatalar.append(f"{k}: özet tabloda birden fazla satır")
    if a.iddialar:
        beklenen = [k for k, _ in iddialari_oku(a.iddialar)]
        eksik = [k for k in beklenen if k not in tablodaki]
        fazla = [k for k in tablodaki if k not in beklenen]
        if eksik:
            hatalar.append(f"listede olup raporda olmayan: {', '.join(eksik)}")
        if fazla:
            uyarilar.append(f"raporda olup listede olmayan: {', '.join(fazla)}")
    if YER_TUTUCU in md:
        hatalar.append(f"doldurulmamış yer tutucu: {md.count(YER_TUTUCU)} adet")
    for ad, rx in SIR.items():
        for m in rx.finditer(md):
            s = m.group(0)
            if ad == 'e-posta' and '***' in s:
                continue
            hatalar.append(f"sır/kişisel veri kalıbı [{ad}] satır {md.count(chr(10), 0, m.start()) + 1}")  # değer yazılmaz
    if a.yasakli:
        kelimeler = [w.strip() for w in open(a.yasakli, encoding='utf-8-sig') if w.strip() and not w.startswith('#')]
        for w in kelimeler:
            if re.search(rf'(?i)\b{re.escape(w)}\b', md):
                hatalar.append(f"yasaklı kelime geçiyor (listedeki {kelimeler.index(w) + 1}. kelime)")  # kelimenin kendisi yazılmaz
    print(f"Rapor: {a.rapor}")
    print(f"Madde: {len(satirlar)} · " + ' · '.join(f"{k} {sayac.get(k, 0)}" for k in KARARLAR if sayac.get(k)))
    for u in uyarilar:
        print(f"[UYARI] {u}")
    for h in hatalar:
        print(f"[HATA] {h}")
    print(f"SONUÇ: {'KALDI' if hatalar else 'GEÇTİ'} ({len(hatalar)} hata, {len(uyarilar)} uyarı)")
    sys.exit(1 if hatalar else 0)


def main():
    ap = argparse.ArgumentParser()
    alt = ap.add_subparsers(dest='komut', required=True)
    alt.add_parser('ayar')
    i = alt.add_parser('iskelet')
    i.add_argument('liste')
    i.add_argument('--rapor', required=True)
    i.add_argument('--kanit', required=True)
    i.add_argument('--baslik', default='İddia doğrulama raporu')
    d = alt.add_parser('denetle')
    d.add_argument('rapor')
    d.add_argument('--iddialar')
    d.add_argument('--yasakli', help='satır başına bir kelime; proje DIŞINDA (scratchpad) tutulur')
    a = ap.parse_args()
    {'iskelet': iskelet, 'denetle': denetle, 'ayar': ayar_yaz}[a.komut](a)


if __name__ == '__main__':
    main()
