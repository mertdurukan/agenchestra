"""hook.py onay bağlamı: SessionStart ve UserPromptSubmit additionalContext'ine eklenir; onay hatası hook'u düşürmez."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import onay  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

OTURUM = "hook-onay-oturum"


class HookOnay(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_hookonay_")
        self.ev = tempfile.mkdtemp(prefix="ork_ev_")  # niyet/panel dosyaları gerçek ev dizinine yazılmasın
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def kos(self, args, stdin=None):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1", HOME=self.ev, USERPROFILE=self.ev)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos(args, cwd=self.proje, env=env, input=stdin)

    def hook(self, olay, girdi=None):
        g = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": olay}
        g.update(girdi or {})
        r = self.kos([HOOK, olay], stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def baglam(self, cikti):
        return (cikti.get("hookSpecificOutput") or {}).get("additionalContext", "")

    def test_session_start_onay_baglami(self):
        a = onay.iste(self.sd, "Perspektif önerisi", "m", tur="perspektif")
        onay.karar_ver(self.sd, a["id"], "onay")
        onay.iste(self.sd, "Bekleyen", "m")
        m = self.baglam(self.hook("SessionStart"))
        self.assertIn("Orkestra bu projede açık", m)  # mevcut bağlam korunur
        self.assertIn(a["id"], m)
        self.assertIn("/orkestra:onay ile uygula", m)
        self.assertIn("1 karar bekliyor", m)

    def test_user_prompt_submit_onay_baglami(self):
        k = onay.iste(self.sd, "Seç", "m", secenekler=["A", "B"], oturum=OTURUM)
        onay.karar_ver(self.sd, k["id"], "onay", secim="B")
        m = self.baglam(self.hook("UserPromptSubmit", {"prompt": "devam et"}))
        self.assertIn(f"{k['id']} kararın: B", m)
        # ikinci istekte tekrarlanmaz
        self.assertNotIn("kararın", self.baglam(self.hook("UserPromptSubmit", {"prompt": "tamam"})))

    def test_session_start_sonrasi_gecmis_user_prompt_submit_te_dokulmez(self):
        a = onay.iste(self.sd, "Eski", "m", tur="perspektif")
        onay.karar_ver(self.sd, a["id"], "onay")
        self.assertIn(a["id"], self.baglam(self.hook("SessionStart")))
        # karar bildirimi dökülmez; bekleyen kalmadığı için yalnız çalıştırma yönergesi gelir
        m = self.baglam(self.hook("UserPromptSubmit", {"prompt": "merhaba"}))
        self.assertNotIn("Panel kararları", m)
        self.assertIn("orkestra:onay", m)

    def test_onay_hatasi_hooku_dusurmez(self):
        # Bozuk şekilli kayıt: onay.baglam_metni KeyError atar
        os.makedirs(os.path.join(self.sd, "onaylar"), exist_ok=True)
        with open(os.path.join(self.sd, "onaylar", "O-001.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "O-001", "durum": "onaylandi", "karar": {"zaman": "2099-01-01T00:00:00", "sonuc": "onay"}}, f)
        with self.assertRaises(KeyError):
            onay.baglam_metni(self.sd, OTURUM, "SessionStart")
        m = self.baglam(self.hook("SessionStart"))
        self.assertIn("Orkestra bu projede açık", m)
        self.assertNotIn("O-001", m)
        self.hook("UserPromptSubmit", {"prompt": "selam"})  # geçerli çıktı, sıfır çıkış kodu

    def test_ozet_onaylar_anahtari(self):
        import ozet
        onay.iste(self.sd, "Bekleyen", "m")
        o = ozet.olustur(self.sd, self.proje)
        self.assertIn("onaylar", o)
        self.assertEqual(o["onaylar"]["bekliyor"], 1)

    def test_session_start_uzun_baglamda_onay_yonlendirmesi_kesilmez(self):
        import contextlib
        import io
        from unittest import mock
        import hook
        import ork_lib as L
        import perspektif
        for i in range(8):
            r = self.kos([CLI, "kart", "yeni", "--baslik", f"Çok uzun başlıklı açık kart numara {i} " * 3, "--basamak", "T1", "--sinif", "belge",
                          "--kabul", "x", "--yazma", "docs/**"])
            self.assertEqual(r.returncode, 0, r.stderr)
        for i in range(40):
            k = onay.iste(self.sd, "Çok uzun bir başlık " * 10, "m", tur="perspektif")
            onay.karar_ver(self.sd, k["id"], "onay")
        om = onay.baglam_metni(self.sd, OTURUM, "SessionStart")
        self.assertGreater(len(om), 800)
        bayat = {"farkli": 12, "kaynakta_commitsiz": True, "kaynak": "x" * 300}
        rapor = {"okunmamis_rapor": "ruya_20261013_1500.md" * 3, "zamani_geldi": False, "calisiyor": False}
        cikti = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(L, "bayatlik", return_value=bayat),                 mock.patch.object(perspektif, "durum", return_value=rapor), contextlib.redirect_stdout(cikti):
            with self.assertRaises(SystemExit):
                hook.session_start({"session_id": OTURUM, "cwd": self.proje})
        m = json.loads(cikti.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(m), 1800)
        self.assertTrue(m.endswith(om), "onay metni bütün kalmalı")
        self.assertIn("/orkestra:onay ile uygula", m)
        self.assertIn("Orkestra bu projede açık", m)


if __name__ == "__main__":
    unittest.main()
