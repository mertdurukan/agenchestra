"""İş şeridi 2 (G-024): TODO.md okuyucu (todo_maddeleri), is_serit ve `orkestra is serit`."""
import json
import os
import shutil
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import is_kaydi as IK  # noqa: E402

ORNEK = """# Yapılacaklar

## Altyapı
- [x] **Langfuse** istemcisi `client.py` yazıldı → çıktı: client.py (13.10)
  - [ ] alt satır madde sayılmaz
  - ayrıntı satırı
- [ ] Açık iş **kalın** ve `kod` G4 için
- [~] Süren iş G5

## Kalite
- [ ] **Kalite-A:** G7-A1 yazıldı ‖ G8-B1/B2 sonra ‖ G9-C1 en son ‖ G7-A1 tekrar
- [x] Tarihli madde (G-014) bitti (14.10)

## Bekleyen kararlar ve riskler
- kutusuz düz satır
- başka düz satır
"""

KOVALAR = ("yapildi", "simdi", "sirada", "planda_kart_yok", "iptal")


def _is_serit_fonk():
    f = getattr(IK, "is_serit", None)
    if f is None:
        import orkestra as O  # noqa: E402
        f = getattr(O, "is_serit", None)
    return f


class TodoMaddeleri(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ork_todo_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def yaz(self, ad, metin):
        with open(os.path.join(self.d, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    # kriter 1
    def test_ornek_maddeler(self):
        self.yaz("todo.md", ORNEK)
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(len(m), 5)
        self.assertEqual([x["durum"] for x in m], ["bitti", "acik", "suruyor", "acik", "bitti"])
        self.assertEqual([x["bolum"] for x in m], ["Altyapı", "Altyapı", "Altyapı", "Kalite", "Kalite"])
        self.assertEqual(m[0]["metin"], "Langfuse istemcisi client.py yazıldı")
        self.assertEqual(m[1]["metin"], "Açık iş kalın ve kod G4 için")
        self.assertEqual(m[1]["adimlar"], ["G4"])
        self.assertEqual(m[2]["adimlar"], ["G5"])
        self.assertEqual(m[0]["adimlar"], [])

    def test_cok_adimli_tekrarsiz_sirali(self):
        self.yaz("todo.md", ORNEK)
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(m[3]["adimlar"], ["G7-A1", "G8-B1/B2", "G9-C1"])
        self.assertNotIn("**", m[3]["metin"])

    def test_kart_kimligi_ve_tarih_adim_degil(self):
        self.yaz("todo.md", ORNEK)
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(m[4]["adimlar"], [])
        self.assertEqual(m[4]["metin"], "Tarihli madde (G-014) bitti")

    def test_g_aralik_tek_belirtec(self):
        self.yaz("todo.md", "- [ ] G7-G9 paralel koşar\n")
        self.assertEqual(IK.todo_maddeleri(self.d)[0]["adimlar"], ["G7-G9"])

    def test_uzun_metin_kisaltilir(self):
        self.yaz("todo.md", "- [ ] " + "a" * 300 + "\n")
        t = IK.todo_maddeleri(self.d)[0]["metin"]
        self.assertLessEqual(len(t), 100)
        self.assertTrue(t.endswith("…"))

    def test_bolumsuz_madde(self):
        self.yaz("todo.md", "- [ ] ilk\n")
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(m[0]["bolum"], "")
        self.assertEqual(m[0]["durum"], "acik")

    def test_alt_satirlar_ve_kutusuzlar_sayilmaz(self):
        self.yaz("todo.md", "## B\n- düz\n  - [ ] girintili\n  - [x] girintili 2\n- [ ] tek\n")
        m = IK.todo_maddeleri(self.d)
        self.assertEqual([x["metin"] for x in m], ["tek"])

    # kriter 2
    def test_buyuk_harf_dosya(self):
        self.yaz("TODO.md", "- [x] bitti G4\n- [ ] açık\n")
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]["durum"], "bitti")

    def test_dosya_yok(self):
        self.assertEqual(IK.todo_maddeleri(self.d), [])

    def test_bos_dosya(self):
        self.yaz("todo.md", "")
        self.assertEqual(IK.todo_maddeleri(self.d), [])

    # kriter 6 (todo_ozet değişmez)
    def test_todo_ozet_degismez(self):
        self.yaz("todo.md", "- [x] a\n- [ ] b\n- [ ] \n  - [ ] alt\n")
        o = IK.todo_ozet(self.d)
        self.assertEqual(o["biten"], 1)
        self.assertEqual(o["acik_maddeler"][0], "b")


class Serit(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def kart_yaz(self, gid, **alan):
        k = {"id": gid, "baslik": f"kart {gid}", "basamak": "T1", "durum": "planlandi",
             "bagimliliklar": []}
        k.update(alan)
        d = os.path.join(self.sd, "gorevler")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)

    def kur(self, todo=None):
        klasor = os.path.join(self.proje, "RNV", "05_x", "001-y")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.is_id = r.stdout.strip().splitlines()[-1].split()[0]
        self.klasor = klasor
        if todo is not None:
            with open(os.path.join(klasor, "TODO.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(todo)
        return self.is_id

    def serit(self):
        f = _is_serit_fonk()
        self.assertIsNotNone(f, "is_serit tanımlı değil")
        return f(self.sd, self.is_id)

    def kartlar_kur(self):
        i = self.is_id
        self.kart_yaz("G-001", **{"is": i, "adim": "G1", "durum": "teslim", "teslim_ozeti": "G1 teslim edildi"})
        self.kart_yaz("G-002", **{"is": i, "adim": "G2", "durum": "isleniyor"})
        self.kart_yaz("G-003", **{"is": i, "adim": "G3", "durum": "denetimde"})
        self.kart_yaz("G-004", **{"is": i, "adim": None, "durum": "onaylandi"})
        self.kart_yaz("G-005", **{"is": i, "adim": "G5", "durum": "planlandi",
                                  "bagimliliklar": ["G-001", "G-002", "G-003"]})
        self.kart_yaz("G-006", **{"is": i, "adim": "G6", "durum": "beklemede"})
        self.kart_yaz("G-007", **{"is": i, "adim": "G7-A1", "durum": "reddedildi"})
        self.kart_yaz("G-008", **{"is": i, "adim": "G8", "durum": "iptal"})
        self.kart_yaz("G-009", **{"is": "I-999", "adim": "G9", "durum": "teslim"})
        self.kart_yaz("G-010", **{"durum": "teslim"})

    def kartlar_of(self, kova):
        return {o["kart"]: o for o in kova if o["tur"] == "kart"}

    # kriter 3
    def test_kovalar(self):
        self.kur()
        self.kartlar_kur()
        s = self.serit()
        self.assertEqual(list(self.kartlar_of(s["yapildi"])), ["G-001"])
        self.assertEqual(list(self.kartlar_of(s["simdi"])), ["G-002", "G-003", "G-004"])
        self.assertEqual(list(self.kartlar_of(s["sirada"])), ["G-005", "G-006", "G-007"])
        self.assertEqual(list(self.kartlar_of(s["iptal"])), ["G-008"])
        tum = [o.get("kart") for k in KOVALAR for o in s[k]]
        self.assertNotIn("G-009", tum)
        self.assertNotIn("G-010", tum)

    def test_kart_ogesi_alanlari(self):
        self.kur()
        self.kartlar_kur()
        s = self.serit()
        g1 = s["yapildi"][0]
        self.assertEqual(g1["tur"], "kart")
        self.assertEqual(g1["adim"], "G1")
        self.assertEqual(g1["metin"], "G1 teslim edildi")
        self.assertEqual(g1["durum"], "teslim")
        self.assertEqual(g1["bekledigi"], [])
        simdi = self.kartlar_of(s["simdi"])
        self.assertEqual(simdi["G-002"]["metin"], "kart G-002")  # teslim_ozeti yok -> baslik
        self.assertIsNone(simdi["G-004"]["adim"])

    def test_bekledigi(self):
        self.kur()
        self.kartlar_kur()
        s = self.serit()
        sirada = self.kartlar_of(s["sirada"])
        self.assertEqual(sorted(sirada["G-005"]["bekledigi"]), ["G-002", "G-003"])  # G-001 teslim
        self.assertEqual(sirada["G-006"]["bekledigi"], [])

    def test_onaylanmis_bagimlilik_bekletmez(self):
        self.kur()
        self.kart_yaz("G-001", **{"is": self.is_id, "durum": "onaylandi"})
        self.kart_yaz("G-002", **{"is": self.is_id, "durum": "planlandi", "bagimliliklar": ["G-001"]})
        s = self.serit()
        self.assertEqual(self.kartlar_of(s["sirada"])["G-002"]["bekledigi"], [])

    # kriter 4
    def test_madde_kartla_eslesir(self):
        self.kur(todo=("- [x] G7 yapıldı\n- [ ] G8-B1/B2 yapılacak\n- [ ] G9 henüz kart yok\n"
                       "- [x] G10 eski bitmiş\n- [~] G11 sürüyor\n- [ ] adımsız açık\n"))
        self.kart_yaz("G-001", **{"is": self.is_id, "adim": "G7-A1", "durum": "isleniyor"})
        self.kart_yaz("G-002", **{"is": self.is_id, "adim": "G8-B1/B2", "durum": "planlandi"})
        s = self.serit()

        def madde(kova):
            return [o["metin"] for o in s[kova] if o["tur"] == "madde"]

        self.assertEqual(madde("simdi"), ["G11 sürüyor"])
        self.assertEqual(madde("yapildi"), ["G10 eski bitmiş"])
        self.assertEqual(madde("planda_kart_yok"), ["G9 henüz kart yok", "adımsız açık"])
        self.assertEqual(madde("sirada"), [])
        self.assertEqual(list(self.kartlar_of(s["simdi"])), ["G-001"])
        self.assertEqual(list(self.kartlar_of(s["sirada"])), ["G-002"])

    def test_ters_onek_eslesme(self):
        # madde adımı '<kart adimi>-' ile başlar (G7-A1 maddesi, G7 kartı); G70 eşleşmez
        self.kur(todo="- [ ] G7-A1 ayrıntılı\n- [ ] G70 başka\n")
        self.kart_yaz("G-001", **{"is": self.is_id, "adim": "G7", "durum": "planlandi"})
        s = self.serit()
        self.assertEqual([o["metin"] for o in s["planda_kart_yok"]], ["G70 başka"])

    def test_madde_ogesi_alanlari_ve_ilerleme(self):
        self.kur(todo="## Bölüm\n- [x] a G4\n- [ ] b G5\n- [x] c\n")
        s = self.serit()
        self.assertEqual(s["ilerleme"], {"biten": 2, "toplam": 3})
        self.assertEqual(s["yapildi"][0], {"tur": "madde", "metin": "a G4", "adimlar": ["G4"],
                                          "bolum": "Bölüm", "durum": "bitti"})
        self.assertEqual([o["metin"] for o in s["yapildi"]], ["a G4", "c"])
        self.assertEqual(s["planda_kart_yok"][0]["durum"], "acik")

    def test_is_alani_ve_bos_serit(self):
        self.kur()
        s = self.serit()
        self.assertEqual(s["is"]["id"], self.is_id)
        self.assertEqual(s["is"]["baslik"], "Deneme işi")
        self.assertEqual(s["is"]["durum"], "acik")
        self.assertEqual(os.path.normcase(os.path.abspath(s["is"]["klasor"])),
                         os.path.normcase(os.path.abspath(self.klasor)))
        for k in KOVALAR:
            self.assertEqual(s[k], [])

    def test_siralama(self):
        self.kur(todo="- [ ] z\n- [ ] a\n")
        self.kart_yaz("G-003", **{"is": self.is_id, "durum": "planlandi"})
        self.kart_yaz("G-001", **{"is": self.is_id, "durum": "planlandi"})
        s = self.serit()
        self.assertEqual(list(self.kartlar_of(s["sirada"])), ["G-001", "G-003"])
        self.assertEqual([o["metin"] for o in s["planda_kart_yok"]], ["z", "a"])

    # kriter 5
    def test_cli_json(self):
        self.kur(todo="- [x] a G4\n- [ ] b\n")
        self.kart_yaz("G-001", **{"is": self.is_id, "adim": "G1", "durum": "isleniyor",
                                  "baslik": "Türkçe başlık ş"})
        r = self.cli("is", "serit", self.is_id, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.loads(r.stdout)
        for k in ("is", "ilerleme") + KOVALAR:
            self.assertIn(k, j)
        self.assertEqual(j["ilerleme"], {"biten": 1, "toplam": 2})
        self.assertIn("Türkçe başlık ş", r.stdout)  # ensure_ascii=False

    def test_cli_duz_cikti(self):
        self.kur(todo="- [x] G4 bitti iş\n- [ ] açık madde\n")
        self.kart_yaz("G-001", **{"is": self.is_id, "adim": "G1", "durum": "isleniyor"})
        self.kart_yaz("G-002", **{"is": self.is_id, "adim": "G2", "durum": "planlandi",
                                  "bagimliliklar": ["G-001"]})
        self.kart_yaz("G-003", **{"is": self.is_id, "durum": "iptal"})
        r = self.cli("is", "serit", self.is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = r.stdout
        self.assertIn(f"{self.is_id} — Deneme işi  [1/2]", o)
        for b in ("✔ Yapıldı", "◐ Şimdi", "○ Sırada", "◌ Planda, kart yok", "⊘ İptal (1)"):
            self.assertIn(b, o)
        self.assertIn("  G4  G4 bitti iş", o)
        self.assertIn("(G-001)", o)
        self.assertIn(" ← G-001", o)

    def test_cli_bos_kova_basligi_yok(self):
        self.kur(todo="- [ ] açık madde\n")
        r = self.cli("is", "serit", self.is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("◌ Planda, kart yok", r.stdout)
        for b in ("✔ Yapıldı", "◐ Şimdi", "○ Sırada", "⊘ İptal"):
            self.assertNotIn(b, r.stdout)

    def test_cli_bilinmeyen_is(self):
        self.assertNotEqual(self.cli("is", "serit", "I-404").returncode, 0)
        self.assertNotEqual(self.cli("is", "serit", "I-404", "--json").returncode, 0)


if __name__ == "__main__":
    unittest.main()
