"""G-153 / I-030 P1: istek_id ve span kimliği tüm kayıtlara yazılır.

`py -3.13 -m pytest plugins/orkestra/tests/test_istek_kimligi.py -q -p no:cacheprovider`

- K1 ork_lib.istek_id_yeni / istek_id_oku: biçim '<oturum ilk 8>-<4 hane sıra>', sıra oturum json'unda (istek_sira, son_istek_id), hata -> None.
- K2 user_prompt_submit sistem iletisi olmayan mesajda istek_id üretir, gunluk 'istek' satırına yazar.
- K3 stop (zaman ana + maliyet hook + ortak_defter), subagent_stop (maliyet + zaman alt + ortak_defter), maliyet tur: istek_id/span_id/ust_span_id.
- K4 KAYIT_SURUMU değişmez; kimlik yoksa hook çökmez, alan yazılmaz ya da null.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import ic_kos  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

ORK = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "abcd1234-aaaa-bbbb-cccc-333344445555"
KISA = OTURUM[:8]
AID = "ajan-kimlik-1"
ID_RE = re.compile(r"^abcd1234-\d{4}$")


def _jsonl(yol, satirlar):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _kullanici(metin, ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": metin}}


def _asistan(ts, mid="m1", arac=True):
    icerik = [{"type": "text", "text": "tamam"}]
    if arac:
        icerik.append({"type": "tool_use", "id": "t1", "name": "Write",
                       "input": {"file_path": "/tmp/x.txt", "content": "a"}})
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": mid, "model": "claude-haiku-5-5", "content": icerik,
                        "usage": {"input_tokens": 10, "output_tokens": 5}}}


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_istek_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        for a in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, a))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        self.atr = os.path.join(self.proje, "agent.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_CODE_SESSION_ID"] = OTURUM
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False),
                   mock.patch.object(perspektif, "durum", return_value={"zamani_geldi": False, "calisiyor": False})]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def kos(self, fn, girdi=None):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi or {})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            fn(g)

    def oturum_yol(self):
        return os.path.join(self.sd, "oturumlar", OTURUM + ".json")

    def oturum_yaz(self, **alan):
        with open(self.oturum_yol(), "w", encoding="utf-8") as f:
            json.dump(alan, f)

    def oturum_oku(self):
        with open(self.oturum_yol(), encoding="utf-8") as f:
            return json.load(f)

    def jl(self, ad):
        return L.jsonl_oku(os.path.join(self.sd, ad))

    def prompt(self, metin="merhaba dünya"):
        self.kos(hook.user_prompt_submit, {"prompt": metin})


class Kimlik(_Ortak):
    def test_k1_islevler_var(self):
        self.assertTrue(callable(getattr(L, "istek_id_yeni", None)))
        self.assertTrue(callable(getattr(L, "istek_id_oku", None)))

    def test_k1_bicim_ve_sira_artisi(self):
        self.oturum_yaz()
        a = L.istek_id_yeni(self.sd, OTURUM)
        b = L.istek_id_yeni(self.sd, OTURUM)
        self.assertEqual(a, f"{KISA}-0001")
        self.assertEqual(b, f"{KISA}-0002")
        self.assertRegex(a, ID_RE)

    def test_k1_oturum_json_alanlari(self):
        self.oturum_yaz(**{"is": "I-004"})
        L.istek_id_yeni(self.sd, OTURUM)
        L.istek_id_yeni(self.sd, OTURUM)
        d = self.oturum_oku()
        self.assertEqual(d["istek_sira"], 2)
        self.assertEqual(d["son_istek_id"], f"{KISA}-0002")
        self.assertEqual(d["is"], "I-004", "mevcut alanlar korunmalı")

    def test_k1_oku_son_kimligi_verir_sira_artirmaz(self):
        self.oturum_yaz()
        y = L.istek_id_yeni(self.sd, OTURUM)
        self.assertEqual(L.istek_id_oku(self.sd, OTURUM), y)
        self.assertEqual(L.istek_id_oku(self.sd, OTURUM), y)
        self.assertEqual(self.oturum_oku()["istek_sira"], 1)

    def test_k1_oturum_dosyasi_yokken_yeni_dosya_acilir(self):
        self.assertFalse(os.path.exists(self.oturum_yol()))
        self.assertEqual(L.istek_id_yeni(self.sd, OTURUM), f"{KISA}-0001")

    def test_k1_oku_kimlik_yokken_none(self):
        self.assertIsNone(L.istek_id_oku(self.sd, OTURUM))
        self.oturum_yaz(**{"is": "I-1"})
        self.assertIsNone(L.istek_id_oku(self.sd, OTURUM))

    def test_k1_bozuk_oturum_dosyasi_none_ve_istisna_yok(self):
        with open(self.oturum_yol(), "w", encoding="utf-8") as f:
            f.write("{bozuk\x00")
        self.assertIsNone(L.istek_id_oku(self.sd, OTURUM))
        self.assertIsNone(L.istek_id_yeni(self.sd, OTURUM))

    def test_k1_gecersiz_girdiler_none(self):
        self.assertIsNone(L.istek_id_yeni(None, OTURUM))
        self.assertIsNone(L.istek_id_yeni(self.sd, None))
        self.assertIsNone(L.istek_id_yeni(self.sd, ""))
        self.assertIsNone(L.istek_id_oku(None, OTURUM))
        self.assertIsNone(L.istek_id_oku(self.sd, None))

    def test_k1_oturum_json_liste_ise_none(self):
        with open(self.oturum_yol(), "w", encoding="utf-8") as f:
            f.write("[1, 2]")
        self.assertIsNone(L.istek_id_yeni(self.sd, OTURUM))

    def test_k1_sira_bozuksa_fail_open(self):
        self.oturum_yaz(istek_sira="x")
        r = L.istek_id_yeni(self.sd, OTURUM)  # istisna fırlatmamalı
        self.assertTrue(r is None or ID_RE.match(r))

    def test_k4_kayit_surumu_degismez(self):
        self.assertEqual(L.KAYIT_SURUMU, 1)


class Istek(_Ortak):
    def test_k2_gunluk_istek_satiri_istek_id_tasir(self):
        self.prompt()
        s = [r for r in self.jl("gunluk.jsonl") if r.get("tur") == "istek"]
        self.assertEqual(len(s), 1)
        self.assertRegex(s[0].get("istek_id") or "", ID_RE)
        self.assertEqual(s[0]["istek_id"], f"{KISA}-0001")
        self.assertEqual(s[0]["metin"], "merhaba dünya")  # mevcut alanlar değişmez

    def test_k2_iki_mesaj_iki_farkli_kimlik(self):
        self.prompt("bir")
        self.prompt("iki")
        s = [r["istek_id"] for r in self.jl("gunluk.jsonl") if r.get("tur") == "istek"]
        self.assertEqual(s, [f"{KISA}-0001", f"{KISA}-0002"])
        self.assertEqual(L.istek_id_oku(self.sd, OTURUM), f"{KISA}-0002")

    def test_k2_sistem_iletisi_yeni_kimlik_uretmez(self):
        self.prompt("ilk")
        self.prompt("<task-notification>bitti</task-notification>")
        self.assertEqual(L.istek_id_oku(self.sd, OTURUM), f"{KISA}-0001")
        self.assertEqual(self.oturum_oku()["istek_sira"], 1)

    def test_k2_baglam_ciktisi_degismez(self):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "prompt": "merhaba"}
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon), self.assertRaises(SystemExit):
            hook.user_prompt_submit(g)
        cikti = tampon.getvalue().strip()
        if cikti:
            d = json.loads(cikti)
            self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_k4_bozuk_oturum_dosyasinda_prompt_cokmez_alan_yazilmaz(self):
        with open(self.oturum_yol(), "w", encoding="utf-8") as f:
            f.write("{bozuk\x00")
        self.prompt()
        s = [r for r in self.jl("gunluk.jsonl") if r.get("tur") == "istek"]
        self.assertEqual(len(s), 1)
        self.assertFalse(s[0].get("istek_id"))
        self.assertEqual(s[0]["v"], 1)


class Satirlar(_Ortak):
    def _span_kontrol(self, r, ana=True):
        iid = f"{KISA}-0001"
        self.assertEqual(r.get("istek_id"), iid, r)
        self.assertEqual(r.get("ust_span_id"), iid, r)
        if ana:
            self.assertRegex(r.get("span_id") or "", rf"^{iid}\.t\d+$")
        else:
            self.assertEqual(r.get("span_id"), f"{iid}.a-{AID}")

    def _ana_tur(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-16T10:00:00Z"), _asistan("2026-10-16T10:00:07Z")])
        self.prompt()
        self.kos(hook.stop)

    def test_k3_stop_zaman_ana_satiri(self):
        self._ana_tur()
        s = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]
        self.assertEqual(len(s), 1)
        self._span_kontrol(s[0])

    def test_k3_stop_maliyet_hook_satirlari(self):
        self._ana_tur()
        s = [r for r in self.jl("maliyet.jsonl") if r.get("kaynak") == "hook"]
        self.assertTrue(s, "stop maliyet satırı yazmadı")
        for r in s:
            self._span_kontrol(r)

    def test_k3_stop_ortak_defter_satiri(self):
        self._ana_tur()
        s = [r for r in self.jl("ortak_defter.jsonl") if r.get("kaynak") == "hook"]
        self.assertTrue(s, "stop ortak_defter satırı yazmadı")
        for r in s:
            self._span_kontrol(r)

    def test_k3_ayni_istekte_ikinci_tur_farkli_span(self):
        self._ana_tur()
        with open(self.tr, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(_asistan("2026-10-16T10:01:00Z", "m2")) + "\n")
        self.kos(hook.stop)
        s = [r["span_id"] for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]
        self.assertEqual(len(s), 2)
        self.assertEqual(len(set(s)), 2, s)

    def _alt(self):
        _jsonl(self.atr, [_kullanici("#GOREV:G-007 #SUREC:is\nişi yap", "2026-10-16T10:00:00Z"),
                          _asistan("2026-10-16T10:02:00Z")])
        self.prompt()
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2",
                                      "agent_transcript_path": self.atr})

    def test_k3_subagent_stop_zaman_alt_satiri(self):
        self._alt()
        s = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "alt"]
        self.assertEqual(len(s), 1)
        self._span_kontrol(s[0], ana=False)

    def test_k3_subagent_stop_maliyet_satirlari(self):
        self._alt()
        s = [r for r in self.jl("maliyet.jsonl") if r.get("agent_id") == AID]
        self.assertTrue(s)
        for r in s:
            self._span_kontrol(r, ana=False)

    def test_k3_subagent_stop_ortak_defter_satiri(self):
        self._alt()
        s = [r for r in self.jl("ortak_defter.jsonl") if r.get("agent_id") == AID]
        self.assertEqual(len(s), 1)
        self._span_kontrol(s[0], ana=False)

    def _maliyet_tur(self, agent_id=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proje)
        kom = [ORK, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-sonnet-5-5",
               "--giris", "100", "--cikis", "50", "--onb-okuma", "30", "--onb-yazma", "20", "--sure-ms", "10"]
        if agent_id:
            kom += ["--agent-id", agent_id]
        p = ic_kos.kos(kom, env=env, cwd=self.proje)
        self.assertEqual(p.returncode, 0, p.stderr)
        s = [r for r in self.jl("maliyet_tur.jsonl") if r.get("kaynak") == "tur"]  # I-319 P3: gözlem defteri
        self.assertTrue(s)
        return s[-1]

    def test_k3_maliyet_tur_ana(self):
        self.prompt()
        r = self._maliyet_tur()
        self._span_kontrol(r)

    def test_k3_maliyet_tur_alt_ajan(self):
        self.prompt()
        r = self._maliyet_tur(AID)
        self._span_kontrol(r, ana=False)

    def test_k4_istek_yokken_alanlar_yazilmaz_ya_da_null(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-16T10:00:00Z"), _asistan("2026-10-16T10:00:07Z")])
        self.kos(hook.stop)  # prompt yok -> kimlik yok
        kontrol = 0
        for ad in ("zaman.jsonl", "maliyet.jsonl", "ortak_defter.jsonl"):
            for r in self.jl(ad):
                kontrol += 1
                for alan in ("istek_id", "span_id", "ust_span_id"):
                    self.assertIsNone(r.get(alan), f"{ad}: {alan}")
                self.assertEqual(r["v"], 1)
        self.assertGreater(kontrol, 0, "stop hiç kayıt yazmadı")
        # kimlik üretilmemiş olmalı; üretim yalnız user_prompt_submit'te
        self.assertIsNone(L.istek_id_oku(self.sd, OTURUM))

    def test_k4_bozuk_oturum_dosyasinda_stop_ve_alt_cokmez(self):
        with open(self.oturum_yol(), "w", encoding="utf-8") as f:
            f.write("{bozuk\x00")
        _jsonl(self.tr, [_kullanici("m", "2026-10-16T10:00:00Z"), _asistan("2026-10-16T10:00:07Z")])
        self.kos(hook.stop)
        _jsonl(self.atr, [_kullanici("#GOREV:G-007 #SUREC:is\nx", "2026-10-16T10:00:00Z"), _asistan("2026-10-16T10:01:00Z")])
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2", "agent_transcript_path": self.atr})
        self.assertTrue(self.jl("zaman.jsonl"))
        for r in self.jl("zaman.jsonl"):
            self.assertFalse(r.get("istek_id"))
        self.assertIsNone(L.istek_id_oku(self.sd, OTURUM))


if __name__ == "__main__":
    unittest.main()
