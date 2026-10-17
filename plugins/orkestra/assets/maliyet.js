'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { B, E, esc } = O;
  const { bayatCiz, ciz, yerlestir } = O;
  const metin = s => esc(O.yolGizle(O.temizMetin(s)));
  const kisalt = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s; };
  const sat = (ad, deger, renk) => `<div class="sat"><span>${renk ? `<i style="background:${renk}"></i>` : ''}${esc(ad)}</span><span>${deger}</span></div>`;
  const r2 = v => Math.round(Number(v) * 100) / 100;
  const sayiMi = v => v != null && isFinite(v);

  // Kaynaklar: S.ozet (ozet.json), S.an (analitik.json; yalnız bu alanınsa), S.tum (analitik-tum.json).
  // Hata anında silinmez; yalnız alan değişince ozet ve analitik sıfırlanır. Kaynak durumu KO, KA, KT kontrol nesnelerinde.
  let KO = null, KA = null, KT = null;
  const S = { ozet: null, an: null, tum: null, donem: 'gunluk', olcek: 'usd', hepsiAcik: false };
  const KAPSAM_ANAHTARI = () => 'orkestra.maliyet.kapsam.' + O.alan;

  const SERI = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)'];
  const MODEL_SIRA = ['opus-5-5', 'sonnet-5-5', 'haiku-5-5', 'fable-5-1'];
  const modelSade = k => String(k ?? '').replace(/^claude-/, '').replace(/\[[^\]]*\]$/, '');
  const digerModel = [];
  const modelRenk = k => {
    const s = modelSade(k), i = MODEL_SIRA.indexOf(s);
    if (i >= 0) return SERI[i];
    if (!digerModel.includes(s)) digerModel.push(s);
    return SERI[Math.min(4 + digerModel.indexOf(s), 7)];
  };

  const sohbetler = () => (S.ozet && Array.isArray(S.ozet.sohbetler)) ? S.ozet.sohbetler : [];
  const mal = () => (S.ozet && S.ozet.maliyet && typeof S.ozet.maliyet === 'object') ? S.ozet.maliyet : {};
  const orkestrali = () => {
    if (S.ozet && S.ozet.orkestra === false) return false;
    const b = O.alanBilgi();
    return b ? !!b.orkestra : true;
  };
  const alanTum = () => (S.tum && Array.isArray(S.tum.alanlar)) ? S.tum.alanlar.find(a => a.id === O.alan) || null : null;
  // Kapsam: kayıtlı sohbet kimliği (alan başına localStorage); listede yoksa yok sayılır
  const kapsamId = () => {
    const id = O.depo.al(KAPSAM_ANAHTARI());
    return id && sohbetler().some(s => s.oturum === id) ? id : null;
  };
  const kapsamSohbet = () => { const id = kapsamId(); return id ? sohbetler().find(s => s.oturum === id) : null; };
  // Kapsamdaki sohbetin kırılımı: nesne | 'yok' (kapanmış sohbet: yalnız toplam bilinir) | null (kapsam yok)
  const kapsamKirilim = () => {
    const id = kapsamId();
    if (!id) return null;
    const o = mal().oturumlar && mal().oturumlar[id];
    return o || 'yok';
  };

  function karo(deger, etiket, alt, ek) {
    return `<div class="karo${ek ? ' ' + ek.sinif : ''}"${ek && ek.renk ? ` style="--renk:${ek.renk}"` : ''}><b>${deger}</b><span>${etiket}</span>${alt ? `<small>${alt}</small>` : ''}</div>`;
  }
  // Aynı değeri taşıyan, sıfır olmayan tutarlar tek karoya iner: [[etiket, değer, alt], …]
  function tutarKarolari(ogeler) {
    const gruplar = [];
    ogeler.forEach(([et, v, alt]) => {
      if (!sayiMi(v) || r2(v) === 0) return;
      const g = gruplar.find(x => x.v === r2(v));
      if (g) { g.etiketler.push(et); if (alt && !g.alt) g.alt = alt; } else gruplar.push({ v: r2(v), etiketler: [et], alt });
    });
    return gruplar.map(g => karo(B.usd(g.v), esc(g.etiketler.join(' · ')), esc(g.alt || ''))).join('');
  }

  // ------------------------------------------------------------ uyarı şeridi ve bayatlık
  const KOTA_PENCERE = [['bes_saat', '5 saatlik sınır'], ['haftalik', 'Haftalık sınır']];
  const SEVIYE_RENK = { iyi: 'var(--good)', uyari: 'var(--warning)', kritik: 'var(--critical)' };
  function kotaVerisi() {
    if (S.an && S.an.kota && S.an.kota.kaynak) return S.an.kota;
    return (S.tum && S.tum.kota) || (S.an && S.an.kota) || null;
  }
  function uyariCiz() {
    const ogeler = [];
    const sure = k => k.sonBasari ? `son başarılı yenileme ${B.saat(k.sonBasari)}` : 'henüz hiç veri alınamadı';
    const sorun = (k, ad, renk) => `<div class="dikkat" style="--renk:${renk}"><span class="simge" aria-hidden="true">!</span>
      <span class="metin"><b>${esc(ad)} alınamadı</b><span class="meta" title="${esc(O.yolGizle(k.hata))}">${esc(sure(k))} · ${metin(kisalt(k.hata, 120))} · yeniden deneniyor</span></span></div>`;
    if (KO && KO.uzunHata) ogeler.push(sorun(KO, 'Sohbet ve token verisi', 'var(--critical)'));
    if (KA && KA.uzunHata && orkestrali()) ogeler.push(sorun(KA, 'Zaman ve ay sonu verisi', 'var(--warning)'));
    if (KT && KT.uzunHata) ogeler.push(sorun(KT, 'Tüm projeler verisi', 'var(--warning)'));
    const kota = kotaVerisi();
    if (kota && kota.kaynak) {
      KOTA_PENCERE.forEach(([a, ad]) => {
        const p = kota[a];
        if (!p || p.seviye === 'iyi' || p.eski) return;
        const doluyor = p.tahmin && p.tahmin.sifirlanmadan_once ? 'Bu hızla sıfırlanmadan önce dolacak.' : '';
        ogeler.push(`<div class="dikkat" style="--renk:${p.seviye === 'kritik' ? 'var(--critical)' : 'var(--warning)'}"><span class="simge" aria-hidden="true">!</span>
          <span class="metin"><b>Kota: ${esc(ad)} ${B.yuzde(p.yuzde / 100)} dolu</b>${doluyor ? `<span class="meta">${esc(doluyor)}</span>` : ''}</span>
          <span class="eylem"><a href="#kota">Kotaya git</a></span></div>`);
      });
    }
    yerlestir($('#uyari'), ogeler.length ? `<div class="uyari-alani">${ogeler.join('')}</div>` : '');
  }
  function bayatBolumu() {
    bayatCiz({
      kpiBayat: O.bayatIsaret(KO, orkestrali() ? KA : null),
      sohbetBayat: O.bayatIsaret(KO),
      zamanBayat: O.bayatIsaret(KA),
      kotaBayat: O.bayatIsaret(orkestrali() ? KA : KT),
      tumBayat: O.bayatIsaret(KT),
    });
  }

  // Veri yok durumu: yükleniyor ya da (son iyi veri yokken) hata satırı
  const yuklemeSatiri = (k, ad) => (k && k.durum === 'hata')
    ? `<p class="bos">${esc(ad)} alınamadı: ${metin(kisalt(k.hata, 200))}</p>` : '<p class="bos">Yükleniyor…</p>';

  // ------------------------------------------------------------ 1. KPI
  function kpiCiz() {
    const kap = $('#kpiIcerik');
    if (!S.ozet) { yerlestir(kap, yuklemeSatiri(KO, 'Harcama verisi')); return; }
    const m = mal(), ork = orkestrali();
    const t = (S.an && ork) ? S.an.trend : null, ay = t && t.ay_sonu;
    const ilkKayit = t && t.ilk_kayit;
    let karolar = '';
    // Bugün + Bu ay: aynı değerde tek karo, sıfır olan gizli
    let buAy = null, buAyAlt = '';
    if (ay && sayiMi(ay.simdiye)) {
      buAy = ay.simdiye;
      buAyAlt = [ay.veri_gun ? `${B.sayi(ay.veri_gun)} günlük veri` : '', ay.onceki_ay ? `geçen ay ${B.usd(ay.onceki_ay)}` : ''].filter(Boolean).join(' · ');
    } else if (!ork) {
      const a = alanTum();
      if (a) buAy = a.ay;
    }
    const ogeler = [['Bugün', m.bugun, ''], ['Bu ay', buAy, buAyAlt]];
    if (!ork) ogeler.push(['Kayıtlı toplam', m.toplam, `${B.sayi(sohbetler().length)} sohbet`]);
    karolar += tutarKarolari(ogeler);
    // Ay sonu tahmini: iki yöntem %10'dan az farklıysa tek değer, değilse aralık
    if (ay && ork) {
      const adaylar = [ay.tahmin_7g, ay.tahmin_ort].filter(sayiMi);
      const bitti = ay.ay_gun && ay.gecen_gun >= ay.ay_gun;
      if (!adaylar.length && !bitti && ay.tahmin_yeterli === false) {
        karolar += karo('–', 'Ay sonu tahmini', esc(`en az 7 günlük veri gerekir (şimdi ${B.sayi(ay.veri_gun || 0)} gün)`));
      } else if (adaylar.length && !bitti) {
        const lo = Math.min(...adaylar), hi = Math.max(...adaylar);
        const buAyIleAyni = r2(lo) === r2(ay.simdiye) && r2(hi) === r2(ay.simdiye);
        if (hi > 0 && !buAyIleAyni) {
          const tek = adaylar.length === 1 || (hi - lo) / hi < 0.10;
          const az = ay.veri_gun != null && ay.veri_gun < 3 ? `yalnız ${B.sayi(ay.veri_gun)} günlük veriye dayanıyor` : '';
          const alt = az || (tek ? 'son 7 günün hızı ve ay ortalaması aynı yönde' : 'son 7 günün hızı ile ay ortalaması arasında');
          karolar += tek
            ? karo(B.usd((lo + hi) / 2), 'Ay sonu tahmini', esc(alt))
            : karo(`${B.usd(lo)} – ${B.usd(hi)}`, 'Ay sonu tahmini', esc(alt), { sinif: 'aralik' });
        }
      }
    }
    // Kota (H5): kalan % karoları yalnız Kota bölümünde (#kota) durur; burada ikinci kez gösterilmez.
    const bugunYok = !sayiMi(m.bugun) || r2(m.bugun) === 0;
    const sonKayit = sohbetler().map(s => s.son).filter(Boolean).sort().pop();
    const tutarVar = [m.bugun, buAy, m.toplam].some(v => sayiMi(v) && r2(v) > 0);
    let html;
    if (!tutarVar) {
      html = '<p class="bos">Henüz maliyet kaydı yok.</p>';
    } else {
      html = `<div class="karolar">${karolar}</div>` +
        (bugunYok ? `<p class="meta kpi-not">Bugün henüz harcama yok${sonKayit ? ` · son kayıt ${B.tarih(sonKayit)}` : ''}.</p>` : '') +
        (ilkKayit ? `<p class="meta kpi-not">İlk kayıt ${B.gun(ilkKayit)}.</p>` : '');
    }
    yerlestir(kap, html);
  }

  // ------------------------------------------------------------ kapsam şeridi
  function seritCiz() {
    const s = kapsamSohbet(), kap = $('#kapsamSerit');
    kap.classList.toggle('gizli', !s);
    yerlestir(kap, s
      ? `<button type="button" class="cip" aria-pressed="true" data-kapsam-kaldir data-anahtar="kapsam-x" title="Kapsamı kaldır">Kapsam: ${esc(kisalt(s.baslik, 48))} ✕</button>
         <span class="meta">${orkestrali() ? 'Sohbet, iş türü, model ve ajan bölümleri' : 'Sohbet ve model bölümleri'} bu sohbete bakıyor; harcama özeti, zaman grafiği ve tüm projeler çalışma alanının tamamını gösterir.</span>`
      : '');
  }

  // ------------------------------------------------------------ 2. Sohbetler
  const SOHBET_ILK = 10;
  // Dönem süzmesi ve görünüm (grafik | liste) alan başına hatırlanır. Dönemli veri token defterindendir (ozet.sohbet_dokum).
  const SD_ADLARI = { gun: 'Bugün', uc: 'Son 3 gün', hafta: 'Son 7 gün', ay: 'Bu ay', tum: 'Tüm zaman' };
  const PENCERE_DONEM = { bugun: 'gun', son_3_gun: 'uc', son_7_gun: 'hafta', bu_ay: 'ay', tum_zaman: 'tum' };
  const SD_ANAHTAR = a => 'orkestra.maliyet.sohbet.' + a + '.' + O.alan;
  const sDonem = () => PENCERE_DONEM[G.pencere.al()] || 'uc';
  const sGorunum = () => O.depo.al(SD_ANAHTAR('gorunum')) === 'liste' ? 'liste' : 'grafik';
  const dokum = () => (S.ozet && S.ozet.sohbet_dokum && Array.isArray(S.ozet.sohbet_dokum.sohbetler)) ? S.ozet.sohbet_dokum : null;
  // YYYY-MM-DD aritmetiği saat dilimi kaymadan (UTC) yapılır
  const gunKaydir = (g, n) => { const d = new Date(g + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const haftaBasi = g => { const d = new Date(g + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return d.toISOString().slice(0, 10); };
  const gunIcinde = (donem, bugun) => ({
    gun: g => g === bugun,
    uc: g => g >= gunKaydir(bugun, -2) && g <= bugun,
    hafta: g => g >= gunKaydir(bugun, -6) && g <= bugun,
    ay: g => g.slice(0, 7) === bugun.slice(0, 7),
    tum: () => true,
  })[donem];
  // Seçici yanındaki tarih aralığı ipucu (ör. «15–17 Eki»); gün bilinmiyorsa boş
  const pencereAralik = id => {
    const dk = dokum(); if (!dk || !dk.gun) return '';
    const bg = dk.gun, ilk = { bugun: bg, son_3_gun: gunKaydir(bg, -2), son_7_gun: gunKaydir(bg, -6), bu_ay: bg.slice(0, 8) + '01' }[id];
    if (!ilk) return 'ilk kayıttan bugüne';
    return ilk === bg ? B.gun(bg) : B.gun(ilk) + ' – ' + B.gun(bg);
  };
  const SOHBET_RENK_SAYISI = 6;
  const sohbetRenk = (k, i) => k === 'diger' ? 'var(--neutral)' : SERI[i];

  // Zaman kovaları: gün → saatler, hafta ve ay → günler, tümü → günler (45 günü aşarsa haftalar)
  function zamanKovalari(donem, dk, sohbetler) {
    const bugun = dk.gun;
    if (donem === 'gun') {
      const saatler = sohbetler.flatMap(e => Object.keys(e.s || {})).map(Number);
      if (!saatler.length) return [];
      const kovalar = [];
      for (let h = Math.min(...saatler); h <= Math.max(...saatler); h++) {
        const hh = String(h).padStart(2, '0');
        kovalar.push({ anahtar: hh, etiket: hh, baslik: `${hh}:00–${hh}:59`, deger: e => (e.s || {})[hh] });
      }
      return kovalar;
    }
    const ic = gunIcinde(donem, bugun);
    const gunler = sohbetler.flatMap(e => Object.keys(e.g || {})).filter(ic).sort();
    if (!gunler.length) return [];
    const ilk = donem === 'uc' ? gunKaydir(bugun, -2) : donem === 'hafta' ? gunKaydir(bugun, -6) : donem === 'ay' ? bugun.slice(0, 8) + '01' : gunler[0];
    const haftalik = donem === 'tum' && (new Date(bugun) - new Date(ilk)) / 864e5 > 45;
    const kovalar = [], goruldu = new Set();
    for (let g = ilk; g <= bugun; g = gunKaydir(g, 1)) {
      const k = haftalik ? haftaBasi(g) : g;
      if (goruldu.has(k)) continue;
      goruldu.add(k);
      kovalar.push({ anahtar: k, etiket: B.gun(k), baslik: haftalik ? `${B.gun(k)} haftası` : B.gun(k), haftalik });
    }
    kovalar.forEach(kv => {
      kv.deger = e => {
        const t = [0, 0];
        Object.entries(e.g || {}).forEach(([g, v]) => { if (ic(g) && (kv.haftalik ? haftaBasi(g) : g) === kv.anahtar) { t[0] += v[0]; t[1] += v[1]; } });
        return t;
      };
    });
    return kovalar;
  }

  function sohbetDonemli(kap, dk) {
    const donem = sDonem(), gorunum = sGorunum(), ic = gunIcinde(donem, dk.gun);
    const secili = kapsamId();
    if (!secili && O.depo.al(KAPSAM_ANAHTARI()) && sohbetler().length) O.depo.koy(KAPSAM_ANAHTARI(), '');
    const eski = {};
    sohbetler().forEach(x => { eski[x.oturum] = x; });
    const hepsi = dk.sohbetler.map(e => {
      const t = [0, 0];
      Object.entries(e.g || {}).forEach(([g, v]) => { if (ic(g)) { t[0] += v[0]; t[1] += v[1]; } });
      return { e, oturum: e.oturum, baslik: e.baslik, usd: t[0], tok: t[1], son: e.son, eski: eski[e.oturum] };
    });
    const satirlar = hepsi.filter(r => r2(r.usd) > 0 || r.oturum === secili).sort((a, b) => b.usd - a.usd);
    const topUsd = satirlar.reduce((a, r) => a + r.usd, 0), topTok = satirlar.reduce((a, r) => a + r.tok, 0);
    $('#sohbetSayi').textContent = satirlar.length ? `${B.sayi(satirlar.length)} sohbet` : '';
    const dugmeGrup = (ad, anahtar, secenekler, simdiki) => `<div class="cipler" role="group" aria-label="${esc(ad)}">${secenekler.map(([v, et]) =>
      `<button type="button" class="cip" data-${anahtar}="${v}" data-anahtar="${anahtar}:${v}" aria-pressed="${simdiki === v}">${et}</button>`).join('')}</div>`;
    const arac = `<div class="arac">${dugmeGrup('Görünüm', 'sgorunum', [['grafik', 'Grafik'], ['liste', 'Liste']], gorunum)}</div>`;
    const ozet = `<p class="meta sohbet-ozet">${esc(SD_ADLARI[donem])}: <b>${B.usd(topUsd)}</b> · ${B.token(topTok)} token · ${B.sayi(satirlar.length)} sohbet</p>`;
    if (!satirlar.length) { yerlestir(kap, arac + ozet + '<p class="bos">Bu dönemde harcama yok.</p>'); return; }

    const enCok = Math.max(satirlar[0].usd, 0.0001);
    let liste = S.hepsiAcik ? satirlar : satirlar.slice(0, SOHBET_ILK);
    if (secili && !liste.some(r => r.oturum === secili)) liste = liste.concat(satirlar.filter(r => r.oturum === secili));
    const ipucu = r => {
      const x = r.eski;
      return `<b>${esc(r.baslik)}</b>` + sat(SD_ADLARI[donem], B.usd(r.usd)) + sat('Token', B.token(r.tok) + ' · ' + B.sayi(r.tok)) +
        sat('Pay', B.yuzde(topUsd ? r.usd / topUsd : 0)) + sat('Son etkinlik', B.tarih(r.son)) +
        (donem === 'tum' && x && sayiMi(x.usd) && r2(x.usd) !== r2(r.usd) ? sat(x.kaynak === 'motor' ? "Claude'un hesabı" : 'Kayıtlı toplam', B.usd(x.usd)) : '') +
        (donem === 'tum' && x ? Object.entries(x.modeller || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => sat(E.model(k), B.usd(v), modelRenk(k))).join('') : '');
    };

    let govde;
    if (gorunum === 'liste') {
      const satir = r => {
        const ad = r.eski
          ? `<button type="button" class="sohbet-ad" aria-pressed="${r.oturum === secili}" data-kapsam="${esc(r.oturum)}" data-anahtar="s:${esc(r.oturum)}">${esc(r.baslik)}</button>`
          : `<span class="sohbet-ad">${esc(r.baslik)}</span>`;
        return `<tr data-ipucu="${esc(ipucu(r))}"${r.oturum === secili ? ' class="secili"' : ''}><td class="ad">${ad}</td><td class="sayi">${B.usd(r.usd)}</td>
          <td class="sayi">${B.token(r.tok)}</td><td class="sayi">${B.yuzde(topUsd ? r.usd / topUsd : 0, 1)}</td><td class="sayi">${B.tarih(r.son)}</td></tr>`;
      };
      govde = `<div class="tablo-kap"><table class="tablo"><thead><tr><th>Sohbet</th><th class="sayi">Tutar</th><th class="sayi">Token</th><th class="sayi">Pay</th><th class="sayi">Son etkinlik</th></tr></thead>
        <tbody>${liste.map(satir).join('')}</tbody></table></div>`;
    } else {
      const ust = satirlar.slice(0, SOHBET_RENK_SAYISI).map(r => r.oturum);
      const anahtarlar = satirlar.length > SOHBET_RENK_SAYISI ? ust.concat(['diger']) : ust;
      const adi = k => k === 'diger' ? 'Diğer sohbetler' : kisalt((satirlar.find(r => r.oturum === k) || {}).baslik, 40);
      const renk = k => sohbetRenk(k, ust.indexOf(k));
      const kovalar = zamanKovalari(donem, dk, satirlar.map(r => r.e));
      const grafikSat = kovalar.map(kv => {
        const parca = {};
        satirlar.forEach(r => {
          const v = kv.deger(r.e);
          if (v && v[0] > 0) { const k = ust.includes(r.oturum) ? r.oturum : 'diger'; parca[k] = (parca[k] || 0) + v[0]; }
        });
        return { etiket: kv.etiket, baslik: kv.baslik, parca };
      });
      const cubuk = r => `<button type="button" class="cubuk sohbet-c" aria-pressed="${r.oturum === secili}"${r.eski ? ` data-kapsam="${esc(r.oturum)}"` : ' disabled'} data-anahtar="s:${esc(r.oturum)}" data-ipucu="${esc(ipucu(r))}">
        <span class="etiket"><span class="ad">${esc(r.baslik)}</span><span class="zaman">${B.tarih(r.son)}</span></span>
        <span class="yol"><span class="dolgu" style="width:${Math.max(0.4, 100 * r.usd / enCok)}%"></span></span>
        <span class="deger">${B.usd(r.usd)}</span><span class="kaynak">${B.token(r.tok)}</span></button>`;
      const grafikAdi = donem === 'gun' ? 'Saat saat' : (kovalar[0] && kovalar[0].haftalik) ? 'Hafta hafta' : 'Gün gün';
      govde = `<h3 class="alt-baslik">${grafikAdi} harcama</h3>` +
        `<div class="grafik">${yiginSutun(genislikOlc(kap, $('#sohbetler')), grafikSat, anahtarlar, renk, adi)}</div>` +
        lejant(anahtarlar.map(k => [adi(k), renk(k)])) +
        `<h3 class="alt-baslik">Sohbetler</h3><div class="cubuklar">${liste.map(cubuk).join('')}</div>`;
    }
    if (satirlar.length > SOHBET_ILK) {
      govde += `<div class="daha"><button type="button" data-anahtar="daha" data-tumunu aria-expanded="${S.hepsiAcik}">${S.hepsiAcik ? 'İlk ' + SOHBET_ILK + ' sohbeti göster' : 'Bütün sohbetler · ' + satirlar.length}</button></div>`;
    }
    yerlestir(kap, arac + ozet + govde);
  }

  function sohbetCiz() {
    const kap = $('#sohbetIcerik');
    if (!S.ozet) { $('#sohbetSayi').textContent = ''; yerlestir(kap, yuklemeSatiri(KO, 'Sohbet verisi')); return; }
    if (S.ozet.acik === false || S.ozet.hata) {
      $('#sohbetSayi').textContent = '';
      yerlestir(kap, `<p class="bos">${S.ozet.hata ? 'Veri üretilemedi: ' + metin(O.hataMetni(S.ozet.hata)) : 'Bu çalışma alanı kapalı.'}</p>`);
      return;
    }
    const dk = dokum();
    if (dk) { sohbetDonemli(kap, dk); return; }
    sohbetKayitli(kap);   // orkestrasız alan: token defteri yok, dönem süzmesi yapılamaz
  }
  function sohbetKayitli(kap) {
    const secili = kapsamId();
    if (!secili && O.depo.al(KAPSAM_ANAHTARI()) && sohbetler().length) O.depo.koy(KAPSAM_ANAHTARI(), '');   // artık listede olmayan sohbet
    const tum = sohbetler().filter(s => sayiMi(s.usd) && (r2(s.usd) > 0 || s.oturum === secili)).sort((a, b) => b.usd - a.usd);
    $('#sohbetSayi').textContent = tum.length ? `${B.sayi(tum.length)} sohbet` : '';
    if (!tum.length) { yerlestir(kap, '<p class="bos">Maliyeti olan sohbet yok.</p>'); return; }
    let liste = S.hepsiAcik ? tum : tum.slice(0, SOHBET_ILK);
    if (secili && !liste.some(s => s.oturum === secili)) liste = liste.concat(tum.filter(s => s.oturum === secili));
    const enCok = Math.max(tum[0].usd, 0.0001);
    const satir = s => {
      const ip = `<b>${esc(s.baslik)}</b>` + sat('Kayıtlı toplam', B.usd(s.usd)) + sat('Kaynak', esc(E.kaynak(s.kaynak) || '–')) +
        sat('Son etkinlik', B.tarih(s.son)) +
        Object.entries(s.modeller || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => sat(E.model(k), B.usd(v), modelRenk(k))).join('');
      return `<button type="button" class="cubuk sohbet-c" aria-pressed="${s.oturum === secili}" data-kapsam="${esc(s.oturum)}" data-anahtar="s:${esc(s.oturum)}" data-ipucu="${esc(ip)}">
        <span class="etiket"><span class="ad">${esc(s.baslik)}</span><span class="zaman">${B.tarih(s.son)}</span></span>
        <span class="yol"><span class="dolgu" style="width:${Math.max(0.4, 100 * s.usd / enCok)}%"></span></span>
        <span class="deger">${B.usd(s.usd)}</span><span class="kaynak">${esc(E.kaynak(s.kaynak, true))}</span></button>`;
    };
    let html = `<div class="cubuklar">${liste.map(satir).join('')}</div>`;
    if (tum.length > SOHBET_ILK) {
      html += `<div class="daha"><button type="button" data-anahtar="daha" data-tumunu aria-expanded="${S.hepsiAcik}">${S.hepsiAcik ? 'İlk ' + SOHBET_ILK + ' sohbeti göster' : 'Bütün sohbetler · ' + tum.length}</button></div>`;
    }
    yerlestir(kap, html);
  }

  // ------------------------------------------------------------ 3. İş türü · Model payı
  function paylar(kap, girdi, etiketle, renkle, bos) {
    // aynı etikete düşen anahtarlar toplanır (ör. bilinmiyor ve '-' → Etiketsiz)
    const toplam = {};
    Object.entries(girdi || {}).forEach(([k, v]) => {
      if (!sayiMi(v) || r2(v) === 0) return;
      const ad = etiketle(k);
      toplam[ad] = toplam[ad] || { v: 0, k };
      toplam[ad].v += v;
    });
    const satirlar = Object.entries(toplam).sort((a, b) => b[1].v - a[1].v);
    if (!satirlar.length) { yerlestir(kap, `<p class="bos">${bos}</p>`); return; }
    const ogeler = satirlar.map(([ad, d], i) => ({ ad, deger: d.v, renk: renkle(d.k, i) }));
    yerlestir(kap, G.pay(ogeler, { bicim: B.usd, toplamEtiket: 'Harcama payı' }));
  }
  // Seçili pencerenin kırılımı: sunucu maliyet.pencere'de verir; eski sunucuda yalnız bugünkü kırılım vardır
  const pencereVeri = () => { const p = mal().pencere && mal().pencere[G.pencere.al()]; return p || mal(); };
  const donemAdi = () => {
    const s = kapsamSohbet();
    if (s) return kisalt(s.baslik, 36) + ' · kayıtlı toplam';
    if (!orkestrali()) return 'kayıtlı toplam';
    return mal().pencere ? G.pencere.ad(G.pencere.al()) : 'bugün';
  };
  const DOKUM_YOK = 'Bu sohbetin dökümü yok: Claude\'un kendi hesabı yalnız toplamı verir.';
  function ikiliCiz() {
    const ork = orkestrali(), yukluyor = !S.ozet, orkYok = !!S.ozet && !ork;
    $('#orkYok').classList.toggle('gizli', !orkYok);
    $('#surecB').classList.toggle('gizli', orkYok);
    $('#ajanB').classList.toggle('gizli', orkYok);
    $('#ikili').classList.toggle('tek', orkYok);
    if (yukluyor) {
      $('#kirilimNot').textContent = '';
      $('#surecDonem').textContent = ''; $('#modelDonem').textContent = '';
      yerlestir($('#surecIcerik'), yuklemeSatiri(KO, 'Harcama verisi'));
      yerlestir($('#modelIcerik'), yuklemeSatiri(KO, 'Harcama verisi'));
      return;
    }
    if (orkYok) {
      yerlestir($('#orkYokIcerik'), `<p class="bos">Bu çalışma alanında orkestra kurulu değil; yalnız sohbet maliyetleri ve model payı anlamlı.</p>
        <details class="nasil"><summary>Nasıl kurulur?</summary>
        <p>Claude-Orchestration klasöründe: <code>python araclar/projeye_kur.py "&lt;proje klasörü&gt;"</code></p>
        <p>Sonra o projede Claude içinde <code>/orkestra:baslat</code>.</p></details>`);
    }
    const kir = kapsamKirilim(), m = pencereVeri(), d = donemAdi();
    // kırılım toplamı (kayıttan) sohbet toplamından (ör. Claude'un hesabı) farklıysa tek satır açıklama
    const ks = kapsamSohbet();
    const fark = kir && kir !== 'yok' && ks && sayiMi(kir.usd) && sayiMi(ks.usd) && Math.abs(kir.usd - ks.usd) >= 0.01;
    $('#kirilimNot').textContent = fark
      ? `Kırılım ${ork ? 'orkestra defterinden' : 'kayıtlı kullanımdan'} (${B.usd(kir.usd)}); sohbet toplamı ${ks.kaynak === 'motor' ? "Claude'un hesabı" : E.kaynak(ks.kaynak, true)}: ${B.usd(ks.usd)}.` : '';
    $('#surecDonem').textContent = d; $('#modelDonem').textContent = d;
    const surec = kir === 'yok' ? null : (kir ? kir.surec : m.surec);
    const model = kir === 'yok' ? null : (kir ? kir.model : m.model);
    if (ork) paylar($('#surecIcerik'), surec, E.surec, (k, i) => SERI[i % SERI.length], kir === 'yok' ? DOKUM_YOK : 'Kayıt yok.');
    paylar($('#modelIcerik'), model, E.model, k => modelRenk(k), kir === 'yok' ? DOKUM_YOK : 'Kayıt yok.');
  }

  // ------------------------------------------------------------ 4. Ajan × iş türü
  function ajanCiz() {
    const kap = $('#ajanIcerik');
    if (!S.ozet) { $('#ajanDonem').textContent = ''; yerlestir(kap, yuklemeSatiri(KO, 'Harcama verisi')); return; }
    if (!orkestrali()) return;
    $('#ajanDonem').textContent = donemAdi();
    const kir = kapsamKirilim(), m = pencereVeri();
    if (kir === 'yok') { yerlestir(kap, `<p class="bos">${DOKUM_YOK}</p>`); return; }
    const satirlar = (kir ? kir.ajan_surec : m.ajan_surec) || [];
    if (!satirlar.length) { yerlestir(kap, '<p class="bos">Kayıt yok.</p>'); return; }
    const tokIp = (ad, v) => v == null ? '' : ` tabindex="0" data-ipucu="${esc('<b>' + ad + '</b>' + B.sayi(v) + ' token')}"`;
    // Isı haritası: ajan × iş türü maliyeti (koyu = pahalı); altta koşu ve token ayrıntısı aynı veriyle tablo
    const ajanlar = [...new Set(satirlar.map(r => r.ajan))].map(k => ({ k, ad: E.ajan(k) }));
    const surecler = [...new Set(satirlar.map(r => r.surec))].map(k => ({ k, ad: E.surec(k) }));
    const isi = G.isi({ satirlar: ajanlar, sutunlar: surecler, satirBasi: 'Ajan', bicim: B.usd, renk: 'var(--s2)',
      deger: (a, c) => satirlar.filter(r => r.ajan === a.k && r.surec === c.k).reduce((t, r) => t + (Number(r.usd) || 0), 0) });
    yerlestir(kap, isi + `<details class="nasil" open><summary>Koşu ve token ayrıntısı</summary><div class="tablo-kap"><table class="tablo"><thead><tr><th>Ajan</th><th>İş türü</th><th class="sayi">Koşu</th>
      <th class="sayi">Giriş token</th><th class="sayi">Çıkış token</th><th class="sayi">Maliyet</th></tr></thead><tbody>` +
      satirlar.map(r => `<tr><td>${esc(E.ajan(r.ajan))}</td><td>${esc(E.surec(r.surec))}</td><td class="sayi">${B.sayi(r.kosu)}</td>
        <td class="sayi"${tokIp('Giriş', r.giris)}>${B.token(r.giris)}</td><td class="sayi"${tokIp('Çıkış', r.cikis)}>${B.token(r.cikis)}</td>
        <td class="sayi">${B.usd(r.usd)}</td></tr>`).join('') + '</tbody></table></div></details>');
  }

  // ------------------------------------------------------------ grafik yardımcıları (düz SVG)
  function eksenAdim(maks) {
    if (maks <= 0) return [1, 1];
    const ham = maks / 4, us = Math.pow(10, Math.floor(Math.log10(ham)));
    const adim = [1, 2, 2.5, 5, 10].map(c => c * us).find(a => a >= ham);
    return [adim, Math.ceil(maks / adim) * adim];
  }
  // satirlar [{etiket, baslik, parca:{anahtar:değer}}]; anahtarlar sabit sırada; ad(k) lejant/ipucu adı, renk(k) dolgu
  function yiginSutun(genislik, satirlar, anahtarlar, renk, ad, { pay = false, yukseklik = 220 } = {}) {
    if (!satirlar.length) return '<p class="bos">Veri yok.</p>';
    const G = Math.max(genislik || 600, 280), Y = yukseklik, sol = pay ? 44 : 64, alt = 22, ust = 8;
    const toplam = satirlar.map(s => anahtarlar.reduce((a, k) => a + (s.parca[k] || 0), 0));
    const [adim, maks] = pay ? [0.25, 1] : eksenAdim(Math.max(...toplam, 0));
    const g = (G - sol) / satirlar.length, bw = Math.max(Math.min(g - 2, 36), 2);
    const yv = v => ust + (Y - ust - alt) * (1 - v / maks);
    let s = `<svg viewBox="0 0 ${G} ${Y}" height="${Y}" role="img" aria-label="Harcama grafiği">`;
    for (let v = 0; v <= maks + 1e-9; v += adim) {
      s += `<line x1="${sol}" x2="${G}" y1="${yv(v)}" y2="${yv(v)}" stroke="var(--grid)"/>`;
      s += `<text x="${sol - 6}" y="${yv(v) + 4}" text-anchor="end">${pay ? B.yuzde(v) : B.usd(v)}</text>`;
    }
    const etiketAdim = Math.max(1, Math.ceil(satirlar.length / Math.max(1, Math.floor((G - sol) / 56))));
    satirlar.forEach((r, i) => {
      const x = sol + i * g + (g - bw) / 2, tp = toplam[i] || 0;
      let taban = 0;
      const dolu = anahtarlar.filter(k => r.parca[k] > 0);
      dolu.forEach((k, j) => {
        const v = pay ? (tp ? r.parca[k] / tp : 0) : r.parca[k];
        const y1 = yv(taban + v), y0 = yv(taban);
        const h = Math.max(y0 - y1 - (j < dolu.length - 1 ? 2 : 0), 0.5);   // dilimler arası 2px boşluk
        s += `<rect x="${x}" y="${y0 - h}" width="${bw}" height="${h}" rx="${j === dolu.length - 1 ? 2 : 0}" fill="${renk(k)}"/>`;
        taban += v;
      });
      const ip = `<b>${esc(r.baslik || r.etiket)}</b>` + sat('Toplam', B.usd(tp)) + (r.token != null ? sat('Token', B.token(r.token)) : '') +
        (r.kalem ? ['giris', 'giriş', 'cikis', 'çıkış', 'onbellek_okuma', 'önbellek okuma', 'onbellek_yazma', 'önbellek yazma']
          .reduce((a, v, i, d) => i % 2 ? a : a + sat(d[i + 1], B.usd(r.kalem.usd[v]) + ' · ' + B.token(r.kalem.token[v])), '') : '') +
        dolu.map(k => sat(ad(k), B.usd(r.parca[k]) + (tp ? ' · ' + B.yuzde(r.parca[k] / tp) : ''), renk(k))).join('');
      s += `<rect x="${sol + i * g}" y="${ust}" width="${g}" height="${Y - ust - alt}" fill="transparent" data-ipucu="${esc(ip)}"/>`;
      if (i % etiketAdim === 0) s += `<text x="${x + bw / 2}" y="${Y - 6}" text-anchor="middle">${esc(r.etiket)}</text>`;
    });
    return s + '</svg>';
  }
  const lejant = ogeler => `<div class="lejant">${ogeler.map(([ad, r]) => `<span><i style="background:${r}"></i>${esc(ad)}</span>`).join('')}</div>`;
  const AYLAR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
  function donemEtiket(donem, tur) {
    if (tur === 'gunluk') return { etiket: B.gun(donem), baslik: B.gun(donem) };
    const h = /^(\d{4})-H(\d+)$/.exec(donem);
    if (h) return { etiket: 'H' + h[2], baslik: `${h[1]} · ${h[2]}. hafta` };
    const a = /^(\d{4})-(\d{2})$/.exec(donem);
    if (a) return { etiket: AYLAR[Number(a[2]) - 1] + ' ' + a[1].slice(2), baslik: AYLAR[Number(a[2]) - 1] + ' ' + a[1] };
    return { etiket: donem, baslik: donem };
  }
  // başta sıfır harcamalı boş günleri at (eksen ilk kayıttan başlar)
  const bastanKirp = (liste, deger) => { let i = 0; while (i < liste.length - 1 && !(deger(liste[i]) > 0)) i++; return liste.slice(i); };
  const SINIR = { gunluk: 30, haftalik: 12, aylik: 24 };
  const genislikOlc = (kap, bolum) => kap.clientWidth || (bolum ? Math.max(bolum.clientWidth - 34, 0) : 0) || 600;

  // ------------------------------------------------------------ 5. Harcama
  function zamanCiz() {
    const kap = $('#zamanIcerik');
    if (S.ozet && !orkestrali()) { yerlestir(kap, '<p class="bos">Harcama yalnız orkestralı çalışma alanlarında tutuluyor.</p>'); return; }
    if (!S.an) { yerlestir(kap, yuklemeSatiri(KA, 'Harcama geçmişi')); return; }
    const t = S.an.trend;
    if (!t || !Array.isArray(t[S.donem])) { yerlestir(kap, '<p class="bos">Harcama geçmişi yok.</p>'); return; }
    const pen = G.pencere.al(), tumu = pen === 'tum_zaman';
    const donem = tumu ? S.donem : 'gunluk';
    let liste = t[donem];
    if (donem === 'gunluk') liste = bastanKirp(liste, r => r.usd);
    if (tumu) liste = liste.slice(-SINIR[donem]);
    else {
      const bugun = liste.length ? liste[liste.length - 1].donem : '';
      const ic = gunIcinde(PENCERE_DONEM[pen], bugun);
      liste = liste.filter(r => ic(r.donem));
    }
    const modeller = [...new Set(liste.flatMap(r => Object.keys(r.model || {})))]
      .sort((x, y) => (MODEL_SIRA.indexOf(x) + 1 || 99) - (MODEL_SIRA.indexOf(y) + 1 || 99));
    const satirlar = liste.map(r => Object.assign(donemEtiket(r.donem, donem), { parca: r.model || {}, token: r.token, kalem: r.kalem }));
    const cipGrup = (ad, anahtar, secenekler) => `<div class="cipler" role="group" aria-label="${esc(ad)}">${secenekler.map(([v, et]) =>
      `<button type="button" class="cip" data-${anahtar}="${v}" data-anahtar="${anahtar}:${v}" aria-pressed="${S[anahtar] === v}">${et}</button>`).join('')}</div>`;
    const arac = `<div class="arac">${tumu ? cipGrup('Birim', 'donem', [['gunluk', 'Günlük'], ['haftalik', 'Haftalık'], ['aylik', 'Aylık']]) : ''}
      ${cipGrup('Ölçek', 'olcek', [['usd', 'Tutar'], ['pay', 'Model payı']])}</div>`;
    const not = kapsamId() ? '<p class="meta kpi-not">Günlük döküm sohbet bazında tutulmuyor; grafik seçili sohbeti değil çalışma alanının tamamını gösterir.</p>' : '';
    yerlestir(kap, arac + `<div class="grafik">${yiginSutun(genislikOlc(kap, $('#zaman')), satirlar, modeller, modelRenk, E.model, { pay: S.olcek === 'pay' })}</div>` +
      lejant(modeller.map(k => [E.model(k), modelRenk(k)])) + not);
  }

  // ------------------------------------------------------------ 6. Kota
  function cizgi(genislik, seriler, esik) {
    const tum = seriler.flatMap(s => s.noktalar);
    if (tum.length < 2) return '<p class="bos">Eğri için en az iki ölçüm gerekir.</p>';
    const G = Math.max(genislik || 600, 280), Y = 180, sol = 44, alt = 22, ust = 8, sag = 8;
    const t0 = Math.min(...tum.map(p => +p.t)), t1 = Math.max(...tum.map(p => +p.t));
    const xv = t => sol + (G - sol - sag) * ((+t - t0) / Math.max(t1 - t0, 1));
    const yv = v => ust + (Y - ust - alt) * (1 - v / 100);
    let s = `<svg viewBox="0 0 ${G} ${Y}" height="${Y}" role="img" aria-label="Kota kullanım eğrisi">`;
    for (let v = 0; v <= 100; v += 25) s += `<line x1="${sol}" x2="${G - sag}" y1="${yv(v)}" y2="${yv(v)}" stroke="var(--grid)"/><text x="${sol - 6}" y="${yv(v) + 4}" text-anchor="end">${B.yuzde(v / 100)}</text>`;
    if (esik) s += `<line x1="${sol}" x2="${G - sag}" y1="${yv(esik)}" y2="${yv(esik)}" stroke="var(--warning)" stroke-dasharray="4 4"/>`;
    for (let i = 0; i <= 2; i++) {
      const t = t0 + (t1 - t0) * i / 2;
      s += `<text x="${xv(t)}" y="${Y - 6}" text-anchor="${i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}">${B.tarih(new Date(t))}</text>`;
    }
    seriler.forEach(sr => {
      if (!sr.noktalar.length) return;
      s += `<path d="${sr.noktalar.map((p, i) => (i ? 'L' : 'M') + xv(p.t) + ',' + yv(p.y)).join(' ')}" fill="none" stroke="${sr.renk}" stroke-width="2" stroke-linejoin="round"/>`;
      const son = sr.noktalar[sr.noktalar.length - 1];
      const ip = `<b>${esc(sr.ad)}</b>` + sat('Son ölçüm', B.tarih(son.t)) + sat('Kullanılan', B.yuzde(son.y / 100));
      s += `<circle cx="${xv(son.t)}" cy="${yv(son.y)}" r="5" fill="${sr.renk}" stroke="var(--surface-1)" stroke-width="2" data-ipucu="${esc(ip)}"/>`;
    });
    return s + '</svg>';
  }
  function kotaCiz() {
    const kap = $('#kotaIcerik');
    const orkYok = !!S.ozet && !orkestrali();
    const kota = kotaVerisi();
    if (!kota) { yerlestir(kap, yuklemeSatiri(orkYok ? KT : KA, 'Kota verisi')); return; }
    const olculen = kota.kaynak ? KOTA_PENCERE.filter(([a]) => kota[a]) : [];
    if (!olculen.length) {
      $('#kotaAciklama').textContent = 'Ölçüm yok: masaüstü uygulaması kota bilgisini vermiyor.';
      yerlestir(kap, `<details class="nasil"><summary>Ölçüm nasıl gelir?</summary>
        <p>Kota değerini Claude yalnız terminaldeki oturumun durum satırına verir. Bir terminalde <code>claude</code> ile bir mesaj gönderince ölçüm burada görünür.</p></details>`);
      return;
    }
    $('#kotaAciklama').textContent = '5 saatlik ve haftalık kullanım sınırı; Claude\'un durum satırından kaydedilir, hesap geneli.';
    const karolar = olculen.map(([a, ad]) => {
      const p = kota[a], renk = SEVIYE_RENK[p.seviye] || 'var(--neutral)';
      const ip = `<b>${esc(ad)}</b>` + sat('Kullanılan', B.yuzde(p.yuzde / 100)) + sat('Son ölçüm', B.tarih(p.olcum)) + (p.saat_basi_hiz != null ? sat('Hız', B.yuzde(p.saat_basi_hiz / 100) + '/sa') : '');
      let alt = p.eski ? (p.not || 'eski ölçüm') : (p.sifirlanma ? `sıfırlanma ${B.tarih(p.sifirlanma)}` : '');
      if (p.tahmin && p.tahmin.sifirlanmadan_once) alt += ` · bu hızla sıfırlanmadan önce dolar (${B.tarih(p.tahmin.dolma)})`;
      return `<div class="karo"><b>%${B.sayi(p.kalan)} kaldı</b><span>${esc(ad)}</span>
        <div class="olcer" role="img" tabindex="0" aria-label="${esc(ad + ': ' + B.yuzde(p.yuzde / 100) + ' kullanıldı')}" data-ipucu="${esc(ip)}"><div style="width:${p.yuzde}%;background:${renk}"></div></div>
        <small>${esc(alt)}</small><small>son ölçüm ${B.tarih(p.olcum)}</small></div>`;
    }).join('');
    const seri = Array.isArray(kota.seri) ? kota.seri : [];
    const seriler = [['bes_saat', '5 saat', 'var(--s1)'], ['haftalik', 'Hafta', 'var(--s2)']].map(([a, ad, r]) => ({
      ad, renk: r, noktalar: seri.filter(n => n[a] != null).map(n => ({ t: new Date(n.zaman), y: n[a] })) }));
    yerlestir(kap, `<div class="karolar">${karolar}</div><div class="grafik ust-bosluk">${cizgi(genislikOlc(kap, $('#kota')), seriler, 80)}</div>` +
      lejant(seriler.map(s => [s.ad, s.renk]).concat([['%80 uyarı eşiği', 'var(--warning)']])));
  }

  // ------------------------------------------------------------ 7. Tüm projeler
  function tumCiz() {
    const t = S.tum, bolum = $('#tum');
    if (!t) {
      const hata = !!(KT && KT.durum === 'hata');
      bolum.classList.toggle('gizli', !hata);
      if (hata) yerlestir($('#tumIcerik'), yuklemeSatiri(KT, 'Tüm projeler verisi'));
      return;
    }
    const alanlar = Array.isArray(t.alanlar) ? t.alanlar : [];
    const az = alanlar.length < (O.tumAlan() ? 1 : 2);   // 'Tüm çalışma alanları' seçiliyken tek alan da gösterilir
    bolum.classList.toggle('gizli', az);
    if (az) return;
    const top = t.toplam || {};
    const karolar = tutarKarolari([['Bugün', top.bugun, ''], ['Son 7 gün', top.hafta, ''], ['Bu ay', top.ay, ''], ['Kayıtlı toplam', top.toplam, `${B.sayi(alanlar.length)} çalışma alanı`]]);
    const adlar = alanlar.map(a => a.ad);
    const renk = ad => SERI[Math.min(adlar.indexOf(ad), 7)];
    const ust = adlar.slice(0, 7);
    const gun = bastanKirp(Array.isArray(t.gunluk) ? t.gunluk : [], g => Object.values(g.alan || {}).reduce((a, b) => a + b, 0)).slice(-SINIR.gunluk);
    const satirlar = gun.map(g => {
      const parca = {}; let diger = 0;
      Object.entries(g.alan || {}).forEach(([a, v]) => { if (ust.includes(a)) parca[a] = v; else diger += v; });
      if (diger) parca['Diğer'] = diger;
      return { etiket: B.gun(g.donem), baslik: B.gun(g.donem), parca };
    });
    const anahtarlar = adlar.length > 7 ? ust.concat(['Diğer']) : ust;
    const rk = a => a === 'Diğer' ? 'var(--neutral)' : renk(a);
    const tablo = `<div class="tablo-kap"><table class="tablo tum-tablo"><thead><tr><th>Çalışma alanı</th><th>Orkestra</th><th class="sayi">Bugün</th>
      <th class="sayi">7 gün</th><th class="sayi">Bu ay</th><th class="sayi">Toplam</th><th class="sayi">Kart</th><th>Model dağılımı</th></tr></thead><tbody>` +
      alanlar.map(a => {
        const ip = `<b>${esc(a.ad)}</b><div class="meta">${esc(a.yol || '')}</div>`;
        return `<tr><td><span class="tab-ad" tabindex="0" data-ipucu="${esc(ip)}" data-anahtar="a:${esc(a.id)}">${esc(a.ad)}</span>${a.id === O.alan ? ' <span class="meta">· seçili</span>' : ''}${a.hata ? `<div class="meta" data-ipucu="${esc('<b>Ham hata</b><div>' + esc(O.yolGizle(a.hata)) + '</div>')}" tabindex="0">hata: ${metin(kisalt(O.hataMetni(a.hata), 80))}</div>` : ''}</td>
          <td>${a.orkestra ? '<span aria-label="kurulu" title="Orkestra kurulu">✓</span>' : '<span aria-label="kurulu değil" title="Orkestra kurulu değil: yalnız sohbet maliyeti">–</span>'}</td>
          <td class="sayi">${B.usd(a.bugun)}</td><td class="sayi">${B.usd(a.hafta)}</td><td class="sayi">${B.usd(a.ay)}</td><td class="sayi"><b>${B.usd(a.toplam)}</b></td>
          <td class="sayi">${a.orkestra ? `${B.sayi(a.teslim)}/${B.sayi(a.kart)}` : '–'}</td>
          <td class="model-dag">${Object.entries(a.model || {}).sort((x, y) => y[1] - x[1]).map(([m, v]) => `${esc(E.model(m))} ${B.usd(v)}`).join(' · ')}</td></tr>`;
      }).join('') + '</tbody></table></div>';
    const kap = $('#tumIcerik');
    yerlestir(kap, (karolar ? `<div class="karolar">${karolar}</div>` : '') +
      `<div class="grafik ust-bosluk">${yiginSutun(genislikOlc(kap, bolum), satirlar, anahtarlar, rk, a => a, { yukseklik: 200 })}</div>` +
      lejant(anahtarlar.map(a => [a, rk(a)])) + `<div class="ust-bosluk">${tablo}</div>` +
      `<details class="nasil ust-bosluk"><summary>Nasıl hesaplanır?</summary><p>${metin(t.not || '')}</p></details>`);
  }

  const hepsi = () => ciz(uyariCiz, seritCiz, kpiCiz, sohbetCiz, ikiliCiz, ajanCiz, zamanCiz, kotaCiz, tumCiz, bayatBolumu);
  // Sohbet kapsamı değişince: şerit, sohbet çubukları, iş türü, model ve ajan yeniden çizilir (özet, zaman ve tüm projeler kapsam dışı)
  const kapsamBolumleri = () => ciz(seritCiz, sohbetCiz, ikiliCiz, ajanCiz, zamanCiz);

  // ------------------------------------------------------------ etkileşim
  function kapsamSec(id) {
    const simdiki = O.depo.al(KAPSAM_ANAHTARI());
    O.depo.koy(KAPSAM_ANAHTARI(), simdiki === id ? '' : id);   // aynı sohbete yeniden tıklamak kapsamı kaldırır
    kapsamBolumleri();
  }
  const ana = $('main');
  ana.addEventListener('click', e => {
    const k = e.target.closest('[data-kapsam]');
    if (k) return kapsamSec(k.dataset.kapsam);
    if (e.target.closest('[data-kapsam-kaldir]')) { O.depo.koy(KAPSAM_ANAHTARI(), ''); kapsamBolumleri(); return; }
    if (e.target.closest('[data-tumunu]')) { S.hepsiAcik = !S.hepsiAcik; return sohbetCiz(); }
    const sg = e.target.closest('[data-sgorunum]');
    if (sg) { O.depo.koy(SD_ANAHTAR('gorunum'), sg.dataset.sgorunum); return sohbetCiz(); }
    const d = e.target.closest('[data-donem]');
    if (d) { S.donem = d.dataset.donem; return zamanCiz(); }
    const o = e.target.closest('[data-olcek]');
    if (o) { S.olcek = o.dataset.olcek; return zamanCiz(); }
  });
  window.addEventListener('orkestra:pencere', () => { S.hepsiAcik = false; ciz(sohbetCiz, ikiliCiz, ajanCiz, zamanCiz); });
  // yapışkan kapsam şeridi kabuğun altında durur: kabuk yüksekliği (dar ekranda sekme satırı) ölçülür
  const kabukYuksekligi = () => { const k = $('#kabuk'); if (k) document.documentElement.style.setProperty('--kabuk-h', (O.rayModu() ? 0 : k.offsetHeight) + 'px'); };
  if (window.ResizeObserver) new ResizeObserver(kabukYuksekligi).observe($('#kabuk'));
  let boyutZamani;
  addEventListener('resize', () => { clearTimeout(boyutZamani); boyutZamani = setTimeout(() => ciz(sohbetCiz, zamanCiz, kotaCiz, tumCiz), 150); });

  // ------------------------------------------------------------ veri
  O.kabuk({ sayfa: 'maliyet' }).then(kabukYuksekligi);
  G.pencere('#gPencere', { aralik: pencereAralik });
  // Pencere yalnız harcama görünümlerinde anlamlı (Özet, Harcama dağılımı)
  const pencereGoster = id => { $('#gPencere').hidden = !['ozet', 'dagilim'].includes(id); };
  window.addEventListener('orkestra:gorunum', e => pencereGoster(e.detail.id));
  G.sekmeler('#gNav', [['ozet', 'Özet'], ['dagilim', 'Harcama dağılımı'], ['verim', 'Verim ve kalite'], ['akis', 'Akış ve sağlık']]);
  // Yeni veri → ilgili bölümler çizilir. Durum değişimi (hata/toparlanma) → yalnız şerit ve başlık işaretleri;
  // son iyi veri yokken ilgili bölümler tam hata satırına geçer.
  KO = O.veri(() => '/ozet.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Sohbet ve token verisi', aralik: 5000,
    gecerli: v => !v.alan || !v.alan.id || v.alan.id === O.alan,
    cizici: v => { S.ozet = v; hepsi(); G.pencere.yenile(); },
    durum: () => ciz(uyariCiz, bayatBolumu, ...(S.ozet ? [] : [kpiCiz, sohbetCiz, ikiliCiz, ajanCiz])),
  });
  // analitik.json orkestrasız alanda varsayılan alanın verisini döndürür: yalnız bu alanınsa kullanılır
  KA = O.veri(() => '/analitik.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Zaman ve kota verisi', aralik: 15000,
    cizici: v => { S.an = (v && v.alan && v.alan.id === O.alan && !v.hata) ? v : null; hepsi(); },
    durum: () => ciz(uyariCiz, bayatBolumu, ...(S.an ? [] : [kpiCiz, zamanCiz, kotaCiz])),
  });
  KT = O.veri('/analitik-tum.json', {
    ad: 'Tüm projeler verisi', aralik: 30000, alanaBagli: false,
    gecerli: v => Array.isArray(v.alanlar),
    cizici: v => { S.tum = v; hepsi(); },
    durum: () => ciz(uyariCiz, bayatBolumu, ...(S.tum ? [] : [kotaCiz, tumCiz])),
  });
  // alan değişince eski alanın verisi artık "son iyi veri" değildir: sıfırla ve bölümleri hemen "Yükleniyor…" ile yeniden çiz
  window.addEventListener('orkestra:alan', () => {
    S.ozet = null; S.an = null; S.hepsiAcik = false;
    hepsi();
  });
})();
