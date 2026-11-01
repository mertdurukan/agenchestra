"""Kart-iş bağı zorunlu (G-035): bağsız kart oluşmaz, bağ yüzünden ret olmaz; sahipsiz kart geri doldurma (`is onar --kartlar`)."""
import datetime
import json
import os
import re
import unittest

import test_cekirdek as TC

ESLEME = {"projeler": ["ACMECO", "Claude_Orkestrasyon"], "surec_deseni": r"^\d{2}_", "gorev_deseni": r"^\d{3}-",
          "haric": ["98_calisma"], "dis_kokler": {}}


class KartIsBagi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    # ------------------------------------------------------------ yardımcılar
    def baglam_yaz(self, **ek):
        e = dict(ESLEME)
        e.update(ek)
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump(e, f)

    def oku(self, yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)

    def kart_json(self, g):
        return self.oku(os.path.join(self.sd, "gorevler", f"{g}.json"))

    def oturum_yolu(self):
        return os.path.join(self.sd, "oturumlar", TC.OTURUM + ".json")

    def oturum_isi(self):
        try:
            return self.oku(self.oturum_yolu()).get("is")
        except FileNotFoundError:
            return None

    def oturumu_birak(self):
        if os.path.exists(self.oturum_yolu()):
            os.remove(self.oturum_yolu())

    def merkez(self):
        return self.oku(os.path.join(self.sd, "isler.json"))

    def yeni(self, baslik="Deneme kartı", yazma=None, *ek):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", baslik, "--sinif", "belge", "--kabul", "k"]
        if yazma:
            a += ["--yazma", yazma]
        return self.cli(*(a + list(ek)))

    def kart_ac(self, baslik="Deneme kartı", yazma=None, *ek):
        r = self.yeni(baslik, yazma, *ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), r

    def klasor_ac(self, goreli, baslik="Hazır iş"):
        yol = os.path.join(self.proje, *goreli.split("/"))
        r = self.cli("is", "ac", baslik, "--klasor", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), yol

    def is_klasoru(self, i):
        return os.path.abspath(self.merkez()["isler"][i]["klasor"])

    def alt_yol_mu(self, yol, kok):
        yol, kok = os.path.normcase(os.path.abspath(yol)), os.path.normcase(os.path.abspath(kok))
        return yol == kok or yol.startswith(kok + os.sep)

    def nnn_klasorleri(self, kok):
        return sorted(x for x in os.listdir(kok) if re.match(r"^\d{3}-", x)) if os.path.isdir(kok) else []

    def sorgu_satirlari(self, stderr, g):
        return [s for s in stderr.splitlines() if f"{g} →" in s]

    def sahipsiz_yap(self, g):
        """Kartı eski sürümdeki gibi 'is' alanı olmayan hâle getirir (is.json kartlar[]'ından da çıkarır)."""
        yol = os.path.join(self.sd, "gorevler", f"{g}.json")
        k = self.oku(yol)
        i = k.pop("is", None)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)
        if i:
            ij = os.path.join(self.is_klasoru(i), "is.json")
            v = self.oku(ij)
            v["kartlar"] = [x for x in v["kartlar"] if x != g]
            with open(ij, "w", encoding="utf-8") as f:
                json.dump(v, f, ensure_ascii=False)

    def anlik(self):
        sonuc = {}
        for kok, dizinler, dosyalar in os.walk(self.proje):
            if "_transkript" in kok:
                continue
            for d in dizinler:
                sonuc[os.path.relpath(os.path.join(kok, d), self.proje)] = None
            for d in dosyalar:
                if d in ("ortak_defter.md", "maliyet.jsonl"):
                    continue
                y = os.path.join(kok, d)
                with open(y, "rb") as f:
                    sonuc[os.path.relpath(y, self.proje)] = f.read()
        return sonuc

    # ------------------------------------------------------------ K1 çözüm sırası
    def test_k1a_acik_is_secenegi_yazma_alanini_ve_oturumu_yener(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.klasor_ac("ACMECO/01_a/002-iki", "iki")  # oturum I-002'de
        g, _ = self.kart_ac("x", "ACMECO/01_a/002-iki/**", "--is", i1)
        self.assertEqual(self.kart_json(g)["is"], i1)
        self.assertEqual(self.oku(os.path.join(self.is_klasoru(i1), "is.json"))["kartlar"], [g])

    def test_k1a_toplu_json_is_alani(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.klasor_ac("ACMECO/01_a/002-iki", "iki")
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"], "is": i1}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart_json(json.loads(r.stdout)[0]["id"])["is"], i1)

    def test_k1b_oturum_isi_yazma_alanindan_once_gelir(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.klasor_ac("ACMECO/01_a/002-iki", "iki")
        self.cli("is", "devam", i1)
        g, _ = self.kart_ac("x", "ACMECO/01_a/002-iki/**")
        self.assertEqual(self.kart_json(g)["is"], i1)

    def test_k1c_yazma_alani_klasorunde_is_json_varsa_o_is_kullanilir(self):
        self.baglam_yaz()
        i1, yol = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        g, _ = self.kart_ac("x", "ACMECO/01_a/001-bir/alt/dosya.py")
        self.assertEqual(self.kart_json(g)["is"], i1)
        self.assertEqual(self.merkez()["sayac"], 1)  # yeni iş açılmadı
        self.assertEqual(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO", "01_a")), ["001-bir"])
        self.assertEqual(self.oku(os.path.join(yol, "is.json"))["kartlar"], [g])

    def test_k1c_klasorde_is_json_yoksa_orada_is_acilir(self):
        self.baglam_yaz()
        klasor = os.path.join(self.proje, "ACMECO", "05_s", "003-var")
        os.makedirs(klasor)
        g, _ = self.kart_ac("x", "ACMECO/05_s/003-var/**")
        i = self.kart_json(g)["is"]
        self.assertTrue(i)
        self.assertEqual(self.is_klasoru(i), os.path.abspath(klasor))
        self.assertTrue(os.path.exists(os.path.join(klasor, "is.json")))
        self.assertEqual(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO", "05_s")), ["003-var"])

    def test_k1c_mutlak_yol_proje_kokune_gore_cozulur(self):
        self.baglam_yaz()
        klasor = os.path.join(self.proje, "ACMECO", "05_s", "003-var")
        os.makedirs(klasor)
        g, _ = self.kart_ac("x", os.path.join(klasor, "a.py"))
        self.assertEqual(self.is_klasoru(self.kart_json(g)["is"]), os.path.abspath(klasor))

    def test_k1c_yazma_alani_ilk_girdi_kullanilir(self):
        self.baglam_yaz()
        klasor = os.path.join(self.proje, "ACMECO", "05_s", "003-ilk")
        os.makedirs(klasor)
        g, _ = self.kart_ac("x", "ACMECO/05_s/003-ilk/**", "--yazma", "ACMECO/05_s/004-ikinci/**")
        self.assertEqual(self.is_klasoru(self.kart_json(g)["is"]), os.path.abspath(klasor))
        self.assertFalse(os.path.exists(os.path.join(self.proje, "ACMECO", "05_s", "004-ikinci")))

    def test_k1c_dis_kok_eslemesi_proje_kokunde_klasor_acar(self):
        dis = os.path.join(self.proje, "_dis_depo").replace("\\", "/")
        os.makedirs(dis)
        self.baglam_yaz(dis_kokler={dis: "Claude_Orkestrasyon"})
        os.makedirs(os.path.join(self.proje, "Claude_Orkestrasyon", "007-eski"))
        g, _ = self.kart_ac("Dış depo işi", dis + "/plugins/x.py")
        kl = self.is_klasoru(self.kart_json(g)["is"])
        self.assertTrue(self.alt_yol_mu(kl, os.path.join(self.proje, "Claude_Orkestrasyon")), kl)
        self.assertEqual(os.path.basename(kl)[:3], "008")

    def test_k1d_gorev_klasorune_cozulmezse_surec_kokunda_nnn_acilir(self):
        self.baglam_yaz()
        sk = os.path.join(self.proje, "ACMECO", "05_sohbet")
        os.makedirs(os.path.join(sk, "001-eski"))
        os.makedirs(os.path.join(sk, "004-baska"))
        os.makedirs(os.path.join(sk, "acik_klasor"))  # numarasız: sayılmaz
        g, _ = self.kart_ac("Çözüm Şeması İşi", "ACMECO/05_sohbet/dosya.md")
        kl = self.is_klasoru(self.kart_json(g)["is"])
        self.assertEqual(os.path.dirname(kl), os.path.abspath(sk))
        ad = os.path.basename(kl)
        self.assertRegex(ad, r"^005-\d{8}-[a-z0-9-]+$")
        self.assertEqual(ad[4:12], datetime.date.today().strftime("%Y%m%d"))
        self.assertIn("cozum", ad)
        self.assertTrue(ad.isascii())

    def test_k1d_proje_kokunda_nnn_ve_ilk_numara_001(self):
        self.baglam_yaz()
        g, _ = self.kart_ac("Kök işi", "Claude_Orkestrasyon/not.md")
        kl = self.is_klasoru(self.kart_json(g)["is"])
        self.assertEqual(os.path.dirname(kl), os.path.abspath(os.path.join(self.proje, "Claude_Orkestrasyon")))
        self.assertRegex(os.path.basename(kl), r"^001-\d{8}-kok-isi$")

    def test_k1d_hicbir_sey_cozulmezse_baglamdaki_ilk_projede_acilir(self):
        self.baglam_yaz()
        g, _ = self.kart_ac("Baska alan", "docs/**")
        kl = self.is_klasoru(self.kart_json(g)["is"])
        self.assertTrue(self.alt_yol_mu(kl, os.path.join(self.proje, "ACMECO")), kl)
        self.assertRegex(os.path.basename(kl), r"^\d{3}-\d{8}-baska-alan$")

    def test_k1d_yazma_alani_hic_yoksa_da_baglanir(self):
        self.baglam_yaz()
        g, _ = self.kart_ac("Yazmasız")
        kl = self.is_klasoru(self.kart_json(g)["is"])
        self.assertTrue(self.alt_yol_mu(kl, os.path.join(self.proje, "ACMECO")), kl)
        self.assertTrue(os.path.exists(os.path.join(kl, "is.json")))

    def test_k1d_nnn_uc_hane_ve_en_buyuk_arti_bir(self):
        self.baglam_yaz()
        sk = os.path.join(self.proje, "ACMECO", "02_x")
        for n in ("009-a", "012-b", "003-c"):
            os.makedirs(os.path.join(sk, n))
        g, _ = self.kart_ac("Yeni", "ACMECO/02_x/dosya.md")
        self.assertTrue(os.path.basename(self.is_klasoru(self.kart_json(g)["is"])).startswith("013-"))

    # ------------------------------------------------------------ K2 asla bağsız / ret yok
    def test_k2_baglam_json_olmasa_da_kart_bagli_ve_basarili(self):
        g, _ = self.kart_ac("Eşlemesiz")
        i = self.kart_json(g)["is"]
        self.assertRegex(i, r"^I-\d{3}$")
        self.assertTrue(os.path.exists(os.path.join(self.is_klasoru(i), "is.json")))

    def test_k2_bozuk_baglam_json_ret_vermez(self):
        with open(os.path.join(self.sd, "baglam.json"), "w") as f:
            f.write("{bozuk")
        g, _ = self.kart_ac("Bozuk eşleme", "ACMECO/x/a.md")
        self.assertTrue(self.kart_json(g)["is"])

    def test_k2_toplu_her_kartta_is_dolu(self):
        self.baglam_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"]},
                       {"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/01_a/002-x/**"]}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        for x in json.loads(r.stdout):
            self.assertTrue(self.kart_json(x["id"]).get("is"), x)

    def test_k2_kod_karti_da_baglanir(self):
        self.baglam_yaz()
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "Kod", "--kabul", "k", "--sinif", "kod", "--test-komutu", "python -m unittest",
                     "--test-alani", "tests/**", "--yazma", "ACMECO/01_a/002-k/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.kart_json(r.stdout.strip()).get("is"))

    # ------------------------------------------------------------ K3 kapalı iş
    def test_k3_kapali_oturum_isi_yazma_alani_isine_gecer(self):
        self.baglam_yaz()
        i0, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        i1, _ = self.klasor_ac("ACMECO/01_a/002-iki", "iki")  # oturum I-002
        self.cli("is", "kapat", i1)
        g, _ = self.kart_ac("x", "ACMECO/01_a/001-bir/**")
        self.assertEqual(self.kart_json(g)["is"], i0)

    def test_k3_kapali_oturum_isi_yazma_alani_yoksa_yeni_is_acilir(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.cli("is", "kapat", i1)
        g, _ = self.kart_ac("Kapalı sonrası", "ACMECO/01_a/dosya.md")
        i = self.kart_json(g)["is"]
        self.assertNotEqual(i, i1)
        self.assertEqual(self.merkez()["isler"][i]["durum"], "acik")
        self.assertEqual(self.merkez()["isler"][i1]["durum"], "kapandi")

    def test_k3_kapali_acik_is_secenegi_hata_vermez(self):
        self.baglam_yaz()
        i1, kl = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.cli("is", "kapat", i1)
        r = self.yeni("x", "ACMECO/01_a/001-bir/**", "--is", i1)
        self.assertEqual(r.returncode, 0, r.stderr)
        i = self.kart_json(r.stdout.strip())["is"]
        self.assertNotEqual(i, i1)
        self.assertEqual(self.merkez()["isler"][i]["durum"], "acik")
        self.assertEqual(self.oku(os.path.join(kl, "is.json"))["kartlar"], [])

    def test_k3_kapali_is_toplu_json_is_alani_hata_vermez(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.cli("is", "kapat", i1)
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"], "is": i1}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        i = self.kart_json(json.loads(r.stdout)[0]["id"])["is"]
        self.assertEqual(self.merkez()["isler"][i]["durum"], "acik")

    # ------------------------------------------------------------ K4 oturum ve merkez dizin
    def test_k4_acilan_is_oturuma_baglanir_ve_kayitlar_guncellenir(self):
        self.baglam_yaz()
        self.assertIsNone(self.oturum_isi())
        g, _ = self.kart_ac("x", "ACMECO/01_a/003-yeni/**")
        i = self.kart_json(g)["is"]
        self.assertEqual(self.oturum_isi(), i)
        ij = self.oku(os.path.join(self.is_klasoru(i), "is.json"))
        self.assertEqual(ij["kartlar"], [g])
        self.assertEqual(ij["oturumlar"][0]["oturum"], TC.OTURUM)
        self.assertIn(i, self.merkez()["isler"])
        self.assertIn(i, self.cli("is", "aktif").stdout)

    def test_k4_mevcut_isi_bulunca_da_oturuma_baglanir(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        self.kart_ac("x", "ACMECO/01_a/001-bir/**")
        self.assertEqual(self.oturum_isi(), i1)

    def test_k4_oturum_zaten_bagliysa_acik_is_oturumu_degistirmez(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        i2, _ = self.klasor_ac("ACMECO/01_a/002-iki", "iki")
        self.kart_ac("x", None, "--is", i1)
        self.assertEqual(self.oturum_isi(), i2)

    def test_k4_ikinci_kart_ayni_isi_kullanir_yeni_klasor_acmaz(self):
        self.baglam_yaz()
        g1, _ = self.kart_ac("a", "ACMECO/01_a/dosya.md")
        g2, _ = self.kart_ac("b", "ACMECO/01_a/dosya.md")
        i = self.kart_json(g1)["is"]
        self.assertEqual(self.kart_json(g2)["is"], i)
        self.assertEqual(self.oku(os.path.join(self.is_klasoru(i), "is.json"))["kartlar"], [g1, g2])
        self.assertEqual(len(self.merkez()["isler"]), 1)

    # ------------------------------------------------------------ K5 stderr izi
    def test_k5_stderr_kart_basina_tek_satir_stdout_degismez(self):
        self.baglam_yaz()
        g, r = self.kart_ac("İz kartı", "ACMECO/01_a/003-yeni/**")
        i = self.kart_json(g)["is"]
        self.assertEqual(r.stdout.strip(), g)
        s = self.sorgu_satirlari(r.stderr, g)
        self.assertEqual(len(s), 1, r.stderr)
        self.assertTrue(s[0].startswith("orkestra:"), s[0])
        self.assertIn(f"{g} → {i}", s[0])
        self.assertIn("yazma_alani", s[0])
        self.assertIn("yeni iş", s[0])

    def test_k5_mevcut_is_icin_yeni_is_denmez(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        g, r = self.kart_ac("x", "ACMECO/01_a/001-bir/**")
        s = self.sorgu_satirlari(r.stderr, g)
        self.assertEqual(len(s), 1, r.stderr)
        self.assertIn(f"{g} → {i1}", s[0])
        self.assertNotIn("yeni iş", s[0])

    def test_k5_oturum_ve_acik_is_yollari_da_tek_satir_yazar(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        g, r = self.kart_ac("x")
        self.assertEqual(len(self.sorgu_satirlari(r.stderr, g)), 1, r.stderr)
        self.assertIn(f"{g} → {i1}", r.stderr)
        g2, r2 = self.kart_ac("y", None, "--is", i1)
        self.assertEqual(len(self.sorgu_satirlari(r2.stderr, g2)), 1, r2.stderr)
        self.assertIn(f"{g2} → {i1}", r2.stderr)

    def test_k5_toplu_kart_basina_bir_satir_stdout_json(self):
        self.baglam_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": f"k{n}", "sinif": "belge", "kabul_kriterleri": ["k"]} for n in range(3)], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]  # stdout hâlâ salt JSON
        for g in ids:
            self.assertEqual(len(self.sorgu_satirlari(r.stderr, g)), 1, r.stderr)

    # ------------------------------------------------------------ K6 toplu tek iş
    def test_k6_toplu_ayni_klasore_cozulen_kartlar_tek_is(self):
        self.baglam_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/05_s/a.md"]},
                       {"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/05_s/b.md"]},
                       {"soru": "Kısa test sorusu?", "baslik": "c", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/05_s/c.md"]}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]
        isler = {self.kart_json(g)["is"] for g in ids}
        self.assertEqual(len(isler), 1)
        self.assertEqual(len(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO", "05_s"))), 1)
        self.assertEqual(len(self.merkez()["isler"]), 1)
        self.assertEqual(self.oku(os.path.join(self.is_klasoru(isler.pop()), "is.json"))["kartlar"], ids)

    def test_k6_toplu_tekrar_kosusunda_ayni_is(self):
        self.baglam_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"]}, {"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge", "kabul_kriterleri": ["k"]}], f)
        self.assertEqual(self.cli("kart", "toplu", plan).returncode, 0)
        self.assertEqual(self.cli("kart", "toplu", plan).returncode, 0)
        self.assertEqual(len(self.merkez()["isler"]), 1)

    def test_k6_toplu_hatali_plan_is_veya_klasor_acmaz(self):
        self.baglam_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"]}, {"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge"}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertNotEqual(r.returncode, 0)  # kabul kriteri eksik: gerçek doğrulama hatası hâlâ ret
        self.assertFalse(os.path.exists(os.path.join(self.sd, "isler.json")))
        self.assertEqual(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO")), [])

    # ------------------------------------------------------------ K7 geri doldurma
    def sahipsiz_hazirla(self):
        """Üç sahipsiz kart: biri mevcut klasörde is.json'lu, ikisi aynı yeni süreç kökünde."""
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        ga, _ = self.kart_ac("a", "ACMECO/01_a/001-bir/**")
        gb, _ = self.kart_ac("b", "ACMECO/05_s/x.md")
        gc, _ = self.kart_ac("c", "ACMECO/05_s/y.md")
        for g in (ga, gb, gc):
            self.sahipsiz_yap(g)
        self.oturumu_birak()
        return i1, (ga, gb, gc)

    def test_k7_kuru_kosu_listeler_ve_hicbir_sey_degistirmez(self):
        i1, (ga, gb, gc) = self.sahipsiz_hazirla()
        once = self.anlik()
        r = self.cli("is", "onar", "--kartlar")
        self.assertEqual(r.returncode, 0, r.stderr)
        for g in (ga, gb, gc):
            self.assertIn(g, r.stdout)
        satir_a = [s for s in r.stdout.splitlines() if ga in s]
        self.assertIn(i1, satir_a[0])  # mevcut klasördeki iş önerilir
        self.assertEqual(self.anlik(), once, "kuru koşu dosya değiştirmemeli")
        self.assertIsNone(self.oturum_isi(), "kuru koşu oturumu bağlamamalı")
        for g in (ga, gb, gc):
            self.assertNotIn("is", self.kart_json(g))

    def test_k7_uygula_kartlara_is_yazar_ve_is_jsona_ekler(self):
        i1, (ga, gb, gc) = self.sahipsiz_hazirla()
        r = self.cli("is", "onar", "--kartlar", "--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart_json(ga)["is"], i1)
        ib, ic = self.kart_json(gb)["is"], self.kart_json(gc)["is"]
        self.assertTrue(ib)
        self.assertEqual(ib, ic, "aynı klasöre çözülen sahipsiz kartlar tek işe bağlanır")
        self.assertNotEqual(ib, i1)
        kl = self.is_klasoru(ib)
        self.assertEqual(os.path.dirname(kl), os.path.abspath(os.path.join(self.proje, "ACMECO", "05_s")))
        self.assertEqual(self.oku(os.path.join(kl, "is.json"))["kartlar"], [gb, gc])
        self.assertIn(ga, self.oku(os.path.join(self.is_klasoru(i1), "is.json"))["kartlar"])
        self.assertIn(ib, self.merkez()["isler"])

    def test_k7_ikinci_kosu_sahipsiz_kart_yok(self):
        self.sahipsiz_hazirla()
        self.assertEqual(self.cli("is", "onar", "--kartlar", "--uygula").returncode, 0)
        once = self.anlik()
        r = self.cli("is", "onar", "--kartlar", "--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sahipsiz kart yok", r.stdout.lower())
        self.assertEqual(self.anlik(), once)
        k = self.cli("is", "onar", "--kartlar")
        self.assertIn("sahipsiz kart yok", k.stdout.lower())

    def test_k7_sahipsiz_kart_yoksa_kuru_kosu_da_yok_der(self):
        self.baglam_yaz()
        self.kart_ac("a", "ACMECO/05_s/x.md")
        r = self.cli("is", "onar", "--kartlar")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sahipsiz kart yok", r.stdout.lower())

    def test_k7_bagli_kartlara_dokunmaz(self):
        self.baglam_yaz()
        g, _ = self.kart_ac("a", "ACMECO/05_s/x.md")
        i = self.kart_json(g)["is"]
        self.assertEqual(self.cli("is", "onar", "--kartlar", "--uygula").returncode, 0)
        self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(len(self.merkez()["isler"]), 1)

    def test_k7_kartlar_bayragi_olmadan_onar_eski_davranis(self):
        self.baglam_yaz()
        self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        r = self.cli("is", "onar")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("sahipsiz", r.stdout.lower())

    # ------------------------------------------------------------ ret düzeltmesi: yetim is.json, bozuk isler.json
    def kimlik_no(self, i):
        return int(i.split("-")[1])

    def test_k1c_yetim_is_json_merkeze_kaydedilir_yeni_klasor_acilmaz(self):
        self.baglam_yaz()
        i1, yol = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        os.remove(os.path.join(self.sd, "isler.json"))  # is.json duruyor, merkez kaydı yok
        g, r = self.kart_ac("x", "ACMECO/01_a/001-bir/**")
        i = self.kart_json(g)["is"]
        self.assertEqual(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO", "01_a")), ["001-bir"], r.stderr)
        self.assertEqual(i, i1)
        self.assertIn(i, self.merkez()["isler"])
        self.assertEqual(self.is_klasoru(i), os.path.abspath(yol))
        self.assertEqual(self.oku(os.path.join(yol, "is.json"))["kartlar"], [g])

    def test_k1c_yetim_is_json_sonrasi_yeni_kimlik_yinelenmez(self):
        self.baglam_yaz()
        i1, _ = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.klasor_ac("ACMECO/01_a/002-iki", "iki")
        self.oturumu_birak()
        os.remove(os.path.join(self.sd, "isler.json"))
        self.kart_ac("x", "ACMECO/01_a/001-bir/**")
        self.oturumu_birak()
        i3, _ = self.klasor_ac("ACMECO/01_a/003-uc", "uc")
        self.assertGreater(self.kimlik_no(i3), 2)
        kimlikler = []
        for k in ("001-bir", "002-iki", "003-uc"):
            kimlikler.append(self.oku(os.path.join(self.proje, "ACMECO", "01_a", k, "is.json"))["id"])
        self.assertEqual(len(set(kimlikler)), 3, kimlikler)
        self.assertGreaterEqual(self.merkez()["sayac"], 3)

    def bozuk_yedekler(self):
        return [x for x in os.listdir(self.sd) if x.startswith("isler.json.bozuk-")]

    def bozuk_merkez_yaz(self):
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk json")

    def test_k2_bozuk_isler_json_kart_yeni_basarili_yedek_ve_yeniden_kurulum(self):
        self.baglam_yaz()
        i1, yol = self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        self.bozuk_merkez_yaz()
        r = self.yeni("Bozuk merkez", "ACMECO/01_a/001-bir/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        g = r.stdout.strip()
        i = self.kart_json(g).get("is")
        self.assertTrue(i)
        self.assertEqual(len(self.bozuk_yedekler()), 1, os.listdir(self.sd))
        merkez = self.merkez()  # geçerli JSON olmalı
        self.assertIn(i, merkez["isler"])
        self.assertIn(i1, merkez["isler"])  # bilinen is.json'dan yeniden kuruldu
        self.assertEqual(self.nnn_klasorleri(os.path.join(self.proje, "ACMECO", "01_a")), ["001-bir"])

    def test_k2_bozuk_isler_json_yeni_is_kimligi_cakismaz(self):
        self.baglam_yaz()
        self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.klasor_ac("ACMECO/01_a/002-iki", "iki")
        self.oturumu_birak()
        self.bozuk_merkez_yaz()
        g, _ = self.kart_ac("Yeni", "ACMECO/01_a/009-yeni/**")  # bilinmeyen klasör: yeni iş açılır
        i = self.kart_json(g)["is"]
        self.assertGreater(self.kimlik_no(i), 2)
        kimlikler = []
        for kok, _d, dosyalar in os.walk(os.path.join(self.proje, "ACMECO")):
            if "is.json" in dosyalar:
                kimlikler.append(self.oku(os.path.join(kok, "is.json"))["id"])
        self.assertEqual(len(kimlikler), 3, kimlikler)
        self.assertEqual(len(set(kimlikler)), 3, kimlikler)

    def test_k2_bozuk_isler_json_bilinen_is_json_yokken_de_kart_olusur(self):
        self.bozuk_merkez_yaz()
        r = self.yeni("Sıfırdan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(self.kart_json(r.stdout.strip()).get("is"))
        self.assertEqual(len(self.bozuk_yedekler()), 1)

    def test_k2_bozuk_isler_json_kart_toplu_basarili(self):
        self.baglam_yaz()
        self.klasor_ac("ACMECO/01_a/001-bir", "bir")
        self.oturumu_birak()
        self.bozuk_merkez_yaz()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"soru": "Kısa test sorusu?", "baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/01_a/001-bir/**"]},
                       {"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": ["ACMECO/01_a/007-x/**"]}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        for x in json.loads(r.stdout):
            self.assertTrue(self.kart_json(x["id"]).get("is"), x)
        self.assertEqual(len(self.bozuk_yedekler()), 1)
        self.merkez()  # geçerli JSON


if __name__ == "__main__":
    unittest.main()
