"""ADR-0102, P-043: kullanıcı kabuğunun komut sözdizimi bağlama eklenir ve yanıttaki ihlal günlüğe yazılır
(scripts/kabuk_profili.py) ve hook bağlantıları. `python -m pytest -q plugins/orkestra/tests/test_kabuk_profili.py`
Metin standarttan okunur; testte sabitlenmez. Hepsi geçici projede koşar. Sınama kümesi yapaydır (mekanizma testi).
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
import kabuk_profili as K  # noqa: E402

ISARET = "ORKESTRA KABUK"
F = "```"

KOMUTLU = ["bu komutu çalıştır", "terminalde ne yazayım", "pushla", "PowerShell hatası aldım", "bash betiği ver", "paketi kur"]
KOMUTSUZ = ["tamam", "planı göster", "özet geç", "tabloyu sırala", "evet onaylıyorum", "rapor yaz"]


def _blok(etiket, govde, oncesi="Şunu çalıştır:"):
    return f"{oncesi}\n\n{F}{etiket}\n{govde}\n{F}\n"


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kabuk_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_KABUK_PROFILI", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ayar_yaz(self, d):
        with open(os.path.join(self.sd, K.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)


class Enjeksiyon(_Proje):
    def test_komut_anan_mesaj_tespiti(self):
        ayar = K.ayar_oku(self.sd)
        for m in KOMUTLU:
            self.assertTrue(K.komut_anan_mi(m, ayar), m)
        for m in KOMUTSUZ:
            self.assertFalse(K.komut_anan_mi(m, ayar), m)

    def test_ilk_mesajda_ekler_sonra_yalniz_komutta(self):
        self.ayar_yaz({"profil": "powershell5"})
        ilk = K.ana_ajan_metni("tamam", self.sd, "o1")
        self.assertTrue(ilk.startswith(ISARET))
        self.assertIn("&&", ilk)
        self.assertEqual(K.ana_ajan_metni("planı göster", self.sd, "o1"), "")
        self.assertTrue(K.ana_ajan_metni("bu komutu çalıştır", self.sd, "o1").startswith(ISARET))
        self.assertTrue(K.ana_ajan_metni("tamam", self.sd, "o2").startswith(ISARET))  # yeni oturum

    def test_bash_profili_bash_metni_verir(self):
        self.ayar_yaz({"profil": "bash"})
        self.assertIn("zsh", K.ana_ajan_metni("tamam", self.sd, "o3"))

    def test_kapali_ve_ortam_degiskeni(self):
        self.ayar_yaz({"mod": "kapali"})
        self.assertEqual(K.ana_ajan_metni("terminal", self.sd, "o4"), "")
        self.ayar_yaz({"mod": "etkin"})
        os.environ["ORKESTRA_KABUK_PROFILI"] = "0"
        self.assertEqual(K.ana_ajan_metni("terminal", self.sd, "o5"), "")

    def test_auto_profil_platforma_gore(self):
        with mock.patch.object(K.sys, "platform", "win32"):
            self.assertEqual(K.profil_sec({"profil": "auto"}), "powershell5")
        with mock.patch.object(K.sys, "platform", "linux"):
            self.assertEqual(K.profil_sec({"profil": "auto"}), "bash")


class StopTaramasi(_Proje):
    def setUp(self):
        super().setUp()
        self.ayar_yaz({"profil": "powershell5"})

    def test_stop_taramasi_yasak_kalibi_yakalar(self):
        y = _blok("powershell", "git add . && git commit -m x")
        self.assertTrue(K.yanit_ihlalleri(y, self.sd))
        self.assertTrue(K.yanit_ihlalleri(_blok("bash", "export A=1"), self.sd))

    def test_bash_profilinde_ve_noktalidan_gecer(self):
        self.assertEqual(K.yanit_ihlalleri(_blok("powershell", "git add .; git commit -m x"), self.sd), [])
        self.ayar_yaz({"profil": "bash"})
        self.assertEqual(K.yanit_ihlalleri(_blok("bash", "git add . && git commit -m x"), self.sd), [])
        self.assertTrue(K.yanit_ihlalleri(_blok("bash", "$env:A = 1"), self.sd))

    def test_alintilanan_ornek_atlanir(self):
        self.assertEqual(K.yanit_ihlalleri(_blok("powershell", "a && b", "Şu yazım yanlış, PS 5.1'de çalışmaz:"), self.sd), [])
        self.assertEqual(K.yanit_ihlalleri(_blok("powershell", "# a && b\nGet-Date"), self.sd), [])
        self.assertEqual(K.yanit_ihlalleri("`a && b` PS 5.1'de yoktur.", self.sd), [])
        self.assertEqual(K.yanit_ihlalleri(_blok("python", "x = a and b && c"), self.sd), [])

    def test_kapali_kip_taramaz(self):
        self.ayar_yaz({"profil": "powershell5", "stop_kip": "kapali"})
        self.assertEqual(K.yanit_ihlalleri(_blok("powershell", "a && b"), self.sd), [])


class HookBaglantisi(_Proje):
    def setUp(self):
        super().setUp()
        import hook
        self.hook = hook
        self.ayar_yaz({"profil": "powershell5"})

    def _cagir(self, fonk, inp):
        alinan = []

        def yakala(obj=None, kod=0):
            if obj is not None:
                alinan.append(obj)
            raise SystemExit(kod)

        with mock.patch.object(self.hook.L, "hook_cikti", yakala), \
                mock.patch.object(self.hook.L, "durum_dizini", lambda cwd=None, olustur=False: self.sd):
            try:
                fonk(inp)
            except SystemExit:
                pass
        return alinan

    def test_hook_user_prompt_submit_satir_ekler(self):
        alinan = self._cagir(self.hook.user_prompt_submit, {"session_id": "h1", "cwd": self.tmp, "prompt": "komutu ver"})
        self.assertTrue(alinan)
        self.assertIn(ISARET, json.dumps(alinan, ensure_ascii=False))

    def test_hook_stop_golge_gunluge_yazar(self):
        y = _blok("powershell", "git add . && git commit -m x")
        with mock.patch.object(self.hook, "_oturum_isi", lambda sd, oid: None):
            self.hook._kabuk_sozdizimi_yanit(self.sd, "h2", {"last_assistant_message": y})
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f if s.strip()]
        k = [s for s in satirlar if s.get("kural") == "kabuk_sozdizimi"]
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["mod"], "golge")
        self.assertEqual(k[0]["tur"], "kural_ihlal")

    def test_hook_stop_ihlalsiz_yazmaz(self):
        self.hook._kabuk_sozdizimi_yanit(self.sd, "h3", {"last_assistant_message": _blok("powershell", "a; b")})
        self.assertFalse(os.path.exists(os.path.join(self.sd, "gunluk.jsonl")))


if __name__ == "__main__":
    unittest.main()
