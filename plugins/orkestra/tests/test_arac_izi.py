"""G-156 / I-030 P4-P5: araç düzeyi span kaydı (zaman.jsonl tur='arac') ve istek 'ne' alanı.

`py -3.13 -m pytest plugins/orkestra/tests/test_arac_izi.py -q -p no:cacheprovider`

- K2 stop / subagent_stop her araç çağrısı için tur='arac' satırı yazar: arac, span_id, ust_span_id, istek_id,
  sure_ms (tool_use -> tool_result zaman farkı), giris/cikis/onbellek_okuma/onbellek_yazma (aynı mesajdaki araç
  sayısına paylaştırılmış, toplam = mesaj usage'ı), tahmin=true. Yazım hatası hook'u düşürmez.
- K3 user_prompt_submit gunluk 'istek' satırına 'ne' ekler (ilk cümle, en çok 120 karakter, tek satır);
  boş ya da sistem iletisinde yazılmaz.
- K4 100 araçlı sentetik transkriptte stop makul sürede biter, araç satırları toplu yazılır.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "abcd1234-aaaa-bbbb-cccc-333344445555"
AID = "ajan-kimlik-1"
TOKEN_ALANLARI = ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")


def _jsonl(yol, satirlar, mod="w"):
    with open(yol, mod, encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _kullanici(metin, ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": metin}}


def _asistan(ts, mid, araclar, usage=None, ayri_satir=False):
    """araclar: [(tool_use_id, ad)]. usage None ise usage alanı yazılmaz."""
    icerik = [{"type": "text", "text": "tamam"}]
    for tid, ad in araclar:
        icerik.append({"type": "tool_use", "id": tid, "name": ad, "input": {"file_path": "/tmp/x.txt", "content": "a"}})
    msg = {"id": mid, "model": "claude-haiku-5-5", "content": icerik}
    if usage is not None:
        msg["usage"] = usage
    return {"type": "assistant", "timestamp": ts, "message": msg}


def _sonuc(ts, tid, hata=False):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": "ok", "is_error": hata}]}}


USAGE = {"input_tokens": 100, "output_tokens": 40, "cache_read_input_tokens": 31, "cache_creation_input_tokens": 7}


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_arac_")
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

    def jl(self, ad):
        return L.jsonl_oku(os.path.join(self.sd, ad))

    def prompt(self, metin="merhaba dünya"):
        self.kos(hook.user_prompt_submit, {"prompt": metin})

    def araclar(self, **filtre):
        return [r for r in self.jl("zaman.jsonl") if r.get("tur") == "arac"
                and all(r.get(k) == v for k, v in filtre.items())]

    def ana_stop(self, satirlar):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-16T10:00:00Z")] + satirlar)
        self.prompt()
        self.kos(hook.stop)

    def alt_stop(self, satirlar):
        _jsonl(self.atr, [_kullanici("#GOREV:G-007 #SUREC:is\nişi yap", "2026-10-16T10:00:00Z")] + satirlar)
        self.prompt()
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2",
                                      "agent_transcript_path": self.atr})


class AracSatiri(_Ortak):
    def test_k2_her_arac_cagrisi_icin_satir_ve_alanlar(self):
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read"), ("t2", "Bash")], USAGE),
            _sonuc("2026-10-16T10:00:07.500Z", "t1"),
            _sonuc("2026-10-16T10:00:12Z", "t2"),
        ])
        s = self.araclar()
        self.assertEqual(sorted(r["arac"] for r in s), ["Bash", "Read"])
        for r in s:
            for alan in ("span_id", "ust_span_id", "istek_id", "sure_ms") + TOKEN_ALANLARI:
                self.assertIn(alan, r, f"{alan} yok: {r}")
            self.assertTrue(r["span_id"])
            self.assertEqual(r["istek_id"], "abcd1234-0001")
            self.assertIs(r["tahmin"], True)
            self.assertEqual(r["v"], 1)

    def test_k2_sure_tool_use_ile_tool_result_farki(self):
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read"), ("t2", "Bash")], USAGE),
            _sonuc("2026-10-16T10:00:07.500Z", "t1"),
            _sonuc("2026-10-16T10:00:12Z", "t2"),
        ])
        s = {r["arac"]: r for r in self.araclar()}
        self.assertEqual(s["Read"]["sure_ms"], 2500)
        self.assertEqual(s["Bash"]["sure_ms"], 7000)

    def test_k2_span_kimlikleri_benzersiz_ve_tura_bagli(self):
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read"), ("t2", "Bash")], USAGE),
            _sonuc("2026-10-16T10:00:06Z", "t1"), _sonuc("2026-10-16T10:00:07Z", "t2"),
        ])
        s = self.araclar()
        self.assertEqual(len({r["span_id"] for r in s}), 2)
        ana = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]
        self.assertEqual(len(ana), 1)
        for r in s:
            self.assertEqual(r["ust_span_id"], ana[0]["span_id"])
            self.assertNotEqual(r["span_id"], ana[0]["span_id"])

    def test_k2_token_paylastirma_toplami_mesaj_usage(self):
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read"), ("t2", "Bash"), ("t3", "Grep")], USAGE),
            _sonuc("2026-10-16T10:00:06Z", "t1"), _sonuc("2026-10-16T10:00:07Z", "t2"), _sonuc("2026-10-16T10:00:08Z", "t3"),
        ])
        s = self.araclar()
        self.assertEqual(len(s), 3)
        beklenen = {"giris": 100, "cikis": 40, "onbellek_okuma": 31, "onbellek_yazma": 7}
        for alan, n in beklenen.items():
            self.assertEqual(sum(r[alan] for r in s), n, alan)  # kalan kaybolmaz (31 / 3 tam bölünmez)
            for r in s:
                self.assertIsInstance(r[alan], int)
                self.assertGreaterEqual(r[alan], 0)
        # paylaşım dengeli: en büyük ile en küçük fark en çok 1
        for alan in beklenen:
            v = [r[alan] for r in s]
            self.assertLessEqual(max(v) - min(v), 1, alan)

    def test_k2_iki_mesaj_ayri_paylastirilir(self):
        u2 = {"input_tokens": 9, "output_tokens": 3, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], USAGE),
            _sonuc("2026-10-16T10:00:06Z", "t1"),
            _asistan("2026-10-16T10:00:07Z", "m2", [("t2", "Bash"), ("t3", "Bash")], u2),
            _sonuc("2026-10-16T10:00:08Z", "t2"), _sonuc("2026-10-16T10:00:09Z", "t3"),
        ])
        s = self.araclar()
        self.assertEqual(len(s), 3)
        self.assertEqual(sum(r["giris"] for r in s), 109)
        self.assertEqual(sum(r["cikis"] for r in s), 43)
        tek = [r for r in s if r["arac"] == "Read"][0]
        self.assertEqual(tek["giris"], 100)  # tek araçlı mesajda tamamı o araca

    def test_k2_ayni_mesaj_kimligi_iki_satira_bolunmus_usage_iki_kez_sayilmaz(self):
        self.ana_stop([
            _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], USAGE),
            _asistan("2026-10-16T10:00:05Z", "m1", [("t2", "Bash")], USAGE),
            _sonuc("2026-10-16T10:00:06Z", "t1"), _sonuc("2026-10-16T10:00:07Z", "t2"),
        ])
        s = self.araclar()
        self.assertEqual(len(s), 2)
        self.assertEqual(sum(r["giris"] for r in s), 100)
        self.assertEqual(sum(r["cikis"] for r in s), 40)

    def test_k2_usage_yok_token_sifir_satir_yine_yazilir(self):
        self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], None), _sonuc("2026-10-16T10:00:06Z", "t1")])
        s = self.araclar()
        self.assertEqual(len(s), 1)
        for alan in TOKEN_ALANLARI:
            self.assertEqual(s[0][alan], 0)
        self.assertIs(s[0]["tahmin"], True)

    def test_k2_sonucu_gelmeyen_arac_satir_yazar_sure_negatif_degil(self):
        self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Bash")], USAGE)])
        s = self.araclar()
        self.assertEqual(len(s), 1)
        self.assertTrue(s[0]["sure_ms"] is None or s[0]["sure_ms"] >= 0)

    def test_k2_hatali_arac_sonucu_da_satir_uretir(self):
        self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Bash")], USAGE),
                       _sonuc("2026-10-16T10:00:06Z", "t1", hata=True)])
        s = self.araclar()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["sure_ms"], 1000)

    def test_k2_arac_olmayan_mesaj_arac_satiri_uretmez(self):
        self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [], USAGE)])
        self.assertEqual(self.araclar(), [])
        self.assertEqual(len([r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"]), 1)

    def test_k2_ayni_tur_ikinci_stop_ayni_aracı_tekrar_yazmaz(self):
        self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], USAGE), _sonuc("2026-10-16T10:00:06Z", "t1")])
        self.assertEqual(len(self.araclar()), 1)
        self.kos(hook.stop)  # yeni içerik yok
        self.assertEqual(len(self.araclar()), 1)
        _jsonl(self.tr, [_asistan("2026-10-16T10:01:00Z", "m2", [("t2", "Edit")], USAGE),
                         _sonuc("2026-10-16T10:01:02Z", "t2")], mod="a")
        self.kos(hook.stop)
        s = self.araclar()
        self.assertEqual(sorted(r["arac"] for r in s), ["Edit", "Read"])
        self.assertEqual(len({r["span_id"] for r in s}), 2)

    def test_k2_subagent_stop_arac_satiri_alt_tura_baglanir(self):
        self.alt_stop([
            _asistan("2026-10-16T10:00:10Z", "m1", [("t1", "Write")], USAGE),
            _sonuc("2026-10-16T10:00:13Z", "t1"),
        ])
        s = self.araclar()
        self.assertEqual(len(s), 1)
        alt = [r for r in self.jl("zaman.jsonl") if r.get("tur") == "alt"]
        self.assertEqual(len(alt), 1)
        self.assertEqual(s[0]["arac"], "Write")
        self.assertEqual(s[0]["sure_ms"], 3000)
        self.assertEqual(s[0]["ust_span_id"], alt[0]["span_id"])
        self.assertEqual(s[0]["istek_id"], "abcd1234-0001")
        self.assertIs(s[0]["tahmin"], True)
        self.assertEqual(s[0]["giris"], 100)

    def test_k2_istek_yokken_cokmez_ve_istek_id_yazilmaz(self):
        _jsonl(self.tr, [_kullanici("m", "2026-10-16T10:00:00Z"),
                         _asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], USAGE), _sonuc("2026-10-16T10:00:06Z", "t1")])
        self.kos(hook.stop)  # prompt yok -> istek_id yok
        for r in self.araclar():
            self.assertFalse(r.get("istek_id"))
        self.assertTrue([r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"])

    def test_k2_yazim_hatasi_hook_u_dusurmez_ana_satir_korunur(self):
        gercek = L.jsonl_ekle

        def kirik(yol, kayit, *a, **k):
            kayitlar = kayit if isinstance(kayit, list) else [kayit]
            if any(isinstance(r, dict) and r.get("tur") == "arac" for r in kayitlar):
                raise OSError("disk dolu (test)")
            return gercek(yol, kayit, *a, **k)

        yamalar = [mock.patch.object(L, "jsonl_ekle", side_effect=kirik)]
        for ad in dir(L):  # toplu yazım için ayrı bir işlev eklenmişse onu da kır
            if "toplu" in ad and callable(getattr(L, ad)) and ad != "jsonl_ekle":
                yamalar.append(mock.patch.object(L, ad, side_effect=OSError("disk dolu (test)")))
        with contextlib.ExitStack() as st:
            for y in yamalar:
                st.enter_context(y)
            self.ana_stop([_asistan("2026-10-16T10:00:05Z", "m1", [("t1", "Read")], USAGE), _sonuc("2026-10-16T10:00:06Z", "t1")])
        self.assertTrue([r for r in self.jl("zaman.jsonl") if r.get("tur") == "ana"], "ana zaman satırı kayboldu")
        self.assertTrue([r for r in self.jl("maliyet.jsonl")], "maliyet satırı kayboldu")


class NeAlani(_Ortak):
    def istek(self):
        s = [r for r in self.jl("gunluk.jsonl") if r.get("tur") == "istek"]
        self.assertEqual(len(s), 1)
        return s[0]

    def test_k3_ilk_cumle(self):
        self.prompt("Bu hatayı düzelt. Sonra testleri çalıştır ve raporla.")
        r = self.istek()
        self.assertIn("Bu hatayı düzelt", r["ne"])
        self.assertNotIn("Sonra", r["ne"])
        self.assertEqual(r["metin"], "Bu hatayı düzelt. Sonra testleri çalıştır ve raporla.")  # mevcut alan değişmez

    def test_k3_soru_ve_unlem_cumle_sonu(self):
        self.prompt("Bu neden çöküyor? Bakar mısın")
        self.assertNotIn("Bakar", self.istek()["ne"])
        self.assertIn("neden çöküyor", self.istek()["ne"])

    def test_k3_satir_sonlari_bosluga_cevrilir_tek_satir(self):
        self.prompt("birinci satır\nikinci satır\r\nüçüncü")
        ne = self.istek()["ne"]
        self.assertNotIn("\n", ne)
        self.assertNotIn("\r", ne)
        self.assertIn("birinci satır", ne)
        self.assertIn("ikinci satır", ne)

    def test_k3_en_cok_120_karakter(self):
        self.prompt("a" * 400)
        ne = self.istek()["ne"]
        self.assertGreater(len(ne), 0)
        self.assertLessEqual(len(ne), 120)

    def test_k3_tam_sinirda_kesilmez(self):
        self.prompt("b" * 120)
        self.assertEqual(self.istek()["ne"], "b" * 120)

    def test_k3_kisa_metin_aynen(self):
        self.prompt("merhaba dünya")
        self.assertEqual(self.istek()["ne"], "merhaba dünya")

    def test_k3_sistem_iletisinde_ne_yazilmaz(self):
        self.prompt("<task-notification>bitti. tamam.</task-notification>")
        self.assertFalse(self.istek().get("ne"))

    def test_k3_bos_ve_bosluk_iletisinde_ne_yazilmaz(self):
        self.prompt("   \n  ")
        self.assertFalse(self.istek().get("ne"))

    def test_k3_ne_istek_id_ile_ayni_satirda(self):
        self.prompt("Şunu yap.")
        r = self.istek()
        self.assertEqual(r["istek_id"], "abcd1234-0001")
        self.assertTrue(r["ne"])


class Performans(_Ortak):
    def _yuz_arac(self):
        satirlar = []
        for i in range(100):
            saniye = 5 + i
            ts = f"2026-10-16T10:{saniye // 60:02d}:{saniye % 60:02d}Z"
            ts2 = f"2026-10-16T10:{(saniye) // 60:02d}:{saniye % 60:02d}.500Z"
            satirlar.append(_asistan(ts, f"m{i}", [(f"t{i}", "Read")], USAGE))
            satirlar.append(_sonuc(ts2, f"t{i}"))
        return satirlar

    def test_k4_yuz_arac_hepsi_yazilir_ve_stop_makul_surede_biter(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-16T10:00:00Z")] + self._yuz_arac())
        self.prompt()
        t0 = time.perf_counter()
        self.kos(hook.stop)
        gecen = time.perf_counter() - t0
        s = self.araclar()
        self.assertEqual(len(s), 100)
        self.assertEqual(len({r["span_id"] for r in s}), 100)
        self.assertLess(gecen, 5.0, f"stop {gecen:.2f} sn")

    def test_k4_arac_satirlari_toplu_yazilir_tek_tek_degil(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-16T10:00:00Z")] + self._yuz_arac())
        self.prompt()
        gercek = L.jsonl_ekle
        cagri = []

        def say(yol, kayit, *a, **k):
            cagri.append(kayit)
            return gercek(yol, kayit, *a, **k)

        with mock.patch.object(L, "jsonl_ekle", side_effect=say):
            self.kos(hook.stop)
        tek_tek = [c for c in cagri if isinstance(c, dict) and c.get("tur") == "arac"]
        self.assertEqual(len(self.araclar()), 100)
        self.assertLessEqual(len(tek_tek), 1, f"{len(tek_tek)} ayrı jsonl_ekle çağrısı: toplu yazım bekleniyordu")


if __name__ == "__main__":
    unittest.main()
