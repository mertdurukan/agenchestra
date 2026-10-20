"""Sistem haritası (ADR-0005): tarama, sır sızıntısı, imza/eskime, plan kapısı, kapanış yenilemesi. Geçici projede koşar."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita as H  # noqa: E402
import is_sirasi as S  # noqa: E402

DEGER = "supersecretvalue123"


class HaritaTemel(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.yaz(".env", f"API_KEY={DEGER}\nDB_PASSWORD={DEGER}\nPLAIN=1\n")
        self.yaz("app/kasa.py", '"""Kasa okuyucu."""\nfrom azure.keyvault.secrets import SecretClient\nimport os\nos.environ.get("OPENAI_API_KEY")\n')
        self.yaz("app/main.py", '"""Ana giriş."""\nif __name__ == "__main__":\n    pass\n')
        self.yaz("Keys/db.env", f"PASS={DEGER}\n")
        self.yaz("sema.sql", "CREATE TABLE IF NOT EXISTS magaza (id int);\n")
        self.yaz("requirements.txt", "requests==2.31.0\n# yorum\n")
        self.yaz(".github/workflows/gece.yml", "name: Gece\non:\n  schedule:\n    - cron: '0 3 * * *'\n")
        self.yaz("config.json", '{"url": "https://api.ornek-servis.com/v1"}')

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, rel, metin):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def kayit(self, katman):
        return {r["id"]: r for r in H.oku(self.kok, self.sd, katman)}

    def test_katmanlar_bulunur(self):
        s = self.kayit("sirlar")
        self.assertIn("sir:env:API_KEY", s)
        self.assertIn("sir:env:OPENAI_API_KEY", s)
        self.assertIn("sir:dosya:db.env", s)
        self.assertEqual(s["sir:azure-key-vault"]["durum"], "dogrulanamadi")
        self.assertIn("veri:magaza", self.kayit("veri_modeli"))
        self.assertIn("bagimlilik:py:requests", self.kayit("bagimliliklar"))
        self.assertIn("dis:api.ornek-servis.com", self.kayit("dis_baglantilar"))
        self.assertIn("surec:workflow:gece.yml", self.kayit("surecler"))
        self.assertIn("giriş noktası", self.kayit("moduller")["modul:app/main.py"]["rol"])

    def test_sir_degeri_hicbir_dosyaya_yazilmaz(self):
        H.yenile(self.kok, self.sd)
        for dizin, _, dosyalar in os.walk(H.klasor_yolu(self.sd)):  # teknolojiler/ alt klasörü de taranır
            for ad in dosyalar:
                with open(os.path.join(dizin, ad), encoding="utf-8") as f:
                    self.assertNotIn(DEGER, f.read(), ad)

    def test_keys_dizini_icerigi_okunmaz(self):
        s = self.kayit("sirlar")
        self.assertNotIn("sir:env:PASS", s)

    def test_degisim_eskitir_yenile_temizler(self):
        H.yenile(self.kok, self.sd)
        self.assertEqual(H.denetle(self.kok, self.sd)["eskimis"], [])
        self.yaz("sema.sql", "CREATE TABLE yeni_tablo (id int);\n")
        d = H.denetle(self.kok, self.sd)
        self.assertIn("veri_modeli", d["eskimis"])
        self.assertNotIn("sirlar", d["eskimis"])
        s = H.yenile(self.kok, self.sd)
        self.assertEqual(s["yenilenen"], ["veri_modeli"])
        veri = self.kayit("veri_modeli")
        self.assertIn("veri:yeni_tablo", veri)
        self.assertNotIn("veri:magaza", veri)  # eski kayıt düştü
        self.assertEqual(H.denetle(self.kok, self.sd)["eskimis"], [])

    def test_silinen_kaynagin_kaydi_kalmaz(self):
        H.yenile(self.kok, self.sd)
        os.remove(os.path.join(self.kok, "app", "main.py"))
        self.assertNotIn("modul:app/main.py", self.kayit("moduller"))

    def test_durum_dizini_taranmaz(self):
        self.yaz(".claude/orkestra/gorev/x.py", '"""Orkestra verisi."""\n')
        self.assertFalse([k for k in self.kayit("moduller") if ".claude" in k])

    def test_kayit_kimlikleri_ve_index_dosyasi(self):
        self.assertIsNone(H.kayit_kimlikleri(self.sd))
        H.yenile(self.kok, self.sd)
        self.assertIn("sir:env:API_KEY", H.kayit_kimlikleri(self.sd))
        self.assertTrue(os.path.isfile(os.path.join(H.klasor_yolu(self.sd), "INDEX.md")))


class HaritaKapisi(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.is_k = os.path.join(self.kok, "is1")
        os.makedirs(self.is_k)
        self.yaz_is(True)
        with open(os.path.join(self.kok, ".env"), "w", encoding="utf-8") as f:
            f.write("API_KEY=x\n")
        self._eski = {a: os.environ.pop(a, None) for a in ("ORKESTRA_HARITA_KAPISI", "ORKESTRA_SIRA_KAPISI")}

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)
        for ad, v in self._eski.items():
            os.environ.pop(ad, None)
            if v is not None:
                os.environ[ad] = v

    def yaz_is(self, harita):
        veri = {"sira": S.SIRA_ADI}
        if harita:
            veri["harita"] = True
        with open(os.path.join(self.is_k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def plan(self, alan):
        with open(os.path.join(self.is_k, "plan.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"## 4. Plan maddeleri\n\n### P1 Deneme\n\n**Ne:** x\n\n{alan}\n")

    def test_alansiz_madde_eksik(self):
        H.yenile(self.kok, self.sd)
        self.plan("")
        self.assertTrue(any("Mevcut varlık" in x for x in S.mevcut_varlik_eksikleri(self.is_k)))

    def test_gecerli_kimlik_gecer_olmayan_eksik(self):
        H.yenile(self.kok, self.sd)
        self.plan("**Mevcut varlık:** sir:env:API_KEY")
        self.assertEqual(S.mevcut_varlik_eksikleri(self.is_k), [])
        self.plan("**Mevcut varlık:** sir:env:YOK_BOYLE")
        self.assertTrue(any("haritada yok" in x for x in S.mevcut_varlik_eksikleri(self.is_k)))

    def test_yok_gerekceli_gecer_gerekcesiz_eksik(self):
        self.plan("**Mevcut varlık:** yok — ara \"harita\" scripts/*.py => 0")
        self.assertEqual(S.mevcut_varlik_eksikleri(self.is_k), [])
        self.plan("**Mevcut varlık:** yok")
        self.assertTrue(any("aranan" in x for x in S.mevcut_varlik_eksikleri(self.is_k)))

    def test_harita_yokken_kimlik_dogrulanamaz(self):
        self.plan("**Mevcut varlık:** sir:env:API_KEY")
        self.assertTrue(any("haritası yok" in x for x in S.mevcut_varlik_eksikleri(self.is_k)))

    def test_bayraksiz_is_ve_env_muaf(self):
        self.plan("")
        self.yaz_is(False)
        self.assertEqual(S.mevcut_varlik_eksikleri(self.is_k), [])
        self.yaz_is(True)
        os.environ["ORKESTRA_HARITA_KAPISI"] = "0"
        self.assertEqual(S.mevcut_varlik_eksikleri(self.is_k), [])

    def test_onay_yonergesi_haritali_iste_harita_okutur(self):
        import is_onay as O
        kayit = {"onay": "bekliyor", "klasor": self.is_k, "harita": True}
        self.assertIn("orkestra harita oku", O.baglam_satiri(kayit, False)[0])
        self.assertNotIn("orkestra harita oku", O.baglam_satiri(dict(kayit, harita=False), False)[0])

    def test_is_ac_ve_kapanis_baglantilari(self):
        import is_kaydi as K
        with open(K.__file__, encoding="utf-8") as f:
            self.assertIn('kayit["harita"] = True', f.read())

    def test_kapanis_yenilemesi_hatayi_yutar(self):
        from komutlar import isler
        eski = H.yenile
        H.yenile = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("deneme hatası"))
        try:
            isler._harita_yenile(self.sd)  # istisna fırlatmamalı
        finally:
            H.yenile = eski


if __name__ == "__main__":
    unittest.main()
