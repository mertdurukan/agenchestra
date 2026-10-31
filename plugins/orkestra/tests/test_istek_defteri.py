"""İstek defteri (ADR-0110): bağlantı çıkarımı deterministiktir; plan ve kapanış kapısı karşılanmamış maddeyi yoklar."""
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import istek_defteri as ID  # noqa: E402
import is_sirasi as S  # noqa: E402
from komutlar import isler  # noqa: E402

# 29.10 isteğine benzeyen 17 bağlantılı mesaj: farklı biçimler, cümle sonu noktalama, tekrar eden bağlantı
URLLER = [f"https://github.com/ornek{i}/depo{i}" for i in range(1, 15)] + [
    "https://example.com/yol/a?x=1&y=2", "https://mcp.example.org/server#bolum", "https://github.com/JuliusBrussee/caveman"]
MESAJ = "Bunları da ekle: " + ", ".join(URLLER[:5]) + ".\n" + "\n".join(f"- {u}" for u in URLLER[5:]) + f"\n(tekrar: {URLLER[0]})"


class IstekDefteri(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def klasor(self, defter=None, plan="# Plan\n", istek=True, kararlar=None):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        kayit = {"id": "I-001", "sira": S.SIRA_ADI}
        if istek:
            kayit["istek"] = True
        if kararlar:
            kayit["kararlar"] = kararlar
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(plan)
        if defter is not None:
            with open(os.path.join(k, ID.DOSYA), "w", encoding="utf-8") as f:
                f.write(defter)
        return k

    def ortam(self):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_ISTEK_DEFTERI_KAPISI": "1"})

    # ---- çıkarım
    def test_17_baglanti_17_madde(self):
        self.assertEqual(ID.baglantilar(MESAJ), URLLER)

    def test_cumle_sonu_noktalama_baglantiya_girmez(self):
        self.assertEqual(ID.baglantilar("bak https://a.io/x. ve https://b.io/y,"), ["https://a.io/x", "https://b.io/y"])

    def test_olustur_defter_yazar_ve_bos_mesajda_hata_verir(self):
        k = self.klasor()
        self.assertEqual(len(ID.olustur(k, MESAJ)), 17)
        self.assertEqual(len(ID._SATIR.findall(open(os.path.join(k, ID.DOSYA), encoding="utf-8").read())), 17)
        with self.assertRaises(ValueError):
            ID.olustur(k, "bağlantı yok")

    def test_serbest_metin_talebi_maddeye_girer(self):
        k = self.klasor()
        self.assertEqual(ID.olustur(k, "bkz https://a.io", ["panelden aç/kapa"]), ["https://a.io", "panelden aç/kapa"])

    # ---- kapı
    def test_planda_anilmayan_madde_ihlal_modunda_reddedilir(self):
        k = self.klasor(defter=ID.defter_metni(["https://a.io", "https://b.io"]), plan="**İstek:** R1\n")
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            e = ID.engel(k)
        self.assertEqual(len(e), 1)
        self.assertIn("R2", e[0])

    def test_hepsi_planda_anilirsa_gecer(self):
        k = self.klasor(defter=ID.defter_metni(["a", "b"]), plan="P1 **İstek:** R1\nP2 **İstek:** R2\n")
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            self.assertEqual(ID.engel(k), [])

    def test_kullanici_yanitiyla_cikarilan_madde_gecer_yanitsiz_gecmez(self):
        defter = "- **R1:** a — Çıkarıldı: D1\n"
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            self.assertTrue(ID.engel(self.klasor(defter=defter)))
        self.proje_temizle()
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            self.assertEqual(ID.engel(self.klasor(defter=defter, kararlar={"D1": {"yanit": "x"}})), [])

    def proje_temizle(self):
        import shutil
        shutil.rmtree(os.path.join(self.proje, "Claude_Orkestrasyon"))

    def test_defter_yoksa_eksik(self):
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            e = ID.engel(self.klasor())
        self.assertTrue(any("istek_defteri.md yok" in x for x in e), e)

    def test_golge_modunda_engellemez(self):
        k = self.klasor(defter=ID.defter_metni(["a"]))
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="golge"):
            self.assertEqual(ID.engel(k), [])

    def test_istek_bayragi_olmayan_is_muaf(self):
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            self.assertEqual(ID.engel(self.klasor(istek=False)), [])

    def test_kapatma_degiskeni(self):
        k = self.klasor(defter=ID.defter_metni(["a"]))
        with mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_ISTEK_DEFTERI_KAPISI": "0"}):
            self.assertEqual(ID.engel(k), [])

    def test_plan_kapisi_istegi_yoklar(self):
        k = self.klasor(defter=ID.defter_metni(["a"]))
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"):
            self.assertTrue(any("R1" in x for x in S.plan_eksikleri(k)))

    def test_kapanis_kapisi_istegi_yoklar(self):
        k = self.klasor(defter=ID.defter_metni(["a"]))
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="ihlal"), \
                mock.patch.dict(os.environ, {"ORKESTRA_OZET_KAPISI": "0", "ORKESTRA_ADR_KAPISI": "0"}):
            s = isler.kapanis_eksigi(self.sd, {"klasor": k})
        self.assertEqual(s[0], "istek")


if __name__ == "__main__":
    unittest.main()
