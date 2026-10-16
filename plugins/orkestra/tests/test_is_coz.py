"""G-154 / I-030 P2: tek is_coz atfı; satır yazılırken iş çözülür, bağsız satır nedenini taşır.

`py -3.13 -m pytest plugins/orkestra/tests/test_is_coz.py -q -p no:cacheprovider`

- K1 ork_lib.is_coz(sd, oturum, gorev) -> (is_id_ya_da_None, atif_nedeni); sıra kart, oturum json, niyet bağlamı; hata -> ('-', 'hata').
- K2 hook (stop, subagent_stop) ve komutlar/maliyet.py is alanını yalnız is_coz'tan yazar; bağsız satırda atif_nedeni var.
- K3 oturum işe bağlanınca (CLI _oturumu_bagla, hook _otomatik_is_ac) bağsız maliyet satırları için atif.jsonl'e tek olay.
- K4 hata yolları fail-open.
"""
import contextlib
import inspect
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import ic_kos  # noqa: E402
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402
from komutlar import isler as ISL  # noqa: E402
from komutlar import maliyet as MAL  # noqa: E402

ORK = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "isc-oturum-1111"
AID = "ajan-isc-1"


def _jsonl_yaz(yol, satirlar):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_iscoz_")
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
        self.niyet_yolu = yol
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

    def yaz(self, *parca, icerik):
        yol = os.path.join(self.sd, *parca)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))

    def oturum(self, **alan):
        self.yaz("oturumlar", f"{OTURUM}.json", icerik=alan)

    def kart(self, gid, **alan):
        self.yaz("gorevler", f"{gid}.json", icerik=dict({"id": gid}, **alan))

    def kos(self, fn, girdi=None):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi or {})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            fn(g)

    def jl(self, ad):
        return L.jsonl_oku(os.path.join(self.sd, ad))

    def bagsiz_maliyet(self, adet=2):
        _jsonl_yaz(os.path.join(self.sd, "maliyet.jsonl"),
                   [{"v": 1, "zaman": "2026-10-16T10:00:0%d+03:00" % i, "oturum": OTURUM, "gorev": "-", "is": None,
                     "maliyet_usd": 0.01, "kaynak": "tur"} for i in range(adet)])

    def is_ac(self, alt="is1"):
        return is_kaydi.is_ac(self.sd, "Deneme işi", os.path.join(self.proje, alt))["id"]

    def maliyet_tur(self, agent_id=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proje)
        kom = [ORK, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-sonnet-5-5",
               "--giris", "100", "--cikis", "50", "--onb-okuma", "30", "--onb-yazma", "20", "--sure-ms", "10"]
        if agent_id:
            kom += ["--agent-id", agent_id]
        p = ic_kos.kos(kom, env=env, cwd=self.proje)
        self.assertEqual(p.returncode, 0, p.stderr)
        s = self.jl("maliyet.jsonl")
        self.assertTrue(s)
        return s[-1]


