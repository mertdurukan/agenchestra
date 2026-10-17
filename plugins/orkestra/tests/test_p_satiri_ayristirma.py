"""I-057: gövdedeki "- P1 …" satırı plan maddesini bölmez; başlıksız eski biçim çalışmaya devam eder."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import is_sirasi as SR  # noqa: E402


class PSatiri(unittest.TestCase):
    def test_govdedeki_madde_isaretli_p_satiri_maddeyi_bolmez(self):
        m = "### P1 Bir\n\n**Ne:**\n\n- P1 testleri koşulur.\n\n**İddialar:** C1\n\n### P2 İki\n\n**İddialar:** C2\n"
        b = SR._p_bloklari(m)
        self.assertEqual(sorted(b), [1, 2])
        self.assertIn("**İddialar:** C1", b[1])

    def test_baslik_yoksa_madde_isaretli_bicim_gecerli(self):
        b = SR._p_bloklari("- P1 bir\n- P2 iki\n")
        self.assertEqual(sorted(b), [1, 2])


if __name__ == "__main__":
    unittest.main()
