"""P6/P7 (I-026): doktor — kontrol çalıştırıcı, onarım sınıfları (A/B/C), kuru koşu, geri alma."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cfg  # noqa: E402
import doktor  # noqa: E402
from doktor import Baglam, Kontrol, Onarim, Sonuc  # noqa: E402


class DoktorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ev = os.path.join(self.tmp.name, "ev")
        p = mock.patch.dict(os.environ, {"ORKESTRA_HOME": self.ev})
        p.start()
        self.addCleanup(p.stop)
        self.log = []

    def kontrol(self, id, sinif_onarim, durum="hata", sinif="onerilen", duzelince="gecti", geri_al=None):
        """Bozuk bir kontrol: onarım uygulanınca durumu `duzelince` olur."""
        durumlar = {"d": durum}

        def kontrol(b):
            return Sonuc(durumlar["d"], "mesaj")

        def uygula():
            self.log.append(id)
            durumlar["d"] = duzelince
            return "yapıldı"

        def onar(b, s):
            return Onarim(sinif_onarim, "açıklama", uygula if sinif_onarim != "C" else None, geri_al, komut="elle")
        return Kontrol(id, id, sinif, kontrol, onar)

    def kos(self, kontroller, **kw):
        return doktor.kos(Baglam(proje=self.tmp.name), kontroller=kontroller, **kw)

    def durum(self, sonuc, id):
        return next(x for x in sonuc["kontroller"] if x["id"] == id)["durum"]

    def test_duzelt_yoksa_hicbir_sey_uygulanmaz(self):
        s = self.kos([self.kontrol("a", "A")])
        self.assertEqual(self.log, [])
        self.assertEqual(self.durum(s, "a"), "hata")

    def test_a_sinifi_duzelt_ile_otomatik(self):
        s = self.kos([self.kontrol("a", "A")], duzelt=True)
        self.assertEqual(self.log, ["a"])
        self.assertEqual(self.durum(s, "a"), "onarildi")

    def test_b_sinifi_evet_ister(self):
        s = self.kos([self.kontrol("b", "B")], duzelt=True)
        self.assertEqual(self.log, [])
        s = self.kos([self.kontrol("b", "B")], duzelt=True, evet_b=True)
        self.assertEqual(self.log, ["b"])
        self.assertEqual(self.durum(s, "b"), "onarildi")

    def test_b_sinifi_etkilesimli_onay(self):
        soruldu = []
        self.kos([self.kontrol("b", "B")], duzelt=True, onay=lambda ac: soruldu.append(ac) or False)
        self.assertEqual((self.log, len(soruldu)), ([], 1))
        self.kos([self.kontrol("b", "B")], duzelt=True, onay=lambda ac: True)
        self.assertEqual(self.log, ["b"])

    def test_c_sinifi_asla_uygulanmaz(self):
        s = self.kos([self.kontrol("c", "C")], duzelt=True, evet_b=True)
        self.assertEqual(self.log, [])
        self.assertFalse(next(x for x in s["kontroller"])["onarim"]["uygulandi"])

    def test_kuru_kosu_yazmaz(self):
        doktor.kos(Baglam(proje=self.tmp.name, kuru=True), duzelt=True, evet_b=True, kontroller=[self.kontrol("a", "A")])
        self.assertEqual(self.log, [])
        self.assertFalse(os.path.exists(self.ev))

    def test_onarim_basarisiz_olursa_durum_hata_kalir(self):
        k = self.kontrol("a", "A")
        eski = k.onar

        def onar(b, s):
            o = eski(b, s)
            o.uygula = lambda: (_ for _ in ()).throw(RuntimeError("patladı"))
            return o
        k.onar = onar
        s = self.kos([k], duzelt=True)
        self.assertEqual(self.durum(s, "a"), "hata")
        self.assertIn("patladı", s["kontroller"][0]["onarim"]["hata"])

    def test_onarim_sonrasi_hala_bozuksa_onarildi_denmez(self):
        s = self.kos([self.kontrol("a", "A", duzelince="hata")], duzelt=True)
        self.assertEqual(self.durum(s, "a"), "hata")

    def test_cokan_kontrol_doktoru_dusurmez(self):
        def boz(b):
            raise RuntimeError("x")
        s = self.kos([Kontrol("z", "z", "zorunlu", boz), self.kontrol("a", "A")])
        self.assertEqual(self.durum(s, "z"), "hata")
        self.assertEqual(s["zorunlu_hata"], ["z"])
        self.assertEqual(len(s["kontroller"]), 2)

    def test_cikis_kodu_yalniz_zorunlu_hatada_1(self):
        sonuc = lambda **kw: {"zorunlu_hata": kw.get("z", [])}
        with mock.patch.object(doktor, "kos", return_value={**sonuc(z=["python"]), "kontroller": [], "kosu": "k", "surum": "s",
                                                           "parmak": "p", "kuru": False, "ozet": {}}):
            self.assertEqual(doktor.main(["--proje", self.tmp.name]), 1)
        with mock.patch.object(doktor, "kos", return_value={**sonuc(), "kontroller": [], "kosu": "k", "surum": "s",
                                                           "parmak": "p", "kuru": False, "ozet": {}}):
            self.assertEqual(doktor.main(["--proje", self.tmp.name]), 0)

    def test_sonuc_kaydi_ve_isaret(self):
        s = self.kos([self.kontrol("a", "A", durum="gecti")])
        self.assertTrue(os.path.isfile(os.path.join(self.ev, "doktor", s["kosu"] + ".json")))
        isaret = cfg.makine_oku()["son_doktor"]
        self.assertEqual(isaret["zaman"], s["kosu"])
        self.assertEqual(isaret["zorunlu_hata"], [])

    def test_geri_al_dosya_onarimi(self):
        yol = os.path.join(self.tmp.name, "x.txt")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("eski")
        k = self.kontrol("a", "A", geri_al={"tur": "dosya", "yol": yol, "onceki": "eski"})
        k2 = self.kontrol("n", "A", geri_al={"tur": "dosya", "yol": yol + ".yeni", "onceki": None})
        with open(yol, "w", encoding="utf-8") as f:
            f.write("yeni")
        with open(yol + ".yeni", "w", encoding="utf-8") as f:
            f.write("y")
        self.kos([k, k2], duzelt=True)
        cikti = doktor.geri_al_son()
        self.assertEqual(len(cikti), 2)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read(), "eski")
        self.assertFalse(os.path.exists(yol + ".yeni"))
        self.assertEqual(doktor.geri_al_son(), [])  # aynı kayıt iki kez uygulanmaz

    def test_geri_al_kaydi_basarisiz_onarimda_yazilmaz(self):
        k = self.kontrol("a", "A", geri_al={"tur": "dosya", "yol": "x", "onceki": ""})
        eski = k.onar

        def onar(b, s):
            o = eski(b, s)
            o.uygula = lambda: (_ for _ in ()).throw(RuntimeError("p"))
            return o
        k.onar = onar
        self.kos([k], duzelt=True)
        self.assertEqual(doktor.geri_al_son(), [])

    def test_makine_config_onarimi_ve_geri_alma(self):
        k = next(x for x in doktor.KONTROLLER if x.id == "makine_config")
        s = self.kos([k], duzelt=True)
        self.assertEqual(self.durum(s, "makine_config"), "onarildi")
        self.assertTrue(cfg.makine_taze_mi())
        d = cfg.makine_oku()["degerler"]
        self.assertIn("python", d)
        self.assertEqual(d["python"]["kaynak"], "doktor")
        doktor.geri_al_son()
        self.assertFalse(os.path.exists(cfg.makine_dosyasi()) and "python" in (cfg.makine_oku().get("degerler") or {}))

    def test_makine_config_eski_makinenin_degerlerini_tasimaz(self):
        cfg.makine_yaz({"bash": "eski-makine-bash"})
        with mock.patch.object(cfg, "parmak_izi", return_value="baska"):
            cfg.makine_yaz({"bash": "eski-makine-bash"})
        # şimdi gerçek parmak izi farklı: dosya bayat
        self.assertFalse(cfg.makine_taze_mi())
        k = next(x for x in doktor.KONTROLLER if x.id == "makine_config")
        self.kos([k], duzelt=True)
        self.assertTrue(cfg.makine_taze_mi())
        self.assertNotEqual(cfg._katman_degeri(cfg.makine_oku(), "bash"), "eski-makine-bash")

    def test_home_cakisma_kontrolu(self):
        k = next(x for x in doktor.KONTROLLER if x.id == "home_cakisma")
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
            self.assertEqual(k.kontrol(Baglam()).durum, "gecti")
            os.makedirs(os.path.join(home, ".claude", "orkestra-makine"))  # makine config'inin evi çakışma sayılmaz
            self.assertEqual(k.kontrol(Baglam()).durum, "gecti")
            os.makedirs(os.path.join(home, ".claude", "orkestra", "gorevler"))
            s = k.kontrol(Baglam())
            self.assertEqual(s.durum, "uyari")
            self.assertEqual(k.onar(Baglam(), s).sinif, "C")  # doktor home klasörünü kendisi taşımaz

    def test_yerlesik_kontrollerin_kimlikleri_benzersiz_ve_siniflari_gecerli(self):
        ids = [k.id for k in doktor.KONTROLLER]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(k.sinif in ("zorunlu", "onerilen", "opsiyonel") for k in doktor.KONTROLLER))

    def test_yerlesik_kontroller_bu_makinede_cokmeden_kosar(self):
        s = doktor.kos(Baglam(proje=self.tmp.name, kuru=True))
        self.assertEqual(len(s["kontroller"]), len(doktor.KONTROLLER))
        self.assertTrue(all(x["durum"] in doktor.DURUMLAR for x in s["kontroller"]))
        json.dumps(s)  # JSON'a uygun
        self.assertFalse(os.path.exists(self.ev), "--kuru yerleşik kontrollerle de ev dizini oluşturmamalı")


if __name__ == "__main__":
    unittest.main()