class TestIsCozSira(_Ortak):
    def test_k1_is_coz_var(self):
        self.assertTrue(callable(getattr(L, "is_coz", None)), "ork_lib.is_coz yok")

    def test_k1_kart_oturumdan_once(self):
        self.kart("G-1", **{"is": "I-100"})
        self.oturum(**{"is": "I-200"})
        self.assertEqual(L.is_coz(self.sd, OTURUM, "G-1"), ("I-100", None))

    def test_k1_kartta_is_yoksa_oturuma_duser(self):
        self.kart("G-1")
        self.oturum(**{"is": "I-200"})
        self.assertEqual(L.is_coz(self.sd, OTURUM, "G-1"), ("I-200", None))

    def test_k1_gorev_tire_ise_oturum(self):
        self.oturum(**{"is": "I-200"})
        self.assertEqual(L.is_coz(self.sd, OTURUM, "-"), ("I-200", None))

    def test_k1_gorev_none_ise_oturum(self):
        self.oturum(**{"is": "I-200"})
        self.assertEqual(L.is_coz(self.sd, OTURUM, None), ("I-200", None))

    def test_k1_niyet_baglami_son_siradadir(self):
        with mock.patch.object(niyet, "son_baglam", return_value="I-300"):
            self.assertEqual(L.is_coz(self.sd, OTURUM, "-")[0], "I-300")
            self.oturum(**{"is": "I-200"})
            self.assertEqual(L.is_coz(self.sd, OTURUM, "-")[0], "I-200")

    def test_k1_oturum_isiz_nedeni(self):
        self.oturum()
        with mock.patch.object(niyet, "son_baglam", return_value=""):
            self.assertEqual(L.is_coz(self.sd, OTURUM, "-"), (None, "oturum-isiz"))

    def test_k1_oturum_dosyasi_yok_oturum_isiz(self):
        with mock.patch.object(niyet, "son_baglam", return_value=""):
            self.assertEqual(L.is_coz(self.sd, OTURUM, "-"), (None, "oturum-isiz"))

    def test_k1_kart_var_isiz_ve_oturum_isiz_kart_isiz(self):
        self.kart("G-1")
        self.oturum()
        with mock.patch.object(niyet, "son_baglam", return_value=""):
            self.assertEqual(L.is_coz(self.sd, OTURUM, "G-1"), (None, "kart-isiz"))

    def test_k1_hata_fail_open(self):
        # G-156: okunamayan kart istisna/'hata' değil, oturumun işine düşer
        self.kart("G-1", **{"is": "I-100"})
        self.oturum(**{"is": "I-200"})
        with mock.patch.object(L, "kart_oku", side_effect=RuntimeError("bozuk")) as km:
            r = L.is_coz(self.sd, OTURUM, "G-1")
        km.assert_called_once_with(self.sd, "G-1")  # hata yolu gerçekten koştu
        self.assertEqual(r, ("I-200", None))  # oturumda iş varken oturum işi döner

    def test_k1_hata_kart_okunamaz_oturumsuz_kart_isiz(self):
        self.kart("G-1", **{"is": "I-100"})
        with mock.patch.object(L, "kart_oku", side_effect=RuntimeError("bozuk")) as km, \
                mock.patch.object(niyet, "son_baglam", return_value=""):
            r = L.is_coz(self.sd, OTURUM, "G-1")
        km.assert_called_once_with(self.sd, "G-1")
        self.assertEqual(r, (None, "kart-isiz"))  # oturumda da iş yoksa mevcut dönüş

    def test_k1_hata_kart_okunamaz_istisna_firlatmaz_niyete_duser(self):
        with mock.patch.object(L, "kart_oku", side_effect=RuntimeError("bozuk")),                 mock.patch.object(niyet, "son_baglam", return_value="I-300"):
            self.assertEqual(L.is_coz(self.sd, OTURUM, "G-1"), ("I-300", None))

    def test_k1_gecersiz_sd_istisna_firlatmaz(self):
        r = L.is_coz(None, OTURUM, "G-1")
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 2)

    def test_k1_bozuk_oturum_json_istisna_firlatmaz(self):
        self.yaz("oturumlar", f"{OTURUM}.json", icerik="{bozuk")
        with mock.patch.object(niyet, "son_baglam", return_value=""):
            r = L.is_coz(self.sd, OTURUM, "-")
        self.assertIsNone(r[0] if r[0] != "-" else None)
        self.assertTrue(r[1])


class TestTekFonksiyon(_Ortak):
    def test_k2_kopya_mantik_kalmadi(self):
        for modul, ad in ((hook, "_kart_isi"), (hook, "_oturum_isi"), (MAL, "_tur_isi")):
            f = getattr(modul, ad, None)
            if f is None:
                continue
            self.assertIn("is_coz", inspect.getsource(f), f"{modul.__name__}.{ad} is_coz'a delege etmiyor")

    def test_k2_hook_ve_maliyet_is_coz_kullanir(self):
        self.assertIn("is_coz", inspect.getsource(hook))
        self.assertIn("is_coz", inspect.getsource(MAL))

    def test_k2_maliyet_tur_bagsiz_satira_neden_yazar(self):
        r = self.maliyet_tur()
        self.assertEqual(r.get("atif_nedeni"), "oturum-isiz")
        self.assertNotIn(r.get("is"), ("I-001", "I-100"))

    def test_k2_maliyet_tur_bagli_satirda_is_var_neden_yok(self):
        self.oturum(**{"is": "I-007"})
        r = self.maliyet_tur()
        self.assertEqual(r["is"], "I-007")
        self.assertFalse(r.get("atif_nedeni"))

    def test_k2_maliyet_tur_kart_oturumdan_once(self):
        self.oturum(**{"is": "I-007"})
        self.kart("G-9", **{"is": "I-050"})
        self.yaz("oturumlar", f"ajan_{AID}.json", icerik={"gorev": "G-9", "surec": "is", "ajan": "orkestra:isci"})
        r = self.maliyet_tur(AID)
        self.assertEqual(r["is"], "I-050")

    def test_k2_stop_zaman_satiri_bagsiz_neden(self):
        _jsonl_yaz(self.tr, [
            {"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"role": "user", "content": "selam"}},
            {"type": "assistant", "timestamp": "2026-10-14T10:00:03Z",
             "message": {"id": "m1", "model": "claude-haiku-5-5", "content": [{"type": "text", "text": "tamam"}],
                         "usage": {"input_tokens": 10, "output_tokens": 5}}}])
        self.kos(hook.stop)
        s = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].get("atif_nedeni"), "oturum-isiz")

    def test_k2_stop_zaman_satiri_bagli_is(self):
        self.oturum(**{"is": "I-004"})
        _jsonl_yaz(self.tr, [
            {"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"role": "user", "content": "selam"}},
            {"type": "assistant", "timestamp": "2026-10-14T10:00:03Z",
             "message": {"id": "m1", "model": "claude-haiku-5-5", "content": [{"type": "text", "text": "tamam"}],
                         "usage": {"input_tokens": 10, "output_tokens": 5}}}])
        self.kos(hook.stop)
        s = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]
        self.assertEqual(s[0]["is"], "I-004")
        self.assertFalse(s[0].get("atif_nedeni"))

    def test_k2_subagent_stop_kart_isi_onceliklidir(self):
        self.oturum(**{"is": "I-004"})
        self.kart("G-7", **{"is": "I-070"})
        _jsonl_yaz(self.atr, [
            {"type": "user", "timestamp": "2026-10-14T10:00:00Z",
             "message": {"role": "user", "content": "#GOREV:G-7 #SUREC:is\nişi yap"}},
            {"type": "assistant", "timestamp": "2026-10-14T10:02:00Z",
             "message": {"id": "m1", "model": "claude-haiku-5-5", "content": [{"type": "text", "text": "ok"}],
                         "usage": {"input_tokens": 10, "output_tokens": 5}}}])
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2", "agent_transcript_path": self.atr})
        s = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "alt"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["is"], "I-070")


