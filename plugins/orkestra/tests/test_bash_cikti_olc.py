"""bash_cikti_olc.py: ağırlık, compaction sıfırlama, aile ayrımı, tekrar, tavan simülasyonu, kesit (ADR-0086, I-232 P3)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import bash_cikti_olc as B  # noqa: E402


def asistan(mid, *bloklar, ts="2026-10-27T08:00:00.000Z"):
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": mid, "content": list(bloklar)}})


def arac(tid, ad, **girdi):
    return {"type": "tool_use", "id": tid, "name": ad, "input": girdi}


def sonuc(tid, metin, ts="2026-10-27T08:00:01.000Z"):
    return json.dumps({"type": "user", "timestamp": ts,
                       "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": metin}]}]}})


SINIR = json.dumps({"type": "system", "subtype": "compact_boundary"})


class Agirlik(unittest.TestCase):
    def test_agirlik_sonraki_cagri_sayisi_kadar(self):
        satirlar = [asistan("a1", arac("t1", "Bash", command="ls")), sonuc("t1", "x" * 100),
                    asistan("a2", {"type": "text", "text": "tamam"}), asistan("a3", {"type": "text", "text": "bitti"})]
        o = B.oturum_tara(satirlar)
        self.assertEqual(o["cagri"], 3)
        r = o["bash"][0]
        self.assertEqual((r["ch"], r["w"], r["canli"]), (100, 2, True))  # a1 sonrası a2, a3

    def test_ayni_mesaj_kimligi_bir_cagri(self):
        satirlar = [asistan("a1", {"type": "text", "text": "a"}), asistan("a1", {"type": "text", "text": "b"})]
        self.assertEqual(B.oturum_tara(satirlar)["cagri"], 1)

    def test_compaction_agirligi_sifirlar_ve_canli_degil(self):
        satirlar = [asistan("a1", arac("t1", "Bash", command="ls")), sonuc("t1", "x" * 50),
                    asistan("a2", {"type": "text", "text": "z"}), SINIR,
                    asistan("a3", arac("t2", "Bash", command="pwd")), sonuc("t2", "y" * 70),
                    asistan("a4", {"type": "text", "text": "z"}), asistan("a5", {"type": "text", "text": "z"})]
        r1, r2 = B.oturum_tara(satirlar)["bash"]
        self.assertEqual((r1["w"], r1["canli"]), (1, False))  # özetlenmeden önce yalnız a2'yi gördü
        self.assertEqual((r2["w"], r2["canli"]), (2, True))

    def test_yan_zincir_sayilmaz(self):
        yan = json.dumps({"type": "assistant", "isSidechain": True, "message": {"id": "s1", "content": []}})
        self.assertEqual(B.oturum_tara([yan])["cagri"], 0)

    def test_kesit_sonrasi_satirlar_sayilmaz(self):
        satirlar = [asistan("a1", {"type": "text", "text": "a"}, ts="2026-10-27T08:00:00.000Z"),
                    asistan("a2", {"type": "text", "text": "b"}, ts="2026-10-27T12:00:00.000Z")]
        kesit = B._utc("2026-10-27T09:00:00Z")
        self.assertEqual(B.oturum_tara(satirlar, kesit)["cagri"], 1)
        self.assertEqual(B.oturum_tara(satirlar)["cagri"], 2)


class Aile(unittest.TestCase):
    def test_orkestra_yalniz_komut_konumunda(self):
        self.assertEqual(B.aile("python C:/x/orkestra.py is todo I-1"), "orkestra is todo/devam")
        self.assertEqual(B.aile("orkestra is devam I-2"), "orkestra is todo/devam")
        self.assertEqual(B.aile("orkestra plan dogrula I-2"), "orkestra diğer")
        # yoldaki 'orkestra' CLI sayılmaz: cd + sed okuma grubundadır
        self.assertNotIn("orkestra", B.aile("cd /c/x/plugins/orkestra && sed -n '1,50p' a.py"))
        self.assertEqual(B.aile("sed -n '1,50p' a.py"), "cat/sed/head/tail tek")
        self.assertEqual(B.aile("cat a.py | head -50"), "cat/sed/awk boru")
        self.assertEqual(B.aile("grep -rn foo ."), "grep/rg")
        self.assertEqual(B.aile("git log --oneline"), "git okuma")


class Tekrar(unittest.TestCase):
    def sec(self, ilk, sonraki):
        satirlar = [asistan("a1", arac("t1", "Bash", command=ilk)), sonuc("t1", "x" * 20)]
        for n, (ad, girdi) in enumerate(sonraki, 2):
            satirlar.append(asistan(f"a{n}", arac(f"t{n}", ad, **girdi)))
        return B.oturum_tara(satirlar)["bash"][0]["tekrar"]

    def test_ayni_komut(self):
        self.assertTrue(self.sec("ls -la", [("Bash", {"command": "ls -la"})]))

    def test_boru_turevi(self):
        self.assertTrue(self.sec("pytest -q", [("Bash", {"command": "pytest -q | tail -5"})]))

    def test_komutta_adi_gecen_dosyanin_okunmasi(self):
        self.assertTrue(self.sec("cat src/a.py", [("Read", {"file_path": "/x/src/a.py"})]))

    def test_alakasiz_sonraki_cagri_tekrar_degil(self):
        self.assertFalse(self.sec("ls -la", [("Bash", {"command": "pwd"}), ("Read", {"file_path": "/x/b.py"})]))

    def test_kayit_yolu_okuma(self):
        satirlar = [asistan("a1", arac("t1", "Bash", command="cat dev.log")),
                    sonuc("t1", "<persisted-output>Output too large. Full output saved to: C:/t/abc123.txt\nön izleme"),
                    asistan("a2", arac("t2", "Read", file_path="C:/t/abc123.txt"))]
        self.assertTrue(B.oturum_tara(satirlar)["bash"][0]["tekrar"])


class Hesap(unittest.TestCase):
    def oturum(self, boyutlar):
        satirlar = []
        for n, ch in enumerate(boyutlar):
            satirlar += [asistan(f"a{n}", arac(f"t{n}", "Bash", command=f"cat dosya{n}.txt")), sonuc(f"t{n}", "x" * ch)]
        satirlar += [asistan("son1", {"type": "text", "text": "."}), asistan("son2", {"type": "text", "text": "."})]
        return B.oturum_tara(satirlar)

    def test_tavan_simulasyonu_onizleme_kadar_birakir(self):
        o = self.oturum([30000, 100])
        c = B.hesapla([o], tavan=10000, onizleme=2500, bootstrap=0)
        r0, r1 = o["bash"]
        beklenen = (30000 - 2500) * r0["w"] / (30000 * r0["w"] + 100 * r1["w"])
        self.assertAlmostEqual(c["simulasyon"]["bash_karakter_azalma"], beklenen)
        self.assertEqual(c["buyuk"], 1)
        self.assertEqual(c["aileler"]["cat/sed/head/tail tek"]["adet"], 1)

    def test_tavan_altinda_kazanc_yok(self):
        c = B.hesapla([self.oturum([500, 900])], tavan=10000, bootstrap=0)
        self.assertEqual(c["simulasyon"]["bash_karakter_azalma"], 0)
        self.assertEqual(c["buyuk"], 0)

    def test_bootstrap_araligi_siralidir_ve_tohum_sabit(self):
        oturumlar = [self.oturum([30000, 100]), self.oturum([200, 300]), self.oturum([25000])]
        a = B.hesapla(oturumlar, bootstrap=200)["simulasyon"]["bootstrap_bash_azalma_95"]
        b = B.hesapla(oturumlar, bootstrap=200)["simulasyon"]["bootstrap_bash_azalma_95"]
        self.assertEqual(a, b)
        self.assertLessEqual(a[0], a[1])

    def test_jeffreys_ust_sinir_oranin_ustunde(self):
        for k, n in ((0, 100), (11, 381), (698, 16562)):
            u = B.jeffreys_ust(k, n)
            self.assertGreater(u, k / n)
            self.assertLess(u, 1)
        self.assertGreater(B.jeffreys_ust(11, 381), B.jeffreys_ust(110, 3810))  # örnek büyüdükçe daralır

    def test_kesilen_cikti_ayri_sayilir_ve_tekrari_olculur(self):
        onizleme = "<persisted-output>\nOutput too large (22KB). Full output saved to: C:/t/x.txt\n" + "y" * 100
        satirlar = [asistan("a1", arac("t1", "Bash", command="cat log.txt")), sonuc("t1", onizleme),
                    asistan("a2", arac("t2", "Read", file_path="C:/t/x.txt")),
                    asistan("a3", arac("t3", "Bash", command="pwd")), sonuc("t3", "ok")]
        o = B.oturum_tara(satirlar)
        self.assertEqual([r["kesildi"] for r in o["bash"]], [True, False])
        c = B.hesapla([o], bootstrap=0)
        self.assertEqual((c["tekrar_kesilen"]["k"], c["tekrar_kesilen"]["n"]), (1, 1))
        self.assertEqual(c["buyuk"], 0)  # önizleme 10.000 altında: ham uzunluk değil kesilme işareti sayılır

    def test_cat_sed_ek_tavan_kazanci(self):
        # 8000 karakterlik cat sonucu genel tavan (10.000) altında kalır; ek tavan 5000 onu önizlemeye (2500) indirir
        satirlar = [asistan("a0", arac("t0", "Bash", command="cat a.txt")), sonuc("t0", "x" * 8000),
                    asistan("a1", arac("t1", "Bash", command="pwd")), sonuc("t1", "y" * 2000),
                    asistan("a2", {"type": "text", "text": "."})]
        o = B.oturum_tara(satirlar)
        c = B.hesapla([o], tavan=10000, onizleme=2500, bootstrap=0)
        w0, w1 = (r["w"] for r in o["bash"])
        beklenen = (8000 - 2500) * w0 / (8000 * w0 + 2000 * w1)
        self.assertAlmostEqual(c["cat_sed_ek"]["ek_tavan"][5000]["azalma"], beklenen)
        self.assertAlmostEqual(c["cat_sed_ek"]["tavan_sonrasi_pay"], 8000 * w0 / (8000 * w0 + 2000 * w1))
        self.assertEqual(c["cat_sed_ek"]["adet"], 1)

    def test_karsilastir_azalma_ve_aralik(self):
        once = [self.oturum([30000, 100]) for _ in range(5)]
        sonra = [self.oturum([2500, 100]) for _ in range(5)]
        r = B.karsilastir(once, sonra, bootstrap=200)
        self.assertGreater(r["azalma"], 0.8)
        self.assertLessEqual(r["bootstrap_95"][0], r["azalma"] + 1e-9)
        self.assertLessEqual(r["azalma"], r["bootstrap_95"][1] + 1e-9)
        self.assertAlmostEqual(B.karsilastir(once, once, bootstrap=0)["azalma"], 0.0)

    def test_bas_oncesi_baslayan_oturum_atlanir(self):
        with tempfile.TemporaryDirectory() as d:
            for ad, ts in (("eski.jsonl", "2026-10-20T08:00:00.000Z"), ("yeni.jsonl", "2026-10-28T08:00:00.000Z")):
                with open(os.path.join(d, ad), "w", encoding="utf-8") as f:
                    f.write(asistan("a1", {"type": "text", "text": "."}, ts=ts) + "\n")
            self.assertEqual(len(B.dizin_tara(d)), 2)
            sonuc = B.dizin_tara(d, bas=B._utc("2026-10-25T00:00:00Z"))
            self.assertEqual([o["oturum"] for o in sonuc], ["yeni.jsonl"])

    def test_klasorden_okur_ve_cli(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "s1.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join([asistan("a1", arac("t1", "Bash", command="cat x.txt")), sonuc("t1", "x" * 15000),
                                   asistan("a2", {"type": "text", "text": "."})]) + "\n")
            self.assertEqual(B.main(["--dizin", d, "--json", "--bootstrap", "0"]), 0)
            c = B.hesapla(B.dizin_tara(d), bootstrap=0)
            self.assertEqual((c["oturum"], c["bash_sonuc"], c["buyuk"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
