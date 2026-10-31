"""agents/ yalnız frontmatter'lı ajan tanımı taşır: alt klasör ya da başlıksız .md eklentiye ajan olarak yüklenir (I-292)."""
import os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(KOK, "agents")


def test_agents_altinda_alt_klasor_yok():
    assert [d for d in os.listdir(AGENTS) if os.path.isdir(os.path.join(AGENTS, d))] == []


def test_her_ajan_dosyasi_frontmatter_ile_baslar():
    kotu = []
    for ad in os.listdir(AGENTS):
        with open(os.path.join(AGENTS, ad), encoding="utf-8") as f:
            if not f.read().startswith("---\n"):
                kotu.append(ad)
    assert kotu == []
