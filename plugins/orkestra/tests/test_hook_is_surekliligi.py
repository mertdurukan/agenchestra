"""G-043: iş sürekliliği kancaları. `python -m pytest plugins/orkestra/tests/test_hook_is_surekliligi.py -q`

(C)  session_start: açık işler satırı (id, başlık, todo x/y, oturumlar.md son satırı) + devam yönergesi.
(D1) stop: işe bağlı oturumda kayda değer turda işin oturumlar.md'sine tek satır eklenir.
(D2) stop: oturum başına en çok bir kez bloklamayan hatırlatma (işe bağlı değil / todo.md güncellenmedi).
Hepsi geçici projede koşar; gerçek ~/.claude ya da proje durum dizinine yazılmaz.
"""
import contextlib
import datetime
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
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "abcdef1234567890-oturum"
KISA = OTURUM[:8]
HATIRLATMA_BAGSIZ = "bu sohbet bir işe bağlı değil"
SATIR_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (\S{8}) · (\d+) araç · \$(\d+\.\d{2}) · nerede kalındı: (.*)$")


def _jsonl(yol, satirlar, ekle=False):
    with open(yol, "a" if ekle else "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _tur_dokunuslu(n=1):
    """Kullanıcı mesajı + dosya yazan asistan turu (kayda değer)."""
    out = [{"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"role": "user", "content": "yap"}}]
    for i in range(n):
        out.append({"type": "assistant", "timestamp": "2026-10-14T10:00:01Z",
                    "message": {"id": f"m-{i}-{os.urandom(3).hex()}", "model": "claude-sonnet-5-5",
                                "content": [{"type": "tool_use", "id": f"t-{i}-{os.urandom(3).hex()}", "name": "Edit",
                                             "input": {"file_path": f"/x/dosya{i}.py"}}],
                                "usage": {"input_tokens": 1000, "output_tokens": 500}}})
    return out


def _tur_dokunussuz():
    return [{"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"role": "user", "content": "selam"}},
            {"type": "assistant", "timestamp": "2026-10-14T10:00:01Z",
             "message": {"id": "m-" + os.urandom(3).hex(), "model": "claude-sonnet-5-5",
                         "content": [{"type": "text", "text": "merhaba"}],
                         "usage": {"input_tokens": 10, "output_tokens": 5}}}]


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_issur_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    # --- yardımcılar
    def is_ac(self, baslik="Deneme işi", alt=None):
        alt = alt or ("is" + str(len(is_kaydi.is_liste(self.sd)) + 1))
        return is_kaydi.is_ac(self.sd, baslik, os.path.join(self.proje, alt))

    def oturum_yolu(self, oid=OTURUM):
        return os.path.join(self.sd, "oturumlar", oid + ".json")

    def oturum_yaz(self, **alanlar):
        with open(self.oturum_yolu(), "w", encoding="utf-8") as f:
            json.dump(alanlar, f)

    def oturum_oku(self):
        with open(self.oturum_yolu(), encoding="utf-8") as f:
            return json.load(f)

    def baglan(self, kayit, baglanma=None, **ek):
        o = {"is": kayit["id"], "is_baglanma": baglanma or L.simdi()}
        o.update(ek)
        self.oturum_yaz(**o)

    def oturumlar_md(self, kayit):
        return os.path.join(kayit["klasor"], "oturumlar.md")

    def md_oku(self, kayit):
        with open(self.oturumlar_md(kayit), encoding="utf-8") as f:
            return f.read()

    def todo_yaz(self, kayit, icerik):
        with open(os.path.join(kayit["klasor"], "todo.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)

    def calistir(self, fn, girdi=None):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi or {})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            fn(g)
        return buf.getvalue()

    def stop(self, tur, **girdi):
        """Transkripte turu ekler, stop() koşar, çıktıyı (dict ya da None) döndürür."""
        _jsonl(self.tr, tur, ekle=True)
        girdi.setdefault("last_assistant_message", "tamamlandı")
        cikti = self.calistir(hook.stop, girdi).strip()
        return json.loads(cikti) if cikti else None


# ============================================================ (C) session_start

class SessionStartAcikIsler(_Ortak):
    def session_start(self, rapor_tekrar=3):
        bayat = {"farkli": 12, "kaynakta_commitsiz": True, "kaynak": "x" * 300}
        rapor = {"okunmamis_rapor": "ruya_20261013_1500.md" * rapor_tekrar, "zamani_geldi": False, "calisiyor": False}
        cikti = io.StringIO()
        with mock.patch.object(L, "bayatlik", return_value=bayat), mock.patch.object(perspektif, "durum", return_value=rapor), \
                contextlib.redirect_stdout(cikti):
            with self.assertRaises(SystemExit):
                hook.session_start({"session_id": OTURUM, "cwd": self.proje})
        return json.loads(cikti.getvalue())["hookSpecificOutput"]["additionalContext"]

    def asili_yaz(self, aid="asili1", dk=45):
        z = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")
        with open(os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"zaman": z, "oturum": OTURUM, "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}, f)

    def kur_uc_is(self):
        a = self.is_ac("Birinci açık iş başlığı")
        b = self.is_ac("İkinci açık iş başlığı")
        k = self.is_ac("KAPALIISBASLIK kapatılan iş")
        self.todo_yaz(a, "# T\n\n- [x] bir\n- [ ] iki\n- [ ] üç\n")
        self.todo_yaz(b, "# T\n\n- [x] a\n- [x] b\n- [ ] c\n- [ ] d\n- [ ] e\n")
        with open(self.oturumlar_md(a), "a", encoding="utf-8", newline="\n") as f:
            f.write("- 2026-10-14 09:00 · aaaaaaaa · 2 araç · $0.10 · nerede kalındı: ESKISATIR_A\n"
                    "- 2026-10-14 10:00 · aaaaaaaa · 3 araç · $0.20 · nerede kalındı: SONSATIR_A\n\n")
        with open(self.oturumlar_md(b), "a", encoding="utf-8", newline="\n") as f:
            f.write("- SONSATIR_B kısa\n")
        is_kaydi.is_durum(self.sd, k["id"], "kapandi")
        return a, b, k

    def test_iki_acik_is_id_todo_ve_son_satir_gorunur_kapali_yok(self):
        a, b, k = self.kur_uc_is()
        m = self.session_start()
        satir = next((s for s in m.splitlines() if s.startswith("Açık işler:")), None)
        self.assertIsNotNone(satir, m)
        self.assertIn(a["id"], satir)
        self.assertIn(b["id"], satir)
        self.assertIn("Birinci açık iş", satir)
        self.assertIn("todo 1/3", satir)
        self.assertIn("todo 2/5", satir)
        self.assertIn("SONSATIR_A", satir)
        self.assertIn("SONSATIR_B", satir)
        self.assertNotIn("ESKISATIR_A", satir, "yalnız son dolu satır")
        self.assertNotIn("KAPALIISBASLIK", m)
        self.assertNotIn(k["id"], satir)

    def test_devam_yonergesi_tek_satir(self):
        self.kur_uc_is()
        m = self.session_start()
        yon = [s for s in m.splitlines() if "orkestra is devam <id>" in s]
        self.assertEqual(len(yon), 1)
        self.assertIn("orkestra is todo <id> --ekle", yon[0])
        self.assertIn("todo.md", yon[0])

    def test_kart_satirindan_sonra_gelir(self):
        self.kur_uc_is()
        kart = {"id": "G-001", "baslik": "Bir kart"}
        with mock.patch.object(L, "kartlar", return_value=[kart]), mock.patch.object(L, "kart_durumu_hesapla", return_value="isleniyor"):
            m = self.session_start()
        self.assertIn("Açık/bekleyen kartlar", m)
        self.assertLess(m.index("Açık/bekleyen kartlar"), m.index("Açık işler:"))

    def test_son_satir_ilk_80_karakter(self):
        a = self.is_ac("Uzun satır işi")
        uzun = "- " + "u" * 78 + "SONRASI_KESILMELI"
        with open(self.oturumlar_md(a), "a", encoding="utf-8", newline="\n") as f:
            f.write(uzun + "\n\n\n")
        m = self.session_start()
        self.assertIn(uzun[:80], m)
        self.assertNotIn("SONRASI_KESILMELI", m)

    def test_baslik_ilk_40_karakter(self):
        a = self.is_ac("B" * 40 + "BASLIKSONU")
        m = self.session_start()
        self.assertIn(a["id"] + " " + "B" * 40, m)
        self.assertNotIn("BASLIKSONU", m)

    def test_en_cok_bes_is(self):
        for i in range(7):
            self.is_ac(f"Is numarasi {i}")
        m = self.session_start()
        satir = next(s for s in m.splitlines() if s.startswith("Açık işler:"))
        self.assertEqual(len(re.findall(r"I-\d+ ", satir)), 5)

    def test_acik_is_yoksa_satir_yok(self):
        k = self.is_ac("Sadece kapalı")
        is_kaydi.is_durum(self.sd, k["id"], "kapandi")
        m = self.session_start()
        self.assertNotIn("Açık işler:", m)
        self.assertIn("Orkestra bu projede açık", m)

    def test_1800_kesiminde_asili_uyari_ve_onay_metni_korunur(self):
        a, b, _ = self.kur_uc_is()
        self.asili_yaz()
        for _ in range(40):
            k = onay.iste(self.sd, "Çok uzun bir başlık " * 10, "m", tur="perspektif")
            onay.karar_ver(self.sd, k["id"], "onay")
        om = onay.baglam_metni(self.sd, OTURUM, "SessionStart")
        self.assertGreater(len(om), 800)
        m = self.session_start(rapor_tekrar=60)
        self.assertLessEqual(len(m), 1800)
        self.assertTrue(m.endswith(om), "onay metni bütün kalmalı")
        self.assertIn("bitmeyen ajan", m)
        self.assertIn("orkestra:isci-t2 G-001 (45 dk)", m)
        self.assertIn("Orkestra bu projede açık", m)

    def test_1800_kesiminde_asili_uyari_acik_islerle_birlikte(self):
        self.kur_uc_is()
        self.asili_yaz()
        m = self.session_start(rapor_tekrar=60)
        self.assertLessEqual(len(m), 1800)
        self.assertIn("bitmeyen ajan", m)
        self.assertIn("TaskStop", m)

    def test_is_klasoru_yoksa_ve_is_json_bozuksa_dusmez(self):
        a = self.is_ac("Klasörü silinecek")
        b = self.is_ac("is.json bozulacak")
        c = self.is_ac("Sağlam iş")
        shutil.rmtree(a["klasor"])
        with open(os.path.join(b["klasor"], "is.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        m = self.session_start()  # istisna fırlatmamalı
        self.assertIn("Orkestra bu projede açık", m)
        self.assertIn(c["id"], m)

    def test_merkez_kayit_bozuksa_dusmez(self):
        self.is_ac("x")
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        m = self.session_start()
        self.assertIn("Orkestra bu projede açık", m)

    def test_is_liste_istisnasi_hook_dusurmez(self):
        self.is_ac("x")
        with mock.patch.object(is_kaydi, "is_liste", side_effect=RuntimeError("patladı")):
            m = self.session_start()
        self.assertIn("Orkestra bu projede açık", m)
        self.assertNotIn("Açık işler:", m)


# ============================================================ (D1) stop → oturumlar.md

class StopOturumSatiri(_Ortak):
    def satirlar(self, kayit):
        return [s for s in self.md_oku(kayit).splitlines() if SATIR_RE.match(s)]

    def test_dokunan_tur_tam_bir_satir_ekler(self):
        a = self.is_ac()
        self.baglan(a)
        once = self.md_oku(a)
        self.stop(_tur_dokunuslu(), last_assistant_message="Testler yazıldı, sıra hook.py kodunda")
        md = self.md_oku(a)
        self.assertTrue(md.startswith(once), "mevcut içerik korunmalı, yalnız sona eklenir")
        yeni = md[len(once):].strip("\n").splitlines()
        self.assertEqual(len(yeni), 1, yeni)
        m = SATIR_RE.match(yeni[0])
        self.assertIsNotNone(m, yeni[0])
        self.assertEqual(m.group(1)[:10], datetime.date.today().isoformat())
        self.assertEqual(m.group(2), KISA)
        self.assertEqual(m.group(3), "1")
        self.assertGreater(float(m.group(4)), 0.0)
        self.assertEqual(m.group(5), "Testler yazıldı, sıra hook.py kodunda")

    def test_arac_sayisi_turla_eslesir(self):
        a = self.is_ac()
        self.baglan(a)
        self.stop(_tur_dokunuslu(3))
        self.assertEqual(SATIR_RE.match(self.satirlar(a)[0]).group(3), "3")

    def test_dokunussuz_turda_satir_eklenmez(self):
        a = self.is_ac()
        self.baglan(a)
        once = self.md_oku(a)
        self.stop(_tur_dokunussuz())
        self.assertEqual(self.md_oku(a), once)

    def test_agent_araci_kayda_deger_sayilir(self):
        a = self.is_ac()
        self.baglan(a)
        tur = _tur_dokunussuz()
        tur[1]["message"]["content"] = [{"type": "tool_use", "id": "t-agent", "name": "Agent", "input": {"description": "d", "prompt": "p"}}]
        self.stop(tur)
        self.assertEqual(len(self.satirlar(a)), 1)

    def test_mevcut_satirlar_korunur_ve_her_tur_bir_satir(self):
        a = self.is_ac()
        self.baglan(a)
        with open(self.oturumlar_md(a), "a", encoding="utf-8", newline="\n") as f:
            f.write("- 2026-10-13 08:00 · eskiotur · 1 araç · $0.01 · nerede kalındı: eski\n")
        self.stop(_tur_dokunuslu())
        self.stop(_tur_dokunuslu())
        md = self.md_oku(a)
        self.assertIn("eskiotur", md)
        self.assertEqual(len(self.satirlar(a)), 3)
        self.assertLess(md.index("eskiotur"), md.index(KISA))

    def test_nerede_kalindi_tek_satir_ve_150_karakter(self):
        a = self.is_ac()
        self.baglan(a)
        uzun = "birinci satır\n\nikinci   satır\t" + "x" * 400
        self.stop(_tur_dokunuslu(), last_assistant_message=uzun)
        satirlar = self.satirlar(a)
        self.assertEqual(len(satirlar), 1)
        nerede = SATIR_RE.match(satirlar[0]).group(5)
        self.assertLessEqual(len(nerede), 150)
        self.assertNotIn("\n", nerede)
        self.assertTrue(nerede.startswith("birinci satır"))
        self.assertNotIn("\n\n", self.md_oku(a)[self.md_oku(a).index(KISA):])

    def test_eski_yan_dosyadaki_is_kullanilir_ve_yan_dosya_degismez(self):
        a = self.is_ac()
        yan = os.path.join(self.sd, "oturumlar", "is_" + OTURUM + ".json")
        eski = json.dumps({"is": a["id"]})
        with open(yan, "w", encoding="utf-8") as f:
            f.write(eski)
        self.stop(_tur_dokunuslu())
        self.assertEqual(len(self.satirlar(a)), 1)
        with open(yan, encoding="utf-8") as f:
            self.assertEqual(f.read(), eski, "yan dosya yalnız okunur")

    def test_perspektif_oturumunda_yazmaz(self):
        a = self.is_ac()
        self.baglan(a)
        once = self.md_oku(a)
        os.environ["ORKESTRA_PERSPEKTIF"] = "1"
        self.stop(_tur_dokunuslu())
        self.assertEqual(self.md_oku(a), once)

    def test_modeller_bossa_yazmaz(self):
        a = self.is_ac()
        self.baglan(a)
        once = self.md_oku(a)
        tur = _tur_dokunuslu()
        for t in tur:
            t.get("message", {}).pop("usage", None)
        self.stop(tur)
        self.assertEqual(self.md_oku(a), once)

    def test_bagli_olmayan_oturum_hicbir_ise_yazmaz(self):
        a = self.is_ac()
        once = self.md_oku(a)
        self.stop(_tur_dokunuslu())
        self.assertEqual(self.md_oku(a), once)

    def test_bilinmeyen_is_id_dusurmez(self):
        self.oturum_yaz(**{"is": "I-999", "is_baglanma": L.simdi()})
        self.stop(_tur_dokunuslu())  # istisna yok

    def test_yazma_istisnasi_hook_dusurmez(self):
        a = self.is_ac()
        self.baglan(a)
        gercek_open = open

        def hedefe_patla(yol, *ar, **kw):
            if str(yol).endswith("oturumlar.md"):
                raise PermissionError("kilitli")
            return gercek_open(yol, *ar, **kw)

        with mock.patch("builtins.open", side_effect=hedefe_patla):
            self.stop(_tur_dokunuslu())  # SystemExit dışında istisna testi düşürür
        self.assertIn("ofset", self.oturum_oku(), "stop geri kalan işini yapmalı")


# ============================================================ (D2) hatırlatma + (5)(6)

class StopHatirlatma(_Ortak):
    def mesaj(self, cikti):
        return (cikti or {}).get("systemMessage") or ""

    def test_bagli_olmayan_oturumda_ilk_stopta_hatirlatir_ikincide_susar(self):
        c1 = self.stop(_tur_dokunuslu())
        self.assertIn(HATIRLATMA_BAGSIZ, self.mesaj(c1))
        self.assertIn("`orkestra is devam <id>`", self.mesaj(c1))
        self.assertIn("`orkestra is ac`", self.mesaj(c1))
        self.assertIn("`orkestra is todo <id> --ekle`", self.mesaj(c1))
        self.assertNotIn("decision", c1)
        self.assertIs(self.oturum_oku().get("is_hatirlatma"), True)
        c2 = self.stop(_tur_dokunuslu())
        self.assertEqual(self.mesaj(c2), "")
        self.assertNotIn("decision", c2 or {})

    def test_kayda_deger_is_yoksa_hatirlatma_yok(self):
        c = self.stop(_tur_dokunussuz())
        self.assertEqual(self.mesaj(c), "")
        self.assertNotIn("is_hatirlatma", self.oturum_oku())

    def test_dokunussuz_tur_hakki_harcamaz(self):
        self.stop(_tur_dokunussuz())
        c = self.stop(_tur_dokunuslu())
        self.assertIn(HATIRLATMA_BAGSIZ, self.mesaj(c))

    def test_perspektif_oturumunda_hatirlatma_yok(self):
        os.environ["ORKESTRA_PERSPEKTIF"] = "1"
        c = self.stop(_tur_dokunuslu())
        self.assertEqual(self.mesaj(c), "")

    def test_todo_baglanmadan_sonra_degistiyse_b_hatirlatmasi_yok(self):
        a = self.is_ac()
        self.baglan(a, baglanma=(datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)).isoformat(timespec="seconds"))
        simdi = datetime.datetime.now().timestamp()
        os.utime(os.path.join(a["klasor"], "todo.md"), (simdi, simdi))
        c = self.stop(_tur_dokunuslu())
        self.assertEqual(self.mesaj(c), "")
        self.assertNotIn(HATIRLATMA_BAGSIZ, self.mesaj(c))

    def test_todo_degismediyse_b_hatirlatmasi_bir_kez(self):
        a = self.is_ac()
        self.baglan(a, baglanma=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
        eski = datetime.datetime.now().timestamp() - 7200
        os.utime(os.path.join(a["klasor"], "todo.md"), (eski, eski))
        c1 = self.stop(_tur_dokunuslu())
        m = self.mesaj(c1)
        self.assertIn(f"Orkestra: {a['id']} todo.md bu oturumda güncellenmedi", m)
        self.assertIn("`orkestra is todo <id> --ekle`", m)
        self.assertIn("`--bitti`", m)
        self.assertNotIn("decision", c1)
        self.assertIs(self.oturum_oku().get("is_hatirlatma"), True)
        c2 = self.stop(_tur_dokunuslu())
        self.assertEqual(self.mesaj(c2), "")

    def test_b_sirali_iste_hatirlatma_guncel_adimi_soyler(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1"}):
            a = self.is_ac()
            self.assertEqual(a.get("sira"), "mevcut-durum-plan-todo")
            self.baglan(a, baglanma=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
            c = self.stop(_tur_dokunuslu())
            m = self.mesaj(c)
        self.assertIn("sıralı iş (P-005)", m)
        self.assertIn("adım: mevcut_durum", m)
        self.assertIn(f"`orkestra is sira {a['id']}`", m)
        self.assertNotIn("`orkestra is todo <id> --ekle`", m)

    def test_b_dokunussuz_turda_cikmaz(self):
        a = self.is_ac()
        self.baglan(a, baglanma=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
        eski = datetime.datetime.now().timestamp() - 7200
        os.utime(os.path.join(a["klasor"], "todo.md"), (eski, eski))
        c = self.stop(_tur_dokunussuz())
        self.assertEqual(self.mesaj(c), "")

    def test_acik_kart_kapisi_block_oncelikli_hatirlatma_reason_sonuna_eklenir(self):
        kart = {"id": "G-777", "baslik": "açık kart", "oturum": OTURUM}
        with mock.patch.object(L, "kartlar", return_value=[kart]), mock.patch.object(L, "kart_durumu_hesapla", return_value="isleniyor"):
            c = self.stop(_tur_dokunuslu())
        self.assertEqual(c.get("decision"), "block")
        self.assertIn("G-777", c["reason"])
        self.assertTrue(c["reason"].rstrip().endswith("`orkestra is todo <id> --ekle` ile yaz."), c["reason"][-200:])
        self.assertIn(HATIRLATMA_BAGSIZ, c["reason"])
        self.assertIs(self.oturum_oku().get("is_hatirlatma"), True)

    def test_kart_kapisi_varken_ikinci_stopta_reason_hatirlatmasiz(self):
        kart = {"id": "G-777", "baslik": "açık kart", "oturum": OTURUM}
        with mock.patch.object(L, "kartlar", return_value=[kart]), mock.patch.object(L, "kart_durumu_hesapla", return_value="isleniyor"):
            self.stop(_tur_dokunuslu())
            c = self.stop(_tur_dokunuslu())
        self.assertEqual(c.get("decision"), "block")
        self.assertNotIn(HATIRLATMA_BAGSIZ, c["reason"])

    def test_stop_hook_active_kart_mesajinda_da_block_yok(self):
        kart = {"id": "G-777", "baslik": "açık kart", "oturum": OTURUM}
        with mock.patch.object(L, "kartlar", return_value=[kart]), mock.patch.object(L, "kart_durumu_hesapla", return_value="isleniyor"):
            c = self.stop(_tur_dokunuslu(), stop_hook_active=True)
        self.assertNotIn("decision", c)
        self.assertIn("G-777", c["systemMessage"])

    def test_mevcut_anahtarlar_korunur(self):
        a = self.is_ac()
        onceki = {"ofset": 0, "baglam": "b", "is": a["id"], "is_baglanma": "2026-10-13T09:00:00+03:00",
                  "is_gecmis": [{"is": a["id"], "zaman": "2026-10-13T09:00:00+03:00"}], "gorev": "G-9", "ozel": {"a": 1}}
        self.oturum_yaz(**onceki)
        self.stop(_tur_dokunuslu())
        o = self.oturum_oku()
        for k in ("is", "is_baglanma", "is_gecmis", "gorev", "ozel"):
            self.assertEqual(o.get(k), onceki[k], f"{k} korunmalı")
        self.assertIn("ofset", o)
        self.assertIn("guncelleme", o)
        self.assertIs(o.get("is_hatirlatma"), True)  # bağlı ama todo eski → (b) hakkı kullanıldı

    def test_hatirlatma_bagsiz_oturumda_mevcut_anahtarlari_korur(self):
        self.oturum_yaz(gorev="G-9", ozel={"a": 1})
        self.stop(_tur_dokunuslu())
        o = self.oturum_oku()
        self.assertEqual(o.get("gorev"), "G-9")
        self.assertEqual(o.get("ozel"), {"a": 1})
        self.assertIs(o.get("is_hatirlatma"), True)

    def test_is_klasoru_yoksa_stop_dusmez(self):
        a = self.is_ac()
        self.baglan(a)
        shutil.rmtree(a["klasor"])
        self.stop(_tur_dokunuslu())  # istisna yok
        self.assertEqual(self.oturum_oku().get("is"), a["id"])

    def test_is_json_bozuksa_stop_dusmez(self):
        a = self.is_ac()
        self.baglan(a)
        with open(os.path.join(a["klasor"], "is.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.stop(_tur_dokunuslu())
        self.assertEqual(self.oturum_oku().get("is"), a["id"])

    def test_merkez_kayit_bozuksa_stop_dusmez(self):
        a = self.is_ac()
        self.baglan(a)
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.stop(_tur_dokunuslu())
        self.assertEqual(self.oturum_oku().get("is"), a["id"])


if __name__ == "__main__":
    unittest.main()
