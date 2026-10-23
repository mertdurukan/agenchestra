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

    def karar_yama(self, karar, puanlar):
        """eslestir/karar sonucunu sabitler (G-151 motorundan bağımsız; hook'un bu sonuca tepkisi sınanır)."""
        st = contextlib.ExitStack()
        st.enter_context(mock.patch.object(is_yonlendirme, "eslestir", return_value=puanlar, create=True))
        st.enter_context(mock.patch.object(is_yonlendirme, "karar", return_value=karar, create=True))
        self.addCleanup(st.close)
        return st

    def oturum_json(self, oid=OTURUM):
        try:
            with open(os.path.join(self.sd, "oturumlar", oid + ".json"), encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {}

    def parca(self, metin, is_id):
        """'Açık işler:' (yalnız kapanış/bayat notu olan işleri sıralayan) satırında verilen işe ait parça; satır ya da parça yoksa ''."""
        satir = next((s for s in metin.splitlines() if s.startswith("Açık işler:")), "")
        return next((p for p in satir[len("Açık işler:"):].split(" ; ") if p.strip().startswith(is_id)), "")


# ============================================================ kriter 1, 2: user_prompt_submit

class IstekIpucu(_Ortak):
    def setUp(self):
        super().setUp()
        self.fatura = self.is_ac("Fatura raporlama entegrasyonu", "001-fatura-raporlama")
        self.diger = self.is_ac("Kampanya takvimi düzenleme", "002-kampanya-takvim")

    def _satir(self, m):
        s = [x for x in m.splitlines() if x.startswith("Yeni görev")]
        self.assertEqual(len(s), 1, m)
        return s[0]

    def _sec(self, idler=None):
        idler = idler or [self.fatura["id"], self.diger["id"]]
        self.karar_yama(("sec", idler), [{"id": i, "puan": 0.5 - n * 0.1} for n, i in enumerate(idler)])

    def test_baglisiz_oturum_belirsizde_en_yakin_ise_kendiliginden_baglanir(self):
        self._sec()
        m = self.istek(ISTEK_FATURA)
        self.assertIn(self.fatura["id"], m)
        self.assertIn("otomatik bağlandı", m)
        self.assertEqual(self.oturum_json().get("is"), self.fatura["id"])

    def test_eslesmeyen_istek_de_ayni_satiri_alir(self):
        self._sec()
        self.assertIn("orkestra is ac", self.istek(ISTEK_ALAKASIZ))

    def test_bagli_oturum_bagli_isi_gosterir(self):
        self.baglan(self.fatura)
        s = self._satir(self.istek(ISTEK_ALAKASIZ))
        self.assertIn("bağlı iş " + self.fatura["id"], s)

    def test_bagli_oturumda_acik_devam_susar_zayif_kalip_belirsiz(self):
        """I-061 P1: 'tamam devam' susar; 'bunu ... kural' belirsiz kalır ve satırı alır."""
        self.baglan(self.fatura)
        self.assertNotIn("Yeni görev (", self.istek("tamam, devam et"))
        self.assertIn("Yeni görev (", self.istek("Bunu bir kural olarak ekle, her belgede alt alta yazılsın"))

    def test_belirsiz_mesaj_zorunlu_yonerge_alir(self):
        """I-061 P2: bağlı oturumda belirsiz mesaj ZORUNLU satırı alır; açık devam almaz."""
        self.baglan(self.fatura)
        self.assertIn("ZORUNLU", self.istek(ISTEK_ALAKASIZ))
        self.assertNotIn("ZORUNLU", self.istek("tamam, devam et"))

    def test_kapali_is_listelenmez(self):
        is_kaydi.is_durum(self.sd, self.fatura["id"], "kapandi")
        self._sec([self.diger["id"]])
        m = self.istek(ISTEK_FATURA)
        self.assertNotIn(self.fatura["id"], m)
        self.assertIn(self.diger["id"], m)

    def test_her_yeni_gorevde_tekrarlanir(self):
        self.baglan(self.fatura)
        self._satir(self.istek(ISTEK_FATURA))
        self._satir(self.istek(ISTEK_ALAKASIZ))

    def test_sistem_iletisinde_satir_yok(self):
        cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": "<task-notification> " + ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertNotIn("Yeni görev (", cikti)

    def test_bos_istekte_cokmez(self):
        self.assertNotIn("Yeni görev (", self.istek(""))

    def test_hook_durum_dosyasi_yazmaz(self):
        self.istek(ISTEK_FATURA)
        adlar = os.listdir(os.path.join(self.sd, "oturumlar"))
        self.assertFalse(any(a.startswith("yonlendirme_") for a in adlar), adlar)


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
        m = self.acilis()
        p = self.parca(m, b["id"])
        self.assertEqual(p, "", "notu olmayan iş 'Açık işler:' satırına girmez")
        self.assertIn(b["id"], m.splitlines()[0])  # ilk satırda kimliğiyle kalır
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
        self.assertIn("otomatik kapandı", p)

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
        self.baglan(a)
        os.remove(os.path.join(a["klasor"], "todo.md"))
        m = self.istek(ISTEK_FATURA)
        self.assertIn("Açık işler: " + a["id"], m)

    def test_acilis_kapanis_kodu_hata_verirse_satir_yine_uretilir(self):
        a = self.is_ac("Fatura raporlama", "001-fatura")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        with mock.patch.object(is_yonlendirme, "kapanis_adaylari", side_effect=RuntimeError("patladı")):
            m = self.acilis()
        self.assertIn("Orkestra bu projede açık", m)
        self.assertIn(a["id"], m)  # not üretilemese de ilk satırda iş kimliği kalır

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


class AlanUyarisi(_Ortak):
    """Bağlı oturum iş klasörü dışına yazınca klasör başına bir kez, engellemeyen tek satır."""

    def _yaz(self, hedef):
        tam = os.path.join(self.proje, hedef)
        return self.calistir(lambda g: hook._alan_uyarisi(self.sd, OTURUM, self.proje, tam), {})

    def test_klasor_disi_bir_kez_uyarir_icinde_susar(self):
        k = self.is_ac("fatura ekranı", "isler/001-fatura")
        self.baglan(k)
        cikti, _ = self._yaz("baska/dosya.py")
        self.assertIn("Alan dışı yazma", cikti)
        cikti2, _ = self._yaz("baska/dosya2.py")
        self.assertEqual(cikti2, "")
        cikti3, _ = self._yaz("isler/001-fatura/todo.md")
        self.assertEqual(cikti3, "")

    def test_bagsiz_oturum_susar(self):
        cikti, _ = self._yaz("baska/dosya.py")
        self.assertEqual(cikti, "")


# ============================================================ G-152 P2-P3: otomatik bağla / aç / seç

class OtomatikYonlendirme(_Ortak):
    """Bağsız oturumda her gerçek mesajda eslestir+karar çalışır (is_yonlendirme, G-151 sözleşmesi:
    eslestir -> [{'id','puan'}], karar -> ('bagla', id) | ('ac', None) | ('sec', [id, id]))."""

    SORU = "Bu fatura raporu neden boş geliyor?"
    DEVAM = "tamam devam et"

    def setUp(self):
        super().setUp()
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        self.fatura = self.is_ac("Fatura raporlama entegrasyonu", "001-fatura-raporlama")
        self.diger = self.is_ac("Kampanya takvimi düzenleme", "002-kampanya-takvim")

    def _puan(self, *idler):
        return [{"id": i, "puan": round(0.9 - n * 0.1, 2)} for n, i in enumerate(idler)]

    def _is_idleri(self):
        return sorted(g["id"] for g in is_kaydi.is_liste(self.sd, "acik"))

    # --- K1 bagla
    def test_bagla_oturumu_isa_baglar(self):
        fid = self.fatura["id"]
        self.karar_yama(("bagla", fid), self._puan(fid))
        m = self.istek(ISTEK_FATURA)
        self.assertIn("bağlandı " + fid, m)
        d = self.oturum_json()
        self.assertEqual(d.get("is"), fid)
        self.assertTrue(d.get("is_baglanma"))
        self.assertEqual([x["is"] for x in d.get("is_gecmis", [])], [fid])
        self.assertIn(OTURUM, [o["oturum"] for o in is_kaydi.is_al(self.sd, fid)["oturumlar"]])

    def test_bagla_yeni_is_acmaz(self):
        fid = self.fatura["id"]
        once = self._is_idleri()
        self.karar_yama(("bagla", fid), self._puan(fid))
        self.istek(ISTEK_FATURA)
        self.assertEqual(self._is_idleri(), once)

    def test_bagla_sonraki_mesajda_baglidir_eslestir_cagrilmaz(self):
        fid = self.fatura["id"]
        self.karar_yama(("bagla", fid), self._puan(fid))
        self.istek(ISTEK_FATURA)
        with mock.patch.object(is_yonlendirme, "eslestir", side_effect=AssertionError("bağlıda çağrılmaz"), create=True):
            self.istek(ISTEK_ALAKASIZ)
        self.assertEqual(self.oturum_json().get("is"), fid)

    # --- K1/K2 ac
    def test_ac_is_turu_etiketsiz_acar_ve_baglar(self):
        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        m = self.istek(ISTEK_ALAKASIZ)
        yeni = set(self._is_idleri()) - once
        self.assertEqual(len(yeni), 1, m)
        yid = yeni.pop()
        self.assertIn("Yeni iş otomatik açıldı", m)
        self.assertIn(yid, m)
        self.assertEqual(self.oturum_json().get("is"), yid)
        self.assertEqual(is_kaydi.is_al(self.sd, yid)["etiketler"], [])
        self.assertIn(OTURUM, [o["oturum"] for o in is_kaydi.is_al(self.sd, yid)["oturumlar"]])

    def test_ac_soru_turu_is_acmaz(self):
        # I-138 P2: ac kararında bilgi sorusu iş açmaz, oturum bağlanmaz
        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        m = self.istek(self.SORU)
        self.assertEqual(set(self._is_idleri()), once, m)
        self.assertFalse(self.oturum_json().get("is"))
        self.assertNotIn("Yeni iş otomatik açıldı", m)

    def test_soru_bagla_kararinda_etiketli_is_acilmaz(self):
        fid = self.fatura["id"]
        once = self._is_idleri()
        self.karar_yama(("bagla", fid), self._puan(fid))
        self.istek(self.SORU)
        self.assertEqual(self._is_idleri(), once)
        self.assertEqual(self.oturum_json().get("is"), fid)

    def test_soru_etiketi_ayari_is_turu_yolunda_etiket_koymaz(self):
        # proje is_esleme.json soru_etiketi'ni ezse de bilgi sorusu iş açmaz; iş türü mesaj etiketsiz iş açar
        with open(os.path.join(self.sd, "is_esleme.json"), "w", encoding="utf-8") as f:
            json.dump({"soru_etiketi": "bilgi-sorusu"}, f)
        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        self.istek(self.SORU)
        self.assertEqual(set(self._is_idleri()), once)
        self.istek(ISTEK_ALAKASIZ)
        yid = (set(self._is_idleri()) - once).pop()
        self.assertEqual(is_kaydi.is_al(self.sd, yid)["etiketler"], [])

    # --- K1 sec
    def test_sec_en_yakin_ise_sormadan_baglar_yeni_is_acmaz(self):
        a, b = self.fatura["id"], self.diger["id"]
        once = self._is_idleri()
        self.karar_yama(("sec", [a, b]), self._puan(a, b))
        m = self.istek(ISTEK_FATURA)
        self.assertIn(a, m)
        self.assertIn("otomatik bağlandı", m)
        self.assertNotIn("seç", m)
        self.assertEqual(self._is_idleri(), once)
        self.assertEqual(self.oturum_json().get("is"), a)

    # --- K2 devam
    def test_devam_turu_bagsizda_is_acmaz_bagsiz_uyarisi_ve_sec(self):
        a, b = self.fatura["id"], self.diger["id"]
        once = self._is_idleri()
        # karar 'ac' dese de devam türünde iş açılmaz
        self.karar_yama(("ac", None), self._puan(a, b))
        m = self.istek(self.DEVAM)
        self.assertEqual(self._is_idleri(), once)
        self.assertIsNone(self.oturum_json().get("is"))
        self.assertIn("bağsız", m.lower())
        self.assertIn("orkestra is devam", m)
        self.assertIn(a, m)

    # --- K1 sistem iletisi
    def test_sistem_iletisinde_otomatik_islem_yok(self):
        once = self._is_idleri()
        self.karar_yama(("ac", None), [])
        self.calistir(hook.user_prompt_submit, {"prompt": "<task-notification> " + ISTEK_ALAKASIZ})
        self.assertEqual(self._is_idleri(), once)
        self.assertIsNone(self.oturum_json().get("is"))

    def test_bos_mesajda_is_acilmaz(self):
        once = self._is_idleri()
        self.karar_yama(("ac", None), [])
        self.istek("")
        self.assertEqual(self._is_idleri(), once)

    # --- K4 bağlı oturum değişmez
    def test_bagli_oturumda_otomatik_islem_yok_ve_k004_ipucu_surer(self):
        self.baglan(self.fatura)
        once = self._is_idleri()
        yok_say = ("istek_sira", "istek_tur", "son_istek_id")

        def karsilastirilacak():
            return {k: v for k, v in self.oturum_json().items() if k not in yok_say}

        onceki = karsilastirilacak()
        with mock.patch.object(is_yonlendirme, "eslestir", side_effect=AssertionError("çağrılmamalı"), create=True), \
                mock.patch.object(is_yonlendirme, "karar", side_effect=AssertionError("çağrılmamalı"), create=True):
            m = self.istek(ISTEK_ALAKASIZ)
        self.assertEqual(self._is_idleri(), once)
        self.assertEqual(karsilastirilacak(), onceki)
        self.assertEqual(karsilastirilacak().get("is"), self.fatura["id"])
        self.assertIn("bağlı iş " + self.fatura["id"], m)
        self.assertNotIn("start_session", m)  # K-004: yeni oturum önerilmez, oturum kendisi geçer

    # --- K3 klasör
    def test_klasor_esleme_ilk_projesi_altinda_NNN_tarih_slug(self):
        os.makedirs(os.path.join(self.proje, "calisma", "004-20260101-eski"))
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump({"projeler": ["calisma", "diger"]}, f)
        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        self.istek("Kuantum gitar öğrenme planı hazırlayalım")
        yid = (set(self._is_idleri()) - once).pop()
        klasor = os.path.normpath(is_kaydi.is_al(self.sd, yid)["klasor"])
        self.assertEqual(os.path.dirname(klasor), os.path.normpath(os.path.join(self.proje, "calisma")))
        self.assertRegex(os.path.basename(klasor), r"^005-\d{8}-kuantum-gitar")

    def test_klasor_esleme_yoksa_durum_dizini_isler_altinda(self):
        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        self.istek(ISTEK_ALAKASIZ)
        yid = (set(self._is_idleri()) - once).pop()
        klasor = os.path.normpath(is_kaydi.is_al(self.sd, yid)["klasor"])
        self.assertEqual(os.path.dirname(klasor), os.path.normpath(os.path.join(self.sd, "isler")))
        self.assertRegex(os.path.basename(klasor), r"^\d{3}-\d{8}-kuantum-gitar")

    def test_proje_altina_yazilamazsa_durum_dizini_isler_altina_duser(self):
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump({"projeler": ["calisma"]}, f)
        gercek = is_kaydi.is_ac
        cagrilar = []

        def sahte(sd, baslik, klasor, *a, **k):
            cagrilar.append(os.path.normpath(klasor))
            if len(cagrilar) == 1:
                raise PermissionError("yazılamaz")
            return gercek(sd, baslik, klasor, *a, **k)

        once = set(self._is_idleri())
        self.karar_yama(("ac", None), [])
        with mock.patch.object(is_kaydi, "is_ac", side_effect=sahte):
            m = self.istek(ISTEK_ALAKASIZ)
        self.assertEqual(len(cagrilar), 2, cagrilar)
        self.assertTrue(cagrilar[0].startswith(os.path.normpath(os.path.join(self.proje, "calisma"))))
        self.assertEqual(os.path.dirname(cagrilar[1]), os.path.normpath(os.path.join(self.sd, "isler")))
        self.assertEqual(os.path.basename(cagrilar[0]), os.path.basename(cagrilar[1]))
        self.assertEqual(len(set(self._is_idleri()) - once), 1)
        self.assertIn("Yeni iş otomatik açıldı", m)

    # --- K3/K7 fail-open
    def test_is_acma_hatasinda_hook_cokmez_ipucu_yoluna_duser(self):
        once = self._is_idleri()
        self.karar_yama(("ac", None), [])
        with mock.patch.object(is_kaydi, "is_ac", side_effect=RuntimeError("disk dolu")):
            cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_ALAKASIZ})
        self.assertEqual(kod, 0)
        m = json.loads(cikti)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Yeni iş otomatik açıldı", m)
        self.assertIn("orkestra is ac", m)  # eski ipucu yolu
        self.assertEqual(self._is_idleri(), once)
        self.assertIsNone(self.oturum_json().get("is"))

    def test_eslestir_hatasinda_hook_cokmez(self):
        with mock.patch.object(is_yonlendirme, "eslestir", side_effect=RuntimeError("patladı"), create=True):
            cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(cikti)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIsNone(self.oturum_json().get("is"))

    def test_baglama_yazimi_hatasinda_hook_cokmez(self):
        fid = self.fatura["id"]
        self.karar_yama(("bagla", fid), self._puan(fid))
        with mock.patch.object(is_kaydi, "is_oturum_bagla", side_effect=RuntimeError("kayıt bozuk")):
            cikti, kod = self.calistir(hook.user_prompt_submit, {"prompt": ISTEK_FATURA})
        self.assertEqual(kod, 0)
        json.loads(cikti)

    # --- gerçek motor (G-151) ile uçtan uca
    def test_gercek_motor_ilgisiz_istek_yeni_is_acar(self):
        once = set(self._is_idleri())
        self.istek("Kuantum gitar öğrenme egzersizleri çalışma programı")
        self.assertEqual(len(set(self._is_idleri()) - once), 1)

    def test_gercek_motor_baslikla_ortusen_istek_isa_baglar(self):
        once = self._is_idleri()
        self.istek("Fatura raporlama entegrasyonu")
        self.assertEqual(self.oturum_json().get("is"), self.fatura["id"])
        self.assertEqual(self._is_idleri(), once)

    # --- K8
    def test_otomatik_is_ac_mevcut_yardimcilari_kullanir(self):
        import inspect
        self.assertTrue(hasattr(hook, "_otomatik_is_ac"), "hook._otomatik_is_ac yok")
        kaynak = inspect.getsource(hook._otomatik_is_ac)
        for parca in ("L.kilit", "L.atomik_yaz", "esleme_oku", "klasor_ayir"):  # klasor_ayir = kilitli sonraki_klasor_adi
            self.assertIn(parca, kaynak)


if __name__ == "__main__":
    unittest.main()
