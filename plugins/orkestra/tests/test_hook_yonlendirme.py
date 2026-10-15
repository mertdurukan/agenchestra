"""G-063: hook.py yönlendirme ipucu (user_prompt_submit) ve kapanış/bayat notu (session_start).
`python -m unittest plugins/orkestra/tests/test_hook_yonlendirme.py`
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
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import is_yonlendirme  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "yonl1234567890-oturum"
ISTEK_FATURA = "fatura raporlama ekranını düzeltelim"
ISTEK_ALAKASIZ = "kuantum gitar öğrenmek istiyorum"


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_yonl_")
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
    def is_ac(self, baslik, alt):
        return is_kaydi.is_ac(self.sd, baslik, os.path.join(self.proje, alt))

    def baglan(self, kayit, oid=OTURUM):
        with open(os.path.join(self.sd, "oturumlar", oid + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": kayit["id"], "is_baglanma": L.simdi()}, f)

    def todo_yaz(self, kayit, icerik):
        with open(os.path.join(kayit["klasor"], "todo.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)

    def kart_yaz(self, gid, is_id, durum):
        L.kart_yaz(self.sd, {"id": gid, "baslik": "kart " + gid, "durum": durum, "is": is_id})

    def calistir(self, fn, girdi):
        """(çıktı_metni, çıkış_kodu)"""
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi)
        buf = io.StringIO()
        kod = None
        with contextlib.redirect_stdout(buf):
            try:
                fn(g)
            except SystemExit as e:
                kod = e.code
        return buf.getvalue(), (0 if kod is None else kod)

    def istek(self, metin, oid=OTURUM):
        """user_prompt_submit koş; additionalContext metnini ('' olabilir) döndür."""
        cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": metin, "session_id": oid})
        self.assertEqual(kod, 0)
        if not cikti.strip():
            return ""
        return json.loads(cikti)["hookSpecificOutput"]["additionalContext"]

    def acilis(self, rapor_tekrar=0):
        bayat = {"farkli": 0, "kaynakta_commitsiz": False, "kaynak": "x"}
        rapor = {"okunmamis_rapor": ("ruya_20261013_1500.md" * rapor_tekrar) or None,
                 "zamani_geldi": False, "calisiyor": False}
        buf = io.StringIO()
        kod = None
        with mock.patch.object(L, "bayatlik", return_value=None), mock.patch.object(perspektif, "durum", return_value=rapor), \
                contextlib.redirect_stdout(buf):
            try:
                hook.session_start({"session_id": OTURUM, "cwd": self.proje})
            except SystemExit as e:
                kod = e.code
        self.assertIn(kod, (0, None))
        return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]

    def eskit(self, kayit, gun):
        """is.json/isler.json güncelleme alanını ve dosya mtime'larını gun gün geriye çek."""
        eski_dt = datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)
        eski = eski_dt.isoformat(timespec="seconds")
        for yol in (os.path.join(self.sd, "isler.json"), os.path.join(kayit["klasor"], "is.json")):
            try:
                with open(yol, encoding="utf-8") as f:
                    d = json.load(f)
                hedef = d.get("isler", {}).get(kayit["id"]) if "isler" in d else d
                if isinstance(hedef, dict):
                    hedef["guncelleme"] = eski
                with open(yol, "w", encoding="utf-8") as f:
                    json.dump(d, f)
            except Exception:
                pass
        t = time.time() - gun * 86400
        for ad in ("is.json", "oturumlar.md"):
            yol = os.path.join(kayit["klasor"], ad)
            if os.path.exists(yol):
                os.utime(yol, (t, t))

    def parca(self, metin, is_id):
        """'Açık işler:' satırında verilen işe ait parça."""
        satir = next(s for s in metin.splitlines() if s.startswith("Açık işler:"))
        return next(p for p in satir[len("Açık işler:"):].split(" ; ") if p.strip().startswith(is_id))


# ============================================================ kriter 1, 2: user_prompt_submit

