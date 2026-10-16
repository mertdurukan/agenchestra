"""close skill'inin betiği: sohbet kaydını sıkıştırma ve açık-iş raporu denetimi.

`py -3.13 -m pytest plugins/orkestra/tests/test_close_sohbet_cikar.py`
Gerçek oturum kaydına dokunmaz; geçici bir jsonl üretir.
"""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
BETIK = os.path.join(AD, "..", "skills", "close", "scripts", "sohbet_cikar.py")
spec = importlib.util.spec_from_file_location("sohbet_cikar", BETIK)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def _kayit(yol):
    satirlar = [
        {"type": "user", "timestamp": "t1", "message": {"content": "ilk istek <system-reminder>gürültü</system-reminder>"}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "a.md"}},
            {"type": "text", "text": "yazdım"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "attachment", "timestamp": "t2", "attachment": {
            "type": "queued_command", "prompt": "tur sürerken gelen istek", "origin": {"kind": "human"}}},
        {"type": "user", "timestamp": "t3", "message": {"content": "/close"}},
    ]
    with open(yol, "w", encoding="utf-8") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


class CloseTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.kayit = os.path.join(self.d, "o.jsonl")
        self.girdi = os.path.join(self.d, "girdi.json")
        _kayit(self.kayit)
        with contextlib.redirect_stdout(io.StringIO()):
            sc.cikar(self.kayit, self.girdi)
        self.veri = json.load(open(self.girdi, encoding="utf-8"))

    def test_mesajlar_numaralanir_gurultu_atilir(self):
        t = self.veri["turlar"]
        self.assertEqual([x["id"] for x in t], ["U1", "U2", "U3"])
        self.assertEqual(t[0]["metin"], "ilk istek")
        self.assertEqual(t[0]["dosyalar"], ["a.md"])
        self.assertIn("tur sürerken", t[1]["metin"])

    def test_cagri_mesaji_kapsam_disi(self):
        self.assertTrue(self.veri["turlar"][2]["kapsam_disi"])

    def test_eylem_yok_ve_olmayan_dosya_isaretlenir(self):
        t = self.veri["turlar"]
        self.assertFalse(t[0]["eylem_yok"])
        self.assertEqual(t[0]["dosyalar_yok"], ["a.md"])
        self.assertTrue(t[1]["eylem_yok"])

    def _denetle(self, metin):
        r = os.path.join(self.d, "r.md")
        open(r, "w", encoding="utf-8").write(metin)
        with contextlib.redirect_stdout(io.StringIO()):
            return sc.denetle(r, self.girdi)

    def test_gecerli_rapor_gecer(self):
        sayim = "## Sayım\n" + "\n".join(
            f"- {e}: {1 if e == 'CEVAPLANDI' else 0}" for e in sc.ETIKETLER)
        self.assertEqual(self._denetle(
            sayim + "\n\n- [CEVAPLANDI] U1, U2: istekler | Kanıt: yanıt\n"), 0)

    def test_eksik_mesaj_ve_yanlis_sayim_kalir(self):
        sayim = "## Sayım\n" + "\n".join(f"- {e}: 0" for e in sc.ETIKETLER)
        self.assertEqual(self._denetle(sayim + "\n\n- [CEVAPLANDI] U1: istek | Kanıt: yanıt\n"), 1)

    def test_acik_madde_eksiksiz_olmaz(self):
        sayim = "## Sayım\n" + "\n".join(
            f"- {e}: {1 if e == 'YAPILMADI' else 0}" for e in sc.ETIKETLER)
        rapor = sayim + "\n\n- [YAPILMADI] U1, U2: istek | Kanıt: yok\n"
        self.assertEqual(self._denetle(rapor), 1)

    def _acik_rapor(self, madde):
        govde = "## Konu 1 — deneme\n\n" + madde + "\n- [CEVAPLANDI] U2: soru | Kanıt: yanıt\n"
        sayim = "## Sayım\n" + "\n".join(
            f"- {e}: {govde.count('- [' + e + ']')}" for e in sc.ETIKETLER)
        return sayim + "\n\n" + govde

    def test_acik_madde_nedenle_gecer(self):
        r = self._acik_rapor("- [YAPILMADI] U1: a.md yazılmalı | Kanıt: dosya yok | "
                             "Neden: rapor bu dosyaya bağlı, yoksa teslim eksik kalır")
        self.assertEqual(self._denetle(r), 0)

    def test_neden_iki_cumle_ya_da_durum_tekrari_kalir(self):
        iki = self._acik_rapor("- [YAPILMADI] U1: a.md yazılmalı | Kanıt: yok | "
                               "Neden: Rapor buna bağlı. Teslim eksik kalır")
        self.assertEqual(self._denetle(iki), 1)
        tekrar = self._acik_rapor("- [YAPILMADI] U1: a.md yazılmalı | Kanıt: yok | Neden: eksik kalan iş")
        self.assertEqual(self._denetle(tekrar), 1)

    def test_liste_is_ve_nedeni_tek_maddede_verir(self):
        r = os.path.join(self.d, "l.md")
        open(r, "w", encoding="utf-8").write(self._acik_rapor(
            "- [YAPILMADI] U1: a.md yazılmalı | Kanıt: yok | Neden: rapor buna bağlı\n"
            "- [KARAR BEKLİYOR] U1: push yapılsın mı | Kanıt: istek yok | Neden: CI dosyası uzak depoda yok"))
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            sc.liste(r)
        cikti = tampon.getvalue()
        self.assertIn("Açık kalan işler (2):", cikti)
        self.assertIn("- **a.md yazılmalı** — rapor buna bağlı.", cikti)
        self.assertIn("- **Karar sizde: push yapılsın mı** — CI dosyası uzak depoda yok.", cikti)
        self.assertNotIn("CEVAPLANDI", cikti)

    def test_liste_acik_yoksa_bunu_soyler(self):
        r = os.path.join(self.d, "l.md")
        open(r, "w", encoding="utf-8").write("- [CEVAPLANDI] U1, U2: istekler | Kanıt: yanıt\n")
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            sc.liste(r)
        self.assertIn("Açık iş yok", tampon.getvalue())

    def test_karisik_aralik_ve_liste_kimligi_ayrisir(self):
        self.assertEqual(sc.kimlikler("U1–U3, U7"), {"U1", "U2", "U3", "U7"})
        self.assertTrue(sc.SATIR.match("- [YAPILDI] U1–U3, U7–U8: istek | Kanıt: x"))

    def test_son_turdaki_asistan_sorusu_cevapsiz_isaretlenir(self):
        d = tempfile.mkdtemp()
        kayit, girdi = os.path.join(d, "o.jsonl"), os.path.join(d, "g.json")
        satirlar = [
            {"type": "user", "timestamp": "t1", "message": {"content": "bir şey yap"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Yaptım. Push edeyim mi?"}]}},
            {"type": "user", "timestamp": "t2", "message": {"content": "/close"}},
        ]
        with open(kayit, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            sc.cikar(kayit, girdi)
        veri = json.load(open(girdi, encoding="utf-8"))
        self.assertEqual(veri["cevapsiz_soru"], "U1")


class SistemMesajiTest(unittest.TestCase):
    """Komut, skill gövdesi ve meta mesajlar kullanıcı isteği sayılmaz (koşu 16.10: 12 mesajın 3'ü sahteydi)."""

    def _cikar(self, mesajlar):
        d = tempfile.mkdtemp()
        kayit, girdi = os.path.join(d, "o.jsonl"), os.path.join(d, "g.json")
        with open(kayit, "w", encoding="utf-8") as f:
            for m in mesajlar:
                satir = {"type": "user", "timestamp": "t", "message": {"content": m}}
                if isinstance(m, dict):
                    satir = {"type": "user", "timestamp": "t", "isMeta": True,
                             "message": {"content": m["meta"]}}
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            sc.cikar(kayit, girdi)
        return json.load(open(girdi, encoding="utf-8"))

    def test_komut_skill_govdesi_ve_meta_atilir(self):
        veri = self._cikar([
            "gerçek istek",
            "<command-name>/reload-plugins</command-name>\n<command-message>reload-plugins</command-message>",
            "<command-message>orkestra:close</command-message>\n<command-name>/orkestra:close</command-name>",
            "Base directory for this skill: C:\\x\\close\n\n# /orkestra:close",
            "This session is being continued from a previous conversation that ran out of context.",
            {"meta": "skill enjekte metni"},
        ])
        self.assertEqual([t["metin"] for t in veri["turlar"]], ["gerçek istek"])
        self.assertEqual(veri["kullanici_mesaji"], 1)
        self.assertEqual(veri["sistem_olaylari"], 5)

    def test_argumanli_komut_kullanici_istegidir(self):
        veri = self._cikar([
            "<command-name>/db-olcum</command-name>\n<command-message>db-olcum</command-message>\n"
            "<command-args>Boyner'i ölç</command-args>"])
        self.assertEqual(veri["turlar"][0]["metin"], "/db-olcum Boyner'i ölç")

    def test_argumanli_close_cagrisi_kapsam_disi(self):
        veri = self._cikar([
            "gerçek istek",
            "<command-name>/orkestra:close</command-name>\n<command-message>orkestra:close</command-message>\n"
            "<command-args>skill konusu</command-args>"])
        self.assertEqual(veri["kullanici_mesaji"], 1)


if __name__ == "__main__":
    unittest.main()
