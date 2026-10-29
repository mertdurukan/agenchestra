"""postgres-yazma sunucusu için izin kuralı (ADR-0093): auto modda bile her çağrı sorulur; okuma sunucusu değişmez."""
import os
import sys
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import izin_politikasi as IP  # noqa: E402

YAZMA = "mcp__plugin_orkestra_postgres-yazma__execute_sql"
OKUMA_SQL = "mcp__plugin_orkestra_postgres__execute_sql"
OKUMA_LISTE = "mcp__plugin_orkestra_postgres__list_schemas"


def karar(arac, auto, mod="genis"):
    with mock.patch.dict(os.environ, {"ORKESTRA_IZIN": mod}), mock.patch.object(IP, "_auto_modu", return_value=auto):
        return IP.karar(arac, {}, sd="x", oturum="o")[0]


class PostgresYazmaIzni(unittest.TestCase):
    def test_yazma_sunucusu_her_modda_sorulur(self):
        for auto in (False, True):
            for mod in ("genis", "kapi"):
                self.assertEqual(karar(YAZMA, auto, mod), "ask", (auto, mod))

    def test_yazma_sunucusunun_her_araci_sorulur(self):
        for ad in ("list_schemas", "get_object_details", "explain_query"):
            self.assertEqual(karar("mcp__plugin_orkestra_postgres-yazma__" + ad, True), "ask", ad)

    def test_okuma_sunucusu_degismez(self):
        self.assertEqual(karar(OKUMA_LISTE, True), "allow")
        self.assertEqual(karar(OKUMA_LISTE, False), "allow")
        self.assertEqual(karar(OKUMA_SQL, True), "allow")  # auto: sınıf açık
        self.assertEqual(karar(OKUMA_SQL, False), "ask")


if __name__ == "__main__":
    unittest.main()
