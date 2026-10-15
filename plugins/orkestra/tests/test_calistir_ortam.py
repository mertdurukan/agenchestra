"""G-123: 'ortam' ret nedeni ve aynı kapı hatası (calistir.js, ret_nedeni.py, agents/denetci.md).

`py -3.13 -m pytest plugins/orkestra/tests/test_calistir_ortam.py -q`

Sahte çalışma zamanı test_calistir_akisi.KOSUM_JS'tir (node yoksa FAIL, skip yok). Kapı girdileri
{gecti, cikis_kodu, ozet}; denetim girdileri ham denetçi kararıdır.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_calistir_akisi import BETIK, KOK, KOSUM_JS, NODE, NODE_YOK_GEREKCE, kart, kod_karti

sys.path.insert(0, os.path.join(KOK, "scripts"))
import ret_nedeni as RN  # noqa: E402

DENETCI_MD = os.path.join(KOK, "agents", "denetci.md")
ONAY = {"karar": "onay", "bulgular": []}


def kapi(ozet, cikis=4):
    return {"gecti": False, "cikis_kodu": cikis, "ozet": ozet}


def ortam_reti():
    return {"karar": "ret", "neden": "ortam", "bulgular": ["yük altında zamanlama"],
            "duzeltme_talimati": "ortamı kontrol et"}


def js_kaynagi():
    with open(BETIK, encoding="utf-8") as f:
        return f.read()


class OrtamTabani(unittest.TestCase):
    def setUp(self):
        if not NODE:  # skip yok
            self.fail(NODE_YOK_GEREKCE)
        self.tmp = tempfile.mkdtemp(prefix="ork_ortam_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos_hepsi(self, gorevler, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=gorevler), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        return json.loads(p.stdout.decode("utf-8"))

    def kos(self, k, **senaryo):
        c = self.kos_hepsi([k], **senaryo)
        return c["sonuc"]["sonuclar"][0], c["cagrilar"], c["loglar"]

    @staticmethod
    def isciler(cagrilar):
        return [x["agentType"] for x in cagrilar if x["phase"] == "İş"]

    @staticmethod
    def denetimler(cagrilar):
        return [x for x in cagrilar if x["phase"] == "Denetim"]


class K1Tanimlar(OrtamTabani):
    def test_ret_nedeni_py(self):
        self.assertIn("ortam", RN.NEDENLER)
        self.assertEqual(RN.KOK["ortam"], "ortam")
        self.assertEqual(RN.kok("ortam"), "ortam")

    def test_calistir_js_neden_listesi_ve_aciklama(self):
        js = js_kaynagi()
        m = re.search(r"const RET_NEDENLERI = \[([^\]]*)\]", js)
        self.assertIn("'ortam'", m.group(1))
        self.assertRegex(js, r"'ortam': '[^']*ortamın")  # RET_NEDEN_ACIKLAMA

    def test_js_ve_py_neden_kodlari_ayni(self):
        m = re.search(r"const RET_NEDENLERI = \[([^\]]*)\]", js_kaynagi())
        self.assertEqual(set(re.findall(r"'([^']+)'", m.group(1))), set(RN.NEDENLER))

    def test_denetci_istemi_ortam_secenegi(self):
        _, c, _ = self.kos(kart(), denetim=[ONAY])
        istem = self.denetimler(c)[0]["istem"]
        self.assertIn("yetenek-yetersiz, ortam", istem)
        self.assertIn("yük altında zamanlama", istem)

    def test_denetci_md_ortam_satiri(self):
        with open(DENETCI_MD, encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        self.assertTrue(any(s.startswith("- `ortam`:") for s in satirlar))


class K2DenetciOrtamReti(OrtamTabani):
    def test_ortam_reti_karti_ortam_durumuna_alir(self):
        s, c, loglar = self.kos(kart(), denetim=[ortam_reti(), ONAY])
        self.assertEqual(s["durum"], "ortam")
        self.assertEqual(s["neden"], "ortam")
        self.assertEqual(s["basamak"], "T2")
        self.assertEqual(s["son_ret"]["neden"], "ortam")
        self.assertIn("gecmis", s)
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"])  # ikinci işçi çağrısı yok
        self.assertEqual(len(self.denetimler(c)), 1)
        self.assertTrue(any("ana ajan kartı beklemede yapmalı" in m for m in loglar))

    def test_ortam_yukseltmez_t3te_de(self):
        s, c, _ = self.kos(kart(basamak="T3"), denetim=[ortam_reti()])
        self.assertEqual((s["durum"], s["basamak"]), ("ortam", "T3"))
        self.assertEqual(self.isciler(c), ["orkestra:isci-t3"])

    def test_bitti_satirinda_ortam_sayisi(self):
        _, _, loglar = self.kos(kart(), denetim=[ortam_reti()])
        bitti = [m for m in loglar if m.startswith("Bitti:")][0]
        self.assertIn("1 ortam", bitti)

    def test_kod_kartinda_da_ortam(self):
        s, c, _ = self.kos(kod_karti(), denetim=[ortam_reti()])
        self.assertEqual((s["durum"], s["neden"], s["basamak"]), ("ortam", "ortam", "T2"))
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"])

    def test_kriter_belirsiz_davranisi_degismedi(self):
        s, _, _ = self.kos(kart(), denetim=[{"karar": "ret", "neden": "kriter-belirsiz", "bulgular": ["b"]}])
        self.assertEqual((s["durum"], s["neden"]), ("kart-duzeltilmeli", "kriter-belirsiz"))


class K3AyniKapiHatasi(OrtamTabani):
    def test_rakam_sure_yol_hex_farki_ayni_sayilir(self):
        a = kapi("FAILED test_x.py::t_zaman - 3 failed in 12.34s C:\\Users\\a\\tmp\\run1\\x.py id=deadbeef01 /tmp/ork_9/y")
        b = kapi("FAILED test_x.py::t_zaman - 5 failed in 0.9s C:\\Users\\b\\tmp\\run2\\x.py id=cafebabe02 /var/q/z")
        s, c, loglar = self.kos(kod_karti(), yesil=[a, b, a, b, a, b])
        self.assertEqual((s["durum"], s["neden"]), ("ortam", "ayni-kapi-hatasi"))
        self.assertEqual(s["basamak"], "T2")
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"] * 2)  # yükseltme yok
        self.assertEqual(self.denetimler(c), [])
        self.assertTrue(any("ana ajan kartı beklemede yapmalı" in m for m in loglar))
        self.assertIn("1 ortam", [m for m in loglar if m.startswith("Bitti:")][0])

    def test_kod_disi_kartta_ayni_on_kontrol_hatasi(self):
        h = kapi("ön kontrol ihlali: yazma alanı dışı")
        s, c, _ = self.kos(kart(), onkontrol=[h, h, h])
        self.assertEqual((s["durum"], s["neden"]), ("ortam", "ayni-kapi-hatasi"))
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"] * 2)

    def test_arada_gecen_kapi_sayaci_sifirlar(self):
        h = kapi("assertion hatası x")
        ret = {"karar": "ret", "neden": "kapsam-eksik", "bulgular": ["eksik"], "duzeltme_talimati": "tamamla"}
        s, c, _ = self.kos(kod_karti(), yesil=[h, True, h, True], denetim=[ret, ONAY])
        self.assertEqual(s["durum"], "onaylandi")
        # kapı hatası, ret, kapı hatası arka arkaya değil: ortam yok; iki ret mevcut kuralla T3'e yükseltir
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2)

    def test_ortam_durumu_bagimli_karti_atlatir(self):
        sonuc = self.kos_hepsi([kod_karti(), kart(id="G-901", bagimliliklar=["G-900"])],
                               yesil=[kapi("aynı hata 1"), kapi("aynı hata 2")])
        d = {x["id"]: x["durum"] for x in sonuc["sonuc"]["sonuclar"]}
        self.assertEqual(d, {"G-900": "ortam", "G-901": "atlandi"})


class K4FarkliKapiHatalari(OrtamTabani):
    def test_farkli_ozetler_iki_ret_yukseltmesi_korunur(self):
        hatalar = [kapi(m) for m in ("import hatası modül a", "assertion hatası b", "sözdizimi hatası c",
                                       "tip hatası d", "anahtar hatası e", "değer hatası f")]
        s, c, _ = self.kos(kod_karti(), yesil=hatalar)
        self.assertEqual(self.isciler(c)[:6], ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertNotEqual(s.get("neden"), "ayni-kapi-hatasi")
        self.assertEqual(self.denetimler(c), [])

    def test_farkli_ozet_duzeltme_turu_ve_onay(self):
        s, c, _ = self.kos(kod_karti(), yesil=[kapi("import hatası modül a"), True])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2"] * 2)
        self.assertIn("yesil-gecmedi", [g.get("karar") for g in s["gecmis"]])

    def test_dikkat_grubu_iki_ret_yukseltmesi_korunur(self):
        r1 = {"karar": "ret", "neden": "kapsam-eksik", "bulgular": ["birinci"], "duzeltme_talimati": "bir"}
        r2 = {"karar": "ret", "neden": "bicim", "bulgular": ["ikinci"], "duzeltme_talimati": "iki"}
        s, c, _ = self.kos(kart(), denetim=[r1, r2, ONAY])
        self.assertEqual(self.isciler(c), ["orkestra:isci-t2", "orkestra:isci-t2", "orkestra:isci-t3"])
        self.assertEqual(s["durum"], "onaylandi")


if __name__ == "__main__":
    unittest.main()
