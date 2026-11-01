"""I-321 (ADR-0135): karar sırası kapısı, yanıt iskeleti ve uzunluk kapısı block seçeneği."""
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import cikti_butce as CB  # noqa: E402
import cikti_sirasi as CS  # noqa: E402
import secim_ekrani_hatirlatma as SH  # noqa: E402

AYAR = CS.ayar_oku()
KORPUS = json.load(open(os.path.join(KOK, "tests", "fixtures", "cikti_sirasi_korpus.json"), encoding="utf-8"))
BASLIKLAR = ["**Sana kalan:**", "## Kullanıcıya kalanlar", "**Karar:**", "**Açık kalanlar:**", "**Onay bekleyen:**", "**Onayına bağlı:**"]
BUTCE_AYAR = json.load(open(os.path.join(KOK, "ayarlar", "cikti_butce.json"), encoding="utf-8"))


class SiraKapisiTest(unittest.TestCase):
    def test_ortada_sana_kalan_ihlal(self):
        y = "Sonuç tek cümle.\n\n**Sana kalan:** dalı birleştir.\n\n- Başka madde\n- Bir madde daha"
        self.assertEqual(CS.ihlal(y, AYAR), "sana kalan")

    def test_sonda_sana_kalan_ihlal_degil(self):
        y = "Sonuç tek cümle.\n\n- Madde 1\n- Madde 2\n\n**Sana kalan:** dalı birleştir."
        self.assertEqual(CS.ihlal(y, AYAR), "")

    def test_sorusuz_karar_basligi_yakalanir(self):
        y = "## Karar\nPaneli I-315 ile birlikte ele almak gerekiyor.\n\n## Ayrıntı\nÖlçüm 61 sn."
        self.assertEqual(CS.ihlal(y, AYAR), "karar")

    def test_kullaniciya_kalanlar_auto_son_bolum(self):
        ihlalli = "Özet.\n\n## Kullanıcıya kalanlar\n- Parola\n\n## Plandan sapmalar\n- Yok"
        temiz = "Özet.\n\n## Plandan sapmalar\n- Yok\n\n## Kullanıcıya kalanlar\n- Parola"
        self.assertEqual(CS.ihlal(ihlalli, AYAR), "kullanıcıya kalanlar")
        self.assertEqual(CS.ihlal(temiz, AYAR), "")

    def test_belge_baglanti_satirlari_bolum_sayilmaz(self):
        y = "Özet.\n\n**Karar:** onay bekliyor.\n\nplan dosyası: [plan.md](x/plan.md)\nto-do dosyası: [todo.md](x/todo.md)"
        self.assertEqual(CS.ihlal(y, AYAR), "")

    def test_kod_citi_ici_baslik_sayilmaz(self):
        y = "Özet.\n\n```\n**Karar:** örnek\n```\n\nSon paragraf."
        self.assertEqual(CS.ihlal(y, AYAR), "")

    def test_benzer_ama_karar_olmayan_baslik_ihlal_degil(self):
        y = "**Otomatik kararlar:** a\n\n**Sonuç:** b\n\n**Karar kapısı:** c"
        self.assertEqual(CS.ihlal(y, AYAR), "")

    def test_mod_ortam_degiskeni_kapatir(self):
        os.environ["ORKESTRA_CIKTI_SIRASI"] = "0"
        try:
            self.assertEqual(CS.mod(AYAR), "kapali")
        finally:
            del os.environ["ORKESTRA_CIKTI_SIRASI"]
        self.assertEqual(CS.mod(AYAR), "block")

    def test_korpus_kacirma_sifir_yanlis_pozitif_siniri(self):
        """20 ihlalli (2 gerçek + 18 türetilmiş) ve 30 ihlalsiz gerçek yanıt: kaçırma 0/20, yanlış pozitif ≤2/30."""
        ihlalsiz = KORPUS["ihlalsiz"]
        self.assertEqual(len(ihlalsiz), 30)
        yanlis_pozitif = sum(1 for y in ihlalsiz if CS.ihlal(y, AYAR))
        ihlalli = list(KORPUS["ihlalli_gercek"])
        for i in range(18):
            ihlalli.append(f"{ihlalsiz[i]}\n\n{BASLIKLAR[i % len(BASLIKLAR)]} bir karar bekliyor.\n\n- sonradan eklenen madde")
        self.assertEqual(len(ihlalli), 20)
        self.assertEqual([i for i, y in enumerate(ihlalli) if not CS.ihlal(y, AYAR)], [])
        self.assertLessEqual(yanlis_pozitif, 2, f"yanlış pozitif {yanlis_pozitif}/30")


class IskeletTest(unittest.TestCase):
    def test_tur_basi_metni_iskeleti_icerir_ve_300u_asmaz(self):
        ham = SH.ayar_oku()["tur_basi_yonerge"]
        self.assertLessEqual(len(ham.strip()), SH.TUR_BASI_SINIR, "iskelet kesilmeden sığmalı")
        metin = SH.tur_basi_metni()
        self.assertEqual(metin, ham.strip())
        for parca in ("tek cümle", "en çok 3 madde", "EN SONA"):
            self.assertIn(parca, metin)

    def test_p001_kurali_karar_en_sonda_der(self):
        kurallar = open(os.path.join(KOK, "kurallar", "eklenti_kurallari.json"), encoding="utf-8").read()
        self.assertIn("EN SONUNDA (ADR-0135", kurallar)


class UzunlukKapisiTest(unittest.TestCase):
    AYAR = {"mod": "block", "tur_siniri": 800, "kapanis_siniri": 300, "muafiyet_kaliplari": BUTCE_AYAR["muafiyet_kaliplari"]}

    def test_800_ustu_asim_nedeni_uretir(self):
        self.assertTrue(CB.asimlar({"toplam": 801, "kapanis": None}, self.AYAR))
        self.assertFalse(CB.asimlar({"toplam": 800, "kapanis": None}, self.AYAR))

    def test_kapsamli_inceleme_istegi_muaf(self):
        for mesaj in ("Bunu detaylı anlat", "kapsamlı inceleme yap", "tam rapor ver", "baştan sona açıkla"):
            self.assertTrue(CB.muaf(mesaj, self.AYAR), mesaj)

    def test_normal_mesaj_muaf_degil(self):
        for mesaj in ("ne demek bu?", "onay uygula", "çözülemeyenleri nasıl çözeceğiz?"):
            self.assertFalse(CB.muaf(mesaj, self.AYAR), mesaj)

    def test_varsayilan_mod_golge(self):
        self.assertEqual(BUTCE_AYAR["mod"], "golge")

    def test_son_kullanici_mesaji_transkriptten_okunur(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "t.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "ilk"}}) + "\n")
                f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}) + "\n")
                f.write(json.dumps({"type": "user", "message": {"content": "detaylı anlat"}}) + "\n")
            self.assertEqual(CB.son_kullanici_mesaji(yol), "detaylı anlat")


if __name__ == "__main__":
    unittest.main()
