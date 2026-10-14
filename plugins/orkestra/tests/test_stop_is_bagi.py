"""G-008: Stop kancası ve iş bağı. `python -m pytest plugins/orkestra/tests/test_stop_is_bagi.py -q`

(a) stop() oturum dosyasındaki mevcut anahtarları (iş bağı dahil) ezmez; geçici `is_<oturum>.json` yan dosyası yazılmaz,
    eski yan dosya varsa bağ kaybolmaz.
(b) Stop kancası, tamamlanma bildirimi gelmemiş arka plan görevi varken niyet 'tur' olayına arka_plan=True yazar.
(c) session_start bağlamı 1800'e kırpılırken asılı ajan uyarısı ve onay metni korunur.
Hepsi geçici projede koşar; gerçek ~/.claude ya da proje durum dizinine yazılmaz.
"""
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "stop-is-bagi-oturum"


def _jsonl(yol, satirlar, ekle=False):
    with open(yol, "a" if ekle else "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _kullanici(metin):
    return {"type": "user", "timestamp": "2026-10-13T10:00:00Z", "message": {"role": "user", "content": metin}}


def _baslat_arac(arac_id, ad="Agent", arka_plan=True):
    giris = {"description": "x", "prompt": "y"} if ad == "Agent" else {"command": "sleep 1"}
    if arka_plan is not None:
        giris["run_in_background"] = arka_plan
    return {"type": "assistant", "timestamp": "2026-10-13T10:00:01Z",
            "message": {"id": "m-" + arac_id, "model": "claude-haiku-5-5", "content": [{"type": "tool_use", "id": arac_id, "name": ad, "input": giris}],
                        "usage": {"input_tokens": 1, "output_tokens": 1}}}


def _baslatildi_sonucu(arac_id, gorev_id):
    return {"type": "user", "timestamp": "2026-10-13T10:00:02Z",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": arac_id,
                                                      "content": f"Command running in background with ID: {gorev_id}. Output is being written to: x"}]}}


def _bildirim(arac_id, gorev_id, durum="completed"):
    return _kullanici(f"<task-notification>\n<task-id>{gorev_id}</task-id>\n<tool-use-id>{arac_id}</tool-use-id>\n"
                      f"<output-file>x</output-file>\n<status>{durum}</status>\n<summary>bitti</summary>\n</task-notification>")


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_stopis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        self.niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", self.niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(self.niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def calistir(self, fn, girdi):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            fn(g)
        return buf.getvalue()

    def oturum_yolu(self):
        return os.path.join(self.sd, "oturumlar", OTURUM + ".json")


