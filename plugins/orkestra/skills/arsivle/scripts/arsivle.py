"""arsivle.py — scratchpad (ya da başka bir çalışma klasörü) -> proje arşivi.

plan1\\scriptler\\sanitize.py (ad eşlemesi + e-posta maskesi) ile plan2_I\\scan.py / scan2.py
(sır ve PII kalıpları) mantığının birleşik, test edilmiş hali.

Kullanım:
  python arsivle.py <kaynak> <hedef_kok> <konu> [--kuru] [--ekle] [--tarih YYYYMMDD]
                    [--ad-esleme DOSYA] [--kayit CSV] [--readme-aciklama METIN --readme-baslangic METIN]
                    [--maskeleme-yok] [--proje KOK]
  python arsivle.py --yalniz-tara <yol>      (kopyalamadan tarar; kapanis.py da kullanır)

Akış (sıra önemli):
  1. Yol kapıları: hedef proje içinde olmalı, kaynak hedefin içinde olmamalı.
  2. Envanter: kimlik/bağlantı dosyaları (db.py, .env, *.pem, *.key …) ve artıklar ATLANIR.
  3. Sır taraması (kaynakta, kopyalamadan ÖNCE): DURDUR sınıfı bir eşleşme varsa hiçbir dosya
     kopyalanmaz, çıkış kodu 2. Sır değeri hiçbir zaman ekrana yazılmaz (yalnız kalıp, dosya, satır, uzunluk).
  4. Maskeleme: e-posta -> <e-posta>, IPv4 -> <ip>, ad eşlemesi (ad -> kod). Eşleme dosyası
     hedefin içinde olamaz; eşlemedeki ad maskeden sonra hâlâ geçiyorsa durur.
  5. Kopyalama (--kuru değilse) -> son tarama (hedefte; DURDUR eşleşmesi varsa çıkış 4).
  6. Taşıma kaydına satır, klasör README iskeleti (yoksa), istenirse arşiv README tablosuna satır.

Çıkış kodları: 0 tamam · 2 sır bulundu (kopyalanmadı) · 3 kullanım/yol hatası · 4 son tarama başarısız
"""
import argparse, csv, datetime as dt, fnmatch, io, json, os, re, shutil, sys, zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BURASI = os.path.dirname(os.path.abspath(__file__))
VARSAYILAN_PROJE = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

# ---------------------------------------------------------------- atlanacak dosyalar
ATLA_DOSYA = [  # kimlik / bağlantı dosyaları: içerik okunmaz, kopyalanmaz
    "db.py", ".env", ".env.*", "*.env", "*.pem", "*.key", "*.pfx", "*.p12", "*.kdbx", "id_rsa*", "id_ed25519*",
    ".credentials*", "credentials.json", "*.secret", ".netrc", ".pgpass", "pgpass.conf", "secrets*",
]
ATLA_KLASOR = ["secrets*", ".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", ".mypy_cache"]
ATLA_ARTIK = ["*.pyc", "~$*", "Thumbs.db", ".DS_Store"]

METIN_UZANTI = {".md", ".txt", ".csv", ".tsv", ".py", ".sql", ".json", ".jsonl", ".yaml", ".yml", ".ini", ".cfg",
                ".toml", ".sh", ".ps1", ".bat", ".cmd", ".js", ".ts", ".tsx", ".html", ".htm", ".xml", ".log",
                ".example", ".conf", ".r", ".ipynb", ".mmd"}
OFIS_UZANTI = {".xlsx", ".xlsm", ".docx", ".pptx"}

