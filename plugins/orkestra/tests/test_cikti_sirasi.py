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
import hook  # noqa: E402
import izin_politikasi  # noqa: E402

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
        """20 ihlalli (2 gerçek + 18 türetilmiş) ve 30 ihlalsiz gerçek yanıt: kaçırma 0/20, yanlış pozitif ≤1/30."""
        ihlalsiz = KORPUS["ihlalsiz"]
        self.assertEqual(len(ihlalsiz), 30)
        yanlis_pozitif = sum(1 for y in ihlalsiz if CS.ihlal(y, AYAR))
        ihlalli = list(KORPUS["ihlalli_gercek"])
        for i in range(18):
            baslik = BASLIKLAR[i % len(BASLIKLAR)]
            sonra = "\n\n## Ek bölüm\n- sonradan eklenen madde" if baslik.startswith("#") else "\n\n- sonradan eklenen madde"
            ayrac = "\n" if baslik.startswith("#") else " "
            ihlalli.append(f"{ihlalsiz[i]}\n\n{baslik}{ayrac}bir karar bekliyor.{sonra}")
        self.assertEqual(len(ihlalli), 20)
        self.assertEqual([i for i, y in enumerate(ihlalli) if not CS.ihlal(y, AYAR)], [])
        self.assertLessEqual(yanlis_pozitif, 1, f"yanlış pozitif {yanlis_pozitif}/30")


def _auto(y):
    return CS.siniflandir(y, AYAR, True)