class StopOfsetAnahtarlari(_Ortak):
    def test_stop_mevcut_anahtarlari_korur(self):
        _jsonl(self.tr, [_kullanici("merhaba")])
        onceki = {"ofset": 0, "baglam": "b", "is": "I-001", "is_baglanma": "2026-10-13T09:00:00+03:00",
                  "is_gecmis": [{"is": "I-001", "zaman": "2026-10-13T09:00:00+03:00"}], "gorev": "G-9", "ozel": {"a": 1}}
        with open(self.oturum_yolu(), "w", encoding="utf-8") as f:
            json.dump(onceki, f)
        self.calistir(hook.stop, {})
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            o = json.load(f)
        for k in ("is", "is_baglanma", "is_gecmis", "gorev", "ozel"):
            self.assertEqual(o.get(k), onceki[k], f"{k} stop() sonrası korunmalı")
        self.assertEqual(o["ofset"], os.path.getsize(self.tr))  # ofset yine ilerler
        self.assertIn("guncelleme", o)
        self.assertIn("baglam", o)

    def test_stop_ikinci_cagrida_da_korur(self):
        _jsonl(self.tr, [_kullanici("bir")])
        with open(self.oturum_yolu(), "w", encoding="utf-8") as f:
            json.dump({"is": "I-007"}, f)
        self.calistir(hook.stop, {})
        _jsonl(self.tr, [_kullanici("iki")], ekle=True)
        self.calistir(hook.stop, {})
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            o = json.load(f)
        self.assertEqual(o["is"], "I-007")
        self.assertEqual(o["ofset"], os.path.getsize(self.tr))

    def test_stop_dosya_yokken_ve_bozukken_calisir(self):
        _jsonl(self.tr, [_kullanici("merhaba")])
        self.calistir(hook.stop, {})
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            self.assertEqual(sorted(json.load(f)), ["baglam", "guncelleme", "ofset"])
        with open(self.oturum_yolu(), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.calistir(hook.stop, {})
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            self.assertIn("ofset", json.load(f))


class StopArkaPlan(_Ortak):
    def tur_olaylari(self):
        return [r for r in L.jsonl_oku(self.niyet_yolu) if r.get("tur") == "tur" and r.get("oturum") == OTURUM]

    def stop_ve_son_tur(self):
        self.calistir(hook.stop, {})
        olaylar = self.tur_olaylari()
        self.assertTrue(olaylar, "stop() 'tur' niyet olayı yazmalı")
        return olaylar[-1]

    def test_acik_arka_plan_ajani_true(self):
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslatildi_sonucu("toolu_A", "ag1")])
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)

    def test_acik_arka_plan_bash_true(self):
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_B", ad="Bash"), _baslatildi_sonucu("toolu_B", "bsh1")])
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)

    def test_tamamlanan_arka_plan_gorevi_yok(self):
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslatildi_sonucu("toolu_A", "ag1"),
                         _bildirim("toolu_A", "ag1")])
        self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))

    def test_arka_plan_olmayan_arac_yok(self):
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A", arka_plan=False), _baslat_arac("toolu_B", ad="Bash", arka_plan=None)])
        self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))

    def test_iki_gorevden_biri_bitti_hala_true(self):
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslat_arac("toolu_B", ad="Bash"),
                         _baslatildi_sonucu("toolu_A", "ag1"), _baslatildi_sonucu("toolu_B", "bsh1"), _bildirim("toolu_A", "ag1")])
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)

    def test_bos_ve_eksik_transkript_true_degil(self):
        self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))
        self.tr = os.path.join(self.proje, "yok.jsonl")
        self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))

    def test_ofset_ilerledikten_sonra_durum_korunur(self):
        # görev ilk turda başlar; sonraki turlarda yeni satırlar ofsetin ötesinde olsa da görev hâlâ açık sayılır, bildirimle kapanır
        _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslatildi_sonucu("toolu_A", "ag1")])
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)
        _jsonl(self.tr, [_kullanici("başka bir şey")], ekle=True)
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)
        _jsonl(self.tr, [_bildirim("toolu_A", "ag1")], ekle=True)
        self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))

    def test_terminal_durumlar_gorevi_kapatir(self):
        for durum in ("failed", "killed", "stopped"):
            with self.subTest(durum=durum):
                _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslatildi_sonucu("toolu_A", "ag1"),
                                 _bildirim("toolu_A", "ag1", durum=durum)])
                self.assertFalse(self.stop_ve_son_tur().get("arka_plan", False))
                with open(self.oturum_yolu(), encoding="utf-8") as f:
                    self.assertFalse(json.load(f).get("acik_gorevler"), "görev açık listeden çıkmalı")
                os.remove(self.oturum_yolu())  # alt test bağımsız başlasın (ofset sıfırlanır)

    def test_terminal_olmayan_durum_kapatmaz(self):
        for durum in ("running", "pending"):
            with self.subTest(durum=durum):
                _jsonl(self.tr, [_kullanici("başlat"), _baslat_arac("toolu_A"), _baslatildi_sonucu("toolu_A", "ag1"),
                                 _bildirim("toolu_A", "ag1", durum=durum)])
                self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)
                os.remove(self.oturum_yolu())

    def test_acik_gorevler_ust_sinirli_en_yeniler_kalir(self):
        satirlar = [_kullanici("başlat")] + [_baslat_arac(f"toolu_{i:02d}") for i in range(60)]
        _jsonl(self.tr, satirlar)
        self.assertIs(self.stop_ve_son_tur().get("arka_plan"), True)
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            liste = json.load(f)["acik_gorevler"]
        self.assertLessEqual(len(liste), 50)
        self.assertIn("toolu_59", liste)
        self.assertNotIn("toolu_00", liste)

    def test_transkript_okuma_istisnasi_kancayi_cokertmez(self):
        _jsonl(self.tr, [_kullanici("merhaba")])
        with mock.patch.object(L, "transkript_oku", side_effect=PermissionError("izin yok")):
            self.calistir(hook.stop, {})  # SystemExit beklenir; başka istisna testi düşürür
        self.assertTrue(self.tur_olaylari(), "okuma hatasında da 'tur' niyet olayı yazılmalı")


