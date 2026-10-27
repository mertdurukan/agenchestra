"""orkestra komutları: kanit (kanıtsız iddia ölçümü, ADR-0085; model çağırmaz, dökümleri salt okur).

`orkestra kanit olc --gun N [--desen GLOB] [--donem-sinir ZAMAN_UTC] [--ornek K --dis-ornek M --kapanis-ornek J --tohum S] [--cikti DOSYA]`
    Bilgi sorusu turlarını sayar, çerçeve içi/dışı katmanlı rastgele örneği etiketleme için JSONL'e yazar
    (ilk satır `_meta`: katman toplamları).
`orkestra kanit ana-olcu ETIKETLI.jsonl [--json]`
    Etiketli dosyadan (her kayıtta `etiket` A/B/C/D) ana ölçüyü ve çerçeve içi/dışı A oranlarını hesaplar.
"""
from __future__ import annotations

import json
import os

from komutlar._ortak import hata, sd_gerekli


def _desen(a, sd) -> str:
    if a.desen:
        return a.desen
    import belge_ara as BA
    import ork_lib as L
    return L.proje_oturum_dizini(BA.proje_kok(sd)) + "*" + os.sep + "*.jsonl"


def cmd_olc(a):
    import kanit_olcum as K
    import soru_sinif
    sd = sd_gerekli()
    r = K.rubrik_oku(sd)
    import time
    simdi = time.time()
    sinir, dosyalar = K.dosya_listesi(a.gun, _desen(a, sd), simdi)
    sinir_z = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(sinir))
    say, ic, dis, kapanis = K.olc(dosyalar, lambda t: soru_sinif.tur(t, sd), r, sinir_z, a.donem_sinir)
    soru = sum(v for k, v in say.items() if k.endswith(":soru"))
    kanitsiz = sum(v for k, v in say.items() if k.endswith(":kanitsiz_iddiali"))
    yazimli = sum(v for k, v in say.items() if k.endswith(":is_kapanis_yazimli"))
    calistirmasiz = sum(v for k, v in say.items() if k.endswith(":is_kapanis_calistirmasiz"))
    print(f"olcum_saati={time.strftime('%Y-%m-%d %H:%M')} pencere_gun={a.gun} dosya={len(dosyalar)} "
          f"soru={soru} cerceve_ic={len(ic)} cerceve_dis={len(dis)}")
    for k in sorted(say):
        print(k, say[k])
    if soru:
        print(f"kanitsiz_iddiali_oran={kanitsiz / soru:.3f}")
    if yazimli:
        print(f"is_kapanis_calistirmasiz_oran={calistirmasiz / yazimli:.3f}")
    if a.cikti:
        meta = {"_meta": {"olcum_saati": time.strftime("%Y-%m-%d %H:%M"), "gun": a.gun, "tohum": a.tohum,
                          "soru": soru, "ic_toplam": len(ic), "dis_toplam": len(dis), "kapanis_toplam": len(kapanis)}}
        satirlar = [meta] + K.ornekle(ic, a.ornek, a.tohum) + K.ornekle(dis, a.dis_ornek, a.tohum) \
            + K.ornekle(kapanis, a.kapanis_ornek, a.tohum)
        with open(a.cikti, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"ornek_yazildi={a.cikti} satir={len(satirlar) - 1}")
    return 0


def cmd_ana_olcu(a):
    import kanit_olcum as K
    r = K.rubrik_oku(None)
    poz = r.get("pozitif_etiket", "A")
    meta, kayit = {}, []
    with open(a.dosya, encoding="utf-8") as f:
        for satir in f:
            d = json.loads(satir)
            if "_meta" in d:
                meta = d["_meta"]
            elif d.get("etiket"):
                kayit.append(d)
    if not meta:
        hata("dosyada _meta satırı yok; `kanit olc --cikti` ile üretilmiş etiketli dosya ver.")
    sayim = {}
    for k in ("ic", "dis", "kapanis"):
        sec = [d for d in kayit if d.get("katman") == k]
        sayim[k] = (sum(1 for d in sec if d["etiket"] == poz), len(sec))
    (ia, i_n), (da, d_n) = sayim["ic"], sayim["dis"]
    if not i_n or not d_n:
        hata("çerçeve içi ve çerçeve dışı katmanlarda etiketli örnek gerekli.")
    nokta, ust = K.ana_olcu(ia, i_n, da, d_n, meta["soru"], meta["ic_toplam"], cekilis=r.get("jeffreys_cekilis", 200000))
    cikti = {"ana_olcu_nokta": nokta, "ana_olcu_ust95": ust, "cerceve_payi": meta["ic_toplam"] / meta["soru"],
             "ic": {"a": ia, "n": i_n}, "dis": {"a": da, "n": d_n},
             "kapanis": {"a": sayim["kapanis"][0], "n": sayim["kapanis"][1]}}
    if a.json:
        print(json.dumps(cikti, ensure_ascii=False, indent=2))
    else:
        print(f"ana_olcu={nokta * 100:.2f}% ust95={ust * 100:.2f}% cerceve_payi={cikti['cerceve_payi']:.3f} "
              f"ic={ia}/{i_n} dis={da}/{d_n} kapanis={cikti['kapanis']['a']}/{cikti['kapanis']['n']}")
    return 0


def kaydet(alt):
    p = alt.add_parser("kanit", help="kanıtsız iddia ölçümü (ADR-0085): örnek çıkar, ana ölçüyü hesapla")
    s = p.add_subparsers(dest="alt", required=True)
    o = s.add_parser("olc", help="bilgi sorusu turlarını say, katmanlı örneği JSONL'e yaz")
    o.add_argument("--gun", type=int, default=14, help="pencere (son N gün, varsayılan 14)")
    o.add_argument("--desen", help="döküm glob'u (varsayılan: bu projenin ve çalışma ağaçlarının dökümleri)")
    o.add_argument("--donem-sinir", dest="donem_sinir", help="UTC 'YYYY-MM-DDTHH:MM'; öncesi 'notsuz', sonrası 'notlu' dönem")
    o.add_argument("--ornek", type=int, default=120, help="çerçeve içi örnek sayısı")
    o.add_argument("--dis-ornek", dest="dis_ornek", type=int, default=60, help="çerçeve dışı örnek sayısı")
    o.add_argument("--kapanis-ornek", dest="kapanis_ornek", type=int, default=30, help="çalıştırmasız iş kapanışı örnek sayısı")
    o.add_argument("--tohum", type=int, default=42)
    o.add_argument("--cikti", help="örnek JSONL yolu (verilmezse yalnız sayılar)")
    o.set_defaults(f=cmd_olc)
    m = s.add_parser("ana-olcu", help="etiketli JSONL'den ana ölçüyü ve Jeffreys %%95 üst sınırını hesapla")
    m.add_argument("dosya")
    m.add_argument("--json", action="store_true")
    m.set_defaults(f=cmd_ana_olcu)