class IstekIpucu(_Ortak):
    def setUp(self):
        super().setUp()
        self.fatura = self.is_ac("Fatura raporlama entegrasyonu", "001-fatura-raporlama")
        self.diger = self.is_ac("Kampanya takvimi düzenleme", "002-kampanya-takvim")

    def test_baglisiz_oturum_uyan_istek_is_devam_ipucu(self):
        m = self.istek(ISTEK_FATURA)
        self.assertIn("orkestra is devam " + self.fatura["id"], m)
        ipucu = [s for s in m.splitlines() if "orkestra is devam" in s]
        self.assertEqual(len(ipucu), 1, m)

    def test_baglisiz_oturum_alakasiz_istek_is_ac_ipucu(self):
        m = self.istek(ISTEK_ALAKASIZ)
        self.assertIn("orkestra is ac", m)
        self.assertNotIn("orkestra is devam", m)
        self.assertEqual(len([s for s in m.splitlines() if "orkestra is ac" in s]), 1, m)

    def test_acik_todo_metni_de_eslesmeyi_tetikler(self):
        self.todo_yaz(self.diger, "# T\n\n- [ ] muhasebe mutabakat tablosunu hazırla\n")
        m = self.istek("mutabakat tablosunu hazırlayalım")
        self.assertIn("orkestra is devam " + self.diger["id"], m)

    def test_kapali_is_aday_olmaz(self):
        is_kaydi.is_durum(self.sd, self.fatura["id"], "kapandi")
        m = self.istek(ISTEK_FATURA)
        self.assertNotIn("orkestra is devam " + self.fatura["id"], m)

    def test_bagli_is_konuya_uyuyorsa_ipucu_yok(self):
        self.baglan(self.fatura)
        m = self.istek(ISTEK_FATURA)
        self.assertNotIn("orkestra is devam", m)
        self.assertNotIn("orkestra is ac", m)

    def test_bagli_is_varken_eslesme_yoksa_ipucu_yok(self):
        self.baglan(self.fatura)
        m = self.istek(ISTEK_ALAKASIZ)
        self.assertNotIn("orkestra is devam", m)
        self.assertNotIn("orkestra is ac", m)

    def test_ayni_oturumda_ayni_ipucu_tekrarlanmaz(self):
        ilk = self.istek(ISTEK_FATURA)
        self.assertIn("orkestra is devam " + self.fatura["id"], ilk)
        ikinci = self.istek("fatura raporlama için bir daha bakalım")
        self.assertNotIn("orkestra is devam", ikinci)

    def test_ayni_is_ac_ipucu_tekrarlanmaz(self):
        self.assertIn("orkestra is ac", self.istek(ISTEK_ALAKASIZ))
        self.assertNotIn("orkestra is ac", self.istek("kuantum gitar nasıl öğrenilir"))

    def test_baska_oturum_ipucunu_yeniden_alir(self):
        self.istek(ISTEK_FATURA)
        m = self.istek(ISTEK_FATURA, oid="baska-oturum-9999")
        self.assertIn("orkestra is devam " + self.fatura["id"], m)

    def test_farkli_ipucu_turu_tekrar_sayilmaz(self):
        self.assertIn("orkestra is devam " + self.fatura["id"], self.istek(ISTEK_FATURA))
        self.assertIn("orkestra is ac", self.istek(ISTEK_ALAKASIZ))

    def test_sistem_iletisinde_ipucu_yok(self):
        cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": "<task-notification> " + ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertNotIn("orkestra is devam", cikti)
        self.assertNotIn("orkestra is ac", cikti)

    def test_sistem_iletisi_ipucu_hakkini_tuketmez(self):
        self.calistir(hook.user_prompt_submit, {"prompt": "<agent-message> " + ISTEK_FATURA})
        m = self.istek(ISTEK_FATURA)
        self.assertIn("orkestra is devam " + self.fatura["id"], m)

    def test_bos_istekte_cokmez(self):
        m = self.istek("")
        self.assertNotIn("orkestra is devam " + self.fatura["id"], m)

    def test_ipucu_durumu_gercek_olmayan_yere_yazilmaz(self):
        self.istek(ISTEK_FATURA)
        izinli = os.path.realpath(self.proje)
        for kok, _, dosyalar in os.walk(self.sd):
            self.assertTrue(os.path.realpath(kok).startswith(izinli))
        # ipucu anahtarı oturumlar/ altında oturuma özel bir json'da tutulur
        adlar = os.listdir(os.path.join(self.sd, "oturumlar"))
        self.assertTrue(any(OTURUM in a and a.endswith(".json") for a in adlar), adlar)


