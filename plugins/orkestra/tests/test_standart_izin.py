"""jira_yorum standardı ile izin politikası tutarlılığı: standart metni ve `orkestra bakim` çelişki uyarısı."""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
from komutlar import bakim  # noqa: E402

ESKI = "Yorum yazılmadan Done'a geçilmez; yorum Jira'ya yazılmadan önce kullanıcıya gösterilir (yazma onaya tabidir)."


class JiraIzinUyari(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self._ort = os.environ.pop("ORKESTRA_IZIN", None)

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)
        if self._ort is not None:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def yaz(self, goreli, icerik):
        yol = os.path.join(self.sd, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)

    def test_standart_metni_politikaya_atif_verir(self):
        with open(os.path.join(KOK, "standartlar", "jira_yorum.md"), encoding="utf-8") as f:
            m = f.read()
        self.assertIn("orkestra izin goster", m)
        self.assertNotIn("onaya tabi", m)

    def test_serbest_politika_ve_eski_metin_uyari_verir(self):
        self.yaz("izin_politikasi.json", json.dumps({"mod": "genis", "mcp": [], "rest_kapi": []}))
        self.yaz("standartlar/jira_yorum.md", "# x\n- " + ESKI + "\n")
        u = bakim.jira_izin_uyari(self.sd)
        self.assertIn("uyarı", u)
        self.assertIn("MCP yazma", u)

    def test_varsayilan_politika_veya_guncel_metin_uyari_vermez(self):
        # varsayılan eklenti politikası Jira yazmasında sorar: eski metin de çelişmez
        self.yaz("standartlar/jira_yorum.md", "# x\n- " + ESKI + "\n")
        self.assertEqual(bakim.jira_izin_uyari(self.sd), "")
        # serbest politika + güncel (eklenti) metin: çelişki yok
        self.yaz("izin_politikasi.json", json.dumps({"mod": "genis", "mcp": [], "rest_kapi": []}))
        os.remove(os.path.join(self.sd, "standartlar", "jira_yorum.md"))
        self.assertEqual(bakim.jira_izin_uyari(self.sd), "")


if __name__ == "__main__":
    unittest.main()
