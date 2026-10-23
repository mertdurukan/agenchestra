"""guncelle.kontrol: kurulu plugin SHA'sı ile GitHub origin/main karşılaştırması (yeni sürüm var mı).

Git gerçek (tempfile altında origin + klon); ortam kurulumu test_guncelle.Ortam'dan gelir.
`py -3.13 -m pytest plugins/orkestra/tests/test_guncelle_kontrol.py`
"""
import os
import shutil
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guncelle as G  # noqa: E402
import test_guncelle as TG  # noqa: E402


class KontrolTest(TG.Ortam):
    def kurulu_sha(self, sha):
        self.surum = sha[:12]
        self.kurulu_yaz([("orkestra@claude-orchestration", "user", None),
                         ("orkestra-ui@claude-orchestration", "user", None)])

    def klon_basi(self):
        return TG.git(self.klon, "rev-parse", "HEAD")

    def test_guncel_origin_ile_ayni_sha(self):
        self.kurulu_sha(self.klon_basi())
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "guncel")
        self.assertEqual(s["fark"], 0)
        self.assertEqual(s["degisiklikler"], [])
        self.assertIsNone(s["neden"])

    def test_yeni_klon_geride_kalsa_bile_origin_ilerlediyse(self):
        self.kurulu_sha(self.klon_basi())
        self.origine_commit()
        TG.yaz(os.path.join(self.origin, "b.txt"), "x")
        TG.git(self.origin, "add", ".")
        TG.git(self.origin, "commit", "-q", "-m", "Yenilik: ikinci yeni")
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "yeni")
        self.assertEqual(s["fark"], 2)
        self.assertEqual(s["yeni"], TG.git(self.origin, "rev-parse", "HEAD")[:7])
        self.assertEqual([d["konu"] for d in s["degisiklikler"]], ["ikinci yeni"])
        self.assertTrue(all(d["sha"] for d in s["degisiklikler"]))

    def test_yalniz_yenilik_commitleri_listelenir(self):
        self.kurulu_sha(self.klon_basi())
        for i, konu in enumerate(["Otomatik commit: x", "Yenilik: kart yalnız özellikte çıkar", "düzeltme"]):
            TG.yaz(os.path.join(self.origin, f"y{i}.txt"), str(i))
            TG.git(self.origin, "add", ".")
            TG.git(self.origin, "commit", "-q", "-m", konu)
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["fark"], 3)
        self.assertEqual(s["yenilik_say"], 1)
        self.assertEqual([d["konu"] for d in s["degisiklikler"]], ["kart yalnız özellikte çıkar"])

    def test_yenilik_yoksa_sayi_sifir_liste_bos(self):
        self.kurulu_sha(self.klon_basi())
        self.origine_commit()
        s = G.kontrol(ev=self.ev)
        self.assertEqual((s["durum"], s["yenilik_say"], s["degisiklikler"]), ("yeni", 0, []))

    def test_kurulu_sha_klonda_bilinmiyorsa_fark_bos_liste_dolu(self):
        self.surum = "aaaa"
        self.kurulu_yaz([("orkestra@claude-orchestration", "user", None)])
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "yeni")
        self.assertIsNone(s["fark"])
        self.assertEqual((s["yenilik_say"], s["degisiklikler"]), (0, []))   # etiketsiz commit özellik sayılmaz

    def test_getir_false_aga_cikmaz(self):
        self.kurulu_sha(self.klon_basi())
        self.origine_commit()
        self.assertEqual(G.kontrol(ev=self.ev, getir=False)["durum"], "guncel")
        self.assertEqual(G.kontrol(ev=self.ev, getir=True)["durum"], "yeni")

    def test_degisiklik_listesi_sinirli(self):
        self.kurulu_sha(self.klon_basi())
        for i in range(G.DEGISIKLIK_SINIRI + 5):
            TG.yaz(os.path.join(self.origin, f"d{i}.txt"), str(i))
            TG.git(self.origin, "add", ".")
            TG.git(self.origin, "commit", "-q", "-m", f"Yenilik: c{i}")
        s = G.kontrol(ev=self.ev)
        self.assertEqual((s["fark"], s["yenilik_say"]), (G.DEGISIKLIK_SINIRI + 5,) * 2)
        self.assertEqual(len(s["degisiklikler"]), G.DEGISIKLIK_SINIRI)

    def test_kirli_klon_isaretlenir_ama_hata_degil(self):
        self.kurulu_sha(self.klon_basi())
        TG.yaz(os.path.join(self.klon, "a.txt"), "elle degisti")
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "guncel")
        self.assertTrue(s["klon_kirli"])

    def test_ag_yok_hata_doner_firlatmaz(self):
        self.kurulu_sha(self.klon_basi())
        shutil.rmtree(self.origin, ignore_errors=True)
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "hata")
        self.assertIn("GitHub'a ulaşılamadı", s["neden"])

    def test_klon_yok_hata(self):
        os.remove(os.path.join(self.ev, ".claude", "plugins", "known_marketplaces.json"))
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "hata")
        self.assertIn("yayın klonu bulunamadı", s["neden"])

    def test_kurulu_plugin_yok_hata(self):
        os.remove(os.path.join(self.ev, ".claude", "plugins", "installed_plugins.json"))
        s = G.kontrol(ev=self.ev)
        self.assertEqual(s["durum"], "hata")
        self.assertIn("installed_plugins.json", s["neden"])

    def test_iki_plugin_farkli_surum_yeni_sayilir(self):
        self.kurulu_sha(self.klon_basi())
        yol = os.path.join(self.ev, ".claude", "plugins", "installed_plugins.json")
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        ilk = metin.index(self.surum)
        metin = metin[:ilk] + "bbbbbbbbbbbb" + metin[ilk + len(self.surum):]
        TG.yaz(yol, metin)
        self.assertEqual(G.kontrol(ev=self.ev)["durum"], "yeni")


if __name__ == "__main__":
    import unittest
    unittest.main()
