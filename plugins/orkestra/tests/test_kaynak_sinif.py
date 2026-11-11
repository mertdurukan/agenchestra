"""I-226 P7/P8 (ADR-0178): soru metninden kaynak sınıfı (scripts/kaynak_sinif.py), sınıfa göre ilk araç satırı ve
kullanıcı itirazı (`ilk_cevap_itiraz`) tespiti. Kalıplar ayardan okunur (`ayarlar/kaynak_sinif.json`); testte sabitlenmez.
`python -m pytest -q plugins/orkestra/tests/test_kaynak_sinif.py`
Örnek sorular gerçek soru biçimindedir; projeye özgü ad taşımaz.
"""
import ast
import contextlib
import io
import json
import os
os.environ["ORKESTRA_HOOK_TEKIL"] = "0"
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
try:  # kod yokken toplama hatası değil, test başarısızlığı olsun
    import kaynak_sinif as KS  # noqa: E402
except ImportError:
    KS = None
import hook  # noqa: E402
import niyet  # noqa: E402
import soru_sinif  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "kaynak_sinif.py")
AYAR = os.path.join(KOK, "ayarlar", "kaynak_sinif.json")
OTURUM = "kaynak1234567890-oturum"
SINIFLAR = ("yerel", "gecmis_oturum", "urun_belgesi", "canli_bulut")

ORNEKLER = {
    "yerel": ["settings.json içinde varsayılan model ne?", "bu hook neden iki kez çalışıyor?",
              "I-226 hangi durumda?", "orkestrada şu an hangi modeli seçtiğimin önemi var mı?",
              "mail.env dosyası nerede?", "`kanit_olcum.py` kaç tur sayıyor?",
              "ADR-0085 block'a geçişi nasıl tanımlıyor?", "P-021 kuralı şu an ne diyor?",
              "ayarlar/soru_sinif.json'da eşik kaç?", "bu projede hangi testler var?",
              "bizde push kuralı ne?", "config/tenants/ nedir?", "orkestra nasıl çalışır?"],
    "gecmis_oturum": ["arşivlenen sohbete göre şimdi ne yapmamız gerekiyor?", "o sohbette ne karar verdik?",
                      "kasaya yazma ya da silme yaptık mı şimdiye kadar?", "önceki oturumda testler geçmiş miydi?"],
    "urun_belgesi": ["Claude Code'da /plugin komutu ne yapıyor?", "marketplace'de nasıl görüntüleyebilir?",
                     "Cursor bu özelliği destekliyor mu?", "otomatik moddayken izin denetimini kim yapıyor?"],
    "canli_bulut": ["azure openai ve cosmos erişimi için sorun ne?", "neden yalnızca 2 kasa için yapıyoruz?",
                    "langfuse trace'leri neden gelmiyor?", "VPN bağlı mı, sunucu ayakta mı?"],
}
SINIF_DISI = ["fallback ne demek?", "iki yaklaşımdan hangisi daha sade?", "böyle çalışması best in class mı?",
              "tenant kavramı nedir?", "yapay zeka nedir?"]
# Denetçi bulgusu: çıpasız genel/kavramsal sorular yerel ya da canlı kaynağa yönlendirilmemeli (hedef: ≤ %10)
GENEL = ["kural nedir?", "ayar ne demek?", "depo ne demek?", "commit mesajı nasıl yazılır?", "panel ne işe yarar?",
         "git branch ile tag farkı ne?", "config nasıl yapılandırılır?", "kayıt olmak için ne gerekir?",
         "IP adresi nedir?", "Redis nedir?", "sunucu ne demek?", "bir script nasıl çalışır?", "DNS nasıl çalışır?",
         "prod ortamı ile test ortamı arasındaki fark ne?", "hook kavramı ne anlama gelir?",
         "bir dosya sistemi nasıl çalışır?", "eklenti mimarisi ne işe yarar?", "VPN ne işe yarar?",
         "repo ile klasör arasındaki fark ne?", "worktree nedir?", "skill yazmak için ne gerekir?"]


class _Ayarli(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(KS, "scripts/kaynak_sinif.py yok")
        self.tmp = tempfile.mkdtemp(prefix="ork_kaynak_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_KANIT_KAPISI"):
            os.environ.pop(k, None)
        self.ayar = KS.ayar_oku(self.sd)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik):
        with open(os.path.join(self.sd, "kaynak_sinif.json"), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))


