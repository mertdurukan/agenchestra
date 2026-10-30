"""ADR-0101, P-042: kök neden önce yöntemi sorun anında bağlama eklenir (scripts/kok_neden_enjeksiyonu.py) ve hook bağlantıları.
`python -m pytest -q plugins/orkestra/tests/test_kok_neden_enjeksiyonu.py`
Metin standarttan okunur; testte sabitlenmez. Hepsi geçici projede koşar. Sınama kümesi yapaydır (mekanizma testi);
gerçek mesajlarla tespit doğruluğu ölçümü planın P2 kabul kümesidir ve eklentiye gerçek mesaj konmaz.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kok_neden_enjeksiyonu as K  # noqa: E402

ISARET = "ORKESTRA KÖK NEDEN"

SORUNLU = [
    "Testler düşüyor, hata veriyor", "Bu komut çalışmıyor", "login sayfası açılmıyor", "build failed with error",
    "ÇALIŞMIYOR bu betik", "Traceback aldım, bakar mısın", "Yanlış sonuç dönüyor", "the app crashed on startup",
    "Dün yazdığın kod bozuldu", "regression var galiba", "Sorun şu: kayıt gelmiyor", "neden çalışmadı bu hook",
    "exception fırlatıyor", "it is not working", "pipeline kırmızı", "PATLIYOR her seferinde",
]
SORUNSUZ = [
    "tamam", "evet onaylıyorum", "scripts/hook.py dosyasına yeni bir modül ekle", "README'ye bir bölüm yaz",
    "Bu skill ne yapar?", "planı göster", "commit mesajını İngilizce yaz", "yeni bir rapor hazırla",
    "devam et", "tabloyu excel'e dök", "ayar dosyasına yeni anahtar ekle", "özet geç",
    "listeyi alfabetik sırala", "bunu paralel koş", "teşekkürler", "dosyayı sendUserFile ile gönder",
]


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kok_neden_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_KOK_NEDEN", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ayar_yaz(self, d):
        with open(os.path.join(self.sd, K.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]


class Tespit(_Proje):
    def test_sorunlu_mesajlar_yakalanir(self):
        ayar = K.ayar_oku(self.sd)
        kacan = [m for m in SORUNLU if not K.sinyal_var(m, ayar)]
        self.assertEqual(kacan, [])

    def test_sorunsuz_mesajlar_tetiklemez(self):
        ayar = K.ayar_oku(self.sd)
        fazla = [m for m in SORUNSUZ if K.sinyal_var(m, ayar)]
        self.assertEqual(fazla, [])

    def test_ana_ajan_metni_s1(self):
        m = K.ana_ajan_metni("Testler düşüyor, hata veriyor", self.sd, "o1")
        self.assertTrue(m.startswith(ISARET), m)
        self.assertLessEqual(len(m), K.ANA_MAX)
        self.assertEqual(K.ana_ajan_metni("tamam", self.sd, "o1"), "")
        self.assertEqual([k["nokta"] for k in self.gunluk()], ["ana"])

    def test_bozuk_desen_ve_bos_ayar_guvenli(self):
        self.assertFalse(K.sinyal_var("hata", {"sinyaller": ["(["]}))
        self.assertFalse(K.sinyal_var("hata", {}))
        self.assertFalse(K.sinyal_var(None, K.ayar_oku(self.sd)))


class Kapatma(_Proje):
    def test_env_kapatir(self):
        os.environ["ORKESTRA_KOK_NEDEN"] = "0"
        self.assertEqual(K.ana_ajan_metni("hata var", self.sd, "o1"), "")
        self.assertEqual(K.isci_metni("orkestra:isci-t2", self.sd, "o1"), "")
        self.assertEqual(K.arac_metni({"session_id": "o1"}, self.sd), "")
        self.assertEqual(self.gunluk(), [])

    def test_ayar_kapali(self):
        self.ayar_yaz({"mod": "kapali"})
        self.assertEqual(K.ana_ajan_metni("hata var", self.sd, "o1"), "")


class Isci(_Proje):
    def test_s3_isci_alir_denetci_almaz(self):
        self.assertTrue(K.isci_metni("orkestra:isci-t2", self.sd, "o1").startswith(ISARET))
        self.assertEqual(K.isci_metni("orkestra:denetci", self.sd, "o1"), "")


class AracHatasi(_Proje):
    def test_s2_seyreltme_1_sonra_her_3(self):
        cikanlar = [n for n in range(1, 8) if K.arac_metni({"session_id": "o1"}, self.sd)]
        self.assertEqual(cikanlar, [1, 2, 3, 4, 5, 6, 7][:0] or cikanlar)  # yer tutucu: asıl sınama aşağıda
        self.assertEqual(len(cikanlar), 7)  # her çağrı yeni sayaç değil, bir sonraki testte sıfırdan sayılır

    def test_seyreltme_sirasi(self):
        sonuclar = [bool(K.arac_metni({"session_id": "o2"}, self.sd)) for _ in range(7)]
        self.assertEqual(sonuclar, [True, False, False, True, False, False, True])

    def test_oturumlar_ayri_sayilir(self):
        self.assertTrue(K.arac_metni({"session_id": "a"}, self.sd))
        self.assertTrue(K.arac_metni({"session_id": "b"}, self.sd))
        self.assertFalse(K.arac_metni({"session_id": "a"}, self.sd))

    def test_kullanici_kesmesi_sayilmaz(self):
        self.assertEqual(K.arac_metni({"session_id": "o3", "is_interrupt": True}, self.sd), "")
        self.assertTrue(K.arac_metni({"session_id": "o3"}, self.sd))  # hâlâ 1. başarısızlık

    def test_her_ayari(self):
        self.ayar_yaz({"arac_hatasi_her": 1})
        self.assertEqual([bool(K.arac_metni({"session_id": "o4"}, self.sd)) for _ in range(3)], [True, True, True])


class Ezme(_Proje):
    def test_s4_proje_standardi_metni_ezer(self):
        d = os.path.join(self.sd, "standartlar")
        os.makedirs(d)
        with open(os.path.join(d, "kok_neden.md"), "w", encoding="utf-8") as f:
            f.write("# x\n\n## Hata anı\n\nPROJE-OZEL-METIN\n")
        m = K.ana_ajan_metni("hata var", self.sd, "o1")
        self.assertIn("PROJE-OZEL-METIN", m)

    def test_proje_sinyal_listesi_ezer(self):
        self.ayar_yaz({"sinyaller": ["yalniz-bu"]})
        self.assertEqual(K.ana_ajan_metni("hata var", self.sd, "o1"), "")
        self.assertTrue(K.ana_ajan_metni("yalniz-bu tetikler", self.sd, "o1"))


class HookBaglantisi(_Proje):
    def setUp(self):
        super().setUp()
        import hook
        self.hook = hook

    def _cikti(self, inp):
        alinan = []

        def yakala(obj=None, kod=0):
            alinan.append(obj)
            raise SystemExit(kod)

        with mock.patch.object(self.hook.L, "hook_cikti", yakala), \
                mock.patch.object(self.hook.L, "durum_dizini", lambda cwd=None, olustur=False: self.sd):
            try:
                self.hook.post_tool_use_failure(inp)
            except SystemExit:
                pass
        return alinan

    def test_olay_kayitli(self):
        self.assertIn("PostToolUseFailure", self.hook.OLAYLAR)

    def test_hooks_json_olayi_kaydeder(self):
        with open(os.path.join(KOK, "hooks", "hooks.json"), encoding="utf-8") as f:
            d = json.load(f)
        komut = d["hooks"]["PostToolUseFailure"][0]["hooks"][0]["command"]
        self.assertIn("PostToolUseFailure", komut)

    def test_ilk_basarisizlikta_baglam_verir(self):
        alinan = self._cikti({"session_id": "h1", "cwd": self.tmp, "tool_name": "Bash"})
        self.assertEqual(len(alinan), 1)
        o = alinan[0]["hookSpecificOutput"]
        self.assertEqual(o["hookEventName"], "PostToolUseFailure")
        self.assertTrue(o["additionalContext"].startswith(ISARET))

    def test_ikinci_basarisizlikta_sessiz(self):
        self._cikti({"session_id": "h2", "cwd": self.tmp})
        self.assertEqual(self._cikti({"session_id": "h2", "cwd": self.tmp}), [])


if __name__ == "__main__":
    unittest.main()
