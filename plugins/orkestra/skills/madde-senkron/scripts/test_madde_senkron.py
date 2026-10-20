"""madde_senkron.py öz-sınaması: geçici klasörde sahte proje (4 kanonik belge + referans) kurar, vakaları koşar.
Gerçek belgelere dokunmaz. Kullanım: python test_madde_senkron.py   (çıkış 0 = hepsi geçti)"""
import shutil, hashlib, io, json, os, shutil, subprocess, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BETIK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "madde_senkron.py")
BELGELER = {
    "belgeler/agentic_degerlendirme_raporu_taslak.md": (
        "# Taslak\n\n## 12. Firmaya öneriler\n\n### 12.3 Hatlar\n\n| # | Bulgu |\n|---|---|\n| A7 | Çipler ekrana ulaşmıyor. |\n"
        "| A8 | Arka plan işi. |\n\n### 12.7 Bekleyen teyitler\n\n- Eski teyit (A3).\n\n---\n\n### 12.8 Ek\n\nmetin\n", "\r\n", True),
    "belgeler/firmaya_oneriler_dis_surum_20261011.md": (
        "# Dış sürüm\n\n| A7 | **Çipler ekrana hiç ulaşmıyor.**<br>Ayrıntı. |\n\n## 7. Sorular\n\n10. Canlı portal çipleri alıyor mu? (A7)\n", "\n", False),
    "belgeler/bulgu_sunumu_20261012.md": ("# Sunum\n\n- Sohbet ajanı: çipler ulaşmıyor (A7, A8).\n", "\n", False),
    "belgeler/dogrulama_plani_20261011.md": ("# Plan\n\n§1.5 ML çöküşü (A1).\n", "\n", False),
    "belgeler/referans.md": ("# Ref\n\n### 6.G Düzeltme günlüğü\n\nG1 eski\n\n<!-- G -->\n\n## Genel\n", "\n", False),
    "db.py": ("PW = 'x'\n", "\n", False),
}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def kur(K):
    ayar = os.path.join(K, ".claude", "madde_senkron"); os.makedirs(ayar, exist_ok=True)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_belgeler_ornek.json"), os.path.join(ayar, "belgeler.json"))
    for g, (t, nl, bom) in BELGELER.items():
        p = os.path.join(K, g); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write((b"\xef\xbb\xbf" if bom else b"") + t.replace("\n", nl).encode("utf-8"))


def plan(K, ad, **kw):
    p = {"aciklama": "A7 canlı portal teyidi", "aile": "oneriler_12", "kimlikler": ["A7"],
         "islemler": [
             {"belge": "belgeler/agentic_degerlendirme_raporu_taslak.md", "tur": "degistir",
              "eski": "| A7 | Çipler ekrana ulaşmıyor. |", "yeni": "| A7 | Çipler ekrana ulaşmıyor (prod teyitli). |"},
             {"belge": "belgeler/agentic_degerlendirme_raporu_taslak.md", "tur": "bolum_sonuna",
              "baslik": "### 12.7 Bekleyen teyitler", "metin": "- Canlı portal çip yolu (A7)."},
             {"belge": "belgeler/firmaya_oneriler_dis_surum_20261011.md", "tur": "degistir",
              "eski": "**Çipler ekrana hiç ulaşmıyor.**", "yeni": "**Çipler ekrana hiç ulaşmıyor (üretimde teyit edildi).**"},
             {"belge": "belgeler/referans.md", "tur": "isaretci_once", "isaretci": "<!-- G -->",
              "metin": "G7 A7 düzeltmesi (13.10.2026)."}],
         "atlanan": {"belgeler/bulgu_sunumu_20261012.md": "sunum özet düzeyinde; cümle hâlâ doğru"}}
    p.update(kw)
    yol = os.path.join(K, f"{ad}.json")
    json.dump(p, open(yol, "w", encoding="utf-8"), ensure_ascii=False)
    return yol


