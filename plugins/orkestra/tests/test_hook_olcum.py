"""G-038: maliyet satırında araç sayıları (N7) ve iş kimliği (T-05).

`py -3.13 -m pytest plugins/orkestra/tests/test_hook_olcum.py -q -p no:cacheprovider`

- SubagentStop hook satırı: araclar (ad -> çağrı), arac_hata (is_error=true sonuç), tekrar_okuma (aynı file_path ikinci+ Read).
- ork_lib.transkript_oku ozetine ayrı 'arac_sayilari' alanı; mevcut 'araclar' kümesi bozulmaz.
- Her maliyet satırında 'is': alt ajanda kartın 'is'i, yoksa oturumun bağlı işi; ana ajan Stop satırında oturumun işi; yoksa None.
- Bozuk oturum dosyası kancayı çökertmez.
Hepsi geçici projede koşar.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402

OTURUM = "olcum-oturum"
AID = "ajan-olcum-1"


def _jsonl(yol, satirlar):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _kullanici(metin):
    return {"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"role": "user", "content": metin}}


def _arac(mid, tid, ad, giris):
    return {"type": "assistant", "timestamp": "2026-10-14T10:00:01Z",
            "message": {"id": mid, "model": "claude-haiku-5-5",
                        "content": [{"type": "tool_use", "id": tid, "name": ad, "input": giris}],
                        "usage": {"input_tokens": 10, "output_tokens": 5}}}


def _sonuc(tid, hata=False):
    b = {"type": "tool_result", "tool_use_id": tid, "content": "x"}
    if hata:
        b["is_error"] = True
    return {"type": "user", "timestamp": "2026-10-14T10:00:02Z", "message": {"role": "user", "content": [b]}}


def _arac_transkripti(ilk="#GOREV:G-001 #SUREC:is\nişi yap"):
    return [
        _kullanici(ilk),
        _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1"),
        _arac("m2", "t2", "Read", {"file_path": "/b.py"}), _sonuc("t2"),
        _arac("m3", "t3", "Read", {"file_path": "/a.py"}), _sonuc("t3"),
        _arac("m4", "t4", "Bash", {"command": "false"}), _sonuc("t4", hata=True),
    ]


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_olcum_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        os.makedirs(os.path.join(self.sd, "gorevler"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        self.atr = os.path.join(self.proje, "agent.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def kos(self, fn, girdi):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            fn(g)

    def alt_ajan_stop(self):
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2", "agent_transcript_path": self.atr})

    def kart_yaz(self, gid, is_=None):
        k = {"id": gid, "baslik": "t", "sinif": "kod", "durum": "isleniyor", "oturum": OTURUM, "isciler": [], "denetciler": [],
             "gecmis": [], "v": 1}
        if is_ is not None:
            k["is"] = is_
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def oturum_yaz(self, **alanlar):
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump(alanlar, f)

    def satirlar(self):
        return L.jsonl_oku(os.path.join(self.sd, "maliyet.jsonl"))


class AracSayimi(_Ortak):
    def test_subagent_stop_arac_alanlari(self):
        _jsonl(self.atr, _arac_transkripti())
        self.alt_ajan_stop()
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["araclar"], {"Read": 3, "Bash": 1})
        self.assertEqual(s[0]["arac_hata"], 1)
        self.assertEqual(s[0]["tekrar_okuma"], 1)
        self.assertEqual(s[0]["kaynak"], "hook")
        self.assertEqual(s[0]["arac_cagrisi"], 4)  # mevcut alan değişmedi

    def test_hatasiz_tekrarsiz_transkript_sifir(self):
        _jsonl(self.atr, [_kullanici("#GOREV:G-001 #SUREC:is\nx"),
                          _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1"),
                          _arac("m2", "t2", "Read", {"file_path": "/b.py"}), _sonuc("t2")])
        self.alt_ajan_stop()
        s = self.satirlar()[0]
        self.assertEqual(s["araclar"], {"Read": 2})
        self.assertEqual(s["arac_hata"], 0)
        self.assertEqual(s["tekrar_okuma"], 0)

    def test_ucuncu_okuma_da_tekrar_sayilir(self):
        _jsonl(self.atr, [_kullanici("x")] + [y for i in range(3) for y in (_arac(f"m{i}", f"t{i}", "Read", {"file_path": "/a.py"}), _sonuc(f"t{i}"))])
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["tekrar_okuma"], 2)

    def test_yalniz_read_tekrari_sayilir(self):
        # Aynı file_path ile Edit/Grep tekrarı "tekrar okuma" değildir.
        _jsonl(self.atr, [_kullanici("x"),
                          _arac("m1", "t1", "Edit", {"file_path": "/a.py"}), _sonuc("t1"),
                          _arac("m2", "t2", "Edit", {"file_path": "/a.py"}), _sonuc("t2"),
                          _arac("m3", "t3", "Read", {"file_path": "/a.py"}), _sonuc("t3")])
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["tekrar_okuma"], 0)

    def test_is_error_false_hata_sayilmaz(self):
        _jsonl(self.atr, [_kullanici("x"), _arac("m1", "t1", "Bash", {"command": "ls"}),
                          {"type": "user", "message": {"role": "user", "content": [
                              {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False}]}}])
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["arac_hata"], 0)

    def test_transkript_oku_arac_sayilari_ayri_alan(self):
        _jsonl(self.atr, _arac_transkripti())
        o = L.transkript_oku(self.atr)
        self.assertEqual(o["araclar"], {"Read": 3, "Bash": 1})  # mevcut küme bozulmadı
        self.assertEqual(o["arac_cagrisi"], 4)
        self.assertEqual(o["arac_sayilari"]["arac_hata"], 1)
        self.assertEqual(o["arac_sayilari"]["tekrar_okuma"], 1)

    def test_transkript_oku_bos_yolda_alan_var(self):
        o = L.transkript_oku(os.path.join(self.proje, "yok.jsonl"))
        self.assertIn("arac_sayilari", o)
        self.assertEqual(o["arac_sayilari"].get("arac_hata", 0), 0)
        self.assertEqual(o["arac_sayilari"].get("tekrar_okuma", 0), 0)


class IsKimligi(_Ortak):
    def hazirla_alt(self):
        _jsonl(self.atr, _arac_transkripti())

    def test_kart_isi_alt_ajan_satirinda(self):
        self.hazirla_alt()
        self.kart_yaz("G-001", "I-001")
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["is"], "I-001")

    def test_kart_isi_oturum_isine_ustun(self):
        self.hazirla_alt()
        self.kart_yaz("G-001", "I-001")
        self.oturum_yaz(**{"is": "I-009"})
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["is"], "I-001")

    def test_kartsiz_alt_ajan_oturum_isini_alir(self):
        _jsonl(self.atr, _arac_transkripti(ilk="gorevsiz is"))
        self.oturum_yaz(**{"is": "I-005"})
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["is"], "I-005")

    def test_kart_isi_yoksa_oturum_isine_duser(self):
        self.hazirla_alt()
        self.kart_yaz("G-001")  # kartta 'is' yok
        self.oturum_yaz(**{"is": "I-005"})
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["is"], "I-005")

    def test_hicbir_bag_yoksa_null(self):
        _jsonl(self.atr, _arac_transkripti(ilk="gorevsiz"))
        self.alt_ajan_stop()
        s = self.satirlar()[0]
        self.assertIn("is", s)
        self.assertIsNone(s["is"])

    def test_ana_ajan_stop_oturum_isi(self):
        _jsonl(self.tr, [_kullanici("merhaba"), _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1")])
        self.oturum_yaz(**{"is": "I-003"})
        self.kos(hook.stop, {})
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["ajan"], "ana-ajan")
        self.assertEqual(s[0]["is"], "I-003")

    def test_ana_ajan_stop_bag_yoksa_null(self):
        _jsonl(self.tr, [_kullanici("merhaba"), _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1")])
        self.kos(hook.stop, {})
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        self.assertIn("is", s[0])
        self.assertIsNone(s[0]["is"])

    def test_ana_ajan_ikinci_turda_da_is_yazilir(self):
        _jsonl(self.tr, [_kullanici("bir"), _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1")])
        self.oturum_yaz(**{"is": "I-003"})
        self.kos(hook.stop, {})  # ofset yazıldı, 'is' korunmalı
        with open(self.tr, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(_arac("m2", "t2", "Read", {"file_path": "/b.py"})) + "\n")
        self.kos(hook.stop, {})
        self.assertEqual([r["is"] for r in self.satirlar()], ["I-003", "I-003"])


class Dayaniklilik(_Ortak):
    def test_bozuk_oturum_dosyasi_alt_ajan_cokmez(self):
        _jsonl(self.atr, _arac_transkripti(ilk="gorevsiz"))
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.alt_ajan_stop()
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        self.assertIsNone(s[0]["is"])
        self.assertEqual(s[0]["araclar"], {"Read": 3, "Bash": 1})

    def test_bozuk_oturum_dosyasi_stop_cokmez(self):
        _jsonl(self.tr, [_kullanici("merhaba"), _arac("m1", "t1", "Read", {"file_path": "/a.py"}), _sonuc("t1")])
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.kos(hook.stop, {})
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        self.assertIsNone(s[0]["is"])

    def test_oturum_json_liste_ise_cokmez(self):
        _jsonl(self.atr, _arac_transkripti(ilk="gorevsiz"))
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            f.write("[1, 2]")
        self.alt_ajan_stop()
        self.assertIsNone(self.satirlar()[0]["is"])

    def test_bozuk_kart_dosyasi_oturum_isine_duser_cokmez(self):
        self.hazirla = _jsonl(self.atr, _arac_transkripti())
        with open(os.path.join(self.sd, "gorevler", "G-001.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.oturum_yaz(**{"is": "I-005"})
        self.alt_ajan_stop()
        self.assertEqual(self.satirlar()[0]["is"], "I-005")


class MevcutDavranis(_Ortak):
    def test_maliyet_kayitlari_ek_alanli_satirlari_tekillestirir(self):
        _jsonl(self.atr, _arac_transkripti(ilk="gorevsiz"))
        self.alt_ajan_stop()
        self.alt_ajan_stop()  # SendMessage ile sürdürülen ajan: birikimli çift satır
        self.assertEqual(len(self.satirlar()), 2)
        k = L.maliyet_kayitlari(self.sd)
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["araclar"], {"Read": 3, "Bash": 1})

    def test_mevcut_satir_alanlari_korunur(self):
        _jsonl(self.atr, _arac_transkripti())
        self.kart_yaz("G-001", "I-001")
        self.alt_ajan_stop()
        s = self.satirlar()[0]
        for k in ("zaman", "oturum", "gorev", "surec", "baglam", "ajan", "agent_id", "sure_ms", "tur", "arac_cagrisi",
                  "perspektif", "kaynak", "model", "giris", "cikis", "onbellek_okuma", "onbellek_yazma", "maliyet_usd"):
            self.assertIn(k, s)
        self.assertEqual(s["gorev"], "G-001")


if __name__ == "__main__":
    unittest.main()
