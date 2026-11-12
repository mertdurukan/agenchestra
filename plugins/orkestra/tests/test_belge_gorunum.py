"""01/02/03 aşama görünümleri (ADR-0179): kayıttan üretilir; üretim notu, kapı kararı ve kimlikli zincir taşır."""
import os
import re
import sys
import types
import unittest

import test_muhendislik_kontrol as TM

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import belge_gorunum as BG  # noqa: E402
import is_kaydi as IK  # noqa: E402
import muhendislik_kontrol as MK  # noqa: E402


class BelgeGorunum(TM.Fikstur):
    def uret(self, kanit=True, **kw):
        k = self.is_kur(**kw)
        if kanit:
            for t in MK.Baglam(k).kosulacak():
                MK.kanit_al(k, t)
        yollar = BG.uret(k)
        metinler = {}
        for yol in yollar:
            with open(yol, encoding="utf-8") as f:
                metinler[os.path.basename(yol)] = f.read()
        return k, metinler

    def test_uc_dosya_uretim_notu_ve_kapi(self):
        _, m = self.uret()
        self.assertEqual(sorted(m), sorted((BG.ANLATIM,) + BG.DOSYALAR))
        self.assertIn("üretilmiştir", m[BG.ANLATIM])
        for no, ad in enumerate(BG.DOSYALAR, 1):
            self.assertIn("üretilmiştir", m[ad])
            self.assertRegex(m[ad], rf"\*\*Kapı {no} \([^)]+\):\*\* (PASS|FAIL|BLOCKED)")

    def test_anlatim_alti_baslik_ve_etiketli_maddeler(self):
        _, m = self.uret()
        a = m[BG.ANLATIM]
        basliklar = re.findall(r"^## (.+)$", a, re.M)
        self.assertEqual(len(basliklar), 6, basliklar)
        for i, b in enumerate(basliklar, 1):
            self.assertTrue(b.startswith(f"{i}. "), b)
        self.assertNotIn("Okuma kuralı", a)
        maddeler = [s for s in a.splitlines() if s.lstrip().startswith("- ")]
        self.assertTrue(maddeler)
        for s in maddeler:
            self.assertRegex(s.lstrip(), r"^- \[(Veri|Çıkarım)\] ", s)

    def test_anlatim_numarali_bolum_govdesi_dolu(self):
        md = ("# Başlık\n\n## 1. İstek hangi yoldan geçiyor\n\n### 1.1 Alt başlık\n\n1. Birinci adım (a.py:3)\n2. İkinci adım\n\n"
              "## 2. Bugünkü davranış\n\n- Davranış `komut`\n\n## 3. Etki\n\n- Etkilenen\n")
        for no, beklenen in ((1, "Birinci adım"), (2, "Davranış")):
            govde = BG._numarali_bolum(md, no)
            self.assertIn(beklenen, govde)
            maddeler = BG._mdden_maddeler(govde)
            self.assertTrue(maddeler)
            self.assertFalse(any("bölümü yok" in x for x in maddeler))
        self.assertNotIn("Etkilenen", BG._numarali_bolum(md, 2))

    def test_anlatim_bilinmeyenler_mevcut_durumdan_gelir(self):
        md = ("## 4. Doğrulanamayanlar\n\n**Sonuç:** Bir madde var.\n\n- **Konu:** özetsiz işler\n"
              "  - **Denenen:** is.json sayıldı (`ozetsiz.py`)\n  - **Engel:** yol kaydedilmedi\n\n## 5. Gap\n\n- x\n")
        plan = "## 6. Doğrulanamayanlar\n\n- Yok\n\n## 7. Tahminler\n\n- x\n"
        b = types.SimpleNamespace(md=md, plan=plan, md_yolu="m.md", pler={}, tler={}, kanitlar=[])
        metin = BG.anlatim(b, {"kademe": "standart"}, "x")
        son = metin.split("## 6. Hâlâ bilinmeyenler", 1)[1]
        for parca in ("Konu:** özetsiz işler", "Denenen:", "Engel:"):
            self.assertIn(parca, son)
        self.assertNotIn("bildirmiyor", son)
        bos = BG.anlatim(types.SimpleNamespace(md="", plan=plan, md_yolu="", pler={}, tler={}, kanitlar=[]), {"kademe": "k"}, "x")
        self.assertIn("doğrulanamayan madde bildirmiyor", bos.split("## 6. Hâlâ bilinmeyenler", 1)[1])

    def test_anlatim_etiket_kurali(self):
        self.assertEqual(BG.etiket("sınanır (a.py:12)"), "[Veri]")
        self.assertEqual(BG.etiket("sınanır (komut: `pytest -q`)"), "[Veri]")
        self.assertEqual(BG.etiket("sınanır, kanıt yok"), "[Çıkarım]")
        self.assertEqual(BG._madde("[Veri] x"), "- [Veri] x")
        self.assertEqual(BG._madde("[Çıkarım] (a.py:3) x"), "- [Çıkarım] (a.py:3) x")

    def test_01_g_s_ve_s_t(self):
        _, m = self.uret()
        b = m["01-Baslangic.md"]
        for parca in ("**G1:**", "**G2:**", "**S1:**", "**S2:**", "S1 → T1", "S2 → T2", "## Yol kararı", "Zincir kopuk."):
            self.assertIn(parca, b)

    def test_01_tsiz_s_gorunur(self):
        _, m = self.uret(tler="- **T1:** S1 — x — Komut: `{} -c \"pass\"`".format(TM.PY))
        self.assertIn("S2 → T yok", m["01-Baslangic.md"])
        self.assertIn("**Kapı 1 (Başlangıç):** FAIL", m["01-Baslangic.md"])
        self.assertIn("- t_s_kapsama: S2: doğrulama planında T yok", m["01-Baslangic.md"])

    def test_02_p_tablosu_ve_baglar(self):
        _, m = self.uret(todo="- [x] P1 Birinci — 2026-11-12: pytest geçti\n- [ ] P2 İkinci\n")
        g = m["02-Gelistirme.md"]
        self.assertIn("| P1 | Birinci | G1 | S1 | bitti |", g)
        self.assertIn("| P2 | İkinci | G2 | S2 | açık |", g)
        self.assertIn("**Todo:** 1/2 bitti", g)
        self.assertIn("- G1 → P1 → S1", g)
        self.assertIn("**Kapı 2 (Geliştirme):** FAIL", g)

    def test_03_t_e_tablosu_ve_tam_zincir(self):
        _, m = self.uret(sonuc="\n## Sonuç\n\n- S1 ve S2 karşılandı.\n")
        d = m["03-Dogrulama-ve-Yayin.md"]
        self.assertRegex(d, r"\| T1 \| S1 \| E1 \| geçti \|")
        self.assertRegex(d, r"\| T2 \| S2 \| E2 \| geçti \|")
        self.assertIn("- G1 → P1 → S1 → T1 → E1 (geçti)", d)
        self.assertIn("S1 ve S2 karşılandı.", d)
        self.assertIn("**Kapı 3 (Doğrulama ve yayın):** PASS", d)

    def test_03_kanitsiz_ve_bayat(self):
        k, m = self.uret(kanit=False)
        self.assertIn("| T1 | S1 | — | yok |", m["03-Dogrulama-ve-Yayin.md"])
        MK.kanit_al(k, 1)
        self.yaz(self.proje, os.path.join("src", "a.py"), "A = 9\n")
        BG.uret(k)
        with open(os.path.join(k, "03-Dogrulama-ve-Yayin.md"), encoding="utf-8") as f:
            self.assertIn("| T1 | S1 | E1 | bayat |", f.read())

    def test_uretim_kaynak_dosyalari_degistirmez(self):
        k = self.is_kur()
        once = {}
        for ad in os.listdir(k):
            with open(os.path.join(k, ad), encoding="utf-8") as f:
                once[ad] = f.read()
        BG.uret(k)
        for ad, metin in once.items():
            with open(os.path.join(k, ad), encoding="utf-8") as f:
                self.assertEqual(f.read(), metin, ad)

    def test_baglanti_listesinde_gorunum(self):
        k, _ = self.uret()
        satirlar = IK.belge_baglantilari(k, self.proje, tumu=True)
        metin = "\n".join(satirlar)
        for ad in BG.DOSYALAR:
            self.assertIn(ad, metin)

    def test_cli_gorunum(self):
        kayit = IK.is_ac(self.sd, "görünüm", os.path.join(self.proje, "Claude_Orkestrasyon", "005-cli"))
        k = self.is_kur(ad=os.path.basename(kayit["klasor"]))
        r = self.cli("is", "gorunum", kayit["id"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for ad in BG.DOSYALAR:
            self.assertIn(ad, r.stdout)
            self.assertTrue(os.path.isfile(os.path.join(k, ad)))


if __name__ == "__main__":
    unittest.main()