# ---------------------------------------------------------------- sır kalıpları
# DURDUR: yüksek güven -> kopyalama durur. UYARI: rapora girer, durdurmaz.
DURDUR = {
    "ozel_anahtar": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "accountkey": re.compile(r"(?i)account_?key\s*[=:\"']+\s*[A-Za-z0-9+/]{20,}={0,2}"),
    "sas_imza": re.compile(r"(?i)[?&]sig=[A-Za-z0-9%+/]{20,}"),
    "authtoken": re.compile(r"(?i)auth_?token[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_.]{12,}"),
    "bearer": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=]{20,}"),
    "parola": re.compile(r"(?i)\b(password|passwd|pwd|parola|sifre|şifre)\b[\"']?\s*[=:]\s*(?P<tirnak>[\"']?)"
                         r"(?!<|\*|\$|%|\{|\(|null\b|none\b|os\.|getenv|environ|input\b|''|\"\"|true\b|false\b)"
                         r"(?P<deger>[^\s\"',;)]{4,})"),
    "dsn_parola": re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mssql|mongodb(?:\+srv)?|redis|amqp)://[^\s:/@]+:(?!\*|<|\$\{)[^\s@/]{3,}@"),
    "pgpassword": re.compile(r"(?i)\bPGPASSWORD\s*=\s*(?!<|\*|\$)\S{4,}"),
    "client_secret": re.compile(r"(?i)client_?secret[\"']?\s*[:=]\s*[\"']?(?!<|\*|\$)[A-Za-z0-9\-_.~]{12,}"),
    "api_anahtari": re.compile(r"(?i)\b(api[_-]?key|x-api-key|subscription[_-]?key)[\"']?\s*[:=]\s*[\"']?(?!<|\*|\$)[A-Za-z0-9\-_]{16,}"),
    "aws_anahtar": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "llm_anahtar": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{24,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
}
UYARI = {
    "uzun_b64": re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{60,}={0,2}(?![A-Za-z0-9+/])"),
    "hassas_kelime": re.compile(r"(?i)\b(sharedaccess\w*|secret|connect_parameter|read_details|post_json_data)\b"),
}
EPOSTA = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
IPV4 = re.compile(r"(?<!\d)(?<!\d\.)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\.?\d)")
GORMEZDEN = re.compile(r"\*\*\*@\*\*\*|<e-posta>|@example\.(com|org)|@users\.noreply")
ORTAM_SIR_ADI = re.compile(r"(?i)(PW|PASS|PASSWORD|SECRET|TOKEN|APIKEY|API_KEY|DSN|CONN)")


def ortam_sirlari():
    """Ortam değişkenlerindeki sır değerleri (ad -> değer). Değer hiçbir yere yazılmaz; yalnız aranır."""
    out = {}
    for k, v in os.environ.items():
        if ORTAM_SIR_ADI.search(k) and v and len(v) >= 6 and not os.path.exists(v) and " " not in v:
            out[k] = v
    return out


def eslesir(ad, kaliplar):
    return any(fnmatch.fnmatch(ad.lower(), k.lower()) for k in kaliplar)


def metin_mi(yol):
    uz = os.path.splitext(yol)[1].lower()
    if uz in METIN_UZANTI or os.path.basename(yol).lower() in ("readme", "dockerfile", "makefile"):
        return True
    if uz in OFIS_UZANTI:
        return False
    try:
        with open(yol, "rb") as f:
            parca = f.read(4096)
        return b"\x00" not in parca and len(parca) > 0 and uz == ""
    except OSError:
        return False


def oku(yol):
    ham = open(yol, "rb").read()
    bom = ham.startswith(b"\xef\xbb\xbf")
    try:
        t = ham.decode("utf-8-sig")
    except UnicodeDecodeError:
        t = ham.decode("cp1254", errors="replace")
    return t, bom


def ofis_metni(yol):
    """xlsx/docx/pptx içindeki XML parçalarını tek metin olarak döndürür (tarama için)."""
    parcalar = []
    with zipfile.ZipFile(yol) as z:
        for n in z.namelist():
            if n.endswith(".xml") or n.endswith(".rels"):
                parcalar.append(z.read(n).decode("utf-8", errors="replace"))
    return "\n".join(parcalar)


def maskeli_goster(kalip, s):
    """Değeri asla göstermez: yalnız anahtar sözcük ve uzunluk."""
    on = re.match(r"^([A-Za-z_\-]{2,25})(?=[\s=:\"'])", s)  # yalnız anahtar sözcük; değerin hiçbir harfi değil
    return f"{on.group(1) if on else kalip}…<{len(s)} karakter>"


