"""G-096: panel.py _kos --test panel.json'u yazmaz; varsayılan yol eskisi gibi yazar. Geçici HOME kullanılır."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(KOK, "scripts", "panel.py")


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def kos(home, *ekstra):
    env = dict(os.environ, HOME=home, USERPROFILE=home)
    port = bos_port()
    p = subprocess.Popen([sys.executable, PANEL, "_kos", str(port), *ekstra], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    durum = os.path.join(home, ".claude", "orkestra-panel", "panel.json")
    try:
        for _ in range(50):
            if p.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.3)
        return durum, os.path.exists(durum), port
    finally:
        p.kill()
        p.wait()


class KosDurum(unittest.TestCase):
    def test_test_bayragi_panel_json_yazmaz(self):
        with tempfile.TemporaryDirectory() as home:
            _, var, _ = kos(home, "--test")
            self.assertFalse(var)

    def test_test_bayragi_mevcut_dosyayi_degistirmez(self):
        with tempfile.TemporaryDirectory() as home:
            d = os.path.join(home, ".claude", "orkestra-panel")
            os.makedirs(d)
            yol = os.path.join(d, "panel.json")
            with open(yol, "w", encoding="utf-8") as f:
                f.write('{"port": 1}')
            kos(home, "--test")
            with open(yol, encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"port": 1}')

    def test_varsayilan_yol_panel_json_yazar(self):
        with tempfile.TemporaryDirectory() as home:
            durum, var, port = kos(home)
            self.assertTrue(var)
            with open(durum, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["port"], port)

    def test_bayrak_kod_yardim_metninde(self):
        with open(PANEL, encoding="utf-8") as f:
            self.assertIn("_kos <port> --test", f.read())


if __name__ == "__main__":
    unittest.main()