class TestDosyalar(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_ayar_semasi(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        self.assertEqual(set(a["siniflar"]), set(SINIFLAR))
        self.assertEqual(sorted(a["sira"]), sorted(SINIFLAR))
        self.assertTrue(a["aciklama"])  # docs/basvuru/ayarlar.md bu anahtardan üretilir
        for k in a["kavram_kaliplari"]:
            re.compile(k)
        for ad, s in a["siniflar"].items():
            self.assertTrue(s["ilk_arac"], ad)
            self.assertTrue(s["kaliplar"] or s["cipa_kaliplari"], ad)
            for k in s["kaliplar"] + s["cipa_kaliplari"]:
                re.compile(k)
        self.assertEqual(a["sinif_kapisi"]["mod"], "golge")  # P-028: block yok
        self.assertIs(a["sinif_kapisi"]["uyari_acik"], False)
        for k in a["itiraz"]["baslangic_kaliplari"] + a["itiraz"]["atif_kaliplari"]:
            re.compile(k["desen"])

    def test_modulde_kalip_sabiti_yok(self):
        # P-022: kalıp ve proje adı kodda değil ayarda
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                for w in ("azure", "cosmos", "claude code", "cursor", "sohbet", "hayır", "yanlış", "settings"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestSinif(_Ayarli):
    def test_her_sinif_gercek_sorular(self):
        for beklenen, sorular in ORNEKLER.items():
            self.assertGreaterEqual(len(sorular), 3)
            for q in sorular:
                with self.subTest(q=q):
                    self.assertEqual(KS.sinif(q, self.sd), beklenen)

    def test_sinif_disi(self):
        for q in SINIF_DISI + ["", None, "   "]:
            with self.subTest(q=q):
                self.assertIsNone(KS.sinif(q, self.sd))

    def test_genel_sorularda_yanlis_yonlendirme_en_cok_yuzde_on(self):
        self.assertEqual(len(GENEL), 21)
        yanlis = [q for q in GENEL if KS.sinif(q, self.sd)]
        self.assertLessEqual(len(yanlis) / len(GENEL), 0.10, yanlis)

    def test_yerel_en_az_on_gercek_soru(self):
        self.assertGreaterEqual(len(ORNEKLER["yerel"]), 10)

    def test_uzun_girdi_hizli(self):
        # ReDoS: boşluksuz uzun girdi (base64 benzeri ya da tek uzun sözcük) sınırlı sürede biter
        import base64
        import time
        girdiler = ["a" * 100_000, "a" * 100_000 + ".py", base64.b64encode(os.urandom(75_000)).decode(),
                    "ğ" * 100_000 + "dık mı", "x/" * 50_000]
        for g in girdiler:
            for fn in (lambda: KS.sinif(g, self.sd), lambda: KS.yonlendirme(g, self.sd),
                       lambda: KS.itiraz_kalibi("hayır " + g, "yanıt", self.sd),
                       lambda: soru_sinif.kaynak_metni(g, self.sd), lambda: KS.kapsamda_mi(g, self.sd)):
                t0 = time.perf_counter()
                fn()
                self.assertLess(time.perf_counter() - t0, 0.5, g[:20])

    def test_giris_siniri_ayarda(self):
        self.assertGreater(self.ayar["giris_max_karakter"], 0)
        self.proje_ayari({"giris_max_karakter": 10})
        self.assertIsNone(KS.sinif("bu soru uzun bir giriş: azure erişimi neden yok?", self.sd))

    def test_buyuk_harf_normallestirme(self):
        self.assertEqual(KS.sinif("AZURE ERİŞİMİ NEDEN YOK?", self.sd), "canli_bulut")
        self.assertEqual(KS.sinif("I-226 NEREDE?", self.sd), "yerel")

    def test_proje_ezmesi_anahtar_bazinda(self):
        self.proje_ayari({"sira": ["yerel"]})
        self.assertIsNone(KS.sinif("azure erişimi neden yok?", self.sd))
        self.assertEqual(KS.sinif("bu hook neden çalışıyor?", self.sd), "yerel")
        self.assertIn("canli_bulut", KS.ayar_oku(self.sd)["siniflar"])

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        self.proje_ayari("{bozuk")
        self.assertEqual(KS.ayar_oku(self.sd), KS.ayar_oku(None))

    def test_gecersiz_regex_atlanir(self):
        a = json.loads(json.dumps(self.ayar))
        a["siniflar"]["yerel"]["kaliplar"] = ["[bozuk"] + a["siniflar"]["yerel"]["kaliplar"]
        self.proje_ayari({"siniflar": a["siniflar"]})
        self.assertEqual(KS.sinif("bu hook neden çalışıyor?", self.sd), "yerel")


class TestSatir(_Ayarli):
    def test_satir_tek_ve_sinirli(self):
        for ad, sorular in ORNEKLER.items():
            s = KS.yonlendirme(sorular[0], self.sd)
            with self.subTest(ad=ad):
                self.assertTrue(s)
                self.assertNotIn("\n", s)
                self.assertLessEqual(len(s), self.ayar["max_karakter"])
                self.assertLessEqual(len(s), 200)
                self.assertIn(self.ayar["siniflar"][ad]["ilk_arac"], s)
                self.assertIn("doğrulanmadı", s)
                self.assertIn("araç sonucundan önce", s)

    def test_sinif_disinda_satir_yok(self):
        self.assertEqual(KS.yonlendirme("fallback ne demek?", self.sd), "")

    def test_sinir_asilinca_verilmez(self):
        self.proje_ayari({"max_karakter": 20})
        self.assertEqual(KS.yonlendirme("azure erişimi neden yok?", self.sd), "")

    def test_p1_satirinin_yerini_alir(self):
        # sınıf eşleşince P1 KAYNAK satırı değil sınıf satırı; eşleşmezse P1 satırı (çift yazım yok)
        p1 = soru_sinif.ayar_oku(self.sd)["kaynak_sozlesmesi"]
        self.assertEqual(soru_sinif.kaynak_metni("azure erişimi neden yok?", self.sd),
                         KS.yonlendirme("azure erişimi neden yok?", self.sd))
        self.assertEqual(soru_sinif.kaynak_metni("fallback ne demek?", self.sd), p1)

    def test_sinif_modulu_hata_atarsa_p1_satiri(self):
        p1 = soru_sinif.ayar_oku(self.sd)["kaynak_sozlesmesi"]
        with mock.patch.object(KS, "yonlendirme", side_effect=RuntimeError("x")):
            self.assertEqual(soru_sinif.kaynak_metni("azure erişimi neden yok?", self.sd), p1)


def tur(istem, yanit, cagrilar=()):
    return {"istem": istem, "zaman": "2026-11-11T10:00", "cagrilar": list(cagrilar), "yanit": yanit}


class TestItiraz(_Ayarli):
    ONCEKI = tur("azure erişimi neden yok?", "Neden IP izin listesi.")

    def test_itiraz_kanitsiz_onceki_tur(self):
        for m in ("hayır, nedeni bu değil, private DNS eksik", "yanlış, öyle bir ayar yok bence",
                  "ilk cevabın yanlıştı, tekrar bak", "dediğin şey doğru değil, kontrol et",
                  "bu doğru değil, dosyada başka yazıyor", "aynı olduğuna emin misin? dosyada başka yazıyor",
                  "çalıştığını söylüyorsun ama ekranda görünmüyor"):
            with self.subTest(m=m):
                o = KS.ilk_cevap_itiraz(m, self.ONCEKI, self.sd)
                self.assertIsNotNone(o)
                self.assertEqual(o["sinif"], "canli_bulut")
                self.assertTrue(o["kalip"])

    def test_kanitli_onceki_tur_olay_yok(self):
        onceki = tur("azure erişimi neden yok?", "Neden IP izin listesi.", [("Bash", {"command": "az x"})])
        self.assertIsNone(KS.ilk_cevap_itiraz("hayır, nedeni bu değil, private DNS eksik", onceki, self.sd))
        self.assertTrue(KS.itiraz_kalibi("hayır, nedeni bu değil, private DNS eksik", onceki["yanit"], self.sd))

    def test_kisa_komut_olay_yok(self):
        for m in ("hayır", "yanlış", "hayır.", "yok", "devam"):
            with self.subTest(m=m):
                self.assertIsNone(KS.ilk_cevap_itiraz(m, self.ONCEKI, self.sd))

    def test_itiraz_olmayan_mesaj(self):
        # denetçinin beş yanlış pozitifi + övgü, komut, özet ve yeni konu örnekleri
        for m in ("şunu düzelt", "yanlış pozitif oranı ne kadar?", "raporu güncelle ve testleri çalıştır",
                  "hayırlı olsun, devam edelim",
                  "hayır, bunu yapma", "ilk cevabın doğruydu, devam et", "ilk yanıtı bir dosyaya yaz",
                  "son cevabı özetle", "yanlış çıktı üretiyor: hata log",
                  "haklıydın, ilk cevabın doğru", "önceki yanıtı md dosyasına yaz", "son yanıtını kısalt",
                  "hayır, şimdi başka konuya geçelim"):
            with self.subTest(m=m):
                self.assertIsNone(KS.ilk_cevap_itiraz(m, self.ONCEKI, self.sd))

    def test_soruya_verilen_hayir_itiraz_degil(self):
        soran = tur("raporu yaz", "Raporu yazdım. Excel'e de dökeyim mi?")
        self.assertIsNone(KS.ilk_cevap_itiraz("hayır, yalnız md yeterli", soran, self.sd))
        # yanıta yönelik atıf kalıbı soru sonrası da sayılır
        self.assertIsNotNone(KS.ilk_cevap_itiraz("ilk cevabın yanlıştı, tekrar bak", soran, self.sd))

    def test_onceki_tur_yok_ya_da_yanitsiz(self):
        self.assertIsNone(KS.ilk_cevap_itiraz("hayır, nedeni bu değil", None, self.sd))
        self.assertIsNone(KS.ilk_cevap_itiraz("hayır, nedeni bu değil", tur("x", ""), self.sd))

    def test_ayarla_kapanir(self):
        self.proje_ayari({"itiraz": dict(self.ayar["itiraz"], acik=False)})
        self.assertIsNone(KS.ilk_cevap_itiraz("hayır, nedeni bu değil, DNS eksik", self.ONCEKI, self.sd))


class TestHook(_Ayarli):
    def setUp(self):
        super().setUp()
        self.tr = os.path.join(self.tmp, "tr.jsonl")
        open(self.tr, "w").close()
        niyet_yolu = os.path.join(self.tmp, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        super().tearDown()

    def transkript(self, *turlar):
        with open(self.tr, "w", encoding="utf-8") as f:
            for istem, yanit, cagrilar in turlar:
                f.write(json.dumps({"type": "user", "timestamp": "2026-11-11T10:00:00Z",
                                    "message": {"role": "user", "content": istem}}) + "\n")
                for ad in cagrilar:
                    f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "id": "t", "name": ad, "input": {"command": "ls"}}]}}) + "\n")
                f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": yanit}]}}) + "\n")

    def istek(self, metin, **ek):
        g = {"session_id": OTURUM, "cwd": self.tmp, "transcript_path": self.tr, "prompt": metin, **ek}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit(g)
            except SystemExit as e:
                self.assertIn(e.code, (0, None))
        c = buf.getvalue().strip()
        return json.loads(c)["hookSpecificOutput"]["additionalContext"] if c else ""

    def olaylar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip() and json.loads(s).get("tur") == "ilk_cevap_itiraz"]

    def test_sinif_satiri_tek_ve_p1_yok(self):
        p1 = soru_sinif.ayar_oku(self.sd)["kaynak_sozlesmesi"]
        ctx = self.istek("azure erişimi neden yok?")
        satir = KS.yonlendirme("azure erişimi neden yok?", self.sd)
        self.assertEqual(ctx.split("\n").count(satir), 1)
        self.assertNotIn(p1, ctx)

    def test_sinif_disinda_p1_satiri(self):
        p1 = soru_sinif.ayar_oku(self.sd)["kaynak_sozlesmesi"]
        self.assertIn(p1, self.istek("fallback ne demek?").split("\n"))

    def test_itiraz_olayi_yazilir(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []))
        self.istek("hayır, nedeni bu değil, private DNS eksik")
        o = self.olaylar()
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]["sinif"], "canli_bulut")
        self.assertEqual(o[0]["oturum"], OTURUM)
        self.assertNotIn("metin", o[0])  # ham mesaj yazılmaz

    def test_yeni_mesaj_dokume_yazilmissa_onceki_tur_kullanilir(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []),
                        ("hayır, nedeni bu değil, private DNS eksik", "", []))
        self.istek("hayır, nedeni bu değil, private DNS eksik")
        self.assertEqual(len(self.olaylar()), 1)

    def test_kanitli_onceki_tur_olay_yok(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", ["Bash"]))
        self.istek("hayır, nedeni bu değil, private DNS eksik")
        self.assertEqual(self.olaylar(), [])

    def test_kisa_komut_olay_yok(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []))
        self.istek("hayır")
        self.assertEqual(self.olaylar(), [])

    def test_ortam_degiskeni_kapatir(self):
        os.environ["ORKESTRA_KANIT_KAPISI"] = "0"
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []))
        self.istek("hayır, nedeni bu değil, private DNS eksik")
        self.assertEqual(self.olaylar(), [])

    def test_alt_ajan_mesaji_olay_yazmaz(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []))
        self.istek("hayır, nedeni bu değil, private DNS eksik", agent_id="alt-1")
        self.assertEqual(self.olaylar(), [])

    def test_hata_sessiz(self):
        self.transkript(("azure erişimi neden yok?", "Neden IP izin listesi.", []))
        with mock.patch.object(KS, "ilk_cevap_itiraz", side_effect=RuntimeError("x")):
            ctx = self.istek("hayır, nedeni bu değil, private DNS eksik")
        self.assertEqual(self.olaylar(), [])
        self.assertTrue(ctx)


if __name__ == "__main__":
    unittest.main()
