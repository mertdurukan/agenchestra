"""ADR-0029: perspektif talimatı iki yerde yaşar (agents/perspektif-ajani.md ve perspektif.ISTEM); anahtar ifadeler ikisinde de bulunur."""
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import perspektif as P  # noqa: E402
import perspektif_talimat as T  # noqa: E402

ANAHTARLAR = (
    "## Doğrulama (P-021)",
    "Geçtiği yerler:",
    "Düzeltme biçimi: kaynakta yeniden yaz, not ekleme",
    "orkestra perspektif dogrula",
    "Öneri yok: <neden>",
    "duzeltme_tekrari",
    "Kanıt:",
)


def _ajan():
    with open(os.path.join(KOK, "agents", "perspektif-ajani.md"), encoding="utf-8") as f:
        return f.read()


class PerspektifTalimat(unittest.TestCase):
    def test_anahtar_ifadeler_iki_kopyada(self):
        ajan, istem = _ajan(), P.ISTEM
        for a in ANAHTARLAR:
            self.assertIn(a, ajan, f"ajan dosyasında yok: {a}")
            self.assertIn(a, istem, f"ISTEM'de yok: {a}")

    def test_dogrulama_bolumu_iki_kopyada_ayni(self):
        def bolum(metin):
            m = re.search(r"## Doğrulama \(P-021\)\n(.*?)(?=\n## |\nKurallar:)", metin, re.S)
            self.assertIsNotNone(m)
            return m.group(1).strip()
        self.assertEqual(bolum(_ajan()), bolum(P.ISTEM))

    def test_istem_bicimlenir(self):
        x = P.ISTEM.format(hafiza="H", proje="P", sd="S")
        self.assertIn("Geçtiği yerler:", x)

    def test_akista_dogrula_kaydetten_once(self):
        ajan = _ajan()
        self.assertLess(ajan.index("perspektif dogrula <rapor yolu>"), ajan.index("perspektif kaydet <rapor yolu>"))


H, PR, SD = "HAFIZA_X", "PROJE_X", "SD_X"
B = chr(92)


def _uret():
    return T.uret(H, PR, SD)


def _md_bolum(ad):
    """md'den bölümün birebir gövdesi (ön madde ve Akış olmadan, satır tabanlı bağımsız ayrıştırma)."""
    satirlar = _ajan().replace(chr(13) + chr(10), chr(10)).split(chr(10))
    cikti, icinde = [], False
    for s in satirlar:
        if s.startswith("## "):
            numarali = re.match(r"## [0-9]+[.]", s) is not None
            if s.startswith("## " + ad):
                icinde = True
            elif not numarali:
                icinde = False
        if icinde:
            cikti.append(s)
    assert cikti, ad
    return chr(10).join(cikti).strip(chr(10))


class TalimatUret(unittest.TestCase):
    def test_md_bolumleri_birebir_icerir(self):
        x = _uret()
        for ad in ("Rapor bölümleri", "Doğrulama (P-021)", "Vaat satırı", "Yayın satırı", "Kurallar"):
            self.assertIn(_md_bolum(ad), x, f"üretilen metinde md bölümü yok: {ad}")

    def test_akis_ve_on_madde_yok(self):
        x = _uret()
        self.assertNotIn("Akış", x)
        self.assertNotIn("perspektif basladi", x)
        self.assertNotIn("name: perspektif-ajani", x)
        self.assertNotIn("maxTurns", x)

    def test_yayin_satiri_var(self):
        self.assertGreaterEqual(_uret().count("Yayın:"), 1)

    def test_bolum_9_ve_10_var_ve_alan_adlari(self):
        x = _uret()
        self.assertIn("## 9. Zaman maliyeti", x)
        self.assertIn("## 10. Fırsatlar", x)
        for alan in ("yukseltilen_kart", "denetim_payi", "yeni kural, eşik doğrulanmadı"):
            self.assertIn(alan, x)

    def test_yollar_yerlesmis(self):
        x = _uret()
        self.assertIn(SD + B + "perspektif" + B + "girdi.json", x)
        self.assertIn(H, x)
        self.assertIn(PR + B + "CLAUDE.md", x)
        self.assertTrue(x.startswith("#SUREC:perspektif" + chr(10)))
        self.assertNotIn("{sd}", x)

    def test_istem_kapsami_korunur(self):
        """Mevcut ISTEM'in taşıdığı bilgi (süreç etiketi, yollar, girdi.json, görev, kaynak satırları) türetilen metinde var."""
        istem = P.ISTEM.format(hafiza=H, proje=PR, sd=SD)
        x = _uret()
        for satir in istem.splitlines():
            if satir.startswith(("#SUREC:", "Sen orkestra sisteminin", "Görev:", "Kaynaklar (", "2. Otomatik hafıza", "3. Proje kuralları")):
                self.assertIn(satir, x, f"ISTEM bilgisi kayıp: {satir[:40]}")
        self.assertIn(SD + B + "perspektif" + B + "girdi.json", istem)
        # ISTEM'in sekiz bölüm başlığı türetilen metindeki bölüm 1-8 ile örtüşür
        for anahtar in ("Özet", "Birleştirilecek kopyalar", "Çelişkiler", "Boyut", "Önerilen değişiklikler",
                        "Skill adayları", "Orkestra sağlığı"):
            self.assertIn(anahtar, istem)
            self.assertIn(anahtar, x)

    def test_numarali_madde_bicimi_rapor_dogrula_ile_uyumlu(self):
        """Yeni bölümler `Kanıt:` satırı ayrıştırıcısını bozmaz: örnek rapordaki §9/§10 öneri satırları dogrulanir."""
        import tempfile
        rapor = chr(10).join(["## 9. Zaman maliyeti", "1. Uzun tur",
                              "   Kanıt: ara " + chr(34) + "x" + chr(34) + " nope.md => 0",
                              "   Vaat: ölçü=ölçülemez; yön=-; kapsam=-", ""])
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "r.md")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(rapor)
            sonuc = P.rapor_dogrula(yol, d, d)
        self.assertEqual(sonuc["toplam"], 1)

    def test_eksik_bolum_hata_verir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "a.md")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(chr(10).join(["---", "name: x", "---", "## Akış", "1. a", "## Kurallar", "- k", ""]))
            with self.assertRaises(ValueError):
                T.uret(H, PR, SD, md_yolu=yol)

    def test_idempotent(self):
        self.assertEqual(_uret(), _uret())


if __name__ == "__main__":
    unittest.main()