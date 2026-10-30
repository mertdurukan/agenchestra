"""I-271: pahalı tur devir ipucu (scripts/devir_esigi.py + hook.stop / hook.user_prompt_submit bağlantısı).
`python -m pytest tests/test_devir_esigi.py -x -q` (plugins/orkestra kökünden). Geçici projede koşar; gerçek ~/.claude'a yazmaz.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir_esigi as DE  # noqa: E402
import hook  # noqa: E402
import niyet  # noqa: E402

OTURUM = "devir-esigi-oturum"


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_de_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_DEVIR_ESIGI"):
            os.environ.pop(k, None)
        nyol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", nyol),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(nyol)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def ayar_yaz(self, icerik):
        with open(os.path.join(self.sd, DE.PROJE_DOSYA), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))


class Esik(_Ortak):
    def test_k1_esik_ustu_turdan_sonra_ipucu_uretilir(self):
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 6_200_000))
        m = DE.ipucu_al(self.sd, OTURUM)
        self.assertIn("6.2 M", m)
        self.assertIn("/orkestra:devir", m)
        self.assertEqual(DE.ipucu_al(self.sd, OTURUM), "")  # bir kez tüketilir
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            self.assertIn("devir_esigi_olay", f.read())

    def test_k2_esik_altinda_ve_esitte_uretilmez(self):
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 4_999_999))
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 5_000_000))
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 0))
        self.assertEqual(DE.ipucu_al(self.sd, OTURUM), "")

    def test_k3_tekrar_araligi(self):
        self.ayar_yaz({"tekrar_aralik_tur": 3})
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))      # tur 1: uyarı
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))     # tur 2: aralık dolmadı
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))     # tur 3
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))      # tur 4: 4-1 >= 3
        self.assertTrue(DE.tur_kaydet(self.sd, "baska-oturum", 9_000_000))  # oturum başına ayrı sayaç

    def test_k3_varsayilan_aralik_20(self):
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))
        sonuc = [DE.tur_kaydet(self.sd, OTURUM, 9_000_000) for _ in range(20)]  # tur 2..21
        self.assertEqual(sonuc.count(True), 1)
        self.assertTrue(sonuc[-1])  # tur 21: 21-1 = 20

    def test_k4_ayardan_okunur(self):
        self.ayar_yaz({"esik_onbellek_okuma": 1000, "tekrar_aralik_tur": 7})
        a = DE.ayar_oku(self.sd)
        self.assertEqual((a["esik_onbellek_okuma"], a["tekrar_aralik_tur"]), (1000, 7))
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 1001))

    def test_k4_eklenti_varsayilani(self):
        a = DE.ayar_oku(self.sd)
        self.assertEqual((a["mod"], a["esik_onbellek_okuma"], a["tekrar_aralik_tur"]), ("ipucu", 5_000_000, 20))

    def test_k4_bozuk_ve_eksik_ayar_varsayilana_duser(self):
        self.ayar_yaz("{bozuk")
        self.assertEqual(DE.ayar_oku(self.sd)["esik_onbellek_okuma"], 5_000_000)
        self.ayar_yaz({"esik_onbellek_okuma": "abc", "tekrar_aralik_tur": -3, "mod": "garip"})
        a = DE.ayar_oku(self.sd)
        self.assertEqual((a["mod"], a["esik_onbellek_okuma"], a["tekrar_aralik_tur"]), ("ipucu", 5_000_000, 20))
        self.ayar_yaz([1, 2])
        self.assertEqual(DE.ayar_oku(self.sd)["tekrar_aralik_tur"], 20)
        with mock.patch.object(DE, "VARSAYILAN_YOL", os.path.join(self.proje, "yok.json")):
            os.remove(os.path.join(self.sd, DE.PROJE_DOSYA))
            self.assertEqual(DE.ayar_oku(self.sd), DE.VARSAYILAN)

    def test_kapali_mod_ve_ortam_degiskeni(self):
        self.ayar_yaz({"mod": "kapali"})
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))
        self.ayar_yaz({"mod": "ipucu"})
        os.environ["ORKESTRA_DEVIR_ESIGI"] = "0"
        self.assertFalse(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))
        self.assertEqual(DE.ipucu_al(self.sd, OTURUM), "")

    def test_bozuk_durum_dosyasi_kancayi_dusurmez(self):
        with open(os.path.join(self.sd, "oturumlar", f"{OTURUM}.devir_esigi.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertTrue(DE.tur_kaydet(self.sd, OTURUM, 9_000_000))
        self.assertIn("9.0 M", DE.ipucu_al(self.sd, OTURUM))


class HookBaglantisi(_Ortak):
    def calistir(self, fn, girdi):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                fn(g)
            except SystemExit:
                pass
        return buf.getvalue()

    def transkript(self, okuma):
        self.tr = os.path.join(self.proje, "tr.jsonl")
        satirlar = [{"type": "user", "timestamp": "2026-10-30T10:00:00Z", "message": {"role": "user", "content": "x"}}]
        for i, parca in enumerate((okuma // 2, okuma - okuma // 2)):  # çok çağrılı tur: toplam okunur
            satirlar.append({"type": "assistant", "timestamp": f"2026-10-30T10:00:0{i + 1}Z",
                             "message": {"id": f"m{i}", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "y"}],
                                         "usage": {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": parca}}})
        with open(self.tr, "w", encoding="utf-8", newline="\n") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def baglam(self):
        ham = self.calistir(hook.user_prompt_submit, {"prompt": "devam"})
        for satir in ham.strip().splitlines():
            try:
                h = json.loads(satir).get("hookSpecificOutput") or {}
            except ValueError:
                continue
            if h.get("additionalContext"):
                return h["additionalContext"]
        return ""

    def test_stop_pahali_tur_sonraki_mesaja_ipucu_ekler(self):
        self.transkript(7_000_000)
        self.calistir(hook.stop, {})
        ek = self.baglam()
        self.assertIn("Orkestra (pahalı tur)", ek)
        self.assertIn("7.0 M", ek)
        self.assertNotIn("pahalı tur", self.baglam())  # ikinci mesajda tekrar yok

    def test_stop_ucuz_tur_ipucu_eklemez(self):
        self.transkript(1_000_000)
        self.calistir(hook.stop, {})
        self.assertNotIn("pahalı tur", self.baglam())


if __name__ == "__main__":
    unittest.main()
