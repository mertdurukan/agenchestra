"""arsivle.py öz-sınaması: geçici klasörde sahte proje + sahte kaynaklar kurar, 12 vakayı koşar.
Tüm "sırlar" her koşuda rastgele üretilir (gerçek değer yok). Gerçek arşive dokunmaz.
Kullanım: python test_arsivle.py      (çıkış 0 = hepsi geçti)"""
import os, random, shutil, string, subprocess, sys, tempfile, zipfile, io

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BETIK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arsivle.py")
URETILEN = []


def r(n):
    v = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))
    URETILEN.append(v)
    return v


def yaz(yol, metin, nl="\n", bom=False):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    open(yol, "wb").write((b"\xef\xbb\xbf" if bom else b"") + metin.replace("\n", nl).encode("utf-8"))


def kur(K):
    proje = os.path.join(K, "proje"); ar = os.path.join(proje, "calisma")
    yaz(os.path.join(ar, "README.md"), "# Arşiv\n\n## Klasörler\n\n| Klasör | İçerik | Başlangıç için |\n|---|---|---|\n"
        "| `plan1\\dalga_raporlari\\` | eski | — |\n| `rakip_20261011\\` | döküm | x |\n"
        "| `tasima_kaydi_20261009.csv` | kayıt | — |\n\n## Sonraki\n", nl="\r\n")
    yaz(os.path.join(ar, "tasima_kaydi_20261009.csv"), "zaman,islem,kaynak,hedef_veya_not\n2026-10-09 08:06:28,tasi,a,b\n", bom=True)
    t = os.path.join(K, "temiz")
    yaz(os.path.join(t, "rapor.md"), "# Rapor\nİletişim: ornek.kisi@firma.com.tr, sunucu 10.20.30.40.\n"
        "Sürüm 2.1.295, tarih 13.10.2026.\nParola: kullanıcıdan istenir.\nAyşe Test tabloyu açtı.\n")
    yaz(os.path.join(t, "betik.py"), "import os\nPASSWORD = os.environ['X_PW']\nconn = connect(password=PASSWORD)\n")
    yaz(os.path.join(t, "alt", "ham.csv"), "a,b\n1,2\n")
    yaz(os.path.join(t, "db.py"), f"PW = '{r(16)}'\n")
    yaz(os.path.join(t, ".env"), f"X_PW={r(16)}\n")
    yaz(os.path.join(t, "__pycache__", "x.pyc"), "\0")
    for ad, ek in [("sirli", ("ham.txt", f"a\nDefaultEndpointsProtocol=https;AccountKey={r(86)}==;x\n")),
                   ("dsn", ("baglanti.md", f"postgresql://kullanici:{r(12)}@host:5432/db\n")),
                   ("ozel", ("anahtar.txt", "-----BEGIN RSA PRIVATE KEY-----\nabc\n")),
                   ("yp", ("not.md", "örnek\npassword = \"ornek-degil-1\"\n"))]:
        shutil.copytree(t, os.path.join(K, ad)); yaz(os.path.join(K, ad, ek[0]), ek[1])
    os.makedirs(os.path.join(K, "xlsx"))
    with zipfile.ZipFile(os.path.join(K, "xlsx", "tablo.xlsx"), "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst><si><t>AuthToken: {r(32)}</t></si></sst>")
    yaz(os.path.join(K, "esleme.tsv"), "K01\tAyşe Test\n")
    shutil.copy(os.path.join(K, "esleme.tsv"), os.path.join(proje, "esleme.tsv"))
    return proje, ar


def kos(*arg, env=None):
    p = subprocess.run([sys.executable, BETIK, *arg], capture_output=True, text=True, encoding="utf-8", env=env)
    return p.returncode, p.stdout + p.stderr


