"""I-319 P4: oturum bir işe bağlandığı anda, bağlanmadan önce yazılmış işsiz maliyet satırları o işe atanır.

`py -3.13 -m pytest plugins/orkestra/tests/test_geriye_atama.py -q -p no:cacheprovider`

Kök neden: bağlanma (komutlar/isler._oturumu_bagla, hook._otomatik_is_ac) yalnız atif.jsonl'e olay yazıyordu;
okuma katmanı (ork_lib.maliyet_kayitlari) atif.jsonl'i hiç okumaz, yalnız maliyet_duzeltme.jsonl'i bindirir.
Düzeltme: ork_lib.baglanma_duzeltmesi bağlanma anında o oturumun işsiz satırlarını maliyet_duzeltme.jsonl'e ekler.

- K1 bağlanma öncesi satırlar bağlanmadan sonra (CLI ve hook otomatik bağlama) işe atanır; bağlanma öncesi kovası 0 USD.
- K2 hiç bağlanmayan oturum '-'/None kalır; başka işe sonradan bağlanma eski atamayı değiştirmez.
- K3 ham maliyet.jsonl byte düzeyinde değişmez; aynı bağlanma tekrarında düzeltme satırı çoğalmaz.
- K4 uçtan uca: hook.stop bağsız satır yazar, bağlanma sonrası okuma işi gösterir.
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
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402
from komutlar import isler as ISL  # noqa: E402

OTURUM = "geri-atama-oturum-1"
BASKA = "geri-atama-oturum-2"
MODEL = "claude-haiku-5-5"


def _satir(oturum, zaman, usd, is_=None, kaynak="hook", agent_id=None):
    """hook._maliyet_satirlari'nin yazdığı biçimde ana ajan satırı tabanı."""
    return {"zaman": zaman, "oturum": oturum, "gorev": "-", "surec": "orkestrasyon", "baglam": "", "ajan": "ana-ajan",
            "agent_id": agent_id, "kaynak": kaynak, "is": is_, **({} if is_ else {"atif_nedeni": "oturum-isiz"})}, usd


