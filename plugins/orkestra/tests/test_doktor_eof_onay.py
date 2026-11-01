"""Arka plan doktoru giriş yokken (EOF) B sınıfı onayı "hayır" sayar ve çökmez (Windows NUL isatty True)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import doktor  # noqa: E402


class EofOnayTest(unittest.TestCase):
    def test_eof_hayir_sayilir(self):
        yakalanan = {}

        def sahte_kos(baglam, duzelt=False, evet_b=False, onay=None):
            yakalanan["onay"] = onay
            return {"zorunlu_hata": [], "ozet": "", "kosu": "x", "surum": "x"}

        ap = doktor.argparse.ArgumentParser()
        doktor.argumanlar(ap)
        a = ap.parse_args(["--duzelt", "--arka-plan"])
        with mock.patch.object(doktor, "kos", sahte_kos), mock.patch.object(doktor, "metin", lambda s: ""), \
                mock.patch.object(sys, "stdin", mock.Mock(isatty=lambda: True)), mock.patch("builtins.input", side_effect=EOFError):
            doktor.calistir(a)


if __name__ == "__main__":
    unittest.main()
