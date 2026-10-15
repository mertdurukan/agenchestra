"""G-105: todo bayatlamasını önleme. `orkestra is todo-denetle`, kart --madde ile otomatik [x], Stop ve SessionStart uyarıları."""
import datetime
import json
import os
import sys
import unittest

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_kaydi as K  # noqa: E402


def oku(yol):
    with open(yol, encoding="utf-8", newline="") as f:
        return f.read()


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="") as f:
        f.write(metin)


class _Temel:
    """Cekirdek'in yardımcılarını kullanır; onun testlerini miras almaz."""
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook
    kart = TC.Cekirdek.kart

    def is_ac(self, alt="is1"):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor

    def kart_durum_yaz(self, gid, durum):
        yol = os.path.join(self.sd, "gorevler", gid + ".json")
        k = json.loads(oku(yol))
        k["durum"] = durum
        yaz(yol, json.dumps(k, ensure_ascii=False, indent=2) + "\n")


class TodoDenetle(_Temel, unittest.TestCase):
    def test_bagsiz_ve_worktree_listelenir_bagli_listelenmez(self):
        i, klasor = self.is_ac()
        yaz(os.path.join(self.proje, "baska", "todo.md"), "- [ ] a\n")
        wt = os.path.join(self.proje, ".claude", "worktrees", "kart-G-001", "is1", "todo.md")
        yaz(wt, "- [ ] a\n")
        r = self.cli("is", "todo-denetle", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        yollar = {os.path.normcase(x["yol"]): x["tur"] for x in out}
        self.assertEqual(yollar.get(os.path.normcase(os.path.join(self.proje, "baska", "todo.md"))), "bagsiz")
        self.assertEqual(yollar.get(os.path.normcase(wt)), "worktree")
        self.assertNotIn(os.path.normcase(os.path.join(klasor, "todo.md")), yollar)
        self.assertEqual(len(out), 2)
        self.assertIn("2 dosya", self.cli("is", "todo-denetle").stdout)

    def test_sorun_yoksa_bos(self):
        self.is_ac()
        self.assertIn("yok", self.cli("is", "todo-denetle").stdout)
        self.assertEqual(K.todo_denetle_satiri(self.sd, self.proje), "")

    def test_sessionstart_en_cok_tek_uyari_satiri(self):
        self.is_ac()
        for ad in ("a", "b", "c"):
            yaz(os.path.join(self.proje, ad, "todo.md"), "- [ ] x\n")
        yaz(os.path.join(self.proje, ".claude", "worktrees", "w", "todo.md"), "- [ ] x\n")
        c = self.hook("SessionStart", {"source": "startup"})
        ek = c["hookSpecificOutput"]["additionalContext"]
        uyarilar = [s for s in ek.splitlines() if "todo dosyası işe bağlı değil" in s]
        self.assertEqual(len(uyarilar), 1, ek)
        self.assertIn("4 todo dosyası", uyarilar[0])
        self.assertIn("1 worktree", uyarilar[0])
        self.assertLessEqual(len(ek), 1800)

    def test_sessionstart_sorun_yoksa_uyari_yok(self):
        self.is_ac()
        ek = self.hook("SessionStart", {"source": "startup"})["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("işe bağlı değil", ek)


class KartMadde(_Temel, unittest.TestCase):
    def hazirla(self, todo, madde):
        i, klasor = self.is_ac()
        yaz(os.path.join(klasor, "todo.md"), todo)
        g = self.kart("--madde", madde) if madde is not None else self.kart()
        self.kart_durum_yaz(g, "onaylandi")
        return i, klasor, g

    def test_madde_kartta_saklanir_ve_teslimde_x_olur(self):
        i, klasor, g = self.hazirla("# t\n- [ ] alfa maddesi\n- [ ] beta maddesi\n", "beta")
        self.assertEqual(json.loads(self.cli("kart", "goster", g).stdout)["madde"], "beta")
        r = self.cli("kart", "teslim", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{g} → teslim", r.stdout)
        bugun = datetime.date.today().isoformat()
        self.assertEqual(oku(os.path.join(klasor, "todo.md")).splitlines()[1:3],
                         ["- [ ] alfa maddesi", f"- [x] beta maddesi — {bugun}: {g} teslim"])

    def test_eslesme_yoksa_teslim_basarili_ve_uyari(self):
        _, klasor, g = self.hazirla("- [ ] alfa\n", "olmayan")
        r = self.cli("kart", "teslim", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{g} → teslim", r.stdout)
        self.assertIn("uyarı", r.stderr)
        self.assertIn("madde işaretlenemedi", r.stderr)
        self.assertEqual(oku(os.path.join(klasor, "todo.md")), "- [ ] alfa\n")

    def test_birden_cok_eslesme_teslim_engellenmez(self):
        _, klasor, g = self.hazirla("- [ ] iş bir\n- [ ] iş iki\n", "iş")
        r = self.cli("kart", "teslim", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 eşleşme", r.stderr)
        self.assertNotIn("[x]", oku(os.path.join(klasor, "todo.md")))

    def test_maddesiz_kart_todoya_dokunmaz(self):
        _, klasor, g = self.hazirla("- [ ] alfa\n", None)
        r = self.cli("kart", "teslim", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("madde işaretlenemedi", r.stderr)
        self.assertEqual(oku(os.path.join(klasor, "todo.md")), "- [ ] alfa\n")

    def test_toplu_json_madde_alani(self):
        self.is_ac()
        plan = os.path.join(self.proje, "plan.json")
        yaz(plan, json.dumps([{"baslik": "A", "sinif": "belge", "kabul_kriterleri": ["x"], "yazma_alani": ["docs/**"],
                               "madde": "alfa"}]))
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        g = json.loads(r.stdout)[0]["id"]
        self.assertEqual(json.loads(self.cli("kart", "goster", g).stdout)["madde"], "alfa")

    def test_bos_madde_reddedilir(self):
        self.is_ac()
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T1", "--kabul", "k", "--yazma", "docs/**",
                     "--sinif", "belge", "--madde", "  ")
        self.assertNotEqual(r.returncode, 0)


class StopUyari(_Temel, unittest.TestCase):
    def hazirla(self, kart_durumu):
        i, klasor = self.is_ac()
        g = self.kart()
        yaz(os.path.join(klasor, "todo.md"), f"# t\n- [ ] {g} ile yapılacak iş\n- [ ] ilgisiz madde\n")
        if kart_durumu:
            self.kart_durum_yaz(g, kart_durumu)
        return i, g

    def stop_mesaj(self):
        return self.hook("Stop", {}).get("systemMessage") or ""

    def test_teslim_kart_uyari_uretir(self):
        i, g = self.hazirla("teslim")
        m = self.stop_mesaj()
        satirlar = [s for s in m.splitlines() if "kartı bitmiş" in s]
        self.assertEqual(len(satirlar), 1, m)
        self.assertIn(g, satirlar[0])
        self.assertIn("1. madde", satirlar[0])
        self.assertIn(f"orkestra is todo {i} --bitti", satirlar[0])

    def test_iptal_kart_uyari_uretir(self):
        _, g = self.hazirla("iptal")
        self.assertIn(g, self.stop_mesaj())

    def test_acik_kart_icin_uyari_yok(self):
        self.hazirla(None)
        self.assertNotIn("kartı bitmiş", self.stop_mesaj())

    def test_madde_zaten_bitmisse_uyari_yok(self):
        i, g = self.hazirla("teslim")
        klasor = K.is_al(self.sd, i)["klasor"]
        yaz(os.path.join(klasor, "todo.md"), f"- [x] {g} ile yapılacak iş\n")
        self.assertNotIn("kartı bitmiş", self.stop_mesaj())


if __name__ == "__main__":
    unittest.main()
