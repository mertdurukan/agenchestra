"""G-093 (TOK-8): hook bağlamı boyutu. Sabit örnek durumla her hook olayı için önce/sonra karakter tablosu.
Önce = değişiklikten önceki biçimlerin test içindeki birebir karşılığı (eski_*); sonra = gerçek hook çıktısı.
Tabloyu görmek için: `py -3.13 -m pytest plugins/orkestra/tests/test_hook_baglam_boyut.py -q -s -p no:cacheprovider`
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "boyut1234567890-oturum"
SINIR = 1800


def _tok(c):
    return round(c / 4)


class BaglamBoyutu(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_boyut_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        os.makedirs(os.path.dirname(yol))
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol), mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()
        self._ornek_kur()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    # ---- sabit örnek durum: 5 açık iş (biri oturuma bağlı), 3 aktif + 5 beklemede kart, 1 bekleyen karar, niyet, asılı ajan
    def _ornek_kur(self):
        self.isler = []
        for i in range(5):
            g = is_kaydi.is_ac(self.sd, f"Uzun başlıklı açık iş numarası {i} ve ayrıntılı açıklama metni", os.path.join(self.proje, f"is{i}"))
            with open(os.path.join(g["klasor"], "todo.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("# T\n\n- [x] a\n- [ ] b\n- [ ] c\n")
            with open(os.path.join(g["klasor"], "oturumlar.md"), "a", encoding="utf-8", newline="\n") as f:
                f.write(f"- 2026-10-14 10:00 · aaaaaaaa · 3 araç · $0.20 · nerede kalındı: SON_{i} " + "u" * 90 + "\n")
            self.isler.append(g)
        self.bagli = self.isler[0]["id"]
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.bagli, "is_baglanma": L.simdi()}, f)
        durumlar = ["isleniyor", "denetimde", "reddedildi"] + ["beklemede"] * 5
        self.kartlar = [{"id": f"G-{100 + i:03d}", "baslik": f"Kart başlığı numarası {i} uzun ayrıntılı iş tanımı", "_d": d}
                        for i, d in enumerate(durumlar)]
        self.assertTrue(onay.iste(self.sd, "Bekleyen karar başlığı", "m", tur="perspektif"))  # durum: bekliyor
        with open(niyet.NIYET_YOLU, "w", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": "2026-10-15T10:00:00+03:00", "oturum": OTURUM, "proje": self.proje, "tur": "niyet",
                                "ne": "hook bağlamını ölç", "neden": "token tasarrufu"}) + "\n")
        self.asili = [{"ajan": "orkestra:isci-t2", "gorev": "G-101", "dakika": 45}]

    def _calistir(self, fn, girdi):
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        buf = io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(L, "bayatlik", return_value=None))
            st.enter_context(mock.patch.object(perspektif, "durum", return_value=rapor))
            st.enter_context(mock.patch.object(L, "kartlar", return_value=self.kartlar))
            st.enter_context(mock.patch.object(L, "kart_durumu_hesapla", side_effect=lambda k: k["_d"]))
            st.enter_context(mock.patch.object(ozet, "asili_ajanlar", return_value=self.asili))
            st.enter_context(mock.patch.object(hook, "_yonlendirme_ipucu", return_value=""))
            st.enter_context(mock.patch.object(hook, "_panel_ac_satiri", return_value=""))
            st.enter_context(contextlib.redirect_stdout(buf))
            try:
                fn(dict({"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "source": "startup"}, **girdi))
            except SystemExit:
                pass
        return buf.getvalue()

    def session_start(self):
        return json.loads(self._calistir(hook.session_start, {}))["hookSpecificOutput"]["additionalContext"]

    def ups(self):
        c = self._calistir(hook.user_prompt_submit, {"prompt": "merhaba, devam edelim"})
        return json.loads(c)["hookSpecificOutput"]["additionalContext"]

    def subagent(self):
        buf = io.StringIO()
        sahte = types.SimpleNamespace(stdout="d" * 1800)
        with mock.patch.object(hook, "ajan_gorevi", return_value=("G-101", "is")), \
                mock.patch.object(L, "kart_oku", return_value={"id": "G-101"}), \
                mock.patch("subprocess.run", return_value=sahte), contextlib.redirect_stdout(buf):
            try:
                hook.subagent_start({"cwd": self.proje, "session_id": OTURUM, "agent_id": "a1", "agent_type": "x"})
            except SystemExit:
                pass
        return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]

    # ---- değişiklikten önceki biçimler
    def eski_session_start(self):
        satirlar = ["Orkestra bu projede açık. Ana ajan: planla → `orkestra kart` ile kartla → işçi + AYRI denetçiyle dağıt "
                    "(`/orkestra:is`) → onaylıyı `orkestra kart teslim` ile topla. Ortak defter: `orkestra defter baglam <id>`.",
                    "Açık/bekleyen kartlar: " + "; ".join(f"{k['id']} [{k['_d']}] {k['baslik'][:40]}" for k in self.kartlar[:8])]
        satirlar.append(hook._acik_isler_satirlari(self.sd, None)[0])  # bağsız biçim eskisiyle aynı
        satirlar.append("Devam için `orkestra is devam <id>`; sıradaki adımları `orkestra is todo <id> --ekle` ile işin todo.md'sine yaz.")
        satirlar.append("Orkestra: 30 dakikadır bitmeyen ajan(lar): orkestra:isci-t2 G-101 (45 dk); "
                        "takıldıysa TaskStop ile durdur ya da kartı beklemede yap.")
        om = (hook._kurallar_satiri() + "\n" + (onay.baglam_metni(self.sd, OTURUM, "SessionStart") or "")).rstrip("\n")
        return "\n".join(satirlar)[:max(0, SINIR - len(om) - 1)] + "\n" + om

    def eski_ups(self):
        return "\n".join([niyet.baglam_metni(OTURUM),
                          "Orkestra: 30 dakikadır bitmeyen ajan(lar): orkestra:isci-t2 G-101 (45 dk); "
                          "takıldıysa TaskStop ile durdur ya da kartı beklemede yap."])

    def eski_subagent(self):
        return "Orkestra bağlamı (yalnız ihtiyacın olan kayıtlar):\n" + "d" * 1800

    # ---- ölçüm
    def olcum(self):
        ss, up, sa = self.session_start(), self.ups(), self.subagent()
        return [("SessionStart", len(self.eski_session_start()), len(ss)),
                ("UserPromptSubmit", len(self.eski_ups()), len(up)),
                ("SubagentStart", len(self.eski_subagent()), len(sa))]

    def test_kriter1_tablo_her_olay_icin_onceki_sonraki(self):
        satirlar = self.olcum()
        toplam = (sum(s[1] for s in satirlar[:2]), sum(s[2] for s in satirlar[:2]))
        print("\n| Olay | Önce kar. | Önce ~tok | Sonra kar. | Sonra ~tok | Fark |\n|---|---|---|---|---|---|")
        for ad, o, s in satirlar + [("SS+UPS toplam", *toplam)]:
            print(f"| {ad} | {o} | {_tok(o)} | {s} | {_tok(s)} | {100 * (o - s) / o:.0f}% |")
        self.assertEqual([s[0] for s in satirlar], ["SessionStart", "UserPromptSubmit", "SubagentStart"])
        for _, o, s in satirlar:
            self.assertGreater(o, 0)
            self.assertGreater(s, 0)
            self.assertLessEqual(s, o)

    def test_kriter2_session_start_ve_ups_toplami_en_az_yuzde_30_kisalir(self):
        s = self.olcum()
        once, sonra = s[0][1] + s[1][1], s[0][2] + s[1][2]
        self.assertLessEqual(sonra, 0.7 * once, f"önce={once} sonra={sonra}")

    def test_kriter3_korunanlar(self):
        ss = self.session_start()
        kr = [x for x in ss.splitlines() if "KURALLAR.md" in x]  # G-092 satırı (3. satır)
        self.assertEqual(len(kr), 1)
        self.assertTrue(os.path.isfile(kr[0].split("Kurallar: ")[1].split(".md")[0] + ".md"))
        self.assertIn("panel kararı bekliyor", ss)  # bekleyen karar uyarısı
        ilk = ss.splitlines()[0]
        # bağlı iş: başlık ve todo; kart kimlik+durum kaybolmaz, beklemede olanlar sayı + kimlik
        self.assertIn(f"Bağlı iş: {self.bagli}", ilk)
        self.assertIn("todo 1/3", ilk)
        self.assertIn("(+4 açık iş)", ilk)
        for k in self.kartlar[:3]:
            self.assertIn(f"{k['id']} [{k['_d']}]", ilk)
        self.assertIn("beklemede 5", ilk)
        self.assertIn("G-107", ilk)
        self.assertIn("orkestra kart liste", ilk)
        self.assertIn("orkestra:isci-t2 G-101 (45 dk)", ss)  # asılı ajan
        self.assertIn("TaskStop", ss)

    def test_session_start_uc_satir_ve_en_cok_600_karakter(self):
        """041 P1: SessionStart bağlamı üç satır (bağlı iş + kart; uyarılar; kurallar + izin) ve ≤600 karakter."""
        ss = self.session_start()
        self.assertEqual(len(ss.splitlines()), 3, ss)
        self.assertLessEqual(len(ss), 600, f"{len(ss)} karakter: {ss!r}")

    def test_model_sapmasi_uyarisi_uc_satirda_kaybolmaz(self):
        with mock.patch.object(hook, "_model_sapma_satiri",
                               return_value="UYARI: ana ajan modeli politika dışı: oturum claude-x, politika varsayılanı claude-y."):
            ss = self.session_start()
        self.assertIn("ana ajan modeli politika dışı", ss)
        self.assertEqual(len(ss.splitlines()), 3, ss)
        self.assertLessEqual(len(ss), 600, f"{len(ss)} karakter: {ss!r}")

    def test_kosul_yoksa_perspektif_ve_panel_satiri_yok(self):
        ss = self.session_start()
        self.assertNotIn("Perspektif", ss)
        self.assertNotIn("preview_start", ss)

    def test_kriter3_ups_niyet_ve_asili_korunur(self):
        up = self.ups()
        self.assertIn('Kayıtlı niyet: ne="hook bağlamını ölç"', up)
        self.assertIn("orkestra niyet --ne", up)
        self.assertIn("--baglam", up)
        self.assertIn("--sonuc", up)
        self.assertIn("orkestra:isci-t2 G-101 (45 dk)", up)

    def test_bagsiz_oturumda_acik_is_kimlikleri_listelenir(self):
        os.remove(os.path.join(self.sd, "oturumlar", OTURUM + ".json"))
        ilk = self.session_start().splitlines()[0]
        self.assertIn("Açık iş 5:", ilk)
        self.assertNotIn("Bağlı iş:", ilk)
        self.assertIn("orkestra is devam <id>", ilk)


if __name__ == "__main__":
    unittest.main()