class AutoKapisiTest(unittest.TestCase):
    """I-322 (ADR-0137): auto'da karar bölümü yok; kesin sınır yuvası sonda ve her madde `Denendi:` kanıtlı."""

    def test_s1_auto_karar_basligi_sahip_ihlali(self):
        for b in ("**Sana kalan:** dalı birleştir.", "**Karar:** B seçilsin.", "**Onay bekleyen:** plan.", "## Seçim\nA mı B mi?"):
            y = f"Sonuç.\n\n{b}\n\nSon paragraf."
            self.assertEqual(_auto(y)[0], "sahip", b)
        self.assertIn("kendin yap", CS.uyari_metni("sana kalan", AYAR, "sahip"))

    def test_s2_yuva_sonda_gecer_ortada_sira(self):
        sonda = "Özet.\n\n## Plandan sapmalar\n- Yok\n\n## Kullanıcıya kalanlar\n- Parola. Denendi: kimlik klasörü tarandı, kayıt yok"
        ortada = "Özet.\n\n## Kullanıcıya kalanlar\n- Parola. Denendi: kayıt yok\n\n## Plandan sapmalar\n- Yok"
        self.assertEqual(_auto(sonda), ("", ""))
        self.assertEqual(_auto(ortada)[0], "sira")

    def test_s3_plan_modu_degismez(self):
        y = "Sonuç.\n\n**Sana kalan:** dalı birleştir.\n\n- Başka madde"
        self.assertEqual(CS.siniflandir(y, AYAR, False), ("sira", "sana kalan"))
        sonda = "Sonuç.\n\n- Madde\n\n**Sana kalan:** dalı birleştir."
        self.assertEqual(CS.siniflandir(sonda, AYAR, False), ("", ""))

    def test_s4_yonerge_300u_asmaz_ve_kaynak_ifadeleri_icerir(self):
        ham = SH.ayar_oku()["tur_basi_yonerge"].strip()
        self.assertLessEqual(len(ham), SH.TUR_BASI_SINIR)
        for parca in ("önce kendin çöz", "Denendi", "Kullanıcıya kalanlar"):
            self.assertIn(parca, ham)
        skill = open(os.path.join(KOK, "skills", "auto", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("Denendi:", skill)

    def test_s5_gercek_iki_ihlal_auto_da_yakalanir(self):
        self.assertEqual([_auto(y)[0] for y in KORPUS["ihlalli_gercek"]], ["sahip", "sahip"])

    def test_s6_yuvadaki_madde_icerikli_denendi_ister(self):
        def yuva(madde):
            return f"Özet.\n\n## Kullanıcıya kalanlar\n{madde}"
        for kotu in ("- Dalı birleştir", "- Parola. Denendi:", "- Parola. Denendi: yok", "- Parola. Denendi: denenmedi",
                     "- Parola. Denendi: -", "- İlk. Denendi: x\n- İkinci madde"):
            self.assertEqual(_auto(yuva(kotu))[0], "kanit", kotu)
        for iyi in ("- Parola. Denendi: kimlik klasörü tarandı, kayıt yok", "Yok", "- Yok",
                    "- İlk. Denendi: a\n- İkinci. Denendi: b"):
            self.assertEqual(_auto(yuva(iyi)), ("", ""), iyi)

    def test_korpus_auto_kolu_kacirma_sifir_plan_ozgu_haric_yanlis_pozitif_sifir(self):
        ihlalsiz = KORPUS["ihlalsiz"]
        plan_ozgu = [i for i, y in enumerate(ihlalsiz) if _auto(y)[0]]
        self.assertEqual(plan_ozgu, [4, 6, 10], "plan_ozgu başlıklar auto_yasak_basliklar'dan türer")
        payda = len(ihlalsiz) - len(plan_ozgu)
        self.assertEqual(payda, 27)
        ihlalli = list(KORPUS["ihlalli_gercek"])
        for i in range(18):
            baslik = BASLIKLAR[i % len(BASLIKLAR)]
            ayrac = "\n" if baslik.startswith("#") else " "
            ihlalli.append(f"{ihlalsiz[i]}\n\n{baslik}{ayrac}bir karar bekliyor.\n\n- sonradan eklenen madde")
        self.assertEqual([i for i, y in enumerate(ihlalli) if not _auto(y)[0]], [])

    def test_hook_auto_blok_eder_plan_modunda_eski_ret_gunluge_sinif_yazar(self):
        y = "Sonuç.\n\n**Sana kalan:** dalı birleştir.\n\n- madde"
        eski = izin_politikasi._auto_modu
        eski_cikti = hook.L.hook_cikti
        ciktilar = []
        hook.L.hook_cikti = lambda obj=None, kod=0: ciktilar.append(obj)
        try:
            for auto, beklenen in ((True, "sahip"), (False, "sira")):
                izin_politikasi._auto_modu = lambda sd, oturum, a=auto: a
                with tempfile.TemporaryDirectory() as sd:
                    ciktilar.clear()
                    hook._cikti_sirasi_yanit(sd, "o1", {"last_assistant_message": y})
                    self.assertEqual(ciktilar[0]["decision"], "block")
                    kayit = [json.loads(x) for x in open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8")]
                    self.assertEqual(kayit[0]["sinif"], beklenen)
                    if auto:
                        self.assertIn("kendin yap", ciktilar[0]["reason"])
        finally:
            izin_politikasi._auto_modu = eski
            hook.L.hook_cikti = eski_cikti


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
        self.assertIn("EN SONUNDA (ORK-ADR-0135", kurallar)


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


class MetinSorusu(unittest.TestCase):
    """ADR-0133: auto yanıtı düz metin soruyla bitiyor mu."""

    def test_soru_biten_yanit_yakalanir(self):
        self.assertTrue(CS.metin_sorusu("Bitti.\nBu kuralı mı kastettin?"))
        self.assertTrue(CS.metin_sorusu("Tamam.\nDevam edeyim mi? "))

    def test_soru_olmayan_ya_da_kod_icindeki_yakalanmaz(self):
        self.assertEqual(CS.metin_sorusu("Bitti. Test geçti."), "")
        self.assertEqual(CS.metin_sorusu("Sonuç\n```\nx = a ? b : c?\n```"), "")
        self.assertEqual(CS.metin_sorusu("Sonuç\n> alıntı soru mu?"), "")
        self.assertEqual(CS.metin_sorusu("Sonuç.\n`a?`"), "")

    def test_auto_sozlesmesi_metin_sorusunu_yasaklar(self):
        self.assertIn("yanıt metninde de soru sorma", hook._AUTO_SOZLESME)