KARMASIK = re.compile(r"[^A-Za-z_.\[\]()çğıöşüÇĞİÖŞÜ]")  # rakam ya da sembol varsa gerçek değer sayılır


def metni_tara(metin, ortam, yoksay=None):
    """-> (durdur[], uyari[]) ; her öğe (kalip, satir_no, gosterim)."""
    durdur, uyari = [], []
    satirlar = metin.splitlines()
    for i, ln in enumerate(satirlar, 1):
        for k, rx in DURDUR.items():
            for m in rx.finditer(ln):
                if k == "parola" and not m.group("tirnak") and not KARMASIK.search(m.group("deger")):
                    # tırnaksız ve yalnız harf/altçizgi/nokta: büyük olasılıkla değişken adı ya da düz yazı
                    uyari.append(("parola_degisken_mi", i, maskeli_goster(k, m.group(0))))
                    continue
                if (yoksay or {}).get(i) in (k, "*"):
                    uyari.append((f"yoksayildi:{k}", i, maskeli_goster(k, m.group(0))))
                    continue
                durdur.append((k, i, maskeli_goster(k, m.group(0))))
        for k, rx in UYARI.items():
            for m in rx.finditer(ln):
                s = m.group(0)
                if k == "uzun_b64" and (s.isalpha() or s.islower() or s.count("/") > 3 or s.isdigit()):
                    continue
                uyari.append((k, i, maskeli_goster(k, s) if k == "uzun_b64" else s[:30]))
        for ad, deger in ortam.items():
            if deger in ln:
                durdur.append((f"ortam_degiskeni_degeri:{ad}", i, f"<{len(deger)} karakter>"))
    return durdur, uyari


def ad_eslemesi_yukle(yol):
    esleme = {}
    if not yol:
        return esleme
    for ln in open(yol, encoding="utf-8-sig"):
        ln = ln.rstrip("\r\n")
        if not ln.strip() or ln.startswith("#"):
            continue
        kod, ad = ln.split("\t", 1)
        esleme[ad.strip()] = kod.strip()
    return esleme


def maskele(metin, esleme, ip_maskele=True):
    sayac = {"e-posta": 0, "ip": 0, "ad": 0}

    def ep(m):
        if GORMEZDEN.search(m.group(0)):
            return m.group(0)
        sayac["e-posta"] += 1
        return "<e-posta>"
    metin = EPOSTA.sub(ep, metin)
    if ip_maskele:
        def ip(m):
            s = m.group(0)
            if s.startswith(("0.", "127.0.0.1")) or s == "255.255.255.255":
                return s
            sayac["ip"] += 1
            return "<ip>"
        metin = IPV4.sub(ip, metin)
    for ad, kod in sorted(esleme.items(), key=lambda x: -len(x[0])):
        rx = re.compile(rf"(?<!\w){re.escape(ad)}(?!\w)", re.I)
        metin, n = rx.subn(kod, metin)
        sayac["ad"] += n
    return metin, sayac


def envanter(kaynak):
    """-> (alinacak[(tam, goreli)], atlanan[(goreli, neden)])"""
    alinacak, atlanan = [], []
    for dp, dn, fn in os.walk(kaynak):
        g_dp = os.path.relpath(dp, kaynak)
        for d in list(dn):
            if eslesir(d, ATLA_KLASOR):
                atlanan.append((os.path.normpath(os.path.join(g_dp, d)) + os.sep, "klasor_dislandi"))
                dn.remove(d)
        for f in sorted(fn):
            g = os.path.normpath(os.path.join(g_dp, f))
            if eslesir(f, ATLA_DOSYA):
                atlanan.append((g, "kimlik_dosyasi"))
            elif eslesir(f, ATLA_ARTIK):
                atlanan.append((g, "artik"))
            else:
                alinacak.append((os.path.join(dp, f), g))
    return alinacak, atlanan


