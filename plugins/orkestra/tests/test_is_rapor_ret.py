"""I-319 P2: `orkestra is rapor` ham `kapi_ret` kaydı ile gerçek ret sayısını ayrı gösterir.
I-271 öncesi yalnız boş denetçi satırından doğmuş `kapi_ret` kayıtları ('denetçi bekleniyor') ret sayılmaz;
kodda değişiklik yoktur, bu dosya davranışı sabitler."""
import json
import os
import unittest

import test_cekirdek as TC

import is_rapor  # noqa: E402  (test_cekirdek scripts yolunu ekler)

ESKI_BEKLEYEN = ("best in class denetimi: `**Üretim noktası:**` satırı `✔` ile başlamıyor (ayrı denetçi doldurur; ADR-0069); "
                 "best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor (ADR-0069)")
GERCEK = "P1: **Üretim noktası:** alanı yok"


class RaporRetAyrimi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def yaz(self, satirlar):
        with open(os.path.join(self.sd, "gunluk.jsonl"), "a", encoding="utf-8") as f:
            for o in satirlar:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")

    def test_eski_bekleyen_kayitlar_ret_sayilmaz_ham_ve_gercek_ayri(self):
        ham = ([{"tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": GERCEK}] * 3
               + [{"tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": ESKI_BEKLEYEN}] * 6
               + [{"tur": "kapi_bekleniyor", "kapi": "uretim_noktasi", "neden": "x"}] * 2)
        self.yaz(ham)
        r = is_rapor.rapor(self.sd)
        self.assertEqual(r["kapi_ret"], {"uretim_noktasi": 3})           # gerçek ret
        self.assertEqual(r["kapi_bekleniyor"], {"uretim_noktasi": 8})    # 6 eski + 2 yeni, ret değil
        ham_kapi_ret = sum(1 for o in ham if o["tur"] == "kapi_ret")
        self.assertEqual(ham_kapi_ret, 9)                                # ham = gerçek + eski bekleyen
        self.assertEqual(ham_kapi_ret, r["kapi_ret"]["uretim_noktasi"] + 6)

    def test_metin_iki_ayri_etiket_gosterir(self):
        self.yaz([{"tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": GERCEK},
                  {"tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": ESKI_BEKLEYEN}])
        m = is_rapor.metin(is_rapor.rapor(self.sd))
        self.assertIn("kapı retleri (ihlal modu): uretim_noktasi 1", m)
        self.assertIn("denetçi bekleniyor (ret sayılmaz): uretim_noktasi 1", m)

    def test_icerik_hatasi_iceren_denetim_satiri_ret_kalir(self):
        # içerik eksiği ('kaydı bulunamadı' / 'tüm maddeler') taşıyan kayıt eski bekleyen değildir
        for neden in (ESKI_BEKLEYEN + "; best in class denetimi: denetçi kaydı bulunamadı",
                      ESKI_BEKLEYEN + "; tüm maddeler yeni yetenek"):
            self.assertFalse(is_rapor._eski_bekleyen(neden), neden)
        self.assertTrue(is_rapor._eski_bekleyen(ESKI_BEKLEYEN))
        self.assertFalse(is_rapor._eski_bekleyen(GERCEK))


if __name__ == "__main__":
    unittest.main()