def kos(*arg):
    r = subprocess.run([sys.executable, BETIK, *arg], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def main():
    K = tempfile.mkdtemp(prefix="madde_senkron_test_")
    kur(K)
    P = ["--proje", K]
    hash0 = {g: sha(os.path.join(K, g)) for g in BELGELER}
    sonuc = []

    def vaka(ad, kosul, o=""):
        sonuc.append(kosul); print(("GEÇTİ " if kosul else "KALDI ") + ad)
        if not kosul:
            print(o[-1800:])

    k, o = kos(*P, "tara", "A7")
    vaka("01 tara: A7 dört kanonik belgenin üçünde bulunur", k == 0 and "bulgu_sunumu_20261012.md: 1 satır" in o and "dogrulama_plani_20261011.md: 0 satır" in o, o)
    k, o = kos(*P, "uygula", plan(K, "p_iyi"), "--kuru")
    vaka("02 kuru: geçerli plan, fark gösterilir, dosyalar değişmez",
         k == 0 and "(prod teyitli)" in o and all(sha(os.path.join(K, g)) == h for g, h in hash0.items()), o)
    k, o = kos(*P, "uygula", plan(K, "p_kapsam", atlanan={}))
    vaka("03 kapsam kapısı: bulgu sunumu gerekçesiz atlanınca durur (çıkış 2)", k == 2 and "KAPSAM" in o, o)
    bozuk = plan(K, "p_bozuk")
    pj = json.load(open(bozuk, encoding="utf-8")); pj["islemler"][2]["eski"] = "BÖYLE BİR METİN YOK"
    json.dump(pj, open(bozuk, "w", encoding="utf-8"), ensure_ascii=False)
    k, o = kos(*P, "uygula", bozuk)
    vaka("04 eşleşme yok: hiçbir dosya yazılmaz (çıkış 2)",
         k == 2 and "ESLESME HATASI (0 != 1)" in o and all(sha(os.path.join(K, g)) == h for g, h in hash0.items()), o)
    k, o = kos(*P, "uygula", plan(K, "p_sir", islemler=[{"belge": "belgeler/bulgu_sunumu_20261012.md", "tur": "degistir",
               "eski": "(A7, A8)", "yeni": "(A7, A8) AccountKey=" + "Q" * 30 + "z9"}], atlanan={
               "belgeler/agentic_degerlendirme_raporu_taslak.md": "testte gerekçe uzunluğu yeterli",
               "belgeler/firmaya_oneriler_dis_surum_20261011.md": "testte gerekçe uzunluğu yeterli"}))
    vaka("05 sır kapısı: eklenen metinde hesap anahtarı kalıbı -> durur", k == 2 and "sır kalıbı" in o and "QQQQ" not in o, o)
    k, o = kos(*P, "uygula", plan(K, "p_db", islemler=[{"belge": "db.py", "tur": "degistir", "eski": "x", "yeni": "y"}]))
    vaka("06 db.py'ye dokunulmaz", k != 0 and "kimlik/bağlantı" in o, o)
    k, o = kos(*P, "uygula", plan(K, "p_iyi2"), "--yedek-kok", os.path.join(K, "yedek"))
    kayit = o.split("Yedek ve kayıt: ")[1].split("\n")[0].strip() if "Yedek ve kayıt: " in o else ""
    ts = open(os.path.join(K, "belgeler/agentic_degerlendirme_raporu_taslak.md"), "rb").read()
    vaka("07 uygula: yazıldı; CRLF + BOM korundu; 12.7 maddesi bölüm sonunda, '---'dan önce",
         k == 0 and ts.startswith(b"\xef\xbb\xbf") and b"\r\n" in ts and b"\n" not in ts.replace(b"\r\n", b"")
         and b"- Eski teyit (A3).\r\n- Canl" in ts and b"(A7).\r\n\r\n---" in ts, o)
    ref = open(os.path.join(K, "belgeler/referans.md"), encoding="utf-8").read()
    vaka("08 işaretçi kaldı, yeni madde hemen önünde", "G7 A7 düzeltmesi (13.10.2026).\n\n<!-- G -->" in ref, ref)
    k, o = kos(*P, "dogrula", kayit)
    vaka("09 dogrula: GEÇTİ", k == 0 and "SONUÇ: GEÇTİ" in o, o)
    dis = os.path.join(K, "belgeler/firmaya_oneriler_dis_surum_20261011.md")
    open(dis, "a", encoding="utf-8").write("plan dışı satır\n")
    k, o = kos(*P, "dogrula", kayit)
    vaka("10 plan dışı değişiklik: dogrula KALDI", k == 1 and "KALDI" in o, o)
    k, o = kos(*P, "geri-al", kayit)
    vaka("11 geri-al: sonradan değişmiş dosyayı ezmez", k == 2 and "yeniden değişmiş" in o, o)
    t = open(dis, encoding="utf-8").read().replace("plan dışı satır\n", "")
    open(dis, "w", encoding="utf-8", newline="\n").write(t)
    k, o = kos(*P, "geri-al", kayit)
    vaka("12 geri-al: tüm belgeler önceki hâline döndü",
         k == 0 and all(sha(os.path.join(K, g)) == h for g, h in hash0.items()), o)
    shutil.rmtree(K, ignore_errors=True)
    print(f"\n{sum(sonuc)}/{len(sonuc)} geçti")
    sys.exit(0 if all(sonuc) else 1)


if __name__ == "__main__":
    main()