def yolu_tara(kok, ortam=None, dosyalar=None, yoksay=None):
    """Bir klasörü (ya da dosya listesini) tarar. -> dict: durdur, uyari, taranamadi, eposta, ip"""
    ortam = ortam_sirlari() if ortam is None else ortam
    if dosyalar is None:
        if os.path.isfile(kok):
            dosyalar = [(kok, os.path.basename(kok))]
            kok = os.path.dirname(kok)
        else:
            dosyalar, _ = envanter(kok)
    sonuc = {"durdur": [], "uyari": [], "taranamadi": [], "eposta": [], "ip": []}
    for tam, g in dosyalar:
        try:
            if metin_mi(tam):
                metin, _ = oku(tam)
            elif os.path.splitext(tam)[1].lower() in OFIS_UZANTI:
                metin = ofis_metni(tam)
            else:
                sonuc["taranamadi"].append(g)
                continue
        except Exception as e:  # bozuk zip vb.
            sonuc["taranamadi"].append(f"{g} ({type(e).__name__})")
            continue
        d, u = metni_tara(metin, ortam, (yoksay or {}).get(os.path.normpath(g)))
        sonuc["durdur"] += [(g,) + x for x in d]
        sonuc["uyari"] += [(g,) + x for x in u]
        n_ep = sum(1 for m in EPOSTA.finditer(metin) if not GORMEZDEN.search(m.group(0)))
        if n_ep:
            sonuc["eposta"].append((g, n_ep))
        n_ip = len(IPV4.findall(metin))
        if n_ip:
            sonuc["ip"].append((g, n_ip))
    return sonuc


def tarama_yazdir(s, baslik):
    print(f"--- {baslik}")
    print(f"DURDUR eşleşmesi: {len(s['durdur'])} | uyarı: {len(s['uyari'])} | e-posta içeren dosya: {len(s['eposta'])}"
          f" | IP içeren dosya: {len(s['ip'])} | taranamayan: {len(s['taranamadi'])}")
    for g, k, i, gos in s["durdur"][:50]:
        print(f"  [DURDUR:{k}] {g}:{i}  {gos}")
    for g, k, i, gos in s["uyari"][:20]:
        print(f"  [uyari:{k}] {g}:{i}  {gos}")
    if len(s["uyari"]) > 20:
        print(f"  … {len(s['uyari']) - 20} uyarı daha")
    for g in s["taranamadi"][:20]:
        print(f"  [taranamadi] {g}")


def icinde(alt, ust):
    alt, ust = os.path.normcase(os.path.abspath(alt)), os.path.normcase(os.path.abspath(ust))
    return alt == ust or alt.startswith(ust.rstrip("\\/") + os.sep)


def satir_sonu(yol):
    try:
        return "\r\n" if b"\r\n" in open(yol, "rb").read() else "\n"
    except OSError:
        return "\n"


def kayda_yaz(kayit, satirlar):
    nl = satir_sonu(kayit) if os.path.exists(kayit) else "\n"
    yeni = not os.path.exists(kayit)
    with open(kayit, "a", encoding="utf-8-sig" if yeni else "utf-8", newline="") as f:
        w = csv.writer(f, lineterminator=nl)
        if yeni:
            w.writerow(["zaman", "islem", "kaynak", "hedef_veya_not"])
        else:
            ham = open(kayit, "rb").read()
            if ham and not ham.endswith(b"\n"):
                f.write(nl)
        for r in satirlar:
            w.writerow(r)


def arsiv_readme_satiri(readme, klasor_adi, aciklama, baslangic):
    """Arşiv README'sinin '## Klasörler' tablosuna, son klasör satırından sonra satır ekler (yeniden okuyarak)."""
    metin = open(readme, "rb").read().decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in metin else "\n"
    satirlar = metin.split(nl)
    hucre = f"`{klasor_adi}\\`"
    if any(s.startswith(f"| {hucre} |") for s in satirlar):
        return "zaten_var"
    try:
        bas = next(i for i, s in enumerate(satirlar) if s.strip() == "## Klasörler")
    except StopIteration:
        raise SystemExit("README'de '## Klasörler' başlığı yok; satırı elle ekleyin.")
    son = None
    for i in range(bas + 1, len(satirlar)):
        s = satirlar[i]
        if s.startswith("## "):
            break
        if re.match(r"^\| `[^`]+\\` \|", s):
            son = i
    if son is None:
        raise SystemExit("Klasör tablosunda klasör satırı bulunamadı; satırı elle ekleyin.")
    temiz = lambda x: x.replace("|", "/").replace("\r", " ").replace("\n", " ").strip()
    satirlar.insert(son + 1, f"| {hucre} | {temiz(aciklama)} | {temiz(baslangic) or '—'} |")
    open(readme, "wb").write(nl.join(satirlar).encode("utf-8"))
    return "eklendi"


