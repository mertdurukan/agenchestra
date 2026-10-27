"""is-anlati taslak denetimi: iki paragraflık anlatıdaki biçim, sayı, sır ve abartı ihlallerini mekanik yakalar.

Asıl kaynak eklentidir (plugins/orkestra/scripts); test: tests/test_is_anlati_denetle.py.

Kullanım:
  python -I is_anlati_denetle.py <dosya> [--guclu-fiil] [--durum Tamam|Kısmen|Engelli]

Çıktı: ihlal yoksa `temiz` (çıkış 0); varsa her satır `KOD: ileti` (çıkış 1).
Kodlar: A01 paragraf sayısı, A02 etiket, A03 kelime aralığı, A04 yasak biçim, A05 sır, A06 şahıs,
A07 abartı, A08 iç süreç sızıntısı, A09 tekrar, A10 Durum Kısmen/Engelli iken sınır ifadesi yok
(baglam["durum"] boşsa ya da Tamam ise atlanır). Salt okur; dosya yazmaz.
"""
import re
import sys

ETIKETLER = ("**Ne yaptım?**", "**Nasıl yaptım?**")
KELIME_ALT, KELIME_UST = 40, 95
TEKRAR_N = 6

SIR_ANAHTAR = re.compile(r"(parola|şifre|password|secret|token|api[_-]?key)\s*[=:]\s*\S+", re.I)
SIR_URL = re.compile(r"://[^\s/:@]+:[^\s/@]+@")
SIR_HEX = re.compile(r"(?<![A-Za-z0-9+/=_-])[0-9a-fA-F]{32,}(?![A-Za-z0-9+/=_-])")
SIR_B64 = re.compile(r"(?<![A-Za-z0-9+/=_-])(?=[A-Za-z0-9+/=_-]*\d)(?=[A-Za-z0-9+/=_-]*[A-Za-z])"
                     r"[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9+/=_-])")

MADDE = re.compile(r"^\s*(?:[-*]\s|\d+\.\s)", re.M)
SHA = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", re.I)
YOL_SURUCU = re.compile(r"(?<!\w)[A-Za-z]:[\\/]")  # tek harfli sürücü; "postgres://" yol sayılmaz
YOL_PARCALI = re.compile(r"(?:[\w.-]+[\\/])+[\w-]+\.[A-Za-z0-9]{1,5}\b")
URL = re.compile(r"https?://|www\.", re.I)

BIRINCI_TEKIL = re.compile(
    r"\b\w{2,}(?:d[ıiuü]m|t[ıiuü]m|yorum|ıyorum|iyorum|uyorum|üyorum)\b", re.I)
# Çoğul: açık liste (genel -dık/-tık soneki otomatik, pratik, kritik, mantık gibi sözcükleri yakalardı).
# Edilgen: -ıldı/-ildi/-uldu/-üldü ile biten fiiller (yapıldı, edildi, çözüldü).
COGUL_EDILGEN = re.compile(
    r"\b(?:yaptık|ettik|ekledik|yazdık|düzelttik|ölçtük|kurduk|okuduk|bulduk|gösterdik|hazırladık|"
    r"uyguladık|tamamladık|çalıştık|denedik|yaptırdık|çözdük|aldık|"
    r"(?!değildi\b)\w{2,}(?:ıldı|ildi|uldu|üldü))\b", re.I)

ABARTI = re.compile(r"\b(çözdüm|çözüldü|başarıyla|sorunsuz|kusursuz|tamamen|eksiksiz|mükemmel)\b", re.I)
ABARTI_SERBEST = {"çözdüm", "başarıyla"}

# A10: Durum Kısmen/Engelli iken taslak en az birini taşır (küçük harfle alt dize araması).
_SINIR_IFADELERI = ("kısmen", "henüz", "bekliyor", "yapılmadı", "teyit", "engel", "açık")
_SINIR_DURUMLARI = {"kısmen", "kismen", "engelli"}

SIZINTI = [
    (re.compile(r"\b[PKGC]-?\d{1,3}\b"), "madde/kural kimliği"),
    (re.compile(r"\bADR-\d+", re.I), "ADR kimliği"),
    (re.compile(r"\bhook\w*", re.I), "hook"),
    (re.compile(r"\bkapı\w*", re.I), "kapı (kural anlamında)"),
    (re.compile(r"orkestra kuralı", re.I), "orkestra kuralı"),
]


def _paragraflar(metin):
    return [p.strip() for p in re.split(r"\n\s*\n", metin.strip()) if p.strip()] if metin.strip() else []


def _govde(par):
    """Paragrafın etiketsiz metni (kelime sayımı ve şahıs denetimi için)."""
    for e in ETIKETLER:
        if par.startswith(e):
            return par[len(e):].strip()
    return par


