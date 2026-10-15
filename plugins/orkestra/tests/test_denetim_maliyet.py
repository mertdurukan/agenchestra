"""calistir.js: denetçi modeli işçiyle aynı basamakta, işçi kapısı (ön kontrol), yeniden denetim kapsamı.

`python -m unittest discover -s plugins/orkestra/tests -p test_denetim_maliyet.py -v`
Akış testleri node gerektirir (test_calistir_akisi.py ile aynı sahte çalışma zamanı); node yoksa skip.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_akisi import BETIK, KOSUM_JS, NODE, NODE_YOK_GEREKCE, kart

ONAY = {"karar": "onay", "bulgular": []}


def ret(*bulgular, neden="kapsam-eksik", talimat="düzelt"):
    return {"karar": "ret", "neden": neden, "bulgular": list(bulgular), "duzeltme_talimati": talimat}


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class DenetimMaliyetTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_denetim_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8", newline="\n") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, gorev, **senaryo):
        """(sonuç, tüm çağrılar). Kapı / ön kontrol ajanı yoktur."""
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=[gorev]), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        cikti = json.loads(p.stdout.decode("utf-8"))
        self.assertEqual([x for x in cikti["cagrilar"] if x["phase"] in ("Kapı", "Ön kontrol")], [])
        return cikti["sonuc"]["sonuclar"][0], cikti["cagrilar"]

    @staticmethod
    def denetimler(c):
        return [x for x in c if x["agentType"] == "orkestra:denetci"]

    @staticmethod
    def adimlar(c):
        def ad(x):
            if x["agentType"] == "orkestra:denetci":
                return "denetim"
            return "is"
        return [ad(x) for x in c]

    # --- denetçi modeli
    def test_t1_haiku_t2_sonnet_t3_t4_opus(self):
        beklenen = {"T1": "haiku", "T2": "sonnet", "T3": "opus", "T4": "opus"}
        for b, model in beklenen.items():
            _, c = self.kos(kart(basamak=b))
            self.assertEqual({x["model"] for x in self.denetimler(c)}, {model}, b)

    def test_t2_iki_retten_sonra_denetim_opus(self):
        s, c = self.kos(kart(), denetim=[ret("a"), ret("b"), ONAY, ONAY])
        modeller = [x["model"] for x in self.denetimler(c)]
        self.assertEqual(modeller[:2], ["sonnet", "sonnet"])  # toplam ret < 2: işçiyle aynı model
        self.assertTrue(len(modeller) > 2 and all(m == "opus" for m in modeller[2:]), modeller)
        self.assertEqual(s["durum"], "onaylandi")

    def test_t1_iki_retten_sonra_opus(self):
        _, c = self.kos(kart(basamak="T1"), denetim=[ret("a"), ret("b")] + [ONAY] * 4)
        modeller = [x["model"] for x in self.denetimler(c)]
        self.assertEqual(modeller[:2], ["haiku", "haiku"])
        self.assertEqual(modeller[2], "opus")

    # --- ön kontrol (işçinin is-bitti kapısı; ayrı ajan yok)
    def test_on_kontrol_ajani_yok_isci_sonra_denetci(self):
        s, c = self.kos(kart(kaynak_dosya="kaynak.md"))
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["is", "denetim"])
        self.assertEqual(c[0]["agentType"], "orkestra:isci-t2")
        self.assertNotIn("on_kontrol.py", c[0]["istem"])

    def test_kapi_gecmezse_denetci_cagrilmaz_ret_uretilir(self):
        ihlal = {"gecti": False, "ihlaller": [{"tur": "satir-sonu", "ayrinti": "a.md CRLF->LF"}]}
        s, c = self.kos(kart(), onkontrol=[ihlal])
        self.assertEqual(self.adimlar(c), ["is", "is", "denetim"])
        duzeltme = [x for x in c if x["phase"] == "İş"][1]["istem"]
        self.assertIn("Ret nedeni: talimat-ihlali", duzeltme)
        self.assertIn("ön kontrol satir-sonu: a.md CRLF->LF", duzeltme)
        self.assertEqual(s["durum"], "onaylandi")

    def test_kapi_reti_normal_ret_sayilir_iki_retle_yukseltir(self):
        ihlal = {"gecti": False, "ihlaller": [{"tur": "kapsam", "ayrinti": "dışarı yazıldı"}]}
        ihlal2 = {"gecti": False, "ihlaller": [{"tur": "bom", "ayrinti": "BOM eklendi"}]}
        s, c = self.kos(kart(), onkontrol=[ihlal, ihlal2])
        isciler = [x["agentType"] for x in c if x["phase"] == "İş"]
        self.assertEqual(isciler, ["orkestra:isci-t2", "orkestra:isci-t2", "orkestra:isci-t3"])
        self.assertEqual(self.denetimler(c)[0]["model"], "opus")  # 2 ret sonrası ilk denetim
        self.assertEqual(s["durum"], "onaylandi")

    def test_isci_sonuc_vermezse_hata(self):
        s, c = self.kos(kart(), onkontrol=[None])  # işçi ajanı null döner → kart 'hata', denetçi çağrılmaz
        self.assertEqual(s["durum"], "hata")
        self.assertEqual(len(self.denetimler(c)), 0)
        self.assertEqual(len([x for x in c if x["phase"] == "İş"]), 1)

    # --- yeniden denetim kapsamı
    def test_ikinci_denetim_isteminde_onceki_bulgular_ve_kapsam_talimati(self):
        s, c = self.kos(kart(), denetim=[ret("kriter 2: KARŞILANMADI — kanıt yok", neden="kanit-yok"), ONAY])
        d = self.denetimler(c)
        self.assertNotIn("Önceki denetimde karşılanmayan kriterler", d[0]["istem"])  # ilk denetim tam
        self.assertIn("Önceki denetimde karşılanmayan kriterler: kriter 2: KARŞILANMADI — kanıt yok", d[1]["istem"])
        self.assertIn("Yalnız bunları ve düzeltmenin yeni bir gerileme getirip getirmediğini", d[1]["istem"])
        self.assertIn("KARŞILANDI denen kriterleri yeniden kanıtlama", d[1]["istem"])
        self.assertEqual(s["durum"], "onaylandi")

    def test_yukseltme_sonrasi_ilk_denetim_tamdir(self):
        s, c = self.kos(kart(), denetim=[ret("a1"), ret("b2"), ONAY, ONAY])
        d = self.denetimler(c)
        self.assertEqual(len(d), 3)  # T2'de 2 denetim, T3'te iki mercek tek çağrıda
        self.assertIn("Önceki denetimde karşılanmayan kriterler: a1", d[1]["istem"])
        for x in d[2:]:  # T3'e yükseltme sonrası ilk denetim: tam
            self.assertNotIn("Önceki denetimde karşılanmayan", x["istem"])
        self.assertEqual(s["durum"], "onaylandi")


if __name__ == "__main__":
    unittest.main()