def readme_iskeleti(hedef, konu_klasor, kopyalanan, atlanan, sayac_toplam, kaynak_etiketi):
    yol = os.path.join(hedef, "README.md")
    if os.path.exists(yol):
        return False
    tarih = re.search(r"(\d{8})$", konu_klasor)
    t = dt.datetime.strptime(tarih.group(1), "%Y%m%d").strftime("%d.%m.%Y") if tarih else ""
    s = [f"# {konu_klasor} ({t})", "",
         "> İÇERİK ÖZETİ: (arşivleyen doldurur: hangi iş, hangi soruya cevap, sonuç belgesi nerede)", "",
         "| Dosya | İçerik |", "|---|---|"]
    s += [f"| `{g.replace(os.sep, '/')}` | |" for g in kopyalanan if g != "README.md"]
    s += ["", "**Güvenlik:** `arsivle.py` ile arşivlendi; sır taraması temiz.",
          f"Maskelenen: e-posta {sayac_toplam['e-posta']}, IP {sayac_toplam['ip']}, ad {sayac_toplam['ad']}."]
    if atlanan:
        s.append("Arşive alınmayanlar: " + ", ".join(f"`{g}` ({n})" for g, n in atlanan) + ".")
    s.append(f"Kaynak: {kaynak_etiketi}.")
    open(yol, "w", encoding="utf-8", newline="\n").write("\n".join(s) + "\n")
    return True