# ============================================================ kriter 3: session_start

class AcilisNotlari(_Ortak):
    def test_todo_tamam_kart_yok_kapat_notu(self):
        a = self.is_ac("Bitmiş iş başlığı", "001-bitmis")
        self.todo_yaz(a, "# T\n\n- [x] bir\n- [x] iki\n")
        p = self.parca(self.acilis(), a["id"])
        self.assertIn("otomatik kapandı", p)
        self.assertNotIn(a["id"], self._acik_idler())

    def _acik_idler(self):
        import is_kaydi
        return [g["id"] for g in is_kaydi.is_liste(self.sd, "acik")]

    def test_todo_tamam_ama_acik_kart_varsa_not_yok(self):
        a = self.is_ac("Bitmiş ama kartlı iş", "001-kartli")
        self.todo_yaz(a, "# T\n\n- [x] bir\n- [x] iki\n")
        self.kart_yaz("G-001", a["id"], "isleniyor")
        self.assertNotIn("orkestra is kapat", self.parca(self.acilis(), a["id"]))

    def test_kapali_kart_not_engellemez(self):
        a = self.is_ac("Kartı teslim edilmiş iş", "001-teslim")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        self.kart_yaz("G-001", a["id"], "teslim")
        self.acilis()
        self.assertNotIn(a["id"], self._acik_idler())

    def test_todo_tamam_degilse_not_yok(self):
        a = self.is_ac("Yarım iş", "001-yarim")
        self.todo_yaz(a, "# T\n\n- [x] bir\n- [ ] iki\n")
        p = self.parca(self.acilis(), a["id"])
        self.assertNotIn("orkestra is kapat", p)
        self.assertNotIn("kapatılabilir", p)

    def test_todo_toplam_sifirsa_not_yok(self):
        a = self.is_ac("Todo'suz iş", "001-todosuz")
        self.todo_yaz(a, "# T\n\n")
        self.assertNotIn("orkestra is kapat", self.parca(self.acilis(), a["id"]))

    def test_14_gun_hareketsiz_bayat(self):
        a = self.is_ac("Eski iş başlığı", "001-eski")
        self.todo_yaz(a, "# T\n\n- [ ] bekleyen\n")
        self.eskit(a, 20)
        self.assertIn("bayat", self.parca(self.acilis(), a["id"]))

    def test_taze_is_bayat_degil(self):
        a = self.is_ac("Taze iş başlığı", "001-taze")
        self.todo_yaz(a, "# T\n\n- [ ] bekleyen\n")
        self.eskit(a, 3)
        self.assertNotIn("bayat", self.parca(self.acilis(), a["id"]))

    def test_diger_isin_satiri_degismez(self):
        a = self.is_ac("Kapanacak iş", "001-kapanacak")
        b = self.is_ac("Sıradan devam eden iş", "002-siradan")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        self.todo_yaz(b, "# T\n\n- [x] bir\n- [ ] iki\n")
        p = self.parca(self.acilis(), b["id"])
        self.assertIn("todo 1/2", p)
        self.assertNotIn("kapat", p)
        self.assertNotIn("bayat", p)

    def test_mevcut_satir_bicimi_korunur(self):
        a = self.is_ac("Kapanacak iş", "001-kapanacak")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        with open(os.path.join(a["klasor"], "oturumlar.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("- SONSATIR_X\n")
        m = self.acilis()
        p = self.parca(m, a["id"])
        self.assertIn("todo 1/1", p)
        self.assertIn("son: - SONSATIR_X", p)
        self.assertIn("Devam için `orkestra is devam <id>`", m)

    def test_1800_kesimi_bozulmaz(self):
        for i in range(5):
            k = self.is_ac("Uzun başlıklı kapanacak iş numara %d " % i + "x" * 40, "00%d-uzun" % (i + 1))
            self.todo_yaz(k, "# T\n\n- [x] bir\n")
            self.eskit(k, 30)
        m = self.acilis(rapor_tekrar=20)
        self.assertLessEqual(len(m), 1800)
        self.assertIn("Açık işler:", m)

    def test_onay_metni_kesilmez_notlar_varken(self):
        for i in range(5):
            k = self.is_ac("Uzun başlıklı kapanacak iş numara %d " % i + "y" * 40, "00%d-uzun" % (i + 1))
            self.todo_yaz(k, "# T\n\n- [x] bir\n")
        with mock.patch("onay.baglam_metni", return_value="ONAY_SENTINEL_METNI"):
            m = self.acilis(rapor_tekrar=20)
        self.assertLessEqual(len(m), 1800)
        self.assertIn("ONAY_SENTINEL_METNI", m)


# ============================================================ kriter 4: hata dayanıklılığı

class HataDayanikli(_Ortak):
    def test_istek_yonlendirme_hata_verirse_cikis_0(self):
        self.is_ac("Fatura raporlama", "001-fatura")
        with mock.patch.object(is_yonlendirme, "yonlendir", side_effect=RuntimeError("patladı")):
            cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(cikti)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_istek_diger_baglam_parcalari_hatada_korunur(self):
        self.is_ac("Fatura raporlama", "001-fatura")
        with mock.patch.object(is_yonlendirme, "yonlendir", side_effect=RuntimeError("patladı")), \
                mock.patch("onay.baglam_metni", return_value="ONAY_KORUNMALI"):
            cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertIn("ONAY_KORUNMALI", json.loads(cikti)["hookSpecificOutput"]["additionalContext"])

    def test_istek_bozuk_isler_json_cikis_0(self):
        self.is_ac("Fatura raporlama", "001-fatura")
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk json")
        cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertNotIn("Traceback", cikti)

    def test_istek_durum_dosyasi_bozuksa_cikis_0(self):
        a = self.is_ac("Fatura raporlama", "001-fatura")
        self.istek(ISTEK_FATURA)
        oturumlar = os.path.join(self.sd, "oturumlar")
        for ad in os.listdir(oturumlar):
            if ad.endswith(".json") and ad.startswith("yonlendirme"):
                with open(os.path.join(oturumlar, ad), "w", encoding="utf-8") as f:
                    f.write("{{bozuk")
        cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)

    def test_istek_todo_eksik_cikis_0(self):
        a = self.is_ac("Fatura raporlama", "001-fatura")
        os.remove(os.path.join(a["klasor"], "todo.md"))
        m = self.istek(ISTEK_FATURA)
        self.assertIn("orkestra is devam " + a["id"], m)

    def test_acilis_kapanis_kodu_hata_verirse_satir_yine_uretilir(self):
        a = self.is_ac("Fatura raporlama", "001-fatura")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        with mock.patch.object(is_yonlendirme, "kapanis_adaylari", side_effect=RuntimeError("patladı")):
            m = self.acilis()
        self.assertIn("Açık işler:", m)
        self.assertIn(a["id"], m)
        self.assertIn("todo 1/1", m)

    def test_acilis_bozuk_is_json_ve_eksik_todo_cikis_0(self):
        a = self.is_ac("Fatura raporlama", "001-fatura")
        b = self.is_ac("Kampanya takvimi", "002-kampanya")
        with open(os.path.join(a["klasor"], "is.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        os.remove(os.path.join(b["klasor"], "todo.md"))
        m = self.acilis()
        self.assertIn("Orkestra bu projede açık", m)
        self.assertIn(b["id"], m)

    def test_acilis_bozuk_merkez_kayit_cikis_0(self):
        self.is_ac("Fatura raporlama", "001-fatura")
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        m = self.acilis()
        self.assertIn("Orkestra bu projede açık", m)


if __name__ == "__main__":
    unittest.main()
