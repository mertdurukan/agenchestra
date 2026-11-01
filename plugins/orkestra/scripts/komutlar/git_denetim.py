"""orkestra komutları: git denetim (dal, stash ve gönderilmemiş iş raporu; salt okunur, I-325).

`orkestra git denetim [--depo YOL]`
"""
from __future__ import annotations

import os


def cmd_git_denetim(a):
    import git_denetim as GD
    print(GD.rapor(os.path.abspath(a.depo)))
    return 0


def kaydet(alt):
    p = alt.add_parser("git", help="git durumu: dal, stash, gönderilmemiş commit (salt okunur)")
    ps = p.add_subparsers(dest="alt", required=True)
    d = ps.add_parser("denetim", help="uzak/yerel dal sınıfı, stash ve commitsiz dosya sayısı")
    d.add_argument("--depo", default=".", help="git deposu (varsayılan: bulunulan dizin)")
    d.set_defaults(f=cmd_git_denetim)
