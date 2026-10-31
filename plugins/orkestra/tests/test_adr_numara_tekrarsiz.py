"""P-015: adr/ klasöründe numaralar tekrarsızdır.

adr_depo.sonraki_no numarayı yazıldığı anda dal ve çalışma ağaçlarından türetir; sonradan main'e giren numarayı göremez
(I-292: iki kez çakıştı). Bu test o boşluğu birleştirme anında kapatır: yeni tekrar numarası testi düşürür.
"""
import os
import re
from collections import defaultdict

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# Birleştirme öncesi gelen, atıfları iki ADR'ye dağılmış eski tekrar; yeni numara bu listeye eklenmez.
BILINEN_ESKI_TEKRAR = {"0103"}


def test_adr_numaralari_tekrarsiz():
    adr = os.path.join(KOK, "adr")
    if not os.path.isdir(adr):
        return
    no = defaultdict(list)
    for ad in os.listdir(adr):
        m = re.match(r"ADR-(\d+)-", ad)
        if m:
            no[m.group(1)].append(ad)
    tekrar = {n: a for n, a in no.items() if len(a) > 1 and n not in BILINEN_ESKI_TEKRAR}
    assert tekrar == {}, f"tekrar eden ADR numarası: {tekrar}"