class IsYanDosyasi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def ac(self, alt="is1"):
        r = self.cli("is", "ac", "Deneme işi", "--klasor", os.path.join(self.proje, alt), "--etiket", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def oturumlar(self):
        return os.path.join(self.sd, "oturumlar")

    def yan_yol(self):
        return os.path.join(self.oturumlar(), "is_" + TC.OTURUM + ".json")

    def ana_yol(self):
        return os.path.join(self.oturumlar(), TC.OTURUM + ".json")

    def stop_calistir(self):
        r = TC.kos([TC.HOOK, "Stop"], self.proje, ortam={"HOME": self.proje, "USERPROFILE": self.proje},
                   stdin=json.dumps({"session_id": TC.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "Stop"}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_is_ac_yan_dosya_yazmaz_ve_ana_dosyaya_baglar(self):
        i = self.ac()
        self.assertFalse(os.path.exists(self.yan_yol()), "is_<oturum>.json artık yazılmamalı")
        with open(self.ana_yol(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["is"], i)
        self.assertIn(i, self.cli("is", "aktif").stdout)

    def test_is_devam_yan_dosya_yazmaz(self):
        self.ac()
        self.ac("is2")
        self.assertEqual(self.cli("is", "devam", "I-001").returncode, 0)
        self.assertFalse(os.path.exists(self.yan_yol()))
        self.assertIn("I-001", self.cli("is", "aktif").stdout)

    def test_stop_hook_sonrasi_bag_ana_dosyada_kalir(self):
        i = self.ac()
        self.stop_calistir()
        self.assertFalse(os.path.exists(self.yan_yol()))
        with open(self.ana_yol(), encoding="utf-8") as f:
            o = json.load(f)
        self.assertEqual(o.get("is"), i, "Stop kancası iş bağını silmemeli")
        self.assertIn("ofset", o)
        self.assertIn(i, self.cli("is", "aktif").stdout)
        g = self.kart()
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["is"], i)

    def test_eski_yan_dosyadan_bag_okunur_aktif_ve_kart(self):
        i = self.ac()
        os.remove(self.ana_yol())  # eski sürüm: bağ yalnız yan dosyada
        with open(self.yan_yol(), "w", encoding="utf-8") as f:
            json.dump({"is": i}, f)
        self.assertIn(i, self.cli("is", "aktif").stdout)
        g = self.kart()
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["is"], i)

    def test_eski_yan_dosya_stop_hook_sonrasi_bag_kaybolmaz(self):
        i = self.ac()
        with open(self.ana_yol(), "w", encoding="utf-8") as f:
            json.dump({"ofset": 3}, f)  # eski Stop hook'unun ezdiği hâl
        with open(self.yan_yol(), "w", encoding="utf-8") as f:
            json.dump({"is": i}, f)
        self.stop_calistir()
        self.assertIn(i, self.cli("is", "aktif").stdout)

    def test_devam_eski_yan_dosyayi_yeniden_yazmaz_ve_yeni_bagi_ana_dosyaya_koyar(self):
        self.ac()
        self.ac("is2")
        os.remove(self.ana_yol())
        eski = json.dumps({"is": "I-001"})
        with open(self.yan_yol(), "w", encoding="utf-8") as f:
            f.write(eski)
        self.assertEqual(self.cli("is", "devam", "I-002").returncode, 0)
        with open(self.yan_yol(), encoding="utf-8") as f:
            self.assertEqual(f.read(), eski, "eski yan dosya yeniden yazılmamalı")
        with open(self.ana_yol(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["is"], "I-002")
        self.assertIn("I-002", self.cli("is", "aktif").stdout)  # eski yan dosya yeni bağı gölgelememeli

    def test_hic_bag_yoksa_aktif_bos(self):
        self.assertIn("bağlı iş yok", self.cli("is", "aktif").stdout)
        self.assertFalse(os.path.exists(self.yan_yol()))


class SessionStartKesim(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_ssk_")
        self.ev = tempfile.mkdtemp(prefix="ork_ev_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = TC.kos([TC.CLI, "baslat"], self.proje, ortam={"HOME": self.ev, "USERPROFILE": self.ev})
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def asili_yaz(self, aid="asili1", dk=45):
        z = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")
        with open(os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"zaman": z, "oturum": OTURUM, "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}, f)

    def session_start(self, rapor_tekrar=60):
        bayat = {"farkli": 12, "kaynakta_commitsiz": True, "kaynak": "x" * 300}
        rapor = {"okunmamis_rapor": "ruya_20261013_1500.md" * rapor_tekrar, "zamani_geldi": False, "calisiyor": False}
        cikti = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(L, "bayatlik", return_value=bayat), \
                mock.patch.object(perspektif, "durum", return_value=rapor), contextlib.redirect_stdout(cikti):
            with self.assertRaises(SystemExit):
                hook.session_start({"session_id": OTURUM, "cwd": self.proje})
        return json.loads(cikti.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_uzun_baglamda_asili_uyari_kesilmez(self):
        self.asili_yaz()
        m = self.session_start()
        self.assertLessEqual(len(m), 1800)
        self.assertIn("bitmeyen ajan", m)
        self.assertIn("orkestra:isci-t2 G-001 (45 dk)", m)
        self.assertIn("TaskStop", m)
        self.assertIn("Orkestra bu projede açık", m)

    def test_asili_uyari_dusuk_oncelikli_satirlardan_once(self):
        self.asili_yaz()
        m = self.session_start(rapor_tekrar=3)  # kısa bağlam: hepsi görünür, sıra denetlenir
        self.assertIn("UYARI: çalışan orkestra kopyası", m)
        self.assertIn("Perspektif raporu hazır", m)
        self.assertLess(m.index("bitmeyen ajan"), m.index("UYARI: çalışan orkestra kopyası"))
        self.assertLess(m.index("bitmeyen ajan"), m.index("Perspektif raporu hazır"))

    def test_uzun_baglamda_asili_uyari_ve_onay_metni_birlikte_saglam(self):
        self.asili_yaz()
        for _ in range(40):
            k = onay.iste(self.sd, "Çok uzun bir başlık " * 10, "m", tur="perspektif")
            onay.karar_ver(self.sd, k["id"], "onay")
        om = onay.baglam_metni(self.sd, OTURUM, "SessionStart")
        self.assertGreater(len(om), 800)
        m = self.session_start()
        self.assertLessEqual(len(m), 1800)
        self.assertTrue(m.endswith(om), "onay metni bütün kalmalı")
        self.assertIn("/orkestra:onay ile uygula", m)
        self.assertIn("bitmeyen ajan", m)
        self.assertIn("Orkestra bu projede açık", m)

    def test_asili_yokken_uyari_yok(self):
        m = self.session_start()
        self.assertNotIn("bitmeyen ajan", m)
        self.assertLessEqual(len(m), 1800)

    def test_kisa_baglamda_hicbir_sey_kesilmez(self):
        self.asili_yaz()
        m = self.session_start(rapor_tekrar=3)
        self.assertIn("bitmeyen ajan", m)
        self.assertIn("Orkestra bu projede açık", m)
        self.assertIn("Perspektif raporu hazır", m)


if __name__ == "__main__":
    unittest.main()
