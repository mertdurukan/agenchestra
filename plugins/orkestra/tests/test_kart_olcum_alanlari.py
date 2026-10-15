"""G-037: ölçüm N2/N3/N4 — kart is_turlari, risk ve butce alanları.
`py -3.13 -m pytest plugins/orkestra/tests/test_kart_olcum_alanlari.py -q -p no:cacheprovider`

N2: `kart durum <id> is-bitti` her çağrıda is_turlari'na {sira, basamak, agent_id, surec, cikti_ozeti_sha, girdi_sha} ekler.
    basamak yalnız hook'un verdiği ajan tipinden ('orkestra:isci-tN' -> 'TN'); kart alanından kopyalanmaz.
N3: kart yeni --risk / toplu 'risk' doğrulanır. N4: --butce-usd/--butce-token / toplu 'butce' yalnız kayıt.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

SHA = re.compile(r"^[0-9a-f]{64}$")
ONEK = "Çalışma ağacı: "


class OlcumAlanlari(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_olcum_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ------------------------------------------------------------ yardımcılar
    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [C.CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return C.kos(a, self.proje)

    def yeni(self, *ek, girdi="iş tanımı", kabul="kriter bir", basamak="T2"):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "ölçüm kartı", "--basamak", basamak, "--girdi", girdi,
                     "--kabul", kabul, "--yazma", "docs/**", "--sinif", "belge", *ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().splitlines()[-1]

    def yol(self, gid):
        return os.path.join(self.sd, "gorevler", f"{gid}.json")

    def oku(self, gid):
        with open(self.yol(gid), encoding="utf-8") as f:
            return json.load(f)

    def yaz(self, gid, **alanlar):
        k = self.oku(gid)
        k.update(alanlar)
        with open(self.yol(gid), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False)

    def bitti(self, gid, tip="orkestra:isci-t2", aid="ajan-1", *ek):
        return self.cli("kart", "durum", gid, "is-bitti", "--ozet", "tamam", *ek, ajan_id=aid, ajan_tipi=tip)

    def tur(self, gid, i=-1):
        return self.oku(gid)["is_turlari"][i]

    def kart_idleri(self):
        d = os.path.join(self.sd, "gorevler")
        if not os.path.isdir(d):
            return []
        return sorted(x[:-5] for x in os.listdir(d) if re.fullmatch(r"G-\d+\.json", x))

    # ------------------------------------------------------------ N2 kriter 1
    def test_isci_t2_kaydi_ve_alanlar(self):
        g = self.yeni()
        r = self.bitti(g)
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.tur(g)
        self.assertEqual(t["basamak"], "T2")
        self.assertEqual(t["agent_id"], "ajan-1")
        self.assertIsInstance(t["sira"], int)
        self.assertRegex(t["girdi_sha"], SHA)
        self.assertIn("surec", t)
        self.assertIn("cikti_ozeti_sha", t)
        self.assertNotEqual(t.get("basamak_kaynak"), "bilinmiyor")

    def test_surec_isciden_is_turetilir(self):
        g = self.yeni()
        self.bitti(g)
        self.assertEqual(self.tur(g)["surec"], "is")

    def test_ardisik_cagrilar_artan_sira(self):
        g = self.yeni()
        self.bitti(g, "orkestra:isci-t2", "a1")
        self.bitti(g, "orkestra:isci-t3", "a2")
        self.bitti(g, "orkestra:isci-t2", "a3")
        turlar = self.oku(g)["is_turlari"]
        self.assertEqual(len(turlar), 3)
        siralar = [t["sira"] for t in turlar]
        self.assertEqual(siralar, sorted(set(siralar)))
        self.assertEqual([t["basamak"] for t in turlar], ["T2", "T3", "T2"])
        self.assertEqual([t["agent_id"] for t in turlar], ["a1", "a2", "a3"])
        self.assertEqual(self.oku(g)["son_is_sira"], siralar[-1])

    # ------------------------------------------------------------ N2 kriter 2
    def test_kart_basamagi_t3_isci_t2_kaydi_t2(self):
        g = self.yeni(basamak="T3")
        self.assertEqual(self.oku(g)["basamak"], "T3")
        self.assertEqual(self.bitti(g, "orkestra:isci-t2").returncode, 0)
        self.assertEqual(self.tur(g)["basamak"], "T2")

    def test_kart_basamagi_t1_isci_t4_kaydi_t4(self):
        g = self.yeni(basamak="T1")
        self.bitti(g, "orkestra:isci-t4")
        self.assertEqual(self.tur(g)["basamak"], "T4")

    # ------------------------------------------------------------ N2 kriter 3
    def test_isci_olmayan_ajan_basamak_null(self):
        for tip in ("orkestra:test-yazari", "bilinmiyor", "general-purpose"):
            g = self.yeni(basamak="T3")
            self.assertEqual(self.bitti(g, tip, "x1").returncode, 0)
            t = self.tur(g)
            self.assertIsNone(t["basamak"], tip)
            self.assertEqual(t["basamak_kaynak"], "bilinmiyor", tip)

    def test_kimliksiz_cagri_basamak_null(self):
        g = self.yeni(basamak="T3")
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "tamam")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.tur(g)
        self.assertIsNone(t["basamak"])
        self.assertEqual(t["basamak_kaynak"], "bilinmiyor")

    def test_ana_ajan_is_bitiremez_kayit_eklenmez(self):
        g = self.yeni()
        r = self.bitti(g, "ana", "ana")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.oku(g).get("is_turlari"))

    # ------------------------------------------------------------ N2 kriter 4
    def girdi_sha(self, g):
        self.bitti(g)
        return self.tur(g)["girdi_sha"]

    def test_ayni_girdi_ayni_sha(self):
        a = self.yeni(girdi="aynı girdi", kabul="k1")
        b = self.yeni(girdi="aynı girdi", kabul="k1")
        self.assertEqual(self.girdi_sha(a), self.girdi_sha(b))

    def test_girdi_degisince_sha_degisir(self):
        a = self.yeni(girdi="girdi bir", kabul="k1")
        b = self.yeni(girdi="girdi iki", kabul="k1")
        self.assertNotEqual(self.girdi_sha(a), self.girdi_sha(b))

    def test_kriter_degisince_sha_degisir(self):
        a = self.yeni(girdi="g", kabul="k1")
        b = self.yeni(girdi="g", kabul="k2")
        self.assertNotEqual(self.girdi_sha(a), self.girdi_sha(b))

    def test_test_komutu_degisince_sha_degisir(self):
        a = self.yeni(girdi="g", kabul="k1")
        b = self.yeni(girdi="g", kabul="k1")
        self.yaz(a, test_komutu="py -m pytest a")
        self.yaz(b, test_komutu="py -m pytest b")
        self.assertNotEqual(self.girdi_sha(a), self.girdi_sha(b))

    def test_agac_oneki_sonucu_degistirmez(self):
        a = self.yeni(girdi="aynı girdi", kabul="k1")
        b = self.yeni(girdi="aynı girdi", kabul="k1")
        self.yaz(b, girdi=ONEK + "C:/baska/yol-kart-G-002\naynı girdi")
        self.assertEqual(self.girdi_sha(a), self.girdi_sha(b))

    def test_onek_sonradan_eklenince_sha_sabit(self):
        g = self.yeni(girdi="sabit girdi", kabul="k1")
        s1 = self.girdi_sha(g)
        self.yaz(g, girdi=ONEK + "C:/x/y\nsabit girdi")
        self.bitti(g, "orkestra:isci-t2", "ajan-2")
        self.assertEqual(self.tur(g)["girdi_sha"], s1)

    # ------------------------------------------------------------ N2 kriter 5
    def _dosya(self, ad, icerik):
        dosya = os.path.join(self.proje, "docs", ad)
        os.makedirs(os.path.dirname(dosya), exist_ok=True)
        with open(dosya, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)
        return dosya

    def test_cikti_icerigi_degisince_sha_degisir(self):
        g = self.yeni()
        dosya = self._dosya("c.md", "birinci")
        self.bitti(g, "orkestra:isci-t2", "a1", "--cikti", dosya)
        s1 = self.tur(g)["cikti_ozeti_sha"]
        self.assertRegex(s1, SHA)
        self._dosya("c.md", "ikinci")
        self.bitti(g, "orkestra:isci-t2", "a2")
        s2 = self.tur(g)["cikti_ozeti_sha"]
        self.assertRegex(s2, SHA)
        self.assertNotEqual(s1, s2)

    def test_ayni_cikti_ayni_sha(self):
        g = self.yeni()
        dosya = self._dosya("c.md", "sabit")
        self.bitti(g, "orkestra:isci-t2", "a1", "--cikti", dosya)
        self.bitti(g, "orkestra:isci-t2", "a2")
        t = self.oku(g)["is_turlari"]
        self.assertEqual(t[0]["cikti_ozeti_sha"], t[1]["cikti_ozeti_sha"])

    def test_olmayan_cikti_dosyasi_atlanir(self):
        g = self.yeni()
        dosya = self._dosya("var.md", "icerik")
        yok = os.path.join(self.proje, "docs", "yok.md")
        self.bitti(g, "orkestra:isci-t2", "a1", "--cikti", dosya)
        s_tek = self.tur(g)["cikti_ozeti_sha"]
        r = self.bitti(g, "orkestra:isci-t2", "a2", "--cikti", yok)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tur(g)["cikti_ozeti_sha"], s_tek)

    # ------------------------------------------------------------ N3 kriter 6
    def test_risk_yazilir(self):
        for deger in ("dusuk", "orta", "yuksek"):
            g = self.yeni("--risk", deger)
            self.assertEqual(self.oku(g)["risk"], deger)

    def test_risk_verilmezse_alan_yok(self):
        self.assertNotIn("risk", self.oku(self.yeni()))

    def test_gecersiz_risk_hata_ve_kart_yazilmaz(self):
        onceki = self.kart_idleri()
        for deger in ("kritik", "", "DUSUK", "yüksek"):
            r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "x", "--kabul", "k", "--sinif", "belge", "--yazma", "docs/**", "--risk", deger)
            self.assertNotEqual(r.returncode, 0, deger)
        self.assertEqual(self.kart_idleri(), onceki)

    def toplu(self, liste):
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            json.dump(liste, f, ensure_ascii=False)
        return self.cli("kart", "toplu", yol)

    def toplu_kart(self, **ek):
        d = {"soru": "Kısa test sorusu?", "baslik": "toplu", "sinif": "belge", "basamak": "T2", "girdi": "g", "kabul_kriterleri": ["k"], "yazma_alani": ["docs/**"]}
        d.update(ek)
        return d

    def test_toplu_risk_yazilir(self):
        r = self.toplu([self.toplu_kart(risk="yuksek"), self.toplu_kart()])
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = self.kart_idleri()
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.oku(ids[0]).get("risk"), "yuksek")
        self.assertNotIn("risk", self.oku(ids[1]))

    def test_toplu_gecersiz_risk_hic_kart_yazmaz(self):
        r = self.toplu([self.toplu_kart(), self.toplu_kart(risk="kritik")])
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.kart_idleri(), [])

    # ------------------------------------------------------------ N4 kriter 7
    def test_butce_yazilir(self):
        g = self.yeni("--butce-usd", "1.5", "--butce-token", "200000")
        b = self.oku(g)["butce"]
        self.assertEqual(b["usd"], 1.5)
        self.assertEqual(b["token"], 200000)
        self.assertEqual(b["kaynak"], "elle")
        self.assertIn("esik_surumu", b)
        self.assertIsNone(b["esik_surumu"])

    def test_butce_verilmezse_alan_yok(self):
        self.assertNotIn("butce", self.oku(self.yeni()))

    def test_butce_yalniz_usd(self):
        b = self.oku(self.yeni("--butce-usd", "2"))["butce"]
        self.assertEqual(b["usd"], 2)
        self.assertIsNone(b["token"])
        self.assertEqual(b["kaynak"], "elle")

    def test_gecersiz_butce_hata_ve_kart_yazilmaz(self):
        onceki = self.kart_idleri()
        for ek in (["--butce-usd", "abc"], ["--butce-token", "x1"], ["--butce-usd", "-1"], ["--butce-token", "-5"]):
            r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "x", "--kabul", "k", "--sinif", "belge", "--yazma", "docs/**", *ek)
            self.assertNotEqual(r.returncode, 0, ek)
        self.assertEqual(self.kart_idleri(), onceki)

    def test_toplu_butce_yazilir(self):
        r = self.toplu([self.toplu_kart(butce={"usd": 0.75, "token": 5000})])
        self.assertEqual(r.returncode, 0, r.stderr)
        g = self.kart_idleri()[0]
        self.assertEqual(self.oku(g)["butce"], {"usd": 0.75, "token": 5000, "kaynak": "elle", "esik_surumu": None})

    def test_butce_sinir_uygulamaz_is_bitti_gecer(self):
        g = self.yeni("--butce-usd", "0.0001", "--butce-token", "1")
        self.assertEqual(self.bitti(g).returncode, 0)

    # ------------------------------------------------------------ geriye uyum
    def test_eski_kart_okunur_ve_is_bitti_calisir(self):
        g = self.yeni()
        k = self.oku(g)
        for alan in ("is_turlari", "risk", "butce"):
            k.pop(alan, None)
        with open(self.yol(g), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False)
        self.assertEqual(self.cli("kart", "goster", g).returncode, 0)
        self.assertEqual(self.cli("kart", "liste", "--json").returncode, 0)
        self.assertEqual(self.bitti(g).returncode, 0)
        self.assertEqual(len(self.oku(g)["is_turlari"]), 1)


if __name__ == "__main__":
    unittest.main()
