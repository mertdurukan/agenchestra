"""I-224: kart açılışında her kabul kriteri ölçülebilir 'kontrol:' alanı taşır, ölçüsüz ifade reddedilir, K-iskeleti üretilir."""
import json
import os
import unittest

import test_cekirdek as TC

ACIK = {"ORKESTRA_KART_KONTROL": "1"}


class KartKontrolAlani(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def kos(self, *args, ortam=None):
        return TC.kos([TC.CLI] + list(args), self.proje, ortam=dict(ACIK, **(ortam or {})))

    def yeni(self, *kabul, ortam=None):
        a = ["kart", "yeni", "--baslik", "X", "--sinif", "belge", "--soru", "Kolon var mı?"]
        for k in kabul:
            a += ["--kabul", k]
        return self.kos(*a, ortam=ortam)

    def plan(self, liste):
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(liste, f)
        return yol

    def kart_json(self, gid):
        with open(os.path.join(self.sd, "gorevler", f"{gid}.json"), encoding="utf-8") as f:
            return json.load(f)

    def gorevler(self):
        d = os.path.join(self.sd, "gorevler")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def ezme_yaz(self, d):
        with open(os.path.join(self.sd, "kart_kontrol.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def gunluk_turleri(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    # ------------------------------------------------------------------ K1
    def test_k1_kontrolsuz_kriter_reddedilir_ve_hangi_kriter_soylenir(self):
        r = self.yeni("Tablo listelenir; kontrol: rg -c tablo rapor.md -> 3", "Rapor yazılır")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("K2", r.stderr)
        self.assertIn("'kontrol:' alanı yok", r.stderr)
        self.assertNotIn("K1 '", r.stderr)
        self.assertIn("örnek:", r.stderr)
        self.assertEqual(self.gorevler(), [])
        self.assertTrue(any(o.get("tur") == "kapi_ret" and o.get("kapi") == "kart_kontrol" for o in self.gunluk_turleri()))

    def test_k1_olculemez_kontrol_reddedilir(self):
        r = self.yeni("Rapor yazılır; kontrol: bakılır")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ölçülebilir değil", r.stderr)
        self.assertEqual(self.gorevler(), [])

    def test_k1_toplu_kontrolsuz_kriter_hicbir_kart_olusmaz(self):
        yol = self.plan([{"soru": "A?", "baslik": "A", "sinif": "belge", "kabul_kriterleri": ["x; kontrol: wc -l a.csv = 10"]},
                         {"soru": "B?", "baslik": "B", "sinif": "belge", "kabul_kriterleri": ["sadece metin"]}])
        r = self.kos("kart", "toplu", yol)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("'kontrol:' alanı yok", r.stderr)
        self.assertEqual(self.gorevler(), [])

    # ------------------------------------------------------------------ K2
    def test_k2_kontrollu_kart_acilir_ve_iskelet_uretilir(self):
        r = self.yeni("Testler geçer; kontrol: pytest tests/test_x.py -> 0 hata",
                      "Satır eklendi; kontrol: scripts/a.py:42",
                      "K5 Sayım tutar; kontrol: `orkestra kart liste`")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kart_json(r.stdout.strip())
        self.assertEqual(len(k["kabul_kriterleri"]), 3)
        isk = k["kanit_iskeleti"]
        self.assertEqual([s.split(":")[0] for s in isk], ["K1", "K2", "K5"])
        self.assertIn("kontrol: scripts/a.py:42", isk[1])
        g = self.kos("kart", "goster", k["id"])
        self.assertIn("kanit_iskeleti", g.stdout)

    def test_k2_toplu_nesne_kriter_metne_cevrilir(self):
        yol = self.plan([{"soru": "A?", "baslik": "A", "sinif": "belge",
                          "kabul_kriterleri": [{"metin": "CSV yazılır", "kontrol": "wc -l out.csv = 11"}]}])
        r = self.kos("kart", "toplu", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kart_json(json.loads(r.stdout)[0]["id"])
        self.assertEqual(k["kabul_kriterleri"], ["CSV yazılır; kontrol: wc -l out.csv = 11"])
        self.assertEqual(len(k["kanit_iskeleti"]), 1)

    # ------------------------------------------------------------------ K3
    def test_k3_olcusuz_ifade_reddedilir(self):
        for metin, kelime in (("Çıktı yeterince iyi; kontrol: wc -l a = 3", "yeterince"),
                              ("Biçim uygun; kontrol: rg -c x a.md = 2", "uygun"),
                              ("Rapor düzgün; kontrol: a.md:10", "düzgün")):
            r = self.yeni(metin)
            self.assertNotEqual(r.returncode, 0, metin)
            self.assertIn("ölçüsüz ifade", r.stderr, metin)
            self.assertIn(kelime, r.stderr, metin)
            self.assertIn("K1", r.stderr, metin)
        self.assertEqual(self.gorevler(), [])

    def test_k3_buyuk_harf_turkce_olcusuz_yakalanir(self):
        r = self.yeni("DÜZGÜN çalışır; kontrol: pytest -q = 0 hata")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ölçüsüz ifade", r.stderr)

    # ------------------------------------------------------------------ mod ve geri uyum
    def test_golge_modu_uyarir_kart_acilir(self):
        self.ezme_yaz({"mod": "golge"})
        r = self.yeni("Rapor yazılır")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gölge", r.stderr)
        self.assertTrue(any(o.get("tur") == "kapi_golge" and o.get("kapi") == "kart_kontrol" for o in self.gunluk_turleri()))
        self.assertEqual(self.kart_json(r.stdout.strip())["kanit_iskeleti"], ["K1: <dosya:satır | komut çıktısı | sayı>"])

    def test_ortam_degiskeni_kapiyi_kapatir(self):
        r = self.yeni("Rapor düzgün yazılır", ortam={"ORKESTRA_KART_KONTROL": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("kanit_iskeleti", self.kart_json(r.stdout.strip()))

    def test_eski_bicim_kart_okunur(self):
        r = self.yeni("eski", ortam={"ORKESTRA_KART_KONTROL": "0"})
        gid = r.stdout.strip()
        self.assertEqual(self.kos("kart", "goster", gid).returncode, 0)
        l = self.kos("kart", "liste")
        self.assertEqual(l.returncode, 0, l.stderr)
        self.assertIn(gid, l.stdout)
        d = self.kos("kart", "durum", gid, "iptal")
        self.assertEqual(d.returncode, 0, d.stderr)

    def test_ayar_dosyasi_ihlal_ile_baslar(self):
        with open(os.path.join(TC.KOK, "ayarlar", "kart_kontrol.json"), encoding="utf-8") as f:
            a = json.load(f)
        self.assertEqual(a["mod"], "ihlal")
        self.assertTrue(a["olcusuz_ifadeler"])
        self.assertTrue(a["olculebilir_kaliplar"])


if __name__ == "__main__":
    unittest.main()
