"""I-319 P3 (ADR-0095): maliyet.jsonl'de her token tek kaynakta yazılır.

`py -3.13 -m pytest plugins/orkestra/tests/test_maliyet_tek_kaynak.py -q -p no:cacheprovider`

Aynı tur için hem Stop/SubagentStop hook'u hem sayaç (`orkestra maliyet tur`) çalışır; maliyet.jsonl'e yalnız
'hook' satırı düşer, sayaç satırı toplamlara girmeyen maliyet_tur.jsonl gözlem defterine gider. Ham defter toplamı
rapor (ork_lib.maliyet_kayitlari) toplamına eşittir: okuyucunun tekilleştirmesi yeni kayıtta bir şey atmaz.
Eski karışık defter (hook + tur aynı oturumda) okuyucuda değişmeden netlenir (geriye uyum).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_istek_kimligi as TK  # noqa: E402  (ortak kurulum: geçici proje, niyet/perspektif yamaları)

L, hook, ic_kos, OTURUM, AID = TK.L, TK.hook, TK.ic_kos, TK.OTURUM, TK.AID
MODEL = "claude-haiku-5-5"


class TekKaynak(TK._Ortak):
    def sayac(self, agent_id=None, cikis=5):
        kom = [TK.ORK, "maliyet", "tur", "--oturum", OTURUM, "--model", MODEL, "--giris", "10", "--cikis", str(cikis),
               "--onb-okuma", "0", "--onb-yazma", "0", "--sure-ms", "7"]
        if agent_id:
            kom += ["--agent-id", agent_id]
        p = ic_kos.kos(kom, env=dict(os.environ, CLAUDE_PROJECT_DIR=self.proje), cwd=self.proje)
        self.assertEqual(p.returncode, 0, p.stderr)

    def ana_tur(self):
        TK._jsonl(self.tr, [TK._kullanici("merhaba", "2026-10-16T10:00:00Z"), TK._asistan("2026-10-16T10:00:07Z")])
        self.prompt()
        self.kos(hook.stop)
        self.sayac()

    def alt_tur(self):
        TK._jsonl(self.atr, [TK._kullanici("#GOREV:G-007 #SUREC:is\nişi yap", "2026-10-16T10:00:00Z"),
                             TK._asistan("2026-10-16T10:02:00Z")])
        self.prompt()
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2", "agent_transcript_path": self.atr})
        self.sayac(AID)

    def kaynaklar(self, agent_id=None):
        return [r.get("kaynak") for r in self.jl("maliyet.jsonl") if (r.get("agent_id") or None) == agent_id]

    def test_ana_tur_tek_kaynak(self):
        self.ana_tur()
        self.assertEqual(self.kaynaklar(), ["hook"], "aynı ana tur maliyet.jsonl'e bir kez (hook) yazılmalı")
        g = self.jl("maliyet_tur.jsonl")
        self.assertEqual([(r["kaynak"], r["agent_id"]) for r in g], [("tur", None)], "sayaç gözlem defterine yazmalı")

    def test_alt_tur_tek_kaynak(self):
        self.alt_tur()
        self.assertEqual(self.kaynaklar(AID), ["hook"])
        self.assertEqual([r["agent_id"] for r in self.jl("maliyet_tur.jsonl")], [AID])

    def test_ham_toplam_rapor_toplamina_esit(self):
        self.ana_tur()
        self.alt_tur()
        ham = self.jl("maliyet.jsonl")
        rapor = L.maliyet_kayitlari(self.sd)
        tok = lambda rs: sum((r.get("giris") or 0) + (r.get("cikis") or 0) for r in rs)  # noqa: E731
        self.assertEqual(tok(ham), tok(rapor))
        self.assertEqual(tok(ham), 2 * (10 + 5), "iki tur, her biri transkriptteki 10+5 token, bir kez")
        self.assertAlmostEqual(sum(r["maliyet_usd"] for r in ham), sum(r["maliyet_usd"] for r in rapor), places=9)

    def test_eski_karisik_defter_okuyucuda_netlenir(self):
        """Geriye uyum: değişiklikten önce yazılmış hook + tur çifti okuyucuda yine tek sayılır."""
        yol = os.path.join(self.sd, "maliyet.jsonl")
        ortak = {"v": 1, "oturum": OTURUM, "agent_id": None, "model": MODEL, "span_id": "s1", "gorev": "-",
                 "giris": 10, "cikis": 5, "onbellek_okuma": 0, "onbellek_yazma": 0}
        TK._jsonl(yol, [dict(ortak, zaman="2026-10-16T10:00:01+03:00", kaynak="hook", maliyet_usd=0.1),
                        dict(ortak, zaman="2026-10-16T10:00:02+03:00", kaynak="tur", tarife="1sa", maliyet_usd=0.1)])
        rapor = L.maliyet_kayitlari(self.sd)
        self.assertEqual(sum(r["cikis"] for r in rapor), 5)


if __name__ == "__main__":
    unittest.main()