def main():
    ap = argparse.ArgumentParser(description="Scratchpad -> arşiv (sır taraması, maskeleme, kayıt)")
    ap.add_argument("kaynak", nargs="?")
    ap.add_argument("hedef_kok", nargs="?", help="ör. <proje>\calisma_arsivi")
    ap.add_argument("konu", nargs="?", help="ör. madde_dogrulama (tarih soneki yoksa eklenir)")
    ap.add_argument("--kuru", action="store_true", help="hiçbir şey yazma; plan + tarama raporu")
    ap.add_argument("--ekle", action="store_true", help="hedef klasör varsa yalnız yeni dosyaları ekle")
    ap.add_argument("--tarih", default=dt.date.today().strftime("%Y%m%d"))
    ap.add_argument("--ad-esleme", help="kod<TAB>ad satırları; proje DIŞINDA durmalı")
    ap.add_argument("--kayit", help="taşıma kaydı CSV (varsayılan: <hedef_kok>\\tasima_kaydi_20261009.csv)")
    ap.add_argument("--readme-aciklama", help="arşiv README tablosu 'İçerik' hücresi")
    ap.add_argument("--readme-baslangic", default="README.md", help="'Başlangıç için' hücresi")
    ap.add_argument("--maskeleme-yok", action="store_true")
    ap.add_argument("--ip-maskeleme-yok", action="store_true")
    ap.add_argument("--proje", default=VARSAYILAN_PROJE)
    ap.add_argument("--yalniz-tara", metavar="YOL")
    ap.add_argument("--yoksay", action="append", default=[], metavar="DOSYA:SATIR[:KALIP]",
                    help="YALNIZ kullanıcı onayıyla: yanlış pozitif bir DURDUR eşleşmesini uyarıya indirir (kayda yazılır)")
    ap.add_argument("--json", action="store_true", help="özet JSON'u da yazdır")
    a = ap.parse_args()

    ortam = ortam_sirlari()
    yoksay = {}
    for y in a.yoksay:
        # DOSYA kaynağa göreli yol; sondan böl: "a/b.md:12" ya da "a/b.md:12:parola"
        m = re.match(r"^(?P<d>.+?):(?P<s>\d+)(?::(?P<k>[\w:\-]+))?$", y)
        if not m:
            ap.error(f"--yoksay biçimi DOSYA:SATIR[:KALIP] olmalı: {y}")
        yoksay.setdefault(os.path.normpath(m["d"]), {})[int(m["s"])] = m["k"] or "*"
    if a.yalniz_tara:
        s = yolu_tara(a.yalniz_tara, ortam)
        tarama_yazdir(s, f"tarama: {a.yalniz_tara}")
        sys.exit(2 if s["durdur"] else 0)

    if not (a.kaynak and a.hedef_kok and a.konu):
        ap.error("kaynak, hedef_kok ve konu gerekli")
    kaynak, hedef_kok, proje = (os.path.abspath(x) for x in (a.kaynak, a.hedef_kok, a.proje))
    konu = re.sub(r"[^\w\-]", "_", a.konu.strip()).strip("_").lower()
    konu_klasor = konu if re.search(r"_\d{8}$", konu) else f"{konu}_{a.tarih}"
    hedef = os.path.join(hedef_kok, konu_klasor)

    # 1. yol kapıları
    hatalar = []
    if not os.path.isdir(kaynak):
        hatalar.append(f"kaynak klasör yok: {kaynak}")
    if not icinde(hedef_kok, proje):
        hatalar.append(f"hedef proje dışında: {hedef_kok} (proje {proje})")
    if icinde(kaynak, hedef) or icinde(hedef, kaynak):
        hatalar.append("kaynak ile hedef iç içe")
    if a.ad_esleme and icinde(a.ad_esleme, proje):
        hatalar.append("ad eşleme dosyası proje içinde olamaz (anahtar arşive girer)")
    if os.path.isdir(hedef) and os.listdir(hedef) and not a.ekle:
        hatalar.append(f"hedef klasör dolu: {hedef} (--ekle ile yalnız yeni dosyalar eklenir)")
    if hatalar:
        print("YOL HATASI:\n  " + "\n  ".join(hatalar))
        sys.exit(3)

    # 2. envanter
    alinacak, atlanan = envanter(kaynak)
    esleme = ad_eslemesi_yukle(a.ad_esleme)

    def yazilacak(t):  # hedefe yazılacak bayt (maskeli)
        if a.maskeleme_yok or not metin_mi(t):
            return open(t, "rb").read()
        metin, bom = oku(t)
        m, _ = maskele(metin, esleme, not a.ip_maskeleme_yok)
        return (b"\xef\xbb\xbf" if bom else b"") + m.encode("utf-8")

    if a.ekle and os.path.isdir(hedef):
        mevcut = [(t, g) for t, g in alinacak if os.path.exists(os.path.join(hedef, g))]
        cakisan = [g for t, g in mevcut if yazilacak(t) != open(os.path.join(hedef, g), "rb").read()
                   and open(t, "rb").read() != open(os.path.join(hedef, g), "rb").read()]
        if cakisan:
            print("ÇAKIŞMA: hedefte aynı adlı ama farklı içerikli dosyalar var (üstüne yazılmaz):")
            for g in cakisan:
                print("  ", g)
            sys.exit(3)
        alinacak = [(t, g) for t, g in alinacak if (t, g) not in mevcut]

    # 3. kaynak taraması (kopyalamadan önce)
    s = yolu_tara(kaynak, ortam, alinacak, yoksay)
    print(f"kaynak: {kaynak}\nhedef : {hedef}\nalınacak dosya: {len(alinacak)} | atlanan: {len(atlanan)}")
    for g, n in atlanan:
        print(f"  [atla:{n}] {g}")
    tarama_yazdir(s, "kaynak taraması (kopyalamadan önce)")
    if s["durdur"]:
        print("\nDURDU: sır kalıbı bulundu, HİÇBİR DOSYA KOPYALANMADI. Değeri kaynağında maskele ya da dosyayı "
              "kaynaktan çıkar, sonra yeniden çalıştır. Sır değerini hiçbir çıktıya yazma.")
        sys.exit(2)

    # 4. maskeleme planı
    yeni_icerik, sayac_toplam = {}, {"e-posta": 0, "ip": 0, "ad": 0}
    if not a.maskeleme_yok:
        for t, g in alinacak:
            if not metin_mi(t):
                continue
            metin, bom = oku(t)
            m, sayac = maskele(metin, esleme, not a.ip_maskeleme_yok)
            kalan = [ad for ad in esleme if re.search(rf"(?<!\w){re.escape(ad)}(?!\w)", m, re.I)]
            if kalan:
                print(f"DURDU: maskeden sonra eşlemedeki ad hâlâ geçiyor: {g} ({len(kalan)} ad)")
                sys.exit(2)
            if m != metin:
                yeni_icerik[g] = (m, bom)
                for k in sayac_toplam:
                    sayac_toplam[k] += sayac[k]
                print(f"  [maskele] {g}  " + ", ".join(f"{k}={v}" for k, v in sayac.items() if v))
    ofis_ep = [g for g, n in s["eposta"] if os.path.splitext(g)[1].lower() in OFIS_UZANTI]
    if ofis_ep:
        print("UYARI: Office dosyalarında e-posta var ve otomatik maskelenmez: " + ", ".join(ofis_ep))

    if a.kuru:
        print(f"\nKURU MOD: hiçbir şey yazılmadı. Kopyalanacak {len(alinacak)} dosya, maskelenecek {len(yeni_icerik)}.")
        sys.exit(0)

    # 5. kopyala + son tarama
    os.makedirs(hedef, exist_ok=True)
    for t, g in alinacak:
        h = os.path.join(hedef, g)
        os.makedirs(os.path.dirname(h), exist_ok=True)
        if g in yeni_icerik:
            m, bom = yeni_icerik[g]
            open(h, "wb").write((b"\xef\xbb\xbf" if bom else b"") + m.encode("utf-8"))
            shutil.copystat(t, h)
        else:
            shutil.copy2(t, h)
    kopyalanan = [g for _, g in alinacak]
    son = yolu_tara(hedef, ortam, yoksay=yoksay)
    tarama_yazdir(son, "son tarama (hedefte)")
    if son["durdur"]:
        print("SON TARAMA BAŞARISIZ: hedefteki eşleşmeleri elle temizle; kayıt ve README yazılmadı.")
        sys.exit(4)

    # 6. kayıt + README
    readme_yeni = readme_iskeleti(hedef, konu_klasor, kopyalanan, atlanan, sayac_toplam, "çalışma klasörü (scratchpad)")
    kayit = a.kayit or os.path.join(hedef_kok, "tasima_kaydi_20261009.csv")
    zaman = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hedef_g = os.path.relpath(hedef, proje)
    satirlar = [[zaman, "arsivle", "scratchpad", f"{hedef_g} ({len(kopyalanan)} dosya; maske e-posta={sayac_toplam['e-posta']}"
                 f" ip={sayac_toplam['ip']} ad={sayac_toplam['ad']})"]]
    satirlar += [[zaman, f"arsivle_atla_{n}", g, "arşive alınmadı"] for g, n in atlanan]
    satirlar += [[zaman, "arsivle_yoksay", f"{d}:{sn}", f"kalıp={k}; kullanıcı onaylı yanlış pozitif"]
                 for d, v in yoksay.items() for sn, k in v.items()]
    kayda_yaz(kayit, satirlar)
    readme_durum = "istenmedi"
    if a.readme_aciklama:
        readme_durum = arsiv_readme_satiri(os.path.join(hedef_kok, "README.md"), konu_klasor,
                                           a.readme_aciklama, a.readme_baslangic)
    ozet = {"hedef": hedef, "kopyalanan": len(kopyalanan), "atlanan": len(atlanan), "maske": sayac_toplam,
            "uyari": len(son["uyari"]), "taranamadi": son["taranamadi"], "klasor_readme_iskeleti": readme_yeni,
            "arsiv_readme_satiri": readme_durum, "kayit": kayit}
    print("\nTAMAM: " + json.dumps(ozet, ensure_ascii=False))
    if readme_yeni:
        print("YAPILACAK: klasör README'sindeki 'İÇERİK ÖZETİ' ve dosya açıklamalarını doldur.")


if __name__ == "__main__":
    main()