def main():
    K = tempfile.mkdtemp(prefix="arsivle_test_")
    proje, ar = kur(K)
    P = ["--proje", proje]
    sonuc = []

    def vaka(ad, kosul, cikti=""):
        sonuc.append((ad, kosul))
        print(("GEÇTİ " if kosul else "KALDI ") + ad)
        if not kosul:
            print(cikti[-1500:])

    k, o = kos(os.path.join(K, "temiz"), ar, "deneme", "--kuru", "--ad-esleme", os.path.join(K, "esleme.tsv"), *P)
    vaka("01 kuru mod: çıkış 0, hiçbir şey yazılmaz", k == 0 and not os.path.exists(os.path.join(ar, "deneme_" + o.split("deneme_")[1][:8])), o)
    k, o = kos(os.path.join(K, "temiz"), ar, "deneme", "--ad-esleme", os.path.join(K, "esleme.tsv"),
               "--readme-aciklama", "Test arşivi", "--readme-baslangic", "rapor.md", *P)
    hedef = [d for d in os.listdir(ar) if d.startswith("deneme_")]
    h = os.path.join(ar, hedef[0]) if hedef else ""
    vaka("02 temiz kopya: çıkış 0", k == 0 and bool(h), o)
    if h:
        rap = open(os.path.join(h, "rapor.md"), encoding="utf-8").read()
        vaka("03 db.py/.env/__pycache__ kopyalanmadı", not any(os.path.exists(os.path.join(h, x)) for x in ("db.py", ".env", "__pycache__")))
        vaka("04 e-posta, IP, ad maskelendi; sürüm/tarih korunur",
             "<e-posta>" in rap and "<ip>" in rap and "K01" in rap and "Ayşe" not in rap and "2.1.295" in rap and "13.10.2026" in rap, rap)
        kayit = open(os.path.join(ar, "tasima_kaydi_20261009.csv"), encoding="utf-8-sig").read()
        vaka("05 taşıma kaydına arsivle + atla satırları", "arsivle," in kayit and "arsivle_atla_kimlik_dosyasi,db.py" in kayit, kayit)
        rd = open(os.path.join(ar, "README.md"), "rb").read().decode("utf-8")
        vaka("06 arşiv README satırı doğru yerde, CRLF korunur",
             f"| `rakip_20261011\\` | döküm | x |\r\n| `{hedef[0]}\\` | Test arşivi | rapor.md |\r\n| `tasima" in rd, rd)
        vaka("07 klasör README iskeleti yazıldı", os.path.exists(os.path.join(h, "README.md")))
    for ad, kalip in [("sirli", "accountkey"), ("dsn", "dsn_parola"), ("ozel", "ozel_anahtar"), ("xlsx", "authtoken")]:
        k, o = kos(os.path.join(K, ad), ar, ad, *P)
        vaka(f"08 sır ({kalip}): çıkış 2, hedef yok, değer ekranda yok",
             k == 2 and f"DURDUR:{kalip}" in o and not any(d.startswith(ad + "_") for d in os.listdir(ar))
             and not any(v in o for v in URETILEN), o)
    gizli = r(14)
    yaz(os.path.join(K, "ortam", "x.txt"), f"satir\nx {gizli} y\n")
    env = dict(os.environ, X_TEST_TOKEN=gizli)
    k, o = kos(os.path.join(K, "ortam"), ar, "ortam", "--kuru", *P, env=env)
    vaka("09 ortam değişkenindeki sır değeri dosyada: çıkış 2, değer çıktıda yok", k == 2 and gizli not in o and "X_TEST_TOKEN" in o, o)
    k1, o1 = kos(os.path.join(K, "yp"), ar, "yp", "--kuru", *P)
    k2, o2 = kos(os.path.join(K, "yp"), ar, "yp", "--kuru", "--yoksay", "not.md:2:parola", *P)
    vaka("10 tırnaklı parola durur; --yoksay ile uyarıya iner", k1 == 2 and k2 == 0 and "yoksayildi:parola" in o2, o1 + o2)
    k, o = kos(os.path.join(K, "temiz"), ar, "baska", "--ad-esleme", os.path.join(proje, "esleme.tsv"), *P)
    vaka("11 proje içindeki eşleme dosyası reddedilir (çıkış 3)", k == 3, o)
    if h:
        k, o = kos(os.path.join(K, "temiz"), ar, hedef[0], "--ekle", "--ad-esleme", os.path.join(K, "esleme.tsv"), *P)
        yaz(os.path.join(K, "temiz", "alt", "ham.csv"), "a,b\n9,9\n")
        k2, o2 = kos(os.path.join(K, "temiz"), ar, hedef[0], "--ekle", "--ad-esleme", os.path.join(K, "esleme.tsv"), *P)
        vaka("12 --ekle: aynı içerik sessiz geçer, farklı içerik çakışma (çıkış 3)", k == 0 and k2 == 3 and "ham.csv" in o2, o + o2)
    shutil.rmtree(K, ignore_errors=True)
    kalan = [a for a, g in sonuc if not g]
    print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} geçti")
    sys.exit(1 if kalan else 0)


if __name__ == "__main__":
    main()