def _kelimeler(s):
    return [w for w in re.sub(r"[^\w\s]", " ", s.lower()).split()]


def denetle(metin, baglam=None):
    """Taslağı denetler; `(kod, ileti)` listesi döner, boşsa temiz."""
    izin = bool((baglam or {}).get("guclu_fiil_izni"))
    ihlal = []
    par = _paragraflar(metin)

    if len(par) != 2:
        ihlal.append(("A01", f"paragraf sayısı {len(par)}; tam 2 olmalı"))

    for i, etiket in enumerate(ETIKETLER[:len(par)]):
        if not par[i].startswith(etiket):
            ihlal.append(("A02", f"{i + 1}. paragraf {etiket} ile başlamalı"))
    if any(l.lstrip().startswith("#") for l in metin.splitlines()):
        ihlal.append(("A02", "başlık satırı (#) olamaz"))

    for i, p in enumerate(par[:2]):
        g = _govde(p)
        n = len(g.split())
        if not KELIME_ALT <= n <= KELIME_UST:
            ihlal.append(("A03", f"{i + 1}. paragraf {n} kelime; {KELIME_ALT}-{KELIME_UST} olmalı"))
        if not BIRINCI_TEKIL.search(g):
            ihlal.append(("A06", f"{i + 1}. paragrafta birinci tekil şahıs fiili yok"))
        m = COGUL_EDILGEN.search(g)
        if m:
            ihlal.append(("A06", f"çoğul/edilgen kalıp: {m.group(0)}"))

    if MADDE.search(metin):
        ihlal.append(("A04", "madde işareti yasak"))
    if "|" in metin:
        ihlal.append(("A04", "tablo yasak"))
    if "`" in metin:
        ihlal.append(("A04", "ters tırnak yasak"))
    if SHA.search(metin):
        ihlal.append(("A04", "commit SHA yasak"))
    if YOL_SURUCU.search(metin) or YOL_PARCALI.search(metin):
        ihlal.append(("A04", "dosya yolu yasak"))
    if URL.search(metin):
        ihlal.append(("A04", "URL yasak"))

    if SIR_ANAHTAR.search(metin) or SIR_URL.search(metin) or SIR_HEX.search(metin) or SIR_B64.search(metin):
        ihlal.append(("A05", "sır kalıbı"))

    for m in ABARTI.finditer(metin):
        k = m.group(1).lower()
        if izin and k in ABARTI_SERBEST:
            continue
        ihlal.append(("A07", f"abartı: {m.group(1)}"))

    for rx, ad in SIZINTI:
        m = rx.search(metin)
        if m:
            ihlal.append(("A08", f"iç süreç sızıntısı ({ad}): {m.group(0)}"))

    if len(par) >= 2:
        a, b = _kelimeler(_govde(par[0])), _kelimeler(_govde(par[1]))
        gram = {tuple(a[i:i + TEKRAR_N]) for i in range(len(a) - TEKRAR_N + 1)}
        if any(tuple(b[i:i + TEKRAR_N]) in gram for i in range(len(b) - TEKRAR_N + 1)):
            ihlal.append(("A09", f"iki paragrafta aynı {TEKRAR_N} kelimelik dizi"))

    durum = _durum(baglam)
    if durum in _SINIR_DURUMLARI:
        kucuk = metin.lower()
        if not any(s in kucuk for s in _SINIR_IFADELERI):
            ihlal.append(("A10", f"Durum {durum.capitalize()} ama taslakta sınır ifadesi yok "
                                 f"({', '.join(_SINIR_IFADELERI)})"))

    return ihlal


def _durum(baglam):
    """baglam['durum'] metninin ilk sözcüğü küçük harfle ('' = yok)."""
    m = re.match(r"\s*(\w+)", str((baglam or {}).get("durum") or ""))
    return m.group(1).lower() if m else ""


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    guclu = "--guclu-fiil" in a
    durum = ""
    if "--durum" in a:
        i = a.index("--durum")
        durum = a[i + 1] if i + 1 < len(a) else ""
        del a[i:i + 2]
    dosyalar = [x for x in a if not x.startswith("--")]
    if len(dosyalar) != 1:
        print("kullanım: is_anlati_denetle.py <dosya> [--guclu-fiil] [--durum Tamam|Kısmen|Engelli]")
        return 2
    try:
        with open(dosyalar[0], encoding="utf-8") as f:
            metin = f.read()
    except OSError as e:
        print(f"HATA: dosya okunamadı: {e}")
        return 2
    ihlal = denetle(metin, {"guclu_fiil_izni": guclu})
    if not ihlal:
        print("temiz")
        return 0
    for kod, ileti in ihlal:
        print(f"{kod}: {ileti}")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
