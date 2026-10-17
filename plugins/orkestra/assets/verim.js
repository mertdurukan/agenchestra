'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { B, E, esc } = O;
  const { bayatCiz, ciz, yerlestir } = O;
  // Ekrana giden serbest metin: markdown soyulur, tam yollar kısaltılır, kaçışlanır.
  const metin = s => esc(O.yolGizle(O.temizMetin(s)));
  const kisalt = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s; };
  const sat = (ad, deger) => `<div class="sat"><span>${esc(ad)}</span><span>${deger}</span></div>`;
  const rozet = (ad, renk) => `<span class="rozet" style="--renk:${renk}"><i></i>${esc(ad)}</span>`;
  // ortak.js'te yok: yüzde değerini CSS genişliği için yuvarla
  const yz = v => Math.round(Math.max(0, Math.min(100, v)) * 100) / 100;

  // V: SON İYİ analitik verisi; hata anında silinmez (yalnız alan değişince sıfırlanır). Durum: K (O.veri kontrol nesnesi).
  let K = null;
  const S = { veri: null, gun: null, gSecili: null, tumKart: false, uyariAcik: false, pencere: 'son_3_gun' };
  const orkestrali = () => { const b = O.alanBilgi(); return b ? !!b.orkestra : true; };
  const veri = () => (S.veri && !S.veri.hata && S.veri.acik !== false) ? S.veri : null;

  // model rengi modele bağlı ve sabit (opus, sonnet, haiku, fable sırası; gerisi sırayla)
  const MODEL_SIRA = ['opus-5-5', 'sonnet-5-5', 'haiku-5-5', 'fable-5-1'];
  const modelRenk = {};
  const renkModel = m => {
    const k = String(m ?? '');
    if (!(k in modelRenk)) {
      const i = MODEL_SIRA.indexOf(k);
      modelRenk[k] = i >= 0 ? `var(--s${i + 1})` : `var(--s${Math.min(5 + Object.keys(modelRenk).filter(x => !MODEL_SIRA.includes(x)).length, 8)})`;
    }
    return modelRenk[k];
  };
  const modelRozet = m => rozet(E.model(m), renkModel(m));
  const SEV = { iyi: ['iyi', 'var(--good)'], uyari: ['dikkat', 'var(--warning)'], kritik: ['kritik', 'var(--critical)'] };
  const sev = s => { const t = SEV[s]; return t ? { ad: t[0], renk: t[1] } : { ad: s ? String(s) : '–', renk: 'var(--neutral)' }; };

  // ------------------------------------------------------------ 0. Hedef panosu (sayfanın en üstü): 5 ölçü x 5 pencere, hedeften sapma
  const OLCU_TANIM = [
    ['ana_ajan_payi', 'Ana ajan payı', 'ust', x => B.yuzde(x), 'ana ajan harcaması / toplam harcama (USD)', v => B.usd(v), 'puan'],
    ['isci_cagrisi_kart', 'İşçi çağrısı / kart', 'ust', x => B.sayi(x, 2), 'işçi çağrısı / kart', v => B.sayi(v), 'adet'],
    ['onayli_kart_usd', 'Onaylı kart başına USD', 'ust', x => B.usd(x), 'onaylı kartların harcaması (USD) / onaylı kart', v => B.sayi(v), 'usd'],
    ['ret_orani', 'Ret oranı', 'band', x => B.yuzde(x), 'ret / (ret + onay) denetimi', v => B.sayi(v), 'puan'],
    ['teknik_not_kapsama', 'Teknik not kapsaması', 'alt', x => B.yuzde(x), 'teknik notu dolu kart / kapı sonrası onaylı kart', v => B.sayi(v), 'puan'],
  ];
  const PENCERE_SIRASI = ['bugun', 'son_3_gun', 'son_7_gun', 'bu_ay', 'tum_zaman'];
  const PENCERE_AD = { bugun: 'Bugün', son_3_gun: 'Son 3 gün', son_7_gun: 'Son 7 gün', bu_ay: 'Bu ay', tum_zaman: 'Tüm zaman' };
  const EKSI = '−';
  // Sapma: işaretli fark, ölçünün kendi biriminde (oran ölçülerinde yüzde puan). Artı = hedefin üstünde; 0 = hedef (bant) içinde.
  const sapmaMetni = (x, birim) => {
    if (x == null) return '';
    if (Math.abs(x) < 1e-9) return 'sapma yok';
    const a = Math.abs(x), isaret = x > 0 ? '+' : EKSI;
    return isaret + (birim === 'puan' ? B.sayi(a * 100, 1) + ' puan' : birim === 'usd' ? B.usd(a) : B.sayi(a, 2)) + ' sapma';
  };
  // durum metni renge bağlı değil: her zaman sözcük ve simge de yazılır
  const DURUM_METNI = { iyi: ['✓', 'hedefte', 'var(--good)'], uyari: ['!', 'dikkat', 'var(--warning)'], kotu: ['✕', 'hedef dışı', 'var(--critical)'], 'veri-yok': ['–', 'veri yok', 'var(--neutral)'] };
  const YORUM_METNI = { 'gevsek-riski': 'gevşeklik riski (bant altı)', 'plan-kusuru': 'plan kusuru (bant üstü)' };
  const durumMetni = (d, yorum) => {
    const t = DURUM_METNI[d] || DURUM_METNI['veri-yok'];
    return { simge: t[0], ad: t[1] + (yorum && YORUM_METNI[yorum] ? ' · ' + YORUM_METNI[yorum] : ''), renk: t[2] };
  };
  const hedefMetni = (tur, h, bicim) => tur === 'band' && Array.isArray(h) ? `hedef ${bicim(h[0])}–${bicim(h[1])}`
    : h == null ? 'hedef –' : `hedef ${tur === 'ust' ? '≤ ' : tur === 'alt' ? '= ' : ''}${bicim(h)}`;
  // Pencere sayfadaki ortak seçiciden gelir (G.pencere); hedef panosu, israf ve ek ölçüler onu izler.
  function panoCiz() {
    S.pencere = G.pencere.al();
    const v = veri(), durumKap = $('#panoDurum');
    const p = v && v.hedef_panosu && v.hedef_panosu.olculer ? v.hedef_panosu : null;
    if (!p) { durumKap.hidden = false; yerlestir(durumKap, `<p class="bos">${v ? 'Hedef panosu verisi yok.' : 'Yükleniyor…'}</p>`); return; }
    durumKap.hidden = true;
    const kutu = ([anahtar, ad, tur, bicim, payTanim, paydaBicim, birim]) => {
      // hedef her pencerede aynı: kutu başlığında bir kez; satırda pencere, değer, sapma ve durum
      const hedef = ((p.olculer[anahtar] || {}).tum_zaman || {}).hedef;
      const satirlar = [S.pencere].map(w => {
        const e = (p.olculer[anahtar] || {})[w] || { durum: 'veri-yok', deger: null };
        const d = durumMetni(e.durum, e.yorum);
        const pay = e.durum === 'veri-yok' ? 'örnek yok' : `${anahtar === 'ana_ajan_payi' || anahtar === 'onayli_kart_usd' ? B.usd(e.pay) : B.sayi(e.pay, 0)} / ${anahtar === 'ana_ajan_payi' ? B.usd(e.payda) : B.sayi(e.payda, 0)}`;
        const sapma = sapmaMetni(e.sapma, birim);
        const ip = `<b>${esc(ad)} · ${esc(PENCERE_AD[w])}</b>${sat('Pay / payda', esc(pay))}${sapma ? sat('Hedeften sapma', esc(sapma.replace(' sapma', ''))) : ''}<div class="meta">${esc(payTanim)}</div>`;
        return `<div class="pano-satir" tabindex="0" data-ipucu="${esc(ip)}" data-pencere="${w}" style="--renk:${d.renk}">
          <span class="pencere">${esc(PENCERE_AD[w])}</span>
          <b class="deger">${e.deger == null ? '–' : bicim(e.deger)}</b>
          <span class="durum"><i aria-hidden="true">${d.simge}</i>${esc(d.ad)}</span>
          <span class="sapma">${esc(sapma)}</span></div>`;
      }).join('');
      // Hedef göstergesi (bullet): değer çubuğu hedef çizgisine ya da banda karşı; renk durumdan, sözcük ve simge satırda
      const ew = (p.olculer[anahtar] || {})[S.pencere] || {};
      const gd = ew.durum === 'iyi' ? 'iyi' : ew.durum === 'uyari' ? 'uyari' : ew.durum === 'kotu' ? 'kotu' : 'yok';
      const bant = tur === 'band' && Array.isArray(hedef) ? hedef : null;
      const hd = tur === 'band' ? null : (Array.isArray(hedef) ? null : hedef);
      const gostergeMaks = Math.max(Number(ew.deger) || 0, Number(hd) || 0, bant ? bant[1] : 0) * 1.3 || 1;
      const gosterge = G.hedef({ deger: ew.deger, hedef: hd, bant, durum: gd, maks: gostergeMaks, bicim, etiket: ad });
      return `<div class="karo pano-kutu" data-olcu="${esc(anahtar)}"><span class="pano-ad">${esc(ad)}</span><small class="pano-hedef">${esc(hedefMetni(tur, hedef, bicim))}</small>${satirlar}${gosterge}</div>`;
    };
    const israf = p.israf || {};
    const israfKutu = w => {
      const i = israf[w];
      if (!i) return '';
      const ned = Object.entries(i.siniflar || {}).map(([k, e]) => `${esc(k)} ${B.sayi(e.ret)}`).join(' · ');
      const ip = `<b>Önlenebilir israf · ${esc(PENCERE_AD[w])}</b><div class="meta">Ret alan işçi turunun defter maliyeti; yalnız önlenebilir sınıf (kapsam, biçim, sayı, kanıt, yetenek) toplanır. Sınıflanmamış ret ayrı sayılır, israfa eklenmez. Eşik sürümü ${esc(B.sayi((israf.tum_zaman || {}).esik_surumu))}.</div>`;
      return ekKutu('Önlenebilir israf', B.usd(i.onlenebilir_usd), `koşuyu yeniden yaptıran ret: ${ned || 'yok'}`, '', ip);
    };
    // Hedef kartları: her kart tek soruya cevap veren ana ölçüyü ve ilgili ek ölçüleri taşır (yeri HEDEF_KART tanımında)
    HEDEF_KART.forEach(h => {
      const yuva = KARTLAR[h.hedef]; if (!yuva) return;
      const ana = OLCU_TANIM.filter(o => h.olcu.includes(o[0])).map(kutu).join('');
      const ek = (h.israf ? israfKutu(S.pencere) : '') + h.ek.map(a => ekKutular(p.ek, a)).join('');
      yerlestir(yuva.ust, ana ? `<div class="karolar pano">${ana}</div>` : '');
      const bag = h.baglanti ? `<p class="g-hk-baglanti"><a href="${esc(h.baglanti[0] + location.search)}">${esc(h.baglanti[1])} →</a></p>` : '';
      yerlestir(yuva.ek, (ek ? `<div class="karolar pano pano-ek">${ek}</div>` : '') + bag);
    });
  }
  // Hedef kartları (I-047): aynı soruya cevap veren ölçüler tek kartta. olcu = hedef panosu ölçüsü, ek = ilgili ek ölçü anahtarları,
  // tasi = ayrıntıya taşınan mevcut bölümler (kimlikleriyle birlikte; betikler yazmaya devam eder).
  const HEDEF_KART = [
    { hedef: 'H1', soru: 'Bir kart bana kaça mal oluyor?', olcu: ['onayli_kart_usd'], ek: ['onayli_kart_toplam_usd', 'onayli_usd_dagilim', 'sinif_basina'], tasi: ['#onayli', '#birim'] },
    { hedef: 'H2', soru: 'Reddedilen iş ne kadar ve neden?', olcu: ['ret_orani'], ek: ['ilk_gecis_onay'], israf: true, tasi: ['#ret'] },
    { hedef: 'H3', soru: 'Bir kart kaç işçi harcıyor?', olcu: ['isci_cagrisi_kart'], ek: ['isci_dagilim'], tasi: [] },
    { hedef: 'H4', soru: 'Ana ajan ne kadar harcıyor?', olcu: ['ana_ajan_payi'], ek: ['ana_kirilim', 'onbellek_isabet'], tasi: [] },
    { hedef: 'H6', soru: 'Kartların teknik notu tam mı?', olcu: ['teknik_not_kapsama'], ek: [], tasi: [], baglanti: ['/teknik', 'Eksik kartlar: Teknik detay'] },
  ];
  const KARTLAR = {};
  HEDEF_KART.forEach(h => { const y = G.hedefKarti({ hedef: h.hedef, soru: h.soru, tasi: h.tasi }); if (y) KARTLAR[h.hedef] = y; });

  // Hedefsiz ek ölçüler (analitik.ek_olculer): her ölçü hedef panosundaki gibi bir kart; seçili pencere (S.pencere) için tek değer.
  // Veri yoksa kart çizilmez. Kart: başlık, ana değer, ayrıntı satırı, isteğe bağlı grafik; tanım ipucunda.
  const nz = (f, v, ...a) => (v == null ? '–' : f(v, ...a));
  const ekKutu = (ad, deger, alt, grafik, ip) => `<div class="karo pano-kutu ek-kutu" tabindex="0" data-ipucu="${esc(ip || '')}"><span class="pano-ad">${esc(ad)}</span><b class="ek-deger">${deger}</b><small class="pano-hedef">${alt}</small>${grafik || ''}</div>`;
  const EK_TANIM = [
    ['ana_kirilim', 'Ana ajan harcaması', 'ana ajan harcamasının işe bağlı, işe bağsız ve perspektif payı (USD)',
      a => [B.usd((Number(a.is_bagli_usd) || 0) + (Number(a.is_bagsiz_usd) || 0) + (Number(a.perspektif_usd) || 0)),
        `işe bağlı ${B.usd(a.is_bagli_usd)} · işe bağsız ${B.usd(a.is_bagsiz_usd)} · perspektif ${B.usd(a.perspektif_usd)}`,
        G.pay([{ ad: 'İşe bağlı', deger: a.is_bagli_usd, renk: 'var(--s1)' }, { ad: 'İşe bağsız', deger: a.is_bagsiz_usd, renk: 'var(--s2)' }, { ad: 'Perspektif', deger: a.perspektif_usd, renk: 'var(--s3)' }], { bicim: B.usd, toplamEtiket: 'Ana ajan harcaması payları' })]],
    ['onayli_kart_toplam_usd', 'Kart başına USD (ana ajan dahil)', 'pencere içindeki tüm harcama (ana ajan dahil) / onaylı kart',
      a => [nz(B.usd, a.deger), `${B.usd(a.pay)} / ${B.sayi(a.payda, 0)} kart`, '']],
    ['isci_dagilim', 'Kart başına işçi', 'kart başına tekil işçi ajanı sayısı; denetçiler dahil değildir',
      a => [`${nz(B.sayi, a.medyan, 1)}`, `medyan · 4+ işçili ${B.sayi(a.kart_ge4, 0)} / ${B.sayi(a.adet, 0)} kart`,
        G.dagilim({ medyan: a.medyan, p90: a.p90, maks: a.en_cok, bicim: x => B.sayi(x, 1), etiket: 'İşçi ajanı sayısı' })]],
    ['onayli_usd_dagilim', 'Onaylı kart USD', 'onaylı kartların kendi harcaması (USD)',
      a => [nz(B.usd, a.medyan), 'medyan',
        G.dagilim({ medyan: a.medyan, p90: a.p90, maks: a.en_cok, bicim: B.usd, etiket: 'Kart harcaması' })]],
    ['ilk_gecis_onay', 'İlk geçişte onay', 'ilk denetim kararı onay olan kart / karar verilmiş kart; hedef yok',
      a => [nz(B.yuzde, a.deger), `${B.sayi(a.pay, 0)} / ${B.sayi(a.payda, 0)} kart`, G.ilerleme(a.pay, a.payda, { renk: 'var(--s1)', etiket: 'İlk geçişte onay' })]],
    ['onbellek_isabet', 'Önbellek isabeti', 'okunan önbellek tokenı / tüm giriş tokenı',
      a => [nz(B.yuzde, (a.ana || {}).deger), `ana ajan · karta bağlı ${nz(B.yuzde, (a.karta_bagli || {}).deger)}`, G.ilerleme(((a.ana || {}).deger || 0) * 100, 100, { renk: 'var(--s1)', etiket: 'Önbellek isabeti' })]],
    ['sinif_basina', 'İş sınıfı maliyeti', 'kartın sınıfına göre kart sayısı ve karta bağlı harcama; en pahalı 5 sınıf',
      a => {
        const l = Object.entries(a).slice(0, 5);
        return l.length ? [B.usd(l.reduce((t, [, e]) => t + (Number(e.usd) || 0), 0)), l.map(([k, e]) => `${esc(k)} ${B.sayi(e.kart, 0)}`).join(' · '),
          G.pay(l.map(([k, e], i) => ({ ad: k, deger: e.usd, renk: `var(--s${i + 1})` })), { bicim: B.usd, toplamEtiket: 'İş sınıfı payları' })] : ['–', 'kart yok', ''];
      }],
  ];
  function ekKutular(ek, yalniz) {
    if (!ek) return '';
    return EK_TANIM.filter(t => !yalniz || t[0] === yalniz).map(([anahtar, ad, tanim, bicim]) => {
      const a = (ek[anahtar] || {})[S.pencere];
      if (!a) return '';
      const [deger, alt, grafik] = bicim(a);
      return ekKutu(ad, deger, alt, grafik, `<b>${ad} · ${PENCERE_AD[S.pencere]}</b><div class="meta">${tanim}</div>`);
    }).join('');
  }

  // ------------------------------------------------------------ 1. Basamak verimliliği
  function basamakCiz() {
    const v = veri(), b = v && v.basamak;
    if (!b) return;
    const pay = b.kucuk_pay_kart, tuttu = pay != null && pay >= b.hedef;
    const modeller = Object.entries(b.is_model_usd || {}).map(([m, u]) => `${E.model(m)} ${B.usd(u)}`).join(' · ');
    let html = '<div class="karolar">' +
      `<div class="karo vurgu" style="--renk:${pay == null ? 'var(--neutral)' : tuttu ? 'var(--good)' : 'var(--warning)'}"><b>${B.yuzde(pay)}</b>
        <span>Haiku ya da Sonnet'te biten kart</span>
        <div class="olcer" aria-hidden="true"><div class="dolgu" style="width:${yz((pay || 0) * 100)}%;--renk:${tuttu ? 'var(--good)' : 'var(--warning)'}"></div><div class="hedef" style="left:${yz(b.hedef * 100)}%"></div></div>
        <small>${pay == null ? '' : rozet(tuttu ? 'hedefte' : 'hedefin altında', tuttu ? 'var(--good)' : 'var(--warning)') + ' '}${B.sayi(b.teslim_kart)} teslim kartı · hedef ${B.yuzde(b.hedef)}</small></div>` +
      `<div class="karo"><b>${B.yuzde(b.kucuk_pay_is_usd)}</b><span>İşçi harcamasında Haiku + Sonnet payı</span><small>${esc(modeller || 'işçi kaydı yok')}</small></div></div>`;
    const sat0 = Array.isArray(b.satirlar) ? b.satirlar : [];
    if (!sat0.length) html += '<p class="bos">Henüz kart yok.</p>';
    else {
      // sıfır olan oran ve sayaçlar "–" gösterilir (hiç olmadı = bilgi yok değil, ama sütunu gürültüyle doldurmasın)
      const oran = (o, a, b2) => (!b2 || !a) ? '–' : `${B.yuzde(o)} <span class="meta" style="display:inline">(${B.sayi(a)}/${B.sayi(b2)})</span>`;
      html += `<div class="tablo-kap"><table class="tablo"><tr><th>Başlangıç basamağı</th><th class="sayi">Kart</th><th class="sayi">İlk seferde geçti</th>
        <th class="sayi">Ret oranı</th><th class="sayi">Yükseltilen</th><th class="sayi">Kart başı</th></tr>` +
        sat0.map(s => `<tr><td>${esc(s.basamak)}</td><td class="sayi">${B.sayi(s.kart)}</td>
          <td class="sayi">${s.denetlenen ? `${B.yuzde(s.ilk_gecis_orani)} <span class="meta" style="display:inline">(${B.sayi(s.ilk_gecis)}/${B.sayi(s.denetlenen)})</span>` : '–'}</td>
          <td class="sayi">${oran(s.ret_orani, s.ret, s.denetim)}</td>
          <td class="sayi">${s.yukseltilen ? B.sayi(s.yukseltilen) : '–'}</td>
          <td class="sayi">${s.kart_basi_usd ? B.usd(s.kart_basi_usd) : '–'}</td></tr>`).join('') + '</table></div>';
    }
    html += `<details class="nasil"><summary>Nasıl hesaplanır?</summary>
      <p>İlk seferde geçti: ilk denetimde onay alan kartların, denetlenen kartlara oranı. Ret oranı: o basamaktaki bütün denetimlerin reddedilen payı. Yükseltilen: daha üst basamağa taşınan kart sayısı. Gerçekleşmeyen durumlar "–" gösterilir.</p></details>`;
    yerlestir($('#basamakIcerik'), html);
  }

  // ------------------------------------------------------------ 1a. Planlayıcı modeli x sınıf x basamak ('planlayici' anahtarı)
  function planlayiciCiz() {
    const v = veri(), p = v && v.planlayici;
    if (!p) return;
    let kap = $('#planlayiciIcerik');
    if (!kap) {   // maliyet.html'de yuva yoksa bölüm basamak bölümünün arkasına eklenir
      const once = $('#basamak');
      if (!once) return;
      const sec = document.createElement('section');
      sec.className = 'bolum'; sec.id = 'planlayici';
      sec.innerHTML = '<h2>Planlayıcı modeli</h2><p class="aciklama">Kartı planlayan modele göre ilk geçiş, kabul başına maliyet ve süre. Örnek sayısı az olan hücreler karar vermez.</p><div id="planlayiciIcerik"></div>';
      once.insertAdjacentElement('afterend', sec);
      kap = $('#planlayiciIcerik');
    }
    const sat0 = [...(p.toplam || []), ...(p.satirlar || [])];
    if (!sat0.length) { yerlestir(kap, '<p class="bos">Henüz kart yok.</p>'); return; }
    const dk = x => x == null ? '–' : B.sayi(Math.round(x * 10) / 10);
    const dolu = x => x == null ? '–' : B.sayi(x);
    let html = `<div class="tablo-kap"><table class="tablo"><tr><th>Planlayıcı</th><th>Sınıf</th><th>Basamak</th><th class="sayi">Kart</th>
      <th class="sayi">İlk geçiş</th><th class="sayi">Alt sınır (Beta %20)</th><th class="sayi">Ret/denetlenen</th><th class="sayi">İşçi/kart</th>
      <th class="sayi">Kabul başına</th><th class="sayi">Süre medyan (dk)</th><th class="sayi">Süre p90 (dk)</th><th>Not</th></tr>` +
      sat0.map(s => `<tr${s.sinif === '*' ? ' style="font-weight:600"' : ''}><td>${esc(s.planlayici)}</td><td>${s.sinif === '*' ? 'toplam' : esc(s.sinif)}</td>
        <td>${s.baslangic_basamak === '*' ? '–' : esc(s.baslangic_basamak)}</td><td class="sayi">${B.sayi(s.n)}</td>
        <td class="sayi">${s.ilk_gecis == null ? '–' : B.yuzde(s.ilk_gecis)}</td><td class="sayi">${s.alt_sinir == null ? '–' : B.yuzde(s.alt_sinir)}</td>
        <td class="sayi">${B.sayi(s.ret)}/${B.sayi(s.denetlenen)}</td><td class="sayi">${dolu(s.isci_kart)}</td>
        <td class="sayi">${s.kabul_usd == null ? '–' : B.usd(s.kabul_usd)}</td><td class="sayi">${dk(s.dk_medyan)}</td><td class="sayi">${dk(s.dk_p90)}</td>
        <td>${s.yeterli ? '' : rozet('yetersiz veri', 'var(--neutral)')}</td></tr>`).join('') + '</table></div>' +
      `<p class="meta">Ölçüm ${esc(String(p.olcum || '').slice(0, 16).replace('T', ' '))} · en az ${B.sayi(p.min_n)} kart</p>`;
    yerlestir(kap, html);
  }

  // ------------------------------------------------------------ 1b. Ret nedenleri ve onaylı iş başı maliyet ('ders' anahtarı)
  const dersVeri = () => { const v = veri(); return v && v.ders && typeof v.ders === 'object' ? v.ders : null; };
  const NEDEN_AD = { 'siniflanmamis': 'sınıflanmamış', 'kapsam-eksik': 'kapsam eksik', 'bicim': 'biçim', 'sayi-tutarsiz': 'sayı tutarsız', 'kanit-yok': 'kanıt yok', 'talimat-ihlali': 'talimat ihlali', 'kriter-belirsiz': 'kriter belirsiz', 'yetenek-yetersiz': 'yetenek yetersiz' };
  const nedenAd = k => NEDEN_AD[k] || String(k);
  const KOK_SIRA = ['kart', 'basamak', 'dikkat', 'siniflanmamis'];
  function retCiz() {
    const d = dersVeri(), kap = $('#retIcerik');
    const satirlar = d && Array.isArray(d.nedenler) ? d.nedenler : null;
    if (!satirlar || !satirlar.length) {
      yerlestir(kap, `<p class="bos">${d ? 'Henüz reddedilen denetim yok.' : 'Ret nedeni verisi yok.'}</p>`);
      return;
    }
    const kokSay = (s, k) => (s.kok && s.kok[k]) ? B.sayi(s.kok[k]) : '–';
    const enSik = s => {
      const g = Object.entries(s.nedenler || {}).sort((p, q) => q[1] - p[1] || String(p[0]).localeCompare(String(q[0])))[0];
      return g ? `${esc(nedenAd(g[0]))} <span class="meta" style="display:inline">(${B.sayi(g[1])}/${B.sayi(s.ret)})</span>` : '–';
    };
    const toplam = d.toplam && d.toplam.ret != null ? d.toplam.ret : satirlar.reduce((t, s) => t + (s.ret || 0), 0);
    const html = `<div class="tablo-kap"><table class="tablo"><tr><th>Sınıf</th><th>Basamak</th><th class="sayi">Ret</th><th>En sık neden</th>
      <th class="sayi">Kart</th><th class="sayi">Basamak</th><th class="sayi">Dikkat</th><th class="sayi">Sınıflanmamış</th></tr>` +
      satirlar.map(s => `<tr><td>${esc(s.sinif)}</td><td>${esc(s.basamak ?? '–')}</td><td class="sayi">${B.sayi(s.ret)}</td><td>${enSik(s)}</td>` +
        KOK_SIRA.map(k => `<td class="sayi">${kokSay(s, k)}</td>`).join('') + '</tr>').join('') +
      `<tr><td><b>Toplam</b></td><td></td><td class="sayi"><b>${B.sayi(toplam)}</b></td><td></td>` +
        KOK_SIRA.map(k => `<td class="sayi"><b>${(d.toplam && d.toplam.kok && d.toplam.kok[k]) ? B.sayi(d.toplam.kok[k]) : '–'}</b></td>`).join('') + '</tr></table></div>' +
      '<p class="aciklama">Reddedilen denetimler sınıf ve basamağa göre; kök kart (kriter belirsiz), basamak (yetenek yetersiz) ya da dikkat (işçi hatası) olarak sayılır, nedensiz retler sınıflanmamış görünür.</p>';
    yerlestir(kap, html);
  }
  function onayliCiz() {
    const d = dersVeri(), kap = $('#onayliIcerik');
    const satirlar = d && Array.isArray(d.verim) ? d.verim : null;
    if (!satirlar || !satirlar.length) {
      yerlestir(kap, `<p class="bos">${d ? 'Henüz kart yok.' : 'Maliyet verimi verisi yok.'}</p>`);
      return;
    }
    const usd = x => x == null ? '–' : B.usd(x);
    const t = d.toplam || {};
    const html = `<div class="tablo-kap"><table class="tablo"><tr><th>Sınıf</th><th>Başlangıç basamağı</th><th class="sayi">Kart</th><th class="sayi">Onaylanan</th>
      <th class="sayi">Ortalama tur</th><th class="sayi">Toplam</th><th class="sayi" title="Sınıfın tüm kart harcaması / onaylanan kart sayısı (red turları dahil)">Onaylanan kart başına (tüm turlar)</th></tr>` +
      satirlar.map(s => `<tr><td>${esc(s.sinif)}</td><td>${esc(s.baslangic_basamak ?? '–')}</td><td class="sayi">${B.sayi(s.kart)}</td><td class="sayi">${B.sayi(s.onaylanan)}</td>
        <td class="sayi">${s.ort_tur != null ? B.sayi(s.ort_tur, 2) : '–'}</td><td class="sayi">${usd(s.toplam_usd)}</td><td class="sayi">${usd(s.onayli_is_basi_usd)}</td></tr>`).join('') +
      `<tr><td><b>Toplam</b></td><td></td><td class="sayi"><b>${B.sayi(t.kart)}</b></td><td class="sayi"><b>${B.sayi(t.onaylanan)}</b></td>
        <td class="sayi"><b>${t.ort_tur != null ? B.sayi(t.ort_tur, 2) : '–'}</b></td><td class="sayi"><b>${usd(t.toplam_usd)}</b></td><td class="sayi"><b>${usd(t.onayli_is_basi_usd)}</b></td></tr></table></div>` +
      '<p class="aciklama">Onaylı iş başı: kartlara bağlı toplam harcamanın onaylanan kart sayısına bölümü; onaylanan yoksa "–" gösterilir.</p>';
    yerlestir(kap, html);
  }

  // ------------------------------------------------------------ 2. Birim maliyet
  function uyariSerit(u) {
    const tur = u.tur === 'kosu' ? 'Koşu' : u.tur === 'gun' ? 'Gün' : '';
    return `<div class="dikkat" style="--renk:var(--warning)"><span class="simge" aria-hidden="true">!</span>
      <span class="metin">${metin(u.metin)}<span class="meta">${esc(tur ? tur + ' · ' : '')}${B.tarih(u.zaman)}</span></span></div>`;
  }
  function birimCiz() {
    const v = veri(), b = v && v.birim;
    if (!b) return;
    let html = '<div class="karolar">' +
      `<div class="karo"><b>${B.usd(b.kart_basi)}</b><span>Teslim edilen kart başına (yalnız teslim kartlar)</span><small>medyan ${B.usd(b.kart_medyan)} · ${B.sayi(b.teslim_kart)} kart</small></div>` +
      `<div class="karo"><b>${B.usd(b.sohbet_basi)}</b><span>Sohbet başına</span><small>medyan ${B.usd(b.sohbet_medyan)} · ${B.sayi(b.sohbet_sayisi)} sohbet</small></div></div>`;
    const uy = Array.isArray(b.uyarilar) ? b.uyarilar : [];
    if (!uy.length) html += `<p class="tek-satir">${rozet('iyi', 'var(--good)')} Son günlerde anormal sıçrama yok.</p>`;
    else {
      const ILK = 3, ilk = uy.slice(0, ILK), kalan = uy.slice(ILK);
      html += `<div class="uyarilar" role="list" aria-label="Maliyet sıçrama uyarıları">${ilk.map(uyariSerit).join('')}` +
        (kalan.length ? `<details class="nasil" id="uyariDetay"${S.uyariAcik ? ' open' : ''}><summary data-anahtar="uyari">${kalan.length} uyarı daha</summary>
          <div class="uyarilar">${kalan.map(uyariSerit).join('')}</div></details>` : '') + '</div>';
    }
    const pahali = Array.isArray(b.en_pahali) ? b.en_pahali : [];
    if (!pahali.length) html += '<p class="bos">Henüz alt ajan koşusu kaydı yok.</p>';
    else {
      const maks = Math.max(...pahali.map(k => k.usd || 0), 0.0001);
      html += '<h3>En pahalı 10 koşu</h3><div class="tablo-kap"><table class="tablo"><tr><th>Ajan</th><th>Model</th><th class="sayi">Tutar</th><th aria-hidden="true"></th></tr>' +
        pahali.map(k => {
          const ek = [k.gorev && k.gorev !== '-' ? k.gorev : '', E.surec(k.surec), B.tarih(k.zaman)].filter(Boolean).join(' · ');
          return `<tr><td class="ad">${esc(E.ajan(k.ajan))}<span class="meta">${esc(ek)}${k.aciklama ? ' · ' + metin(kisalt(O.temizMetin(k.aciklama), 90)) : ''}</span></td>
            <td>${modelRozet(k.model)}</td><td class="sayi">${B.usd(k.usd)}</td>
            <td><span class="mini" aria-hidden="true"><i style="width:${yz((k.usd || 0) / maks * 100)}%;--renk:${renkModel(k.model)}"></i></span></td></tr>`;
        }).join('') + '</table></div>';
    }
    html += `<details class="nasil"><summary>Nasıl hesaplanır?</summary>
      <p>Kart başına: teslim edilen kartlara bağlı işçi ve denetçi harcamasının ortalaması. Sohbet başına: sohbetlerin toplam harcaması. Sıçrama uyarısı: tamamlanmış günler ve aynı türün medyanıyla karşılaştırılır; bugünün kısmi günü dışarıda kalır.</p></details>`;
    yerlestir($('#birimIcerik'), html);
  }

  // ------------------------------------------------------------ 3. Kart akışı
  const ASAMA = [['kuyruk', 'kuyruk_dk', 'Kuyrukta bekleme', 'var(--s4)'], ['is', 'is_dk', 'İş', 'var(--s1)'], ['denetim bekleme', 'denetim_bekleme_dk', 'Denetçi başlamayı bekleme', 'var(--s2)'], ['denetim calisma', 'denetim_calisma_dk', 'Denetçi çalışması', 'var(--s7)']];
  function akisCiz() {
    const v = veri(), a = v && v.akis;
    if (!a) return;
    const o = a.ozet || {};
    const darbogaz = o.darbogaz;
    const kt = (anahtar, deger, etiket, alt, renk) => {
      const dar = anahtar === darbogaz;
      return `<div class="karo${dar ? ' vurgu' : ''}"${dar ? ` style="--renk:${renk}"` : ''}><b>${B.dk(deger)}</b><span>${etiket}</span>
        <small>${alt}</small>${dar ? '<small><strong style="color:var(--text-primary)">▲ Darboğaz</strong> · medyanda en uzun aşama</small>' : ''}</div>`;
    };
    const esik = o.uzun_esik_dk || 30;
    const uzunNot = n => n ? ` · <strong style="color:var(--warning)">⚠ ${B.sayi(n)} kart ${esik} dk üzeri</strong>` : '';
    let html = '';
    if (!o.kart) html = '<p class="bos">Henüz teslim edilen kart yok; akış teslimden sonra ölçülür.</p>';
    else html = '<div class="karolar">' +
      `<div class="karo"><b>${B.dk(o.toplam_medyan)}</b><span>Plandan teslime (medyan)</span><small>ort. ${B.dk(o.toplam_ort)} · @@SAYIM@@</small></div>` +
      kt('kuyruk', o.kuyruk_medyan, 'Kuyrukta bekleme (medyan)', `kart → işçi başladı · ort. ${B.dk(o.kuyruk_ort)}${uzunNot(o.kuyruk_uzun)}`, ASAMA[0][3]) +
      kt('is', o.is_medyan, 'İş süresi (medyan)', `işçi çalışması, düzeltmeler dahil · ort. ${B.dk(o.is_ort)}`, ASAMA[1][3]) +
      kt('denetim bekleme', o.denetim_bekleme_medyan, 'Denetçi başlamayı bekleme (medyan)', `iş bitti → denetçi başladı · ort. ${B.dk(o.denetim_bekleme_ort)} · ${B.sayi(o.denetim_ayrilan || 0)} kartta ayrıldı${uzunNot(o.denetim_uzun)}`, ASAMA[2][3]) +
      kt('denetim calisma', o.denetim_calisma_medyan, 'Denetçi çalışması (medyan)', `denetçi başladı → karar · ort. ${B.dk(o.denetim_calisma_ort)}`, ASAMA[3][3]) + '</div>';
    const teslimMi = k => k.toplam_dk != null || k.durum === 'teslim';
    const acikMi = k => !teslimMi(k) && k.durum !== 'iptal';
    // teslimler ölçümü olanlar; açık kartlar (Sırada dahil) ölçümsüz de gelir
    const tum = (Array.isArray(a.kartlar) ? a.kartlar : []).filter(k => teslimMi(k) ? (k.toplam_dk != null || k.kuyruk_dk != null) : acikMi(k)).reverse();   // en yeni önce
    // kuyruk süresi: ölçülmüşse o; Sırada kartta oluşturulma zamanından şimdiye; yoksa null
    const kuyrukDk = k => {
      if (k.kuyruk_dk != null) return k.kuyruk_dk;
      if (k.durum !== 'planlandi' || !k.olusturma) return null;
      const t = Date.parse(k.olusturma);
      return isNaN(t) ? null : Math.max(0, (Date.now() - t) / 60000);
    };
    const deg = (k, f) => f === 'kuyruk_dk' ? kuyrukDk(k) : k[f];
    const teslimSay = tum.filter(teslimMi).length, siradaSay = tum.filter(k => k.durum === 'planlandi').length, surenSay = tum.length - teslimSay - siradaSay;
    const sayim = `${B.sayi(teslimSay)} teslim · ${B.sayi(surenSay)} süren · ${B.sayi(siradaSay)} sırada`;
    if (tum.length) {
      const LIMIT = 8;
      let tSira = 0;
      const liste = S.tumKart ? tum : tum.filter(k => acikMi(k) || tSira++ < LIMIT);

      // ölçek yalnız teslim edilen kartlardan; süren kartın çubuğu taralıdır ve ölçeği aşarsa kırpılır
      const maks = Math.max(...tum.filter(teslimMi).map(k => ASAMA.reduce((t, [, f]) => t + (k[f] || 0), 0)), 0.0001);
      // süren aşama kartın durumundan: Sırada → kuyruk, Çalışıyor/Reddedildi → iş, Denetimde → denetçi başladıysa çalışma, değilse başlamayı bekleme
      const SUREN = { planlandi: 'kuyruk', isleniyor: 'is', reddedildi: 'is', denetimde: 'denetim bekleme' };
      const surenAsama = k => k.durum === 'denetimde' && k.denetim_basladi ? 'denetim calisma' : SUREN[k.durum];
      const baslik = (ad, anahtar) => `<th class="sayi${anahtar === darbogaz ? ' vurgu-sutun' : ''}">${ad}${anahtar === darbogaz ? ' ▲' : ''}</th>`;
      const hucre = (k, anahtar, f) => {
        const suren = !teslimMi(k) && surenAsama(k) === anahtar;
        const dv = deg(k, f), deger = dv != null ? B.dk(dv) : '–';
        const uzun = (anahtar === 'kuyruk' || anahtar === 'denetim bekleme') && dv != null && dv > esik
          ? ` <span title="${esik} dk üzeri bekleme" style="color:var(--warning)">⚠</span>` : '';
        return `<td class="sayi${anahtar === darbogaz ? ' vurgu-sutun' : ''}">${suren ? deger + ' · <em>sürüyor</em>' : deger}${uzun}</td>`;
      };
      const durumEt = k => { if (teslimMi(k)) return ''; const d = E.durum(k.durum); return ` ${rozet(d.ad, d.renk)}`; };
      const cubuk = k => {
        const tarali = !teslimMi(k);
        const parca = ASAMA.map(([, f, , r]) => deg(k, f) ? [deg(k, f), r] : null).filter(Boolean);
        const toplamK = parca.reduce((t, p) => t + p[0], 0);
        const olcek = tarali && toplamK > maks ? maks / toplamK : 1;       // ölçeği aşan süren kart kırpılır
        return `<span class="asama${tarali ? ' suren' : ''}" aria-hidden="true">${parca.map(([d, r]) => `<i${tarali ? ' class="tarali"' : ''} style="width:${yz(d * olcek / maks * 100)}%;--renk:${r}"></i>`).join('')}${tarali && toplamK > maks ? '<b>…</b>' : ''}</span>`;
      };
      html += `<p class="meta tablo-ust">Tablo: ${sayim}. Süren ve sıradaki kartların ölçümü sürüyor; toplamı ve aşamalar eksik.</p>`;
      html += `<div class="tablo-kap"><table class="tablo"><tr><th>Kart</th><th>Basamak</th><th class="sayi">Tur</th>${baslik('Kuyruk', 'kuyruk')}${baslik('İş', 'is')}${baslik('Denetçi bekleme', 'denetim bekleme')}${baslik('Denetçi çalışma', 'denetim calisma')}
        <th class="sayi">Toplam</th><th>Aşamalar</th></tr>` +
        liste.map(k => `<tr><td class="ad">${esc(k.id)}${durumEt(k)}<span class="meta">${metin(kisalt(k.baslik, 70))}</span></td><td>${esc(k.basamak || '–')}</td><td class="sayi">${B.sayi(k.tur)}</td>
          ${hucre(k, 'kuyruk', 'kuyruk_dk')}${hucre(k, 'is', 'is_dk')}${hucre(k, 'denetim bekleme', 'denetim_bekleme_dk')}${hucre(k, 'denetim calisma', 'denetim_calisma_dk')}
          <td class="sayi">${teslimMi(k) ? B.dk(k.toplam_dk) : '–'}</td>
          <td>${cubuk(k)}</td></tr>`).join('') + '</table></div>';
      html += `<div class="lejant">${ASAMA.map(([, , ad, r]) => `<span><i style="--renk:${r}"></i>${ad}</span>`).join('')}</div>`;
      if (tum.length > liste.length || S.tumKart) html += `<button type="button" class="tablo-dugme" id="tumKartDugme" data-anahtar="tumkart" aria-expanded="${S.tumKart}">${S.tumKart ? `Yalnız son ${LIMIT} teslim ve açık kartları göster` : `Tümünü göster · ${sayim}`}</button>`;
    } else if (o.kart) html += '<p class="bos">Akışı ölçülebilen kart yok.</p>';
    html += `<details class="nasil"><summary>Nasıl hesaplanır?</summary>
      <p>Kuyruk: kart oluşturulduktan işçi başlayana kadar. İş: işçi çalışma süreleri toplamı. Denetçi başlamayı bekleme: iş bitti ile denetçi başlaması arası. Denetçi çalışması: denetçi başlaması ile denetim kararı arası. Denetçi başlangıcı kartta kayıtlı değilse (eski kartlar) denetçi koşu kaydından türetilir; ikisi de yoksa kart bu iki sütunda boş kalır ve ölçüye girmez. Kutular medyanı gösterir; birkaç uzun bekleyen kart ortalamayı şişirdiği için ortalama küçük yazıyla yanında durur. ${esik} dk üzeri kuyruk ve denetçi bekleme ⚠ ile işaretlenir. Denetim turu sayılırken denetimsiz tekrar is-bitti'ler birleştirilir: bekleme son is-bitti'den sayılır. Darboğaz, medyanı en uzun olan aşamadır; tabloda o sütun vurgulanır.</p></details>`;
    yerlestir($('#akisIcerik'), html.replace('@@SAYIM@@', sayim));
  }

  // ------------------------------------------------------------ 4. Paralel zaman çizelgesi
  const ROL = [['isci', 'İşçi'], ['denetci', 'Denetçi'], ['diger', 'Diğer'], ['bakim', 'Bakım'], ['ana', 'Ana']];
  const BOSLUK_MS = 30 * 60000;                 // bundan uzun boşluklar kesik eksenle sıkıştırılır
  const anahtarOf = x => [x.bas, x.bit, x.ajan, x.oturum, x.gorev].join('|');
  const sureMetni = dkSure => dkSure < 1 ? '< 1 dk' : B.dk(dkSure);

  function ganttModel(liste) {
    const k = liste.map(x => ({ x, b: Date.parse(x.bas), s: Date.parse(x.bit) })).filter(o => !isNaN(o.b) && !isNaN(o.s))
      .map(o => ({ ...o, s: Math.max(o.s, o.b), rol: ROL.some(r => r[0] === o.x.rol) ? o.x.rol : 'diger' })).sort((p, q) => p.b - q.b || p.s - q.s);
    if (!k.length) return null;
    // dolu aralıklar: aralarındaki boşluk ≤ 30 dk ise aynı parça; daha uzunsa parçalar arası kesik
    const seg = [];
    k.forEach(o => {
      const son = seg[seg.length - 1];
      if (son && o.b - son.t1 <= BOSLUK_MS) son.t1 = Math.max(son.t1, o.s); else seg.push({ t0: o.b, t1: o.s });
    });
    seg.forEach(g => { g.t1 = Math.max(g.t1, g.t0 + 60000); });
    const dolu = seg.reduce((t, g) => t + (g.t1 - g.t0), 0);
    const kesik = Math.max(dolu * 0.05, 60000);       // her sıkıştırılmış boşluğa ayrılan sabit genişlik
    let at = 0;
    seg.forEach((g, i) => { g.off = at; at += (g.t1 - g.t0) + (i < seg.length - 1 ? kesik : 0); });
    const toplam = at;
    const pos = t => {
      let g = seg[0];
      for (const s of seg) if (s.t0 <= t) g = s;
      return (g.off + Math.min(Math.max(t - g.t0, 0), g.t1 - g.t0)) / toplam * 100;
    };
    // şeritler: rol başına, çakışmayanlar aynı şeride
    const gruplar = ROL.map(([id, ad]) => {
      const uyeler = k.filter(o => o.rol === id);
      const seritler = [];
      uyeler.forEach(o => { let i = seritler.findIndex(son => son <= o.b); if (i < 0) { i = seritler.length; seritler.push(0); } seritler[i] = o.s; o.serit = i; });
      return { id, ad, uyeler, serit: seritler.length };
    }).filter(g => g.uyeler.length);
    // en çok eşzamanlı ajan
    let es = 0, enCok = 0;
    k.flatMap(o => [[o.b, 1], [o.s, -1]]).sort((p, q) => p[0] - q[0] || p[1] - q[1]).forEach(([, d]) => { es += d; enCok = Math.max(enCok, es); });
    // eksen işaretleri: her parçanın başı + düzenli aralıklar; birbirine %8'den yakın etiket konmaz
    const isaretler = [];
    let sonPos = -99;
    seg.forEach(g => {
      const sure = g.t1 - g.t0, adim = sure > 4 * 3600e3 ? 3600e3 : sure > 90 * 60e3 ? 1800e3 : sure > 30 * 60e3 ? 600e3 : 300e3;
      const adaylar = [g.t0];
      for (let t = Math.ceil((g.t0 + 1) / adim) * adim; t < g.t1; t += adim) adaylar.push(t);
      adaylar.forEach(t => { const p = pos(t); if (p - sonPos >= 8) { isaretler.push({ t, p }); sonPos = p; } });
    });
    const bosluklar = [];
    for (let i = 0; i < seg.length - 1; i++) {
      bosluklar.push({ sol: (seg[i].off + (seg[i].t1 - seg[i].t0)) / toplam * 100, genis: kesik / toplam * 100, ms: seg[i + 1].t0 - seg[i].t1 });
    }
    return { k, seg, pos, gruplar, enCok, isaretler, bosluklar, toplam: k.reduce((t, o) => t + (o.x.usd || 0), 0) };
  }

  function ganttCiz() {
    const v = veri(), a = v && v.akis;
    if (!a) return;
    const gunler = Array.isArray(a.gunler) ? a.gunler : [];
    // gün seçici: seçenek listesi değişince yenilenir, seçim korunur
    const sec = $('#ganttGun');
    const secHtml = gunler.map(g => `<option value="${esc(g)}">${esc(B.gun(g))}</option>`).join('');
    if (sec.__html !== secHtml) { sec.innerHTML = secHtml; sec.__html = secHtml; }
    if (!gunler.includes(S.gun)) S.gun = gunler[0] || null;
    sec.value = S.gun || '';
    const kap = $('#ganttIcerik'), ayr = $('#ganttAyrinti');
    const liste = (Array.isArray(a.kosular) ? a.kosular : []).filter(x => x.gun === S.gun);
    const m = liste.length ? ganttModel(liste) : null;
    if (!m) {
      $('#ganttOzet').textContent = '';
      yerlestir(kap, `<p class="bos">${gunler.length ? 'Bu gün alt ajan koşusu yok.' : 'Henüz alt ajan koşusu kaydı yok.'}</p>`);
      yerlestir(ayr, '');
      return;
    }
    $('#ganttOzet').textContent = `${B.sayi(m.k.length)} koşu · en çok ${B.sayi(m.enCok)} ajan aynı anda · ${B.usd(m.toplam)}`;
    let secili = null;
    const satirSayisi = m.gruplar.length + 1;
    let h = `<div class="g-kaydir"><div class="g-izgara" role="group" aria-label="Paralel zaman çizelgesi">`;
    h += `<div class="g-eksen">${m.isaretler.map((t, i) => `<span class="${t.p < 4 ? 'bas' : t.p > 96 ? 'son' : ''}" style="left:${yz(t.p)}%">${B.saat(t.t)}</span>`).join('')}</div>`;
    h += `<div class="g-zemin" style="grid-row:1 / span ${satirSayisi}">` +
      m.isaretler.map(t => `<span class="cizgi" style="left:${yz(t.p)}%"></span>`).join('') +
      m.bosluklar.map(b2 => `<span class="kesik" style="left:${yz(b2.sol)}%;width:${yz(b2.genis)}%" data-ipucu="${esc('<b>Sıkıştırılmış boşluk</b>' + sat('Süre', B.dk(b2.ms / 60000)) + '<div class="meta">30 dakikadan uzun boşluklar çizelgede kısaltılır.</div>')}"></span>`).join('') + '</div>';
    m.gruplar.forEach((g, gi) => {
      h += `<div class="g-etiket" style="grid-row:${gi + 2}">${esc(g.ad)}<small>${B.sayi(g.uyeler.length)} koşu</small></div><div class="g-seritler" style="grid-row:${gi + 2}">`;
      for (let s = 0; s < g.serit; s++) {
        h += '<div class="g-serit">' + g.uyeler.filter(o => o.serit === s).map(o => {
          const x = o.x, sol = m.pos(o.b), gen = Math.max(m.pos(o.s) - sol, 0);
          const anahtar = anahtarOf(x), acik = S.gSecili === anahtar;
          if (acik) secili = o;
          const etiket = x.gorev && x.gorev !== '-' && gen * 8 > 44 ? esc(x.gorev) : '';
          const sure = sureMetni((o.s - o.b) / 60000);
          const ad = `${E.ajan(x.ajan)}, ${x.gorev && x.gorev !== '-' ? x.gorev + ', ' : ''}${sure}, ${B.usd(x.usd)}`;
          return `<button type="button" class="g-cubuk" style="left:min(${yz(sol)}%, calc(100% - 8px));width:${yz(gen)}%;--renk:${renkModel(x.model)}" data-k="${esc(anahtar)}" data-anahtar="g:${esc(anahtar)}"
            aria-pressed="${acik}" aria-controls="ganttAyrinti" aria-label="${esc(ad)}" data-ipucu="${esc('<b>' + esc(E.ajan(x.ajan)) + '</b>' + sat('Süre', sure) + sat('Maliyet', B.usd(x.usd)) + '<div class="meta">Tıkla: ayrıntıyı aç</div>')}">${etiket}</button>`;
        }).join('') + '</div>';
      }
      h += '</div>';
    });
    h += '</div></div>';
    const modeller = [...new Set(m.k.map(o => o.x.model))];
    h += `<div class="lejant" aria-label="Renkler: model">${modeller.map(md => `<span><i style="--renk:${renkModel(md)}"></i>${esc(E.model(md))}</span>`).join('')}` +
      (m.bosluklar.length ? '<span><i class="tarali"></i>sıkıştırılmış boşluk (30 dk+)</span>' : '') + '</div>';
    yerlestir(kap, h);
    // ayrıntı satırı
    if (!secili) { S.gSecili = null; yerlestir(ayr, ''); return; }
    const x = secili.x;
    const alan = (ad, d, genis) => `<div${genis ? ' class="genis"' : ''}><dt>${esc(ad)}</dt><dd>${d}</dd></div>`;
    yerlestir(ayr, `<div class="g-ayrinti" style="--renk:${renkModel(x.model)}">
      <div class="ust"><b>${esc(E.ajan(x.ajan))}</b><button type="button" id="ganttKapat" data-anahtar="gkapat">Kapat</button></div>
      <dl class="alanlar">${alan('Görev', x.gorev && x.gorev !== '-' ? esc(x.gorev) : 'Kartsız')}${alan('İş türü', esc(E.surec(x.surec)))}${alan('Model', modelRozet(x.model))}
      ${alan('Süre', esc(sureMetni((secili.s - secili.b) / 60000)))}${alan('Saat', `${B.saat(secili.b)} – ${B.saat(secili.s)}`)}${alan('Maliyet', B.usd(x.usd))}
      ${x.aciklama ? alan('Açıklama', metin(x.aciklama), true) : ''}</dl></div>`);
  }

  // ------------------------------------------------------------ 5. Skill getirisi
  function skillCiz() {
    const v = veri(), s = v && v.skill;
    if (!s) return;
    const kul = Object.entries(s.kullanim || {}).sort((p, q) => q[1] - p[1]);
    const adaylar = Array.isArray(s.adaylar) ? s.adaylar : [];
    if (!kul.length && !adaylar.length) {
      yerlestir($('#skillIcerik'), '<p class="bos">Henüz skill kullanımı ya da adayı kaydı yok. <code>/orkestra:skill-avi</code> ya da perspektif önerdiğinde burada listelenir.</p>');
      return;
    }
    const toplamKul = kul.reduce((t, [, n]) => t + n, 0);
    let html = '<div class="karolar">' +
      `<div class="karo"><b>${B.sayi(toplamKul)}</b><span>Skill çağrısı</span><small>${B.sayi(kul.length)} farklı skill</small></div>` +
      (adaylar.length ? `<div class="karo"><b>${B.usd(s.aday_tasarruf_toplam)}</b><span>Adayların tahmini tasarrufu</span><small>${B.sayi(adaylar.length)} aday</small></div>` : '') + '</div>';
    if (kul.length) {
      const maks = Math.max(...kul.map(p => p[1]), 1);
      html += '<h3>Kullanım</h3><div class="cubuklar">' + kul.map(([ad, n]) =>
        `<div class="cubuk"><span class="etiket" title="${esc(ad)}"><code>${esc(ad)}</code></span><span class="yol"><span class="dolgu" style="width:${yz(n / maks * 100)}%"></span></span><span class="deger">×${B.sayi(n)}</span></div>`).join('') + '</div>';
    }
    if (adaylar.length) {
      html += '<h3>Adaylar</h3><div class="tablo-kap"><table class="tablo"><tr><th>Skill adayı</th><th class="sayi">Sıklık</th><th>Beklenen tasarruf</th></tr>' +
        adaylar.map(a => `<tr><td class="ad"><code>${esc(a.ad)}</code><span class="meta">${B.tarih(a.zaman)}</span></td><td class="sayi">${a.siklik != null ? B.sayi(a.siklik) : '–'}</td>
          <td>${a.tasarruf_usd != null ? '<b>' + B.usd(a.tasarruf_usd) + '</b> ' : ''}<span class="meta" style="display:inline">${metin(a.tasarruf_metni || 'gerekçede belirtilmemiş')}</span></td></tr>`).join('') + '</table></div>';
    } else html += '<p class="bos">Henüz skill adayı yok.</p>';
    html += `<details class="nasil"><summary>Nasıl hesaplanır?</summary>
      <p>Kullanım: kayıt başladığından beri her skill'in kaç kez çağrıldığı. Aday: skill avcısının ya da perspektifin önerdiği, henüz yazılmamış tekrarlı iş; tasarruf, gerekçesinde belirtilen tahmindir.</p></details>`;
    yerlestir($('#skillIcerik'), html);
  }

  // ------------------------------------------------------------ 6. Sağlık
  function saglikKaro(seviye, baslik, deger, alt, ipucu) {
    const d = sev(seviye);
    return `<div class="karo vurgu" style="--renk:${d.renk}" tabindex="0" data-ipucu="${esc(ipucu)}" aria-label="${esc(baslik + ': ' + deger.replace(/<[^>]*>/g, '') + ', ' + d.ad)}">
      <b>${deger}</b><span>${esc(baslik)}</span><small>${rozet(d.ad, d.renk)}${alt}</small></div>`;
  }
  function saglikCiz() {
    const v = veri(), s = v && v.saglik;
    if (!s) return;
    const h = s.hafiza || {}, r = s.perspektif || {}, e = s.etiketsiz || {}, k = s.hook || {};
    const buyuk = Array.isArray(h.en_buyuk) ? h.en_buyuk : [];
    const hIp = `<b>Hafıza okuma sınırı</b>` + '<div class="meta">MEMORY.md (okunan dizin)</div>' + sat('Satır', B.sayi(h.satir) + ' / ' + B.sayi(h.satir_sinir)) + sat('Bayt', B.sayi(h.bayt) + ' / ' + B.sayi(h.bayt_sinir)) + '<div class="meta">Tüm hafıza</div>' + sat('Konu dosyası', B.sayi(h.dosya)) + sat('Toplam boyut', B.sayi(h.toplam_bayt) + ' bayt') +
      (buyuk.length ? `<div class="meta">En büyük dosyalar</div>` + buyuk.map(([ad, bayt]) => sat(String(ad), B.sayi(bayt) + ' bayt')).join('') : '') +
      (h.yol ? `<div class="meta">${esc(O.yolGizle(h.yol))}</div>` : '');
    const rIp = `<b>Son perspektif</b>` + sat('Zaman', B.tarih(r.son)) + sat('Bekleyen oturum', B.sayi(r.oturum_sayaci)) + sat('Okunmamış rapor', r.okunmamis_rapor ? 'var' : 'yok') +
      sat('Zamanı geldi', r.zamani_geldi ? 'evet' : 'hayır') + (r.son_hata ? `<div class="meta">Son hata kaydı: ${esc(r.son_hata)}</div>` : '');
    const ajanlar = Object.entries(e.ajanlar || {});
    const eIp = `<b>Etiketsiz koşular (7 gün)</b>` + (ajanlar.length ? ajanlar.map(([ad, n]) => sat(E.ajan(ad), '×' + B.sayi(n))).join('') : '<div class="meta">Etiketsiz koşu yok.</div>') +
      '<div class="meta">Etiketsiz: alt ajan koşusunda kart ve iş türü etiketi yok.</div>';
    const olaylar = Object.entries(k.olaylar || {});
    const kIp = `<b>Hook hataları</b>` + sat('Son 7 gün', B.sayi(k.son7)) + sat('Toplam', B.sayi(k.toplam)) +
      olaylar.map(([ad, n]) => sat(ad, '×' + B.sayi(n))).join('') +
      (k.son ? `<div class="meta">Son: ${esc(k.son.olay)} · ${B.tarih(k.son.zaman)}<br>${metin(kisalt(k.son.hata || '', 160))}</div>` : '');
    const rGun = r.son ? (r.gun_once === 0 ? 'bugün' : `${B.sayi(r.gun_once)} gün önce`) : 'hiç';
    const html = '<div class="karolar">' +
      saglikKaro(h.seviye, 'Hafıza okuma sınırı (MEMORY.md)', h.var ? `${B.sayi(h.satir)}/${B.sayi(h.satir_sinir)} satır` : 'MEMORY.md yok',
        h.var ? `MEMORY.md: ${B.sayi(h.bayt)} / ${B.sayi(h.bayt_sinir)} bayt · sınıra ${B.yuzde(1 - (h.doluluk || 0))} var · tüm hafıza: ${B.sayi(h.dosya)} dosya, ${B.sayi(h.toplam_bayt)} bayt` : 'hafıza dizini bulunamadı', hIp) +
      saglikKaro(r.seviye, 'Son perspektif', rGun,
        [B.tarih(r.son), `${B.sayi(r.oturum_sayaci)} oturumdur bekliyor`, r.okunmamis_rapor ? 'okunmamış rapor var' : '', r.zamani_geldi ? 'zamanı geldi' : '', r.son_hata ? 'hata kaydı var' : ''].filter(x => x && x !== '–').join(' · ') + ` · <a href="${esc('/onaylar' + location.search)}">Onaylar'da gör</a>`, rIp) +
      saglikKaro(e.seviye, 'Etiketsiz koşu oranı (7 gün)', B.yuzde(e.oran), `${B.sayi(e.etiketsiz)}/${B.sayi(e.kosu)} alt ajan koşusunda etiket yok`, eIp) +
      saglikKaro(k.seviye, 'Hook hataları (7 gün)', B.sayi(k.son7), k.son ? `son: ${B.tarih(k.son.zaman)}` : `toplam ${B.sayi(k.toplam)}`, kIp) + '</div>';
    yerlestir($('#saglikIcerik'), html);
  }

  // ------------------------------------------------------------ durum: bayatlık, hata, orkestrasız
  function bayatBolumu() {
    const i = O.bayatIsaret(K), e = {};
    ['pano', 'basamak', 'ret', 'onayli', 'birim', 'akis', 'gantt', 'skill', 'saglik'].forEach(ad => { e[ad + 'Bayat'] = i; });
    bayatCiz(e);
  }
  function uyariCiz() {
    const sure = K && K.sonBasari ? `son başarılı yenileme ${B.saat(K.sonBasari)}` : 'henüz hiç veri alınamadı';
    yerlestir($('#verimUyari'), K && K.uzunHata && orkestrali() ? `<div class="dikkat" style="--renk:var(--critical)"><span class="simge" aria-hidden="true">!</span>
      <span class="metin"><b>Analitik verisi alınamadı</b><span class="meta" title="${esc(O.yolGizle(K.hata))}">${esc(sure)} · ${metin(kisalt(K.hata, 120))} · yeniden deneniyor</span></span></div>` : '');
  }
  const KABUL = ['pano', 'basamak', 'ret', 'onayli', 'birim', 'akis', 'gantt', 'skill', 'saglik'];
  function durumCiz() {
    const ork = orkestrali();
    $('#icerik').classList.toggle('gizli', !ork);
    $('#pano').classList.toggle('gizli', !ork);
    $('#orkestrasiz').hidden = ork;
    if (!ork) {
      yerlestir($('#orkIcerik'), `<p class="bos">Bu çalışma alanında orkestra kurulu değil; burada yalnız <a href="/maliyet${O.alan ? '?alan=' + encodeURIComponent(O.alan) : ''}">Maliyet</a> sayfası anlamlı.</p>
        <details class="nasil"><summary>Nasıl kurulur?</summary>
        <p>Claude-Orchestration klasöründe: <code>python araclar/projeye_kur.py "&lt;proje klasörü&gt;"</code></p>
        <p>Sonra o projede Claude içinde <code>/orkestra:baslat</code>.</p></details>`);
    }
    return ork;
  }
  // Son iyi veri yokken: bekliyorsa "Yükleniyor…", hata varsa hata satırı. Veri varsa bölümlere dokunmaz.
  function veriYokCiz() {
    if (veri()) return;
    const hata = S.veri && S.veri.hata ? O.hataMetni(S.veri.hata) : (K && K.durum === 'hata' ? K.hata : '');
    const m = S.veri && S.veri.acik === false ? `<p class="bos">${metin(S.veri.mesaj || 'Bu çalışma alanında orkestra açık değil.')}</p>` : hata ? `<p class="bos">Veri alınamadı: ${metin(kisalt(hata, 200))}. Birkaç saniyede bir yeniden deneniyor.</p>` : '<p class="bos">Yükleniyor…</p>';
    // pano: kartlar sabit kabuktur, yalnız durum satırı yazılır (kartların içi veri gelince doldurulur)
    KABUL.forEach(ad => { if (ad === 'pano') { const d = $('#panoDurum'); d.hidden = false; yerlestir(d, m); } else yerlestir($('#' + ad + 'Icerik'), m); });
    $('#ganttOzet').textContent = '';
    yerlestir($('#ganttAyrinti'), '');
    $('#ganttGun').innerHTML = ''; $('#ganttGun').__html = '';
  }

  const hepsi = () => { if (durumCiz()) ciz(panoCiz, basamakCiz, planlayiciCiz, retCiz, onayliCiz, birimCiz, akisCiz, ganttCiz, skillCiz, saglikCiz, bayatBolumu, uyariCiz); else ciz(bayatBolumu, uyariCiz); };

  // ------------------------------------------------------------ etkileşim
  const ana = $('main');
  window.addEventListener('orkestra:pencere', panoCiz);
  ana.addEventListener('click', e => {
    const c = e.target.closest('button.g-cubuk');
    if (c) { S.gSecili = S.gSecili === c.dataset.k ? null : c.dataset.k; ganttCiz(); return; }
    if (e.target.closest('#ganttKapat')) {
      const onceki = S.gSecili; S.gSecili = null; ganttCiz();
      const dugme = [...document.querySelectorAll('button.g-cubuk')].find(b => b.dataset.k === onceki);
      if (dugme) dugme.focus({ preventScroll: true });
      return;
    }
    if (e.target.closest('#tumKartDugme')) { S.tumKart = !S.tumKart; akisCiz(); return; }
  });
  ana.addEventListener('keydown', e => {
    if (e.key === 'Escape' && S.gSecili && e.target.closest && e.target.closest('#gantt')) { S.gSecili = null; ganttCiz(); }
  });
  ana.addEventListener('toggle', e => { if (e.target.id === 'uyariDetay') S.uyariAcik = e.target.open; }, true);
  $('#ganttGun').addEventListener('change', e => { S.gun = e.target.value; S.gSecili = null; ganttCiz(); });

  // ------------------------------------------------------------ veri
  if (!O.sayfa) O.kabuk({ sayfa: 'verim' });   // Maliyet sayfasında kabuğu maliyet.js kurar
  K = O.veri(() => '/analitik.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Analitik verisi', aralik: 15000,
    gecerli: v => v && (v.acik === false || (v.basamak && v.birim && v.akis && v.saglik && (!v.alan || !v.alan.id || v.alan.id === O.alan))),
    cizici: v => { S.veri = v; hepsi(); },
    durum: () => ciz(durumCiz, ...(veri() ? [] : [veriYokCiz]), bayatBolumu, uyariCiz),
  });
  // alan değişince eski alanın verisi artık "son iyi veri" değildir: sıfırla, bölümleri hemen "Yükleniyor…" yap
  window.addEventListener('orkestra:alan', () => {
    S.veri = null; S.gun = null; S.gSecili = null; S.tumKart = false; S.uyariAcik = false;
    ciz(durumCiz, veriYokCiz, bayatBolumu, uyariCiz);
  });
  ciz(durumCiz, veriYokCiz);
})();