class GeriyeAtama(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_geri_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        for a in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, a))
        self.tr = os.path.join(self.proje, "tr.jsonl")
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
        L._MALIYET_ONBELLEK.clear()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        L._MALIYET_ONBELLEK.clear()
        shutil.rmtree(self.proje, ignore_errors=True)

    # -- yardımcılar
    def yaz(self, oturum, zaman, usd, is_=None):
        """Tek token yazıcısı (hook._maliyet_satirlari) üzerinden satır yazar."""
        taban, usd = _satir(oturum, zaman, usd, is_)
        hook._maliyet_satirlari(self.sd, {"modeller": {MODEL: {"giris": 10, "cikis": 5, "onbellek_okuma": 0,
                                                                "onbellek_yazma": 0, "maliyet_usd": usd}}}, taban)

    def is_ac(self, alt="is1"):
        return is_kaydi.is_ac(self.sd, "Deneme işi", os.path.join(self.proje, alt))["id"]

    def bagla_cli(self, is_id):
        ISL._oturumu_bagla(self.sd, is_id)

    def oku(self, oturum=None):
        L._MALIYET_ONBELLEK.clear()
        return [r for r in L.maliyet_kayitlari(self.sd) if oturum is None or r.get("oturum") == oturum]

    @staticmethod
    def isiz_usd(rows):
        return round(sum(r.get("maliyet_usd") or 0 for r in rows if not r.get("is") or r.get("is") == "-"), 6)

    def ham(self):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "rb") as f:
            return f.read()

    # -- K1
    def test_k1_cli_baglanma_onceki_satirlar_ise_atanir(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.25)
        self.yaz(OTURUM, "2026-11-01T10:01:00+03:00", 2.50)
        self.assertEqual(self.isiz_usd(self.oku(OTURUM)), 3.75)  # bağlanma öncesi kovası
        isid = self.is_ac()
        self.bagla_cli(isid)
        self.yaz(OTURUM, "2026-11-01T10:05:00+03:00", 0.50, is_=isid)  # bağlandıktan sonra yazılan satır
        rows = self.oku(OTURUM)
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["is"] for r in rows}, {isid})
        self.assertEqual(self.isiz_usd(rows), 0.0)
        self.assertEqual([r.get("atif_kaynagi") for r in rows[:2]], ["baglanma", "baglanma"])
        self.assertFalse(any(r.get("atif_nedeni") for r in rows))

    def test_k1_hook_otomatik_baglama_onceki_satirlari_atar(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 0.40)
        isid = self.is_ac()
        self.assertTrue(hook._otomatik_is_ac(self.sd, OTURUM, "deneme istegi", proje=self.proje, is_id=isid))
        rows = self.oku(OTURUM)
        self.assertEqual([r["is"] for r in rows], [isid])
        self.assertEqual(self.isiz_usd(rows), 0.0)

    # -- K2
    def test_k2_baglanmayan_oturum_isiz_kalir(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.00)
        self.yaz(BASKA, "2026-11-01T10:00:30+03:00", 0.75)
        self.bagla_cli(self.is_ac())
        baska = self.oku(BASKA)
        self.assertEqual(len(baska), 1)
        self.assertIsNone(baska[0].get("is"))
        self.assertEqual(baska[0].get("atif_nedeni"), "oturum-isiz")
        self.assertEqual(self.isiz_usd(self.oku(OTURUM)), 0.0)

    def test_k2_ikinci_baglanma_eski_atamayi_degistirmez(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.00)
        a, b = self.is_ac("is1"), self.is_ac("is2")
        self.bagla_cli(a)
        self.yaz(OTURUM, "2026-11-01T10:02:00+03:00", 2.00, is_=a)
        self.bagla_cli(b)
        self.assertEqual([r["is"] for r in self.oku(OTURUM)], [a, a])

    def test_k2_baglanmalar_arasindaki_isiz_satir_sonraki_ise_gider(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.00)
        a, b = self.is_ac("is1"), self.is_ac("is2")
        self.bagla_cli(a)
        self.yaz(OTURUM, "2026-11-01T10:10:00+03:00", 0.30)  # bağ düştükten sonra işsiz satır
        self.bagla_cli(b)
        self.assertEqual([r["is"] for r in self.oku(OTURUM)], [a, b])

    # -- K3
    def test_k3_ham_defter_degismez_ve_tekrar_cogalmaz(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.00)
        self.yaz(OTURUM, "2026-11-01T10:01:00+03:00", 1.00)
        once = self.ham()
        isid = self.is_ac()
        self.bagla_cli(isid)
        self.bagla_cli(isid)
        self.assertEqual(L.baglanma_duzeltmesi(self.sd, OTURUM, isid), 0)
        self.assertEqual(self.ham(), once)
        duz = L.jsonl_oku(os.path.join(self.sd, "maliyet_duzeltme.jsonl"))
        self.assertEqual(len(duz), 2)
        self.assertEqual({d["kaynak"] for d in duz}, {"baglanma"})

    def test_k3_hata_baglamayi_bozmaz(self):
        self.yaz(OTURUM, "2026-11-01T10:00:00+03:00", 1.00)
        isid = self.is_ac()
        with mock.patch.object(L, "jsonl_toplu_ekle", side_effect=OSError("disk")):
            self.bagla_cli(isid)
        with open(os.path.join(self.sd, "oturumlar", f"{OTURUM}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("is"), isid)

    # -- K4
    def test_k4_uctan_uca_stop_sonra_baglanma(self):
        with open(self.tr, "w", encoding="utf-8", newline="\n") as f:
            for s in ({"type": "user", "timestamp": "2026-11-01T07:00:00Z", "message": {"role": "user", "content": "selam"}},
                      {"type": "assistant", "timestamp": "2026-11-01T07:00:03Z",
                       "message": {"id": "m1", "model": MODEL, "content": [{"type": "text", "text": "tamam"}],
                                   "usage": {"input_tokens": 1000, "output_tokens": 500}}}):
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            hook.stop(g)
        once = self.oku(OTURUM)
        self.assertTrue(once)
        self.assertGreater(self.isiz_usd(once), 0)
        isid = self.is_ac()
        self.bagla_cli(isid)
        sonra = self.oku(OTURUM)
        self.assertEqual({r["is"] for r in sonra}, {isid})
        self.assertEqual(self.isiz_usd(sonra), 0.0)


if __name__ == "__main__":
    unittest.main()
