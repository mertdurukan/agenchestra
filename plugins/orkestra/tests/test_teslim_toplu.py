"""G-058: `kart teslim-toplu --json-dosya <f>` — onaylı kartları tek çağrıda teslim eder; kart başına `kart teslim` kurallarının aynısı."""
import json
import os
import unittest

import test_cekirdek as TC

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}
ISCI = {"ajan_id": "w1", "ajan_tipi": "orkestra:isci-t1"}
DENETCI = {"ajan_id": "d1", "ajan_tipi": "orkestra:denetci"}


class TeslimToplu(unittest.TestCase):
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

    def onayli(self):
        g = self.kart()
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", **ISCI)
        self.ok("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 tamam", **DENETCI)
        return g

    def onaysiz(self):
        g = self.kart()
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", **ISCI)
        return g  # denetimde

    def dosya(self, icerik, ad="toplu.json", ham=False):
        yol = os.path.join(self.proje, ad)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik if ham else json.dumps(icerik, ensure_ascii=False))
        return yol

    def toplu(self, liste, **kim):
        return self.cli("kart", "teslim-toplu", "--json-dosya", self.dosya(liste), **(kim or ANA))

    def sonuclar(self, r):
        s = json.loads(r.stdout)
        self.assertIsInstance(s, list)
        return {x["id"]: x for x in s}

    def olaylar(self, g):
        return [x.get("olay") for x in self.oku(g)["gecmis"]]

    # K1
    def test_k1_iki_onayli_kart_tek_cagrida_teslim_olur(self):
        a, b = self.onayli(), self.onayli()
        r = self.toplu([{"id": a, "ozet": "birinci tamam"}, {"id": b, "ozet": "ikinci tamam"}])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.sonuclar(r)
        self.assertEqual(set(s), {a, b})
        for g, ozet in ((a, "birinci tamam"), (b, "ikinci tamam")):
            self.assertEqual(s[g]["sonuc"], "teslim")
            self.assertIn("mesaj", s[g])
            k = self.oku(g)
            self.assertEqual(k["durum"], "teslim")
            self.assertEqual(self.olaylar(g).count("teslim"), 1)
            self.assertTrue(any(x.get("olay") == "teslim" and x.get("zaman") for x in k["gecmis"]))
            self.assertEqual(k["teslim_ozeti"], ozet)

    def test_k1_tek_kartli_liste(self):
        a = self.onayli()
        r = self.toplu([{"id": a, "ozet": "tek"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sonuclar(r)[a]["sonuc"], "teslim")
        self.assertEqual(self.oku(a)["durum"], "teslim")

    def test_k1_toplu_teslim_tek_kart_teslimiyle_ayni_kart_alanlarini_uretir(self):
        a, b = self.onayli(), self.onayli()
        self.ok("kart", "teslim", a, "--ozet", "aynı özet", **ANA)
        self.assertEqual(self.toplu([{"id": b, "ozet": "aynı özet"}]).returncode, 0)
        ka, kb = self.oku(a), self.oku(b)
        self.assertEqual(ka["durum"], kb["durum"])
        self.assertEqual(ka["teslim_ozeti"], kb["teslim_ozeti"])
        self.assertEqual(self.olaylar(a)[-3:], self.olaylar(b)[-3:])

    def test_k1_stdout_yalniz_json_listesi(self):
        a = self.onayli()
        r = self.toplu([{"id": a, "ozet": "x"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsInstance(json.loads(r.stdout), list)

    # K2
    def test_k2_onaysiz_kart_hata_digerleri_teslim_cikis_4(self):
        a, kotu, b = self.onayli(), self.onaysiz(), self.onayli()
        once = self.ham(kotu)
        r = self.toplu([{"id": a, "ozet": "a"}, {"id": kotu, "ozet": "k"}, {"id": b, "ozet": "b"}])
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        s = self.sonuclar(r)
        self.assertEqual(s[a]["sonuc"], "teslim")
        self.assertEqual(s[b]["sonuc"], "teslim")
        self.assertEqual(s[kotu]["sonuc"], "hata")
        self.assertIn("teslim için denetçi onayı gerekli", s[kotu]["mesaj"])
        self.assertEqual(self.oku(a)["durum"], "teslim")
        self.assertEqual(self.oku(b)["durum"], "teslim")
        self.assertEqual(self.ham(kotu), once)
        self.assertNotIn("teslim", self.olaylar(kotu))

    def test_k2_hatali_kart_basta_olsa_da_sonrakiler_islenir(self):
        kotu, a = self.onaysiz(), self.onayli()
        r = self.toplu([{"id": kotu, "ozet": "k"}, {"id": a, "ozet": "a"}])
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertEqual(self.oku(a)["durum"], "teslim")
        self.assertEqual(self.oku(kotu)["durum"], "denetimde")

    def test_k2_olmayan_kart_hata_digerleri_teslim_cikis_4(self):
        a = self.onayli()
        r = self.toplu([{"id": "G-999", "ozet": "yok"}, {"id": a, "ozet": "a"}])
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        s = self.sonuclar(r)
        self.assertEqual(s["G-999"]["sonuc"], "hata")
        self.assertTrue(s["G-999"]["mesaj"])
        self.assertEqual(s[a]["sonuc"], "teslim")
        self.assertEqual(self.oku(a)["durum"], "teslim")

    def test_k2_ayni_kart_ikinci_kez_teslim_hata(self):
        a = self.onayli()
        self.ok("kart", "teslim", a, "--ozet", "ilk", **ANA)
        once = self.ham(a)
        r = self.toplu([{"id": a, "ozet": "ikinci"}])
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.sonuclar(r)[a]["sonuc"], "hata")
        self.assertEqual(self.ham(a), once)

    def test_k2_retli_kart_hata(self):
        g = self.kart()
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "e", "--cikti", "docs/a.md", **ISCI)
        self.ok("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "eksik",
                "--talimat", "düzelt", **DENETCI)
        r = self.toplu([{"id": g, "ozet": "x"}])
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertEqual(self.sonuclar(r)[g]["sonuc"], "hata")
        self.assertNotEqual(self.oku(g)["durum"], "teslim")

    def test_k2_hepsi_hata_cikis_4(self):
        r = self.toplu([{"id": self.onaysiz(), "ozet": "x"}, {"id": "G-998", "ozet": "y"}])
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertTrue(all(x["sonuc"] == "hata" for x in json.loads(r.stdout)))

    # yetki: tek kart yoluyla aynı kural
    def test_yetki_ana_olmayan_ajan_teslim_edemez(self):
        a = self.onayli()
        once = self.ham(a)
        r = self.toplu([{"id": a, "ozet": "x"}], **ISCI)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ham(a), once)

    # uç durumlar
    def test_bos_liste_cikis_0_ve_bos_json(self):
        r = self.toplu([])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])

    def test_bozuk_json_dosyasi_reddedilir(self):
        a = self.onayli()
        once = self.ham(a)
        r = self.cli("kart", "teslim-toplu", "--json-dosya", self.dosya("{bozuk", ham=True), **ANA)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ham(a), once)

    def test_olmayan_dosya_reddedilir(self):
        r = self.cli("kart", "teslim-toplu", "--json-dosya", os.path.join(self.proje, "yok.json"), **ANA)
        self.assertNotEqual(r.returncode, 0)

    def test_json_dizi_degil_reddedilir(self):
        a = self.onayli()
        once = self.ham(a)
        r = self.toplu({"id": a, "ozet": "x"})
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ham(a), once)

    def test_id_eksik_girdi_hata_digerleri_islenir(self):
        a = self.onayli()
        r = self.toplu([{"ozet": "idsiz"}, {"id": a, "ozet": "a"}])
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.oku(a)["durum"], "teslim")
        self.assertIn("hata", [x["sonuc"] for x in json.loads(r.stdout)])

    def test_ozetsiz_girdi_teslim_olur_tek_kart_gibi(self):
        a = self.onayli()
        r = self.toplu([{"id": a}])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.oku(a)["durum"], "teslim")

    def test_defter_kaydi_dusulur(self):
        a = self.onayli()
        self.assertEqual(self.toplu([{"id": a, "ozet": "defter notu"}]).returncode, 0)
        with open(os.path.join(self.sd, "ortak_defter.jsonl"), encoding="utf-8") as f:
            satirlar = [json.loads(x) for x in f if x.strip()]
        self.assertTrue(any(x.get("gorev") == a and x.get("sonuc") == "TESLİM" for x in satirlar))

    # K3: tek kart yolu değişmez
    def test_k3_tek_kart_teslim_hala_calisir(self):
        a = self.onayli()
        r = self.cli("kart", "teslim", a, "--ozet", "tek", **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{a} → teslim", r.stdout)

    def test_k3_tek_kart_onaysiz_hala_3_ile_reddedilir(self):
        g = self.onaysiz()
        r = self.cli("kart", "teslim", g, **ANA)
        self.assertEqual(r.returncode, 3)
        self.assertIn("teslim için denetçi onayı gerekli (durum: denetimde)", r.stderr)


if __name__ == "__main__":
    unittest.main()
