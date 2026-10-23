"""niyet._hayalet: worktree sohbetinin transkripti <ana>--claude-worktrees-<ad> klasöründedir; hayalet sayılmaz.

`python -m unittest discover -s plugins/orkestra/tests -p test_niyet_hayalet_worktree.py -v`
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import niyet  # noqa: E402

PROJE = "C:/proje_deneme"


class HayaletWorktreeTesti(unittest.TestCase):
    def _hayalet(self, klasor_adi, oturum="abc"):
        with tempfile.TemporaryDirectory() as kok:
            ana = os.path.join(kok, "C--proje-deneme")
            if klasor_adi:
                os.makedirs(os.path.join(kok, klasor_adi))
                open(os.path.join(kok, klasor_adi, oturum + ".jsonl"), "w").close()
            with mock.patch.object(niyet.L, "proje_oturum_dizini", return_value=ana):
                return niyet._hayalet(oturum, PROJE, {})

    def test_ana_klasorde_transkript_hayalet_degil(self):
        self.assertFalse(self._hayalet("C--proje-deneme"))

    def test_worktree_klasorunde_transkript_hayalet_degil(self):
        self.assertFalse(self._hayalet("C--proje-deneme--claude-worktrees-is-ab12"))

    def test_hicbir_klasorde_transkript_yoksa_hayalet(self):
        self.assertTrue(self._hayalet(None))

    def test_baska_projenin_klasoru_sayilmaz(self):
        self.assertTrue(self._hayalet("C--proje-deneme2--claude-worktrees-x"))


if __name__ == "__main__":
    unittest.main()
