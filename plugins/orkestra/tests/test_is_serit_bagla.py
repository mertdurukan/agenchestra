"""İş şeridi 1 (G-023) + kart-iş bağı zorunlu (G-035): kart oluşturmada iş/adım otomatik bağı, adim_coz,
is_klasorle_bul ve `orkestra is bagla --geriye [--uygula]`. Geçici proje dizininde koşar.

G-035 kuralı: kart oluşturma asla bağsız bitmez ve bağ yüzünden reddedilmez; sıra (a) --is, (b) oturumun açık işi,
(c)/(d) yazma_alani ilk girdisinin klasörü (test_alani çözüme katılmaz). `kart yeni` artık bağsız kart üretemediğinden
`is bagla --geriye` testleri bağsız kartı doğrudan kart JSON'u yazarak kurar (bagsiz_kart)."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import is_kaydi as IK  # noqa: E402


def agac_ozeti(kok):
    """Dizindeki tüm dosyaların (yol, içerik özeti) listesi; kuru koşunun yan etkisiz olduğunu doğrulamak için."""
    out = []
    for dp, _, dosyalar in os.walk(kok):
        for ad in sorted(dosyalar):
            yol = os.path.join(dp, ad)
            with open(yol, "rb") as f:
                out.append((os.path.relpath(yol, kok), hashlib.sha1(f.read()).hexdigest()))
    return sorted(out)


class AdimCoz(unittest.TestCase):
    def test_yedi_ornek(self):
        ornekler = [
            ("PE-636 G4: x", "G4"),
            ("PE-636 G7-A1: x", "G7-A1"),
            ("PE-636 G8-B1/B2: x", "G8-B1/B2"),
            ("PE-636: G7-G9 paralel", "G7-G9"),
            ("PE-636 Kalite-A altyapı", None),
            ("SURECLER listesine ekle", None),
            ("G-015 kart kimliği biçimi", None),
        ]
        for baslik, bek in ornekler:
            self.assertEqual(IK.adim_coz(baslik), bek, baslik)

    def test_ucdurumlar(self):
        self.assertIsNone(IK.adim_coz(""))
        self.assertIsNone(IK.adim_coz("G-1: tire"))
        self.assertEqual(IK.adim_coz("G12: iki haneli"), "G12")
        self.assertEqual(IK.adim_coz("G4 boşlukla biter"), "G4")
        self.assertEqual(IK.adim_coz("PE-1 G10-C2: x"), "G10-C2")
        self.assertIsNone(IK.adim_coz("Genel G4: ortada"))


class Bagla(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    # ------------------------------------------------------------ yardımcılar
    def baglam_yaz(self, dis=None):
        d = {"surum": 1, "projeler": ["RNV", "Claude_Orkestrasyon"], "surec_deseni": r"^\d{2}_",
             "gorev_deseni": r"^\d{3}-", "haric": ["98_calisma"], "dis_kokler": {}}
        if dis:
            d["dis_kokler"] = {dis: "Claude_Orkestrasyon"}
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def gorev_klasoru(self, ad="001-y", surec="05_x"):
        return os.path.join(self.proje, "RNV", surec, ad)

    def oku(self, yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)

    def kart_json(self, g):
        return self.oku(os.path.join(self.sd, "gorevler", f"{g}.json"))

    def kart_json_yaz(self, g, veri):
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)

    def isler(self):
        return self.oku(os.path.join(self.sd, "isler.json"))["isler"]

    def is_json(self, klasor):
        return self.oku(os.path.join(klasor, "is.json"))

    def yeni(self, baslik, *yazma, ek=()):
        a = ["kart", "yeni", "--baslik", baslik, "--kabul", "k", "--sinif", "belge"]
        for y in yazma:
            a += ["--yazma", y]
        r = self.cli(*a, *ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().splitlines()[-1]

    def bagsiz_kart(self, g, baslik, yazma):
        """`is` alanı olmayan kartı doğrudan yazar (eski/göç kartı); `kart yeni` G-035 gereği bunu üretemez."""
        veri = {
            "id": g, "baslik": baslik, "sinif": "-", "basamak": "T2", "baslangic_basamak": "T2", "girdi": "",
            "kabul_kriterleri": ["k"], "yazma_alani": list(yazma), "bagimliliklar": [], "durum": "planlandi",
            "oturum": TC.OTURUM, "olusturma": "2026-10-14T00:00:00+03:00", "isciler": [], "denetciler": [],
            "denetimler": [], "ciktilar": [], "gecmis": [{"zaman": "2026-10-14T00:00:00+03:00", "olay": "olusturuldu",
                                                          "basamak": "T2"}], "v": 1}
        if IK.adim_coz(baslik):  # kart yeni de adim'ı yazar; geriye testi yalnız is bağını sınasın
            veri["adim"] = IK.adim_coz(baslik)
        self.kart_json_yaz(g, veri)
        self.assertNotIn("is", self.kart_json(g))
        return g

    def is_ac(self, baslik, klasor):
        r = self.cli("is", "ac", baslik, "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    # ------------------------------------------------------------ is_klasorle_bul
    def test_is_klasorle_bul(self):
        k = self.gorev_klasoru()
        self.assertIsNone(IK.is_klasorle_bul(self.sd, k))
        i = self.is_ac("a", k)
        self.assertEqual(IK.is_klasorle_bul(self.sd, k), i)
        # normpath + casefold
        self.assertEqual(IK.is_klasorle_bul(self.sd, os.path.join(k, "..", "001-Y").replace("\\", "/")), i)
        self.assertEqual(IK.is_klasorle_bul(self.sd, k.upper()), i)
        self.assertIsNone(IK.is_klasorle_bul(self.sd, self.gorev_klasoru("002-z")))
        # kapalı iş bulunmaz
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        self.assertIsNone(IK.is_klasorle_bul(self.sd, k))

    def test_is_klasorle_bul_kapali_degil_ilk_acik(self):
        k = self.gorev_klasoru()
        i1 = self.is_ac("a", k)
        self.assertEqual(self.cli("is", "kapat", i1).returncode, 0)
        i2 = self.is_ac("b", k)
        self.assertEqual(IK.is_klasorle_bul(self.sd, k), i2)

    # ------------------------------------------------------------ kriter 2
    def test_yeni_kart_gorev_klasoru_isi_olusur(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        g = self.yeni("kart", os.path.join(k, "src", "a.py").replace("\\", "/"))
        self.assertEqual(self.kart_json(g)["is"], "I-001")
        kayit = self.isler()["I-001"]
        self.assertEqual(os.path.normcase(os.path.abspath(kayit["klasor"])), os.path.normcase(os.path.abspath(k)))
        self.assertEqual(kayit["baslik"], "001-y")
        self.assertEqual(self.is_json(k)["kartlar"], [g])

    def test_yeni_kart_var_olan_ise_baglanir_ikinci_is_acilmaz(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        i = self.is_ac("elle açıldı", k)
        g = self.yeni("kart", os.path.join(k, "a.py").replace("\\", "/"))
        self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(list(self.isler()), [i])
        self.assertEqual(self.is_json(k)["kartlar"], [g])

    def test_test_alani_gorev_klasorunu_cozmez(self):
        # G-035: çözüm yazma_alani esas; test_alani'ndaki görev klasörü işi belirlemez (eski G-023 kuralı kalktı).
        # yazma 'docs/**' çözülemez → (d) ilk projede (RNV) başlığa göre yeni iş; kart yine bağlı, çıkış 0.
        self.baglam_yaz()
        k = self.gorev_klasoru()
        r = self.cli("kart", "yeni", "--baslik", "kod", "--kabul", "k", "--sinif", "kod", "--yazma", "docs/**",
                     "--test-komutu", "echo x", "--test-alani", os.path.join(k, "tests", "t.py").replace("\\", "/"))
        self.assertEqual(r.returncode, 0, r.stderr)
        g = r.stdout.strip().splitlines()[-1]
        self.assertEqual(self.kart_json(g)["is"], "I-001")
        kayit = self.isler()["I-001"]
        self.assertEqual(kayit["baslik"], "kod")
        self.assertNotEqual(os.path.normcase(os.path.abspath(kayit["klasor"])), os.path.normcase(os.path.abspath(k)))
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(kayit["klasor"]))),
                         os.path.normcase(os.path.join(self.proje, "RNV")))

    def test_kapali_gorev_isine_kart_baglanmaz(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        i = self.is_ac("a", k)
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        g = self.yeni("kart", os.path.join(k, "a.py").replace("\\", "/"))
        self.assertNotEqual(self.kart_json(g).get("is"), i)  # kapalı işe kart bağlanmaz

    # ------------------------------------------------------------ kriter 3
    def test_toplu_ayni_gorev_klasoru_tek_is(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([
                {"baslik": "PE-636 G4: a", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": [os.path.join(k, "a.py").replace("\\", "/")]},
                {"baslik": "PE-636 G5: b", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": [os.path.join(k, "b.py").replace("\\", "/")]},
            ], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]
        self.assertEqual(len(self.isler()), 1)
        self.assertEqual([self.kart_json(g)["is"] for g in ids], ["I-001", "I-001"])
        self.assertEqual(self.is_json(k)["kartlar"], ids)
        self.assertEqual([self.kart_json(g)["adim"] for g in ids], ["G4", "G5"])

    def test_toplu_farkli_gorev_klasorleri_oturum_isi_tek_is(self):
        # G-035: (b) oturumun açık işi (c)'den önce gelir; ilk kartın açtığı iş oturuma bağlanır, ikinci kart ona gider.
        self.baglam_yaz()
        k1, k2 = self.gorev_klasoru("001-y"), self.gorev_klasoru("002-z")
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([
                {"baslik": "a", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": [os.path.join(k1, "a.py").replace("\\", "/")]},
                {"baslik": "b", "sinif": "belge", "kabul_kriterleri": ["k"], "yazma_alani": [os.path.join(k2, "b.py").replace("\\", "/")]},
            ], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]
        self.assertEqual(len(self.isler()), 1)
        self.assertEqual(self.kart_json(ids[0])["is"], "I-001")
        self.assertEqual(self.kart_json(ids[1])["is"], "I-001")
        self.assertEqual(self.is_json(k1)["kartlar"], ids)  # iş ilk kartın görev klasöründe açıldı
        self.assertFalse(os.path.exists(os.path.join(k2, "is.json")))

    # ------------------------------------------------------------ kriter 4
    def test_proje_duzeyi_baglam_oturum_isine_baglanir(self):
        dis = tempfile.mkdtemp(prefix="ork_dis_")
        try:
            self.baglam_yaz(dis=dis.replace("\\", "/"))
            i = self.is_ac("oturum işi", os.path.join(self.proje, "is1"))
            g = self.yeni("dış", os.path.join(dis, "x", "a.py").replace("\\", "/"))
            self.assertEqual(self.kart_json(g)["is"], i)
            self.assertEqual(list(self.isler()), [i])
            # RNV/<süreç> düzeyi (görev klasörü yok) de oturum işine gider
            g2 = self.yeni("süreç", os.path.join(self.proje, "RNV", "05_x", "not.md").replace("\\", "/"))
            self.assertEqual(self.kart_json(g2)["is"], i)
            self.assertEqual(list(self.isler()), [i])
        finally:
            import shutil
            shutil.rmtree(dis, ignore_errors=True)

    def test_proje_duzeyi_oturum_isi_yoksa_kart_yine_baglanir(self):
        # G-035: kart asla bağsız kalmaz; oturum işi de yoksa (d) ilk projede yeni iş açılır ve oturuma bağlanır.
        self.baglam_yaz()
        g = self.yeni("düz", "docs/**")
        self.assertEqual(self.kart_json(g)["is"], "I-001")
        kayit = self.isler()["I-001"]
        self.assertEqual(kayit["baslik"], "düz")
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(kayit["klasor"]))),
                         os.path.normcase(os.path.join(self.proje, "RNV")))
        g2 = self.yeni("ikinci", "docs/**")  # artık oturum işi var → aynı işe
        self.assertEqual(self.kart_json(g2)["is"], "I-001")
        self.assertEqual(list(self.isler()), ["I-001"])

    def test_acik_is_baglamdan_onceliklidir(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        i = self.is_ac("başka", os.path.join(self.proje, "is1"))
        g = self.yeni("kart", os.path.join(k, "a.py").replace("\\", "/"), ek=("--is", i))
        self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(list(self.isler()), [i])  # görev klasörü için iş açılmadı

    def test_baglam_json_yoksa_bugunku_davranis(self):
        i = self.is_ac("oturum", os.path.join(self.proje, "is1"))
        g = self.yeni("kart", os.path.join(self.gorev_klasoru(), "a.py").replace("\\", "/"))
        self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(list(self.isler()), [i])

    # ------------------------------------------------------------ kriter 5
    def test_adim_alani(self):
        g1 = self.yeni("PE-636 G7-A1: x", "docs/**")
        g2 = self.yeni("Kalite altyapı", "docs/**")
        g3 = self.yeni("PE-636 G8-B1/B2: y", "docs/**")
        self.assertEqual(self.kart_json(g1)["adim"], "G7-A1")
        self.assertNotIn("adim", self.kart_json(g2))
        self.assertEqual(self.kart_json(g3)["adim"], "G8-B1/B2")

    # ------------------------------------------------------------ kriter 6
    def _geriye_kurulum(self):
        """G-001: yazma görev klasöründe (baglam); G-002: yalnız docs (oturum); G-003: adim eksik.
        Kartlar doğrudan JSON olarak yazılır (G-035 sonrası `kart yeni` bağsız kart üretmez), `is` alanı boştur."""
        k = self.gorev_klasoru()
        g1 = self.bagsiz_kart("G-001", "PE-636 G4: a", [os.path.join(k, "a.py").replace("\\", "/")])
        g2 = self.bagsiz_kart("G-002", "PE-636 G5: b", ["docs/**"])
        g3 = self.bagsiz_kart("G-003", "PE-636 G7-A1: c", ["docs/**"])
        v = self.kart_json(g3)
        v.pop("adim", None)
        self.kart_json_yaz(g3, v)
        for g in (g1, g2, g3):
            self.assertNotIn("is", self.kart_json(g))
        self.baglam_yaz()
        i = self.is_ac("görev işi", k)  # oturum bağlanır, is.json oturumlar[] test oturumunu içerir
        return k, i, (g1, g2, g3)

    def test_geriye_kuru_kosu_dosya_degistirmez_ve_listeler(self):
        k, i, (g1, g2, g3) = self._geriye_kurulum()
        once = agac_ozeti(self.proje)
        r = self.cli("is", "bagla", "--geriye")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(agac_ozeti(self.proje), once)
        self.assertIn(f"{g1} → {i} (baglam)", r.stdout)
        self.assertIn(f"{g2} → {i} (oturum)", r.stdout)
        self.assertIn(f"{g3} → {i} (oturum)", r.stdout)
        self.assertIn(f"{g3} adim=G7-A1", r.stdout)
        self.assertNotIn(f"{g1} adim=", r.stdout)
        self.assertNotIn("fark yok", r.stdout)

    def test_geriye_uygula_ve_ikinci_kosu_fark_yok(self):
        k, i, (g1, g2, g3) = self._geriye_kurulum()
        r = self.cli("is", "bagla", "--geriye", "--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        for g in (g1, g2, g3):
            self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(self.kart_json(g3)["adim"], "G7-A1")
        self.assertEqual(self.is_json(k)["kartlar"], [g1, g2, g3])
        self.assertEqual(len(self.isler()), 1)
        r2 = self.cli("is", "bagla", "--geriye")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("fark yok", r2.stdout)
        self.assertNotIn("→", r2.stdout)
        r3 = self.cli("is", "bagla", "--geriye", "--uygula")
        self.assertIn("fark yok", r3.stdout)
        self.assertEqual(self.is_json(k)["kartlar"], [g1, g2, g3])  # çift kayıt yok

    def test_geriye_degisiklik_yoksa_fark_yok(self):
        r = self.cli("is", "bagla", "--geriye")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fark yok", r.stdout)

    def test_geriye_baglam_bulunamazsa_yeni_is_acmaz_kuru_kosuda(self):
        # görev klasörü için iş yok: kuru koşu iş oluşturmamalı
        k = self.gorev_klasoru()
        self.bagsiz_kart("G-001", "a", [os.path.join(k, "a.py").replace("\\", "/")])
        self.baglam_yaz()
        r = self.cli("is", "bagla", "--geriye")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.sd, "isler.json")))

    def test_geriye_kapali_ise_baglamaz(self):
        g = self.bagsiz_kart("G-001", "PE-636 G4: a", ["docs/**"])
        i = self.is_ac("sonra açıldı", os.path.join(self.proje, "is1"))
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        r = self.cli("is", "bagla", "--geriye", "--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("is", self.kart_json(g))
        self.assertEqual(self.is_json(os.path.join(self.proje, "is1"))["kartlar"], [])

    # ------------------------------------------------------------ kriter 7
    def test_geriye_dolu_is_degismez(self):
        self.baglam_yaz()
        k = self.gorev_klasoru()
        i1 = self.is_ac("birinci", os.path.join(self.proje, "is1"))
        i2 = self.is_ac("görev işi", k)  # oturum artık I-002'de
        # görev klasöründe yazan ama açıkça I-001'e bağlı kart
        g = self.yeni("PE-636 G9: z", os.path.join(k, "a.py").replace("\\", "/"), ek=("--is", i1))
        v = self.kart_json(g)
        v.pop("adim", None)
        self.kart_json_yaz(g, v)
        r = self.cli("is", "bagla", "--geriye", "--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(f"{g} → ", r.stdout)
        self.assertEqual(self.kart_json(g)["is"], i1)
        self.assertEqual(self.kart_json(g)["adim"], "G9")  # eksik adim eklenir
        self.assertEqual(self.is_json(os.path.join(self.proje, "is1"))["kartlar"], [g])
        self.assertEqual(self.is_json(k)["kartlar"], [])
        self.assertIn("fark yok", self.cli("is", "bagla", "--geriye").stdout)

    def test_geriye_dolu_is_dry_run_adim_satiri(self):
        self.baglam_yaz()
        i1 = self.is_ac("birinci", os.path.join(self.proje, "is1"))
        g = self.yeni("PE-636 G9: z", "docs/**", ek=("--is", i1))
        v = self.kart_json(g)
        v.pop("adim", None)
        self.kart_json_yaz(g, v)
        r = self.cli("is", "bagla", "--geriye")
        self.assertIn(f"{g} adim=G9", r.stdout)
        self.assertNotIn("adim", self.kart_json(g))  # kuru koşu yazmadı


if __name__ == "__main__":
    unittest.main()
