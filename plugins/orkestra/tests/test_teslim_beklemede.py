"""G-049: denetçi onayı almış kart beklemede'den `kart teslim` ile teslim edilebilir; onaysız/retli/yeni işli kart edilemez."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}
ISCI = {"ajan_id": "w1", "ajan_tipi": "orkestra:isci-t1"}
DENETCI = {"ajan_id": "d1", "ajan_tipi": "orkestra:denetci"}
MESAJ = "teslim için denetçi onayı gerekli (durum: beklemede)"


class TeslimBeklemede(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def yol(self, g):
        return os.path.join(self.sd, "gorevler", f"{g}.json")

    def oku(self, g):
        with open(self.yol(g), encoding="utf-8") as f:
            return json.load(f)

    def ham(self, g):
        with open(self.yol(g), "rb") as f:
            return f.read()

    def ok(self, *args, **kim):
        r = self.cli(*args, **kim)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def isci_bitti(self, g, ozet="eklendi"):
        self.ok("kart", "durum", g, "is-bitti", "--ozet", ozet, "--cikti", "docs/a.md", **ISCI)

    def denetle(self, g, karar):
        if karar == "ret":
            self.ok("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "k1 eksik",
                    "--talimat", "düzelt", **DENETCI)
        else:
            self.ok("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 tamam", **DENETCI)

    def beklemede(self, g):
        self.ok("kart", "durum", g, "beklemede", **ANA)

    def olaylar(self, g):
        return [x.get("olay") for x in self.oku(g)["gecmis"]]

    # K1
    def test_k1_onayli_beklemede_kart_teslim_edilir(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.beklemede(g)
        r = self.cli("kart", "teslim", g, "--ozet", "tarayıcı kontrolü tamam", **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.oku(g)
        self.assertEqual(k["durum"], "teslim")
        olaylar = self.olaylar(g)
        self.assertIn("beklemeden-teslim", olaylar)
        self.assertIn("teslim", olaylar)
        self.assertLess(olaylar.index("beklemeden-teslim"), olaylar.index("teslim"))
        self.assertEqual(olaylar.count("beklemeden-teslim"), 1)
        self.assertTrue(any(x.get("olay") == "beklemeden-teslim" and x.get("zaman") for x in k["gecmis"]))

    def test_k1_ret_sonra_onay_sonra_beklemede_teslim_edilir(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "ret")
        self.isci_bitti(g, "düzeltildi")
        self.denetle(g, "onay")
        self.beklemede(g)
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.oku(g)["durum"], "teslim")

    def test_k1_beklemeye_alinmamis_onayli_kartta_olay_yok(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.ok("kart", "teslim", g, **ANA)
        self.assertNotIn("beklemeden-teslim", self.olaylar(g))

    # K2
    def _reddedilmeli(self, g):
        once = self.ham(g)
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn(MESAJ, r.stderr)
        self.assertEqual(self.ham(g), once)

    def test_k2_onaysiz_beklemede_reddedilir(self):
        g = self.kart()
        self.isci_bitti(g)
        self.beklemede(g)
        self._reddedilmeli(g)

    def test_k2_son_karari_ret_beklemede_reddedilir(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "ret")
        self.beklemede(g)
        self._reddedilmeli(g)

    def test_k2_beklemede_sonrasi_ret_reddedilir(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.beklemede(g)
        self.denetle(g, "ret")
        once = self.ham(g)
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.ham(g), once)
        self.assertNotIn("beklemeden-teslim", self.olaylar(g))

    # K3
    def test_k3_onay_sonrasi_beklemede_sonra_yeni_isci_ciktisi_teslim_edilemez(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.beklemede(g)
        self.isci_bitti(g, "yeni çıktı")
        once = self.ham(g)
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("teslim için denetçi onayı gerekli", r.stderr)
        self.assertEqual(self.ham(g), once)
        self.assertNotIn("beklemeden-teslim", self.olaylar(g))

    # G-102: birleştirme başarısızsa 'beklemeden-teslim' olayı yazılmaz; başarılı birleşmede tam bir kez yazılır
    def agacli_onayli_beklemede(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.beklemede(g)
        k = self.oku(g)
        k["calisma_agaci"] = {"depo": self.proje, "yol": os.path.join(self.proje, "agac"), "dal": f"kart/{g}", "taban": "HEAD"}
        with open(self.yol(g), "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)
        return g

    def teslim_et(self, g, sonuc):
        from unittest import mock
        import orkestra as O
        with mock.patch.object(O.L, "kart_agaci_birlestir", return_value=sonuc), \
                mock.patch.object(O.L, "proje_dizini", return_value=self.proje):
            return O._teslim_et(self.sd, g, "ozet")

    CATISMA = {"sonuc": "catisma", "dosyalar": ["a.py"], "mesaj": "çatışma"}
    TAMAM = {"sonuc": "tamam", "mesaj": "birleşti", "commit": "abc123"}

    def test_g102_k1_birlesmeyen_beklemede_kartta_olay_yazilmaz(self):
        import orkestra as O
        g = self.agacli_onayli_beklemede()
        with self.assertRaises(O._TeslimHatasi) as c:
            self.teslim_et(g, self.CATISMA)
        self.assertEqual(c.exception.kod, 4)
        k = self.oku(g)
        self.assertNotEqual(k["durum"], "teslim")
        self.assertNotIn("beklemeden-teslim", self.olaylar(g))
        with self.assertRaises(O._TeslimHatasi):  # yeniden deneme de yazmaz
            self.teslim_et(g, self.CATISMA)
        self.assertEqual(self.olaylar(g).count("beklemeden-teslim"), 0)

    def test_g102_k2_basarisiz_sonra_basarili_olay_tam_bir_kez(self):
        import orkestra as O
        g = self.agacli_onayli_beklemede()
        for _ in range(2):
            with self.assertRaises(O._TeslimHatasi):
                self.teslim_et(g, self.CATISMA)
        self.teslim_et(g, self.TAMAM)
        k = self.oku(g)
        self.assertEqual(k["durum"], "teslim")
        olaylar = self.olaylar(g)
        self.assertEqual(olaylar.count("beklemeden-teslim"), 1)
        self.assertLess(olaylar.index("beklemeden-teslim"), olaylar.index("teslim"))

    # K4 (davranış değişmez)
    def test_k4_beklemede_kart_goster_ve_liste_hala_beklemede(self):
        g = self.kart()
        self.isci_bitti(g)
        self.denetle(g, "onay")
        self.beklemede(g)
        self.assertIn("beklemede", self.cli("kart", "goster", g).stdout)
        self.assertIn("beklemede", self.cli("kart", "liste").stdout)
        self.assertEqual(self.oku(g)["durum"], "beklemede")

    # diğer durumlar aynen
    def test_denetimde_kart_teslim_edilemez(self):
        g = self.kart()
        self.isci_bitti(g)
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("teslim için denetçi onayı gerekli (durum: denetimde)", r.stderr)


if __name__ == "__main__":
    unittest.main()
