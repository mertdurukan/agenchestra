"""is_kaydi: id üretimi, sıralama, klasör şablonu, tekrarsızlık, todo sayımı, eşzamanlılık."""
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as K  # noqa: E402


class IsKaydiTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.sd = os.path.join(self._t.name, "orkestra")
        os.makedirs(self.sd)
        self.kok = os.path.join(self._t.name, "isler")

    def test_ilk_id(self):
        self.assertEqual(K.yeni_is_id(self.sd), "I-001")
        self.assertEqual(K.yeni_is_id(self.sd), "I-002")

    def test_999dan_sonra_1000(self):
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"sayac": 999, "isler": {}}, f)
        self.assertEqual(K.yeni_is_id(self.sd), "I-1000")

    def test_sayisal_siralama(self):
        self.assertEqual(K.is_sirala(["I-1000", "I-999", "I-002"]), ["I-002", "I-999", "I-1000"])
        self.assertEqual(K.is_no("I-1000"), 1000)

    def test_is_ac_mevcut_dosyalari_ezmez(self):
        kl = os.path.join(self.kok, "a")
        os.makedirs(kl)
        for ad in ("plan.md", "todo.md", "oturumlar.md"):
            with open(os.path.join(kl, ad), "w", encoding="utf-8") as f:
                f.write("ÖZEL " + ad)
        K.is_ac(self.sd, "Baslik", kl, ["x"])
        for ad in ("plan.md", "todo.md", "oturumlar.md"):
            with open(os.path.join(kl, ad), encoding="utf-8") as f:
                self.assertEqual(f.read(), "ÖZEL " + ad)

    def test_is_ac_sablon_ve_kayit(self):
        kl = os.path.join(self.kok, "b")
        k = K.is_ac(self.sd, "Başlık", kl, ["e1"])
        self.assertEqual(k["id"], "I-001")
        for ad in ("plan.md", "todo.md", "oturumlar.md", "is.json"):
            self.assertTrue(os.path.exists(os.path.join(kl, ad)))
        self.assertEqual(K.is_al(self.sd, "I-001")["etiketler"], ["e1"])
        self.assertIsNone(K.is_al(self.sd, "I-009"))

    def test_liste_ve_durum(self):
        for i in range(3):
            K.is_ac(self.sd, f"t{i}", os.path.join(self.kok, str(i)))
        K.is_durum(self.sd, "I-002", "kapandi")
        self.assertEqual([x["id"] for x in K.is_liste(self.sd)], ["I-001", "I-002", "I-003"])
        self.assertEqual([x["id"] for x in K.is_liste(self.sd, "kapandi")], ["I-002"])
        self.assertEqual(K.is_al(self.sd, "I-002")["durum"], "kapandi")
        with self.assertRaises(ValueError):
            K.is_durum(self.sd, "I-001", "yanlis")

    def test_kart_ve_oturum_tekrarsiz(self):
        K.is_ac(self.sd, "t", os.path.join(self.kok, "c"))
        for _ in range(2):
            K.is_kart_ekle(self.sd, "I-001", "G-001")
            K.is_oturum_bagla(self.sd, "I-001", "oturum-1")
        k = K.is_al(self.sd, "I-001")
        self.assertEqual(k["kartlar"], ["G-001"])
        self.assertEqual([o["oturum"] for o in k["oturumlar"]], ["oturum-1"])
        self.assertIn("baglanma", k["oturumlar"][0])

    def test_todo_ozet(self):
        kl = os.path.join(self.kok, "d")
        os.makedirs(kl)
        with open(os.path.join(kl, "todo.md"), "w", encoding="utf-8") as f:
            f.write("# T\n- [x] bir\n- [X] iki\n- [ ] üç\n  - [ ] dört\nnot\n")
        self.assertEqual(K.todo_ozet(kl), {"toplam": 4, "biten": 2, "acik_maddeler": ["üç", "dört"]})
        self.assertEqual(K.todo_ozet(os.path.join(self.kok, "yok"))["toplam"], 0)

    def test_replace_gecici_izin_hatasinda_yeniden_dener(self):
        gercek = os.replace
        cagri = []

        def sahte(a, b):
            cagri.append(1)
            if len(cagri) <= 2:
                raise PermissionError(13, "Erişim engellendi")
            return gercek(a, b)

        with mock.patch.object(K.os, "replace", sahte), mock.patch.object(K.time, "sleep"):
            self.assertEqual(K.yeni_is_id(self.sd), "I-001")
        self.assertEqual(len(cagri), 3)
        self.assertEqual([a for a in os.listdir(self.sd) if a.startswith(".tmp_")], [])
        self.assertEqual(K.yeni_is_id(self.sd), "I-002")

    def test_replace_kalici_hatada_tmp_birakmaz(self):
        def sahte(a, b):
            raise PermissionError(13, "Erişim engellendi")

        with mock.patch.object(K.os, "replace", sahte), mock.patch.object(K.time, "sleep"):
            with self.assertRaises(PermissionError):
                K.yeni_is_id(self.sd)
        self.assertEqual([a for a in os.listdir(self.sd) if a.startswith(".tmp_")], [])

    def test_eszamanli_id_cakismaz(self):
        sonuc, hata = [], []

        def calis():
            try:
                for _ in range(10):
                    sonuc.append(K.yeni_is_id(self.sd))
            except Exception as e:  # noqa: BLE001
                hata.append(e)

        th = [threading.Thread(target=calis) for _ in range(6)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        self.assertEqual(hata, [])
        self.assertEqual(len(sonuc), 60)
        self.assertEqual(len(set(sonuc)), 60)


    def _agac(self):
        out = []
        for kok, dizinler, dosyalar in os.walk(self._t.name):
            out += [os.path.join(kok, x) for x in dizinler + dosyalar]
        return sorted(out)

    def test_onar_kuru_kosu_bos_sd_hicbir_sey_olusturmaz(self):
        once = self._agac()
        r = K.onar(self.sd, [], uygula=False)
        self.assertFalse(r["yazildi"])
        self.assertEqual(self._agac(), once)
        self.assertEqual(os.listdir(self.sd), [])

    def test_onar_kuru_kosu_dolu_sd_dosya_dizin_degistirmez(self):
        K.is_ac(self.sd, "a", os.path.join(self.kok, "a"))
        K.is_ac(self.sd, "b", os.path.join(self.kok, "b"))
        os.remove(os.path.join(self.sd, "isler.json"))
        once = self._agac()
        K.onar(self.sd, [os.path.join(self.kok, "a")], uygula=False)
        self.assertEqual(self._agac(), once)


if __name__ == "__main__":
    unittest.main()