class TestAtifOlayi(_Ortak):
    def _bagla_cli(self, is_id):
        ISL._oturumu_bagla(self.sd, is_id)

    def test_k3_cli_baglanma_tek_atif_olayi(self):
        self.bagsiz_maliyet(2)
        isid = self.is_ac()
        self._bagla_cli(isid)
        ev = self.jl("atif.jsonl")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["oturum"], OTURUM)
        self.assertEqual(ev[0]["is"], isid)
        self.assertTrue(ev[0].get("zaman"))
        self.assertTrue(ev[0].get("kaynak"))

    def test_k3_ayni_oturum_is_tekrar_yazilmaz(self):
        self.bagsiz_maliyet(2)
        isid = self.is_ac()
        self._bagla_cli(isid)
        self._bagla_cli(isid)
        self.assertEqual(len(self.jl("atif.jsonl")), 1)

    def test_k3_baska_ise_baglaninca_yeni_olay(self):
        self.bagsiz_maliyet(1)
        a = self.is_ac("is1")
        b = self.is_ac("is2")
        self._bagla_cli(a)
        self._bagla_cli(b)
        self.assertEqual([e["is"] for e in self.jl("atif.jsonl")], [a, b])

    def test_k3_ham_maliyet_defteri_degismez(self):
        self.bagsiz_maliyet(3)
        yol = os.path.join(self.sd, "maliyet.jsonl")
        once = open(yol, "rb").read()
        self._bagla_cli(self.is_ac())
        self.assertEqual(open(yol, "rb").read(), once)

    def test_k3_bagsiz_satir_yoksa_olay_yok(self):
        isid = self.is_ac()
        self._bagla_cli(isid)
        self.assertEqual(self.jl("atif.jsonl"), [])

    def test_k3_baska_oturumun_bagsiz_satiri_sayilmaz(self):
        _jsonl_yaz(os.path.join(self.sd, "maliyet.jsonl"),
                   [{"v": 1, "zaman": "2026-10-16T10:00:00+03:00", "oturum": "baska-oturum", "gorev": "-", "is": None,
                     "maliyet_usd": 0.01, "kaynak": "tur"}])
        self._bagla_cli(self.is_ac())
        self.assertEqual(self.jl("atif.jsonl"), [])

    def test_k3_zaten_isli_satir_sayilmaz(self):
        _jsonl_yaz(os.path.join(self.sd, "maliyet.jsonl"),
                   [{"v": 1, "zaman": "2026-10-16T10:00:00+03:00", "oturum": OTURUM, "gorev": "-", "is": "I-001",
                     "maliyet_usd": 0.01, "kaynak": "tur"}])
        self._bagla_cli(self.is_ac())
        self.assertEqual(self.jl("atif.jsonl"), [])

    def test_k3_hook_otomatik_baglama_atif_yazar(self):
        self.bagsiz_maliyet(2)
        isid = self.is_ac()
        sonuc = hook._otomatik_is_ac(self.sd, OTURUM, "deneme istegi", proje=self.proje, is_id=isid)
        self.assertTrue(sonuc)
        ev = self.jl("atif.jsonl")
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["oturum"], ev[0]["is"]), (OTURUM, isid))
        hook._otomatik_is_ac(self.sd, OTURUM, "deneme istegi", proje=self.proje, is_id=isid)
        self.assertEqual(len(self.jl("atif.jsonl")), 1)

    def test_k3_atif_hatasi_baglamayi_bozmaz(self):
        self.bagsiz_maliyet(1)
        isid = self.is_ac()
        with mock.patch.object(L, "jsonl_ekle", side_effect=OSError("disk")):
            try:
                self._bagla_cli(isid)
            except OSError as e:
                self.fail(f"atif hatasi baglamayi dusurdu: {e}")
        with open(os.path.join(self.sd, "oturumlar", f"{OTURUM}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("is"), isid)


if __name__ == "__main__":
    unittest.main()
