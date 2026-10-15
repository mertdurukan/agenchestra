"""G-121: kart açılışında zorunlu soru alanı, geniş tarama uyarısı, calistir.js istem satırı."""
import json
import os
import re
import unittest

import test_cekirdek as TC

CALISTIR = os.path.join(TC.KOK, "workflows", "calistir.js")


class KartSoru(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def kos(self, *args):
        return TC.kos([TC.CLI] + list(args), self.proje)

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

    def yeni(self, soru=None, sinif="belge", girdi=None, ek=()):
        a = ["kart", "yeni", "--baslik", "X", "--sinif", sinif, "--kabul", "k"]
        if soru is not None:
            a += ["--soru", soru]
        if girdi:
            a += ["--girdi", girdi]
        return self.kos(*a, *ek)

    def ezme_yaz(self, d):
        os.makedirs(self.sd, exist_ok=True)
        with open(os.path.join(self.sd, "kart_soru.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    # ------------------------------------------------------------------ K1
    def test_k1_soru_yok_reddedilir(self):
        r = self.yeni()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("soru zorunlu", r.stderr)
        self.assertEqual(self.gorevler(), [])

    def test_k1_bos_ve_bosluk_soru_reddedilir(self):
        for s in ("", "   ", "\t"):
            r = self.yeni(s)
            self.assertNotEqual(r.returncode, 0, repr(s))
            self.assertIn("soru zorunlu", r.stderr, repr(s))
        self.assertEqual(self.gorevler(), [])

    def test_k1_cok_satirli_soru_reddedilir(self):
        r = self.yeni("Birinci soru?\nİkinci soru?")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tek cümle", r.stderr)
        self.assertEqual(self.gorevler(), [])

    def test_k1_uzun_soru_reddedilir_sinirda_kabul(self):
        r = self.yeni("a" * 201)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tek cümle", r.stderr)
        ok = self.yeni("b" * 200)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_k1_gecerli_soru_kartta_saklanir(self):
        r = self.yeni("Kolon var mı?")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart_json(r.stdout.strip())["soru"], "Kolon var mı?")

    def test_k1_proje_ezmesi_soru_max_karakter(self):
        self.ezme_yaz({"soru_max_karakter": 20})
        self.assertNotEqual(self.yeni("x" * 21).returncode, 0)
        self.assertEqual(self.yeni("x" * 20).returncode, 0)

    # ------------------------------------------------------------------ K2
    def test_k2_toplu_sorusuz_kart_reddeder_hicbiri_olusmaz(self):
        yol = self.plan([{"soru": "Bir soru?", "baslik": "A", "sinif": "belge", "kabul_kriterleri": ["k"]},
                         {"baslik": "B", "sinif": "belge", "kabul_kriterleri": ["k"]}])
        r = self.kos("kart", "toplu", yol)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("soru zorunlu", r.stderr)
        self.assertEqual(self.gorevler(), [])

    def test_k2_toplu_gecersiz_soru_hicbiri_olusmaz(self):
        yol = self.plan([{"soru": "Bir soru?", "baslik": "A", "sinif": "belge", "kabul_kriterleri": ["k"]},
                         {"soru": "iki\nsatır", "baslik": "B", "sinif": "belge", "kabul_kriterleri": ["k"]}])
        r = self.kos("kart", "toplu", yol)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.gorevler(), [])

    def test_k2_toplu_sorulu_plan_kartlari_soru_ile_olusur(self):
        yol = self.plan([{"soru": "Soru bir?", "baslik": "A", "sinif": "belge", "kabul_kriterleri": ["k"]},
                         {"soru": "Soru iki?", "baslik": "B", "sinif": "belge", "kabul_kriterleri": ["k"]}])
        r = self.kos("kart", "toplu", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]
        self.assertEqual([self.kart_json(g)["soru"] for g in ids], ["Soru bir?", "Soru iki?"])

    # ------------------------------------------------------------------ K3
    def test_k3_soru_alansiz_eski_kart_okunur(self):
        r = self.yeni("Eski mi?")
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        yol = os.path.join(self.sd, "gorevler", f"{gid}.json")
        k = self.kart_json(gid)
        k.pop("soru")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.assertEqual(self.kos("kart", "goster", gid).returncode, 0)
        l = self.kos("kart", "liste")
        self.assertEqual(l.returncode, 0, l.stderr)
        self.assertIn(gid, l.stdout)
        d = self.kos("kart", "durum", gid, "iptal")
        self.assertEqual(d.returncode, 0, d.stderr)
        self.assertEqual(self.kart_json(gid)["durum"], "iptal")

    # ------------------------------------------------------------------ K4
    def test_k4_analiz_sinifi_genis_kalip_uyari_verir_kart_olusur(self):
        r = self.yeni("Kolon var mı?", sinif="arastirma", girdi="Tüm tenantlarda distinct sayım yap")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("uyarı", r.stderr)
        self.assertIn("geniş tarama", r.stderr)
        self.assertIn("--genislet-onay", r.stderr)
        gid = r.stdout.strip()
        self.assertIn(gid, r.stderr)
        self.assertTrue(gid.startswith("G-"))
        self.assertFalse(self.kart_json(gid).get("genislet_onay"))

    def test_k4_soru_metni_de_taranir(self):
        r = self.yeni("Bütün şemalarda kolon var mı?", sinif="analitik")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("geniş tarama", r.stderr)

    def test_k4_genislet_onay_uyariyi_kaldirir_ve_saklanir(self):
        r = self.yeni("Kolon var mı?", sinif="arastirma", girdi="Tüm tenantlarda distinct sayım yap", ek=("--genislet-onay",))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("geniş tarama", r.stderr)
        self.assertIs(self.kart_json(r.stdout.strip())["genislet_onay"], True)

    def test_k4_analiz_disi_sinifta_uyari_yok(self):
        r = self.yeni("Kolon var mı?", sinif="belge", girdi="Tüm tenantlarda distinct sayım yap")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("geniş tarama", r.stderr)

    def test_k4_dar_kapsam_uyari_yok(self):
        r = self.yeni("Kolon var mı?", sinif="arastirma", girdi="Bir tabloda kolon adını kontrol et")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("geniş tarama", r.stderr)

    def test_k4_toplu_uyarir_ve_genislet_onay_json(self):
        yol = self.plan([{"soru": "Var mı?", "baslik": "A", "sinif": "arastirma", "girdi": "count(*) hepsi", "kabul_kriterleri": ["k"]},
                         {"soru": "Var mı?", "baslik": "B", "sinif": "arastirma", "girdi": "count(*) hepsi",
                          "kabul_kriterleri": ["k"], "genislet_onay": True}])
        r = self.kos("kart", "toplu", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        a, b = [x["id"] for x in json.loads(r.stdout)]
        self.assertIn(f"uyarı {a}", r.stderr)
        self.assertNotIn(f"uyarı {b}", r.stderr)
        self.assertIs(self.kart_json(b)["genislet_onay"], True)

    def test_k4_proje_ezmesi_kalip_listesini_degistirir(self):
        self.ezme_yaz({"genis_tarama_kaliplari": ["kahve"]})
        r1 = self.yeni("Var mı?", sinif="arastirma", girdi="Tüm tenantlarda distinct sayım yap")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertNotIn("geniş tarama", r1.stderr)
        r2 = self.yeni("Var mı?", sinif="arastirma", girdi="kahve tablosu")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("geniş tarama", r2.stderr)

    def test_k4_proje_ezmesi_analiz_siniflari(self):
        self.ezme_yaz({"analiz_siniflari": ["belge"]})
        r = self.yeni("Var mı?", sinif="belge", girdi="Tüm tenantlarda distinct sayım")
        self.assertIn("geniş tarama", r.stderr)
        r2 = self.yeni("Var mı?", sinif="arastirma", girdi="Tüm tenantlarda distinct sayım")
        self.assertNotIn("geniş tarama", r2.stderr)

    def test_k4_bozuk_ezme_dosyasi_varsayilana_duser(self):
        os.makedirs(self.sd, exist_ok=True)
        with open(os.path.join(self.sd, "kart_soru.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        r = self.yeni("Var mı?", sinif="arastirma", girdi="Tüm tenantlarda distinct sayım")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("geniş tarama", r.stderr)

    # ------------------------------------------------------------------ K5 / kullanım / ayar
    def test_k5_calistir_js_isci_ve_test_yazari_istemlerinde_soru_satiri(self):
        with open(CALISTIR, encoding="utf-8") as f:
            js = f.read()
        for fn in ("isciIstemi", "testYazariIstemi"):
            m = re.search(r"function %s\(.*?\n}\n" % fn, js, re.S)
            self.assertIsNotNone(m, fn)
            govde = m.group(0)
            self.assertIn("Soru: ${k.soru}", govde, fn)
            self.assertLess(govde.index("Görev:"), govde.index("Soru:"), fn)

    def test_kullanim_metni_soru_ve_genislet_onay(self):
        with open(TC.CLI, encoding="utf-8") as f:
            ust = f.read(6000)
        self.assertIn("--soru", ust)
        self.assertIn("--genislet-onay", ust)

    def test_ayar_dosyasi_varsayilanlari(self):
        yol = os.path.join(TC.KOK, "ayarlar", "kart_soru.json")
        self.assertTrue(os.path.isfile(yol))
        with open(yol, encoding="utf-8") as f:
            a = json.load(f)
        self.assertEqual(a["soru_max_karakter"], 200)
        self.assertEqual(a["analiz_siniflari"], ["analiz", "analitik", "arastirma"])
        for k in a["genis_tarama_kaliplari"]:
            re.compile(k)
        self.assertTrue(a["genis_tarama_kaliplari"])


if __name__ == "__main__":
    unittest.main()
