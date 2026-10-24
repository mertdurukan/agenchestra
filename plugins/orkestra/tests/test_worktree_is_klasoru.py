"""I-220: worktree oturumunda hook iş klasörünü oturum kökünde açar, onay kapısı aynı yolu kabul eder.

Gerçek kombinasyon: `CLAUDE_PROJECT_DIR` = ana ağaç, hook girdisindeki `cwd` = oturum worktree'si (tests/worktree_ortam.py).
`python -m unittest tests.test_worktree_is_klasoru` (plugin kökünden)

- K1 çözücü: açık `cwd` ortam değişkeninden önce gelir; argümansız çağrı eski davranışı korur.
- K2 hook: `cwd` _yonlendirme_ipucu -> _otomatik_yonlendirme -> _otomatik_is_ac zincirinde iletilir; klasör worktree altında açılır.
- K3 onay kapısı: ana ağaç kaydının worktree'deki eşdeğer yoluna izin verir, ilgisiz yola ve is.json'a vermez.
"""
import os
import sys
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import is_onay  # noqa: E402
import ork_lib as L  # noqa: E402
from worktree_ortam import WorktreeOrtamMixin, n  # noqa: E402


class CozucuOncelik(WorktreeOrtamMixin, unittest.TestCase):
    def setUp(self):
        self.kur_worktree_ortami("ana")

    def tearDown(self):
        self.temizle_worktree_ortami()

    def test_acik_cwd_ortami_ezer(self):
        self.assertEqual(n(L.oturum_koku(self.wt)), n(self.wt))
        self.assertEqual(n(L.baglanti_koku(self.ana, self.wt)), n(self.wt))

    def test_alt_klasor_cwd_worktree_kokune_cozulur(self):
        alt = os.path.join(self.wt, "derin", "klasor")
        os.makedirs(alt)
        self.assertEqual(n(L.baglanti_koku(self.ana, alt)), n(self.wt))

    def test_cwd_ana_agacsa_ana_agac_kalir(self):
        self.assertEqual(n(L.baglanti_koku(self.ana, self.ana)), n(self.ana))

    def test_argumansiz_cagri_eski_davranis(self):  # ortam ana ağaç, cwd argümanı yok -> ana ağaç
        self.assertEqual(n(L.baglanti_koku(self.ana)), n(self.ana))

    def test_ortam_yokken_cwd_worktree_kokune_cozulur(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.assertEqual(n(L.baglanti_koku(self.ana, self.wt)), n(self.wt))

    def test_ortam_worktree_iken_degismez(self):
        os.environ["CLAUDE_PROJECT_DIR"] = self.wt
        self.assertEqual(n(L.baglanti_koku(self.ana, self.wt)), n(self.wt))
        self.assertEqual(n(L.baglanti_koku(self.ana)), n(self.wt))


class HookIsKlasoru(WorktreeOrtamMixin, unittest.TestCase):
    OTURUM = "wto-oturum-1"

    def setUp(self):
        self.kur_worktree_ortami("ana")

    def tearDown(self):
        self.temizle_worktree_ortami()

    def _acik_klasor(self):
        liste = is_kaydi.is_liste(self.sd, "acik")
        self.assertEqual(len(liste), 1, liste)
        return liste[0]["klasor"]

    def test_is_klasoru_worktree_altinda_acilir(self):
        hook._otomatik_is_ac(self.sd, self.OTURUM, "yeni bir ozellik ekle", proje=self.ana, cwd=self.wt)
        klasor = self._acik_klasor()
        self.assertTrue(n(klasor).startswith(n(os.path.join(self.wt, "Is")) + "/"), klasor)

    def test_cwd_verilmezse_eski_davranis_ana_agac(self):
        hook._otomatik_is_ac(self.sd, self.OTURUM, "yeni bir ozellik ekle", proje=self.ana)
        klasor = self._acik_klasor()
        self.assertTrue(n(klasor).startswith(n(os.path.join(self.ana, "Is")) + "/"), klasor)

    def test_yonlendirme_ipucu_cwd_iletir(self):
        with mock.patch.object(hook, "_otomatik_yonlendirme", return_value="x") as m:
            hook._yonlendirme_ipucu(self.sd, self.OTURUM, "istek", self.ana, cwd=self.wt)
        self.assertEqual(m.call_args.kwargs.get("cwd"), self.wt)

    def test_otomatik_yonlendirme_cwd_iletir(self):
        import is_yonlendirme
        import soru_sinif
        with mock.patch.object(soru_sinif, "tur", return_value="gorev"), \
                mock.patch.object(is_yonlendirme, "karar", return_value=("ac", None)), \
                mock.patch.object(hook, "_otomatik_is_ac", return_value="x") as m:
            hook._otomatik_yonlendirme(self.sd, self.OTURUM, "yeni bir ozellik ekle", self.ana, cwd=self.wt)
        self.assertEqual(m.call_args.kwargs.get("cwd"), self.wt)


class OnayKapisiEsdeger(WorktreeOrtamMixin, unittest.TestCase):
    def setUp(self):
        self.kur_worktree_ortami("ana")  # ortam ana ağaç: kapı worktree'yi ortamdan değil yoldan anlamalı
        self.kayit = {"id": "I-900", "klasor": os.path.join(self.ana, "Is", "001-ornek")}

    def tearDown(self):
        self.temizle_worktree_ortami()

    def test_worktree_esdeger_yola_izin(self):
        tam = os.path.join(self.wt, "Is", "001-ornek", "plan.md")
        self.assertEqual(is_onay.yazma_engeli(self.kayit, self.ana, tam), "")

    def test_ana_agac_kayit_yoluna_izin_degismez(self):
        tam = os.path.join(self.ana, "Is", "001-ornek", "plan.md")
        self.assertEqual(is_onay.yazma_engeli(self.kayit, self.ana, tam), "")

    def test_worktree_ilgisiz_yola_izin_yok(self):
        tam = os.path.join(self.wt, "baska", "plan.md")
        self.assertIn("P-016", is_onay.yazma_engeli(self.kayit, self.ana, tam))

    def test_worktree_baska_is_klasorune_izin_yok(self):
        tam = os.path.join(self.wt, "Is", "002-baska", "plan.md")
        self.assertIn("P-016", is_onay.yazma_engeli(self.kayit, self.ana, tam))

    def test_worktree_esdeger_is_json_yazilmaz(self):
        tam = os.path.join(self.wt, "Is", "001-ornek", "is.json")
        self.assertIn("is.json", is_onay.yazma_engeli(self.kayit, self.ana, tam))

    def test_worktree_disi_klasor_adi_benzeri_yola_izin_yok(self):
        tam = os.path.join(self.ana, ".claude", "worktrees-baska", "Is", "001-ornek", "plan.md")
        self.assertIn("P-016", is_onay.yazma_engeli(self.kayit, self.ana, tam))


if __name__ == "__main__":
    unittest.main()
