"""İş todo yazma: is_kaydi.todo_ekle / todo_bitir ve `orkestra is todo <id> --ekle/--bitti/--not` (G-042)."""
import datetime
import os
import subprocess
import sys
import tempfile
import threading
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as K  # noqa: E402


def oku(yol):
    with open(yol, encoding="utf-8", newline="") as f:
        return f.read()


def yaz(yol, metin):
    with open(yol, "w", encoding="utf-8", newline="") as f:
        f.write(metin)


class TodoFonksiyon(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.k = self._t.name
        self.todo = os.path.join(self.k, "todo.md")

    def test_ekle_dosya_yoksa_baslikla_olusturur(self):
        r = K.todo_ekle(self.k, "ilk madde")
        self.assertEqual(r, "ilk madde")
        self.assertEqual(oku(self.todo), "# Yapılacaklar\n\n- [ ] ilk madde\n")

    def test_ekle_sona_ekler_mevcutu_korur(self):
        yaz(self.todo, "# t\n- [x] a\n- [ ] b\n")
        K.todo_ekle(self.k, "c")
        self.assertEqual(oku(self.todo), "# t\n- [x] a\n- [ ] b\n- [ ] c\n")

    def test_ekle_son_satir_newlinesiz_ise_once_newline(self):
        yaz(self.todo, "# t\n- [ ] b")
        K.todo_ekle(self.k, "c")
        self.assertEqual(oku(self.todo), "# t\n- [ ] b\n- [ ] c\n")

    def test_ekle_ozete_yansir(self):
        yaz(self.todo, "- [x] a\n- [ ] b\n")
        K.todo_ekle(self.k, "yeni")
        o = K.todo_ozet(self.k)
        self.assertEqual(o["toplam"], 3)
        self.assertEqual(o["acik_maddeler"], ["b", "yeni"])

    def test_bitir_sayi_acik_maddeler_icinde_n_inci(self):
        yaz(self.todo, "- [x] eski\n- [ ] bir\n- [ ] iki\n- [ ] üç\n")
        r = K.todo_bitir(self.k, "2")
        self.assertEqual(r, "iki")
        self.assertEqual(oku(self.todo), "- [x] eski\n- [ ] bir\n- [x] iki\n- [ ] üç\n")

    def test_bitir_sayi_aralik_disi_hata_dosya_degismez(self):
        ilk = "- [ ] bir\n- [ ] iki\n"
        yaz(self.todo, ilk)
        for s in ("0", "3", "99"):
            with self.assertRaises(ValueError):
                K.todo_bitir(self.k, s)
        self.assertEqual(oku(self.todo), ilk)

    def test_bitir_alt_dize_buyuk_kucuk_duyarsiz_tek_eslesme(self):
        yaz(self.todo, "- [ ] Testleri YAZ\n- [ ] dokümanı güncelle\n")
        r = K.todo_bitir(self.k, "testleri yaz")
        self.assertEqual(r, "Testleri YAZ")
        self.assertEqual(oku(self.todo), "- [x] Testleri YAZ\n- [ ] dokümanı güncelle\n")

    def test_bitir_sifir_eslesme_valueerror(self):
        ilk = "- [ ] a\n- [ ] b\n"
        yaz(self.todo, ilk)
        with self.assertRaises(ValueError):
            K.todo_bitir(self.k, "yok")
        self.assertEqual(oku(self.todo), ilk)

    def test_bitir_cok_eslesme_valueerror_adaylar_mesajda(self):
        ilk = "- [ ] test bir\n- [ ] test iki\n- [ ] başka\n"
        yaz(self.todo, ilk)
        with self.assertRaises(ValueError) as c:
            K.todo_bitir(self.k, "test")
        self.assertIn("test bir", str(c.exception))
        self.assertIn("test iki", str(c.exception))
        self.assertEqual(oku(self.todo), ilk)

    def test_bitir_yalniz_acik_maddelerde_arar(self):
        yaz(self.todo, "- [x] kritik iş\n- [ ] diğer\n")
        with self.assertRaises(ValueError):
            K.todo_bitir(self.k, "kritik")

    def test_bitir_not_bugunun_tarihiyle_eklenir(self):
        yaz(self.todo, "- [ ] a\n")
        K.todo_bitir(self.k, "1", not_="tamam oldu")
        bugun = datetime.date.today().isoformat()
        self.assertEqual(oku(self.todo), f"- [x] a — {bugun}: tamam oldu\n")

    def test_bitir_girinti_alt_satir_ve_isaret_korunur(self):
        yaz(self.todo, "# t\n- [ ] ust\n  - [ ] iç madde\n    ayrıntı satırı\n* [ ] yıldızlı\n")
        r = K.todo_bitir(self.k, "iç madde", not_="ok")
        self.assertEqual(r.split(" — ")[0], "iç madde")
        bugun = datetime.date.today().isoformat()
        self.assertEqual(oku(self.todo),
                         f"# t\n- [ ] ust\n  - [x] iç madde — {bugun}: ok\n    ayrıntı satırı\n* [ ] yıldızlı\n")
        K.todo_bitir(self.k, "yıldızlı")
        self.assertIn("* [x] yıldızlı\n", oku(self.todo))

    def test_bitir_not_olmadan_satir_sonu_degismez(self):
        yaz(self.todo, "- [ ] a\n- [ ] b\n")
        K.todo_bitir(self.k, "b")
        self.assertEqual(oku(self.todo), "- [ ] a\n- [x] b\n")

    def test_bitir_dosya_yoksa_hata(self):
        with self.assertRaises(ValueError):
            K.todo_bitir(self.k, "1")

    def test_ekle_is_parcacigi_kilit_40_madde(self):
        def is_(p):
            for n in range(20):
                K.todo_ekle(self.k, f"{p}-{n}")
        ts = [threading.Thread(target=is_, args=(p,)) for p in ("a", "b")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        satirlar = oku(self.todo).splitlines()
        madde = [s for s in satirlar if s.startswith("- [ ] ")]
        self.assertEqual(len(madde), 40)
        self.assertEqual(len(set(madde)), 40)

    def test_ekle_iki_surec_kilit_40_madde(self):
        kod = ("import sys; sys.path.insert(0, sys.argv[1]); import is_kaydi as K\n"
               "for n in range(20): K.todo_ekle(sys.argv[2], sys.argv[3] + '-' + str(n))\n")
        scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
        env = dict(os.environ, PYTHONUTF8="1")
        ps = [subprocess.Popen([sys.executable, "-c", kod, scripts, self.k, p], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for p in ("x", "y")]
        for p in ps:
            _, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err)
        madde = [s for s in oku(self.todo).splitlines() if s.startswith("- [ ] ")]
        self.assertEqual(len(madde), 40)
        self.assertEqual(len(set(madde)), 40)


class TodoCli(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def ac(self, alt="is1"):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", "Todo işi", "--klasor", klasor, "--etiket", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), os.path.join(klasor, "todo.md")

    def test_ekle_ve_listede_gorunur_toplam_artar(self):
        i, todo = self.ac()
        yaz(todo, "# t\n- [x] a\n- [ ] b\n")
        once = self.cli("is", "todo", i).stdout
        self.assertIn("todo 1/2", once)
        r = self.cli("is", "todo", i, "--ekle", "X maddesi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("todo 1/3", r.stdout)
        self.assertTrue(oku(todo).endswith("- [ ] X maddesi\n"))
        sonra = self.cli("is", "todo", i).stdout
        self.assertIn("todo 1/3", sonra)
        self.assertIn("  [ ] X maddesi", sonra)

    def test_bitti_sayi_ve_parca(self):
        i, todo = self.ac()
        yaz(todo, "- [ ] alfa\n- [ ] beta\n- [ ] gama\n")
        r = self.cli("is", "todo", i, "--bitti", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [ ] alfa\n- [x] beta\n- [ ] gama\n")
        self.assertIn("todo 1/3", r.stdout)
        r = self.cli("is", "todo", i, "--bitti", "GAM")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [ ] alfa\n- [x] beta\n- [x] gama\n")
        self.assertIn("todo 2/3", r.stdout)

    def test_bitti_sifir_ya_da_cok_eslesme_hata_dosya_degismez(self):
        i, todo = self.ac()
        ilk = "- [ ] test bir\n- [ ] test iki\n"
        yaz(todo, ilk)
        for s in ("yok", "test", "7"):
            r = self.cli("is", "todo", i, "--bitti", s)
            self.assertNotEqual(r.returncode, 0, s)
            self.assertTrue(r.stderr.strip(), s)
            self.assertEqual(oku(todo), ilk)
        r = self.cli("is", "todo", i, "--bitti", "test")
        self.assertIn("test bir", r.stderr + r.stdout)

    def test_not_satir_sonuna_eklenir_girinti_korunur(self):
        i, todo = self.ac()
        yaz(todo, "- [ ] ust\n  - [ ] iç iş\n    alt satır\n")
        r = self.cli("is", "todo", i, "--bitti", "iç", "--not", "bitti notu")
        self.assertEqual(r.returncode, 0, r.stderr)
        bugun = datetime.date.today().isoformat()
        self.assertEqual(oku(todo), f"- [ ] ust\n  - [x] iç iş — {bugun}: bitti notu\n    alt satır\n")

    def test_ekle_ve_bitti_birlikte_hata(self):
        i, todo = self.ac()
        yaz(todo, "- [ ] a\n")
        r = self.cli("is", "todo", i, "--ekle", "x", "--bitti", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stderr.strip())
        self.assertEqual(oku(todo), "- [ ] a\n")

    def test_kapali_ise_ekle_hata(self):
        i, todo = self.ac()
        yaz(todo, "- [ ] a\n")
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        r = self.cli("is", "todo", i, "--ekle", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(oku(todo), "- [ ] a\n")

    def test_seceneksiz_cikti_degismez_salt_okuma(self):
        i, todo = self.ac()
        ilk = "- [x] a\n- [ ] b\n- [ ] c\n"
        yaz(todo, ilk)
        r = self.cli("is", "todo", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, f"{i} todo 1/3\n  [ ] b\n  [ ] c\n")
        self.assertEqual(oku(todo), ilk)

    def test_bilinmeyen_is_hata(self):
        r = self.cli("is", "todo", "I-999", "--ekle", "x")
        self.assertNotEqual(r.returncode, 0)

    def test_cli_iki_surec_20ser_ekle_40_madde(self):
        i, todo = self.ac()
        def is_(p):
            for n in range(20):
                r = self.cli("is", "todo", i, "--ekle", f"{p}{n}")
                self.assertEqual(r.returncode, 0, r.stderr)
        ts = [threading.Thread(target=is_, args=(p,)) for p in ("p", "q")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        madde = {s for s in oku(todo).splitlines() if s.startswith("- [ ] ")}
        self.assertEqual(len(madde), 40)


if __name__ == "__main__":
    unittest.main()
