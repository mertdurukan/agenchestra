import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { HamOzet, KartOzeti, UiOzet } from '../types'

// Veri kaynağı: çekirdek plugin'in hook'ları ve CLI'ı her durum değişikliğinde `.claude/orkestra/ozet.json` yazar.
// Mod yalnız bu dosyayı okur (süreç başlatmaz); okuyamazsa nedenini panelde gösterir.
const OZET = '.claude/orkestra/ozet.json'
const PANE = 'orkestra'
const veri = atom({ plugin: 'orkestra-ui', key: 'veri' } as const, null)

const ACIK = ['isleniyor', 'denetimde', 'reddedildi', 'onaylandi', 'beklemede', 'planlandi']
const ESKI_DK = 10

// tr-TR para biçimi: |v| < 1000 iki ondalık ($5,73); ≥ 1000 sıfır ondalık ($1.668); negatifte −$.
export function usd(n: number | undefined): string {
  const v = n ?? 0
  const binlik = (t: string) => t.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  const govde = Math.abs(v) < 1000
    ? (([t, o]) => `${binlik(t)},${o}`)(Math.abs(v).toFixed(2).split('.'))
    : binlik(String(Math.round(Math.abs(v))))
  return `${v < 0 ? '−' : ''}$${govde}`
}

function kes(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, Math.max(0, n - 1)) + '…'
}

// Markdown işaretlerini soyar (**, __, `, [a](b)) ve boşlukları sadeleştirir.
export function temizMetin(s: string): string {
  return (s ?? '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\*{1,3}|_{2}|`/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Eski ozet.json'da `olay` yoksa sez: en çok 4 kelime ve kart kimliği / teslim / denetim içeren metin yalnız durum işaretidir.
function olaymi(r: { metin: string; olay?: boolean }): boolean {
  if (r.olay !== undefined) return r.olay
  const m = temizMetin(r.metin)
  return m.split(' ').length <= 4 && /\bg-\d+\b|teslim|denetim/.test(m.replace(/İ/g, 'i').toLowerCase())
}

// Bu sohbette süren arka plan işi: sohbetin kendi görevleri + proje çapında perspektif koşusu ve onay uygulaması.
export function arkaSayisi(h: HamOzet, oturum: string): number {
  const a = h.arka_plan
  return (a?.oturumlar?.[oturum] ?? 0) + (a?.perspektif === true ? 1 : 0) + (a?.uygulama === true ? 1 : 0)
}

// Prompt üstü bant yazısı: "<biten>/<toplam> yapıldı · işlem devam ediyor" (bu sohbetin işleri); todo yoksa yalnız ikinci parça.
export function bantMetni(o: Pick<UiOzet, 'isler'>): string {
  const isler = (o.isler ?? []).filter(x => x.toplam > 0 && x.benim !== false)
  const toplam = isler.reduce((a, x) => a + x.toplam, 0)
  const biten = isler.reduce((a, x) => a + x.biten, 0)
  return toplam === 0 ? 'işlem devam ediyor' : `${biten}/${toplam} yapıldı · işlem devam ediyor`
}

// Ham anlık görüntüyü bu oturumun gözünden panel verisine çevirir.
export function donustur(h: HamOzet, oturum: string): UiOzet {
  const ot = h.maliyet?.oturumlar?.[oturum]
  const hepsi = h.kartlar ?? []
  const kartlar: KartOzeti[] = hepsi
    .filter(k => ACIK.includes(k.durum))
    .slice(0, 25)
    .map(k => ({ id: k.id, baslik: k.baslik, durum: k.durum, basamak: k.basamak, isci: k.isci, denetim: k.denetim, usd: k.usd }))
  const teslimler = hepsi.filter(k => k.durum === 'teslim')
  const son = teslimler.reduce<(typeof teslimler)[number] | undefined>(
    (a, k) => (a === undefined || (k.guncelleme ?? '') > (a.guncelleme ?? '') ? k : a), undefined)
  return {
    acik: true,
    kartlar,
    sayac: h.sayac ?? {},
    maliyet: { bugun: h.maliyet?.bugun ?? 0, oturum: ot?.usd ?? 0 },
    arka: arkaSayisi(h, oturum),
    teslim: { sayi: teslimler.length, sonId: son?.id, sonSaat: (son?.guncelleme ?? '').slice(11, 16) || undefined },
    defter: (h.defter ?? []).filter(r => !olaymi(r)).slice(-3).map(r => ({
      saat: (r.zaman ?? '').slice(11, 16), gorev: r.gorev, metin: kes(temizMetin(r.metin), 160),
    })),
    perspektif: h.perspektif ?? h.ruya,  // ruya: eski ozet.json anahtarı
    uretim: h.uretim,
    // Bant yalnız bu sohbetin bağlı işlerini sayar (benim); `oturumlar` yoksa (eski ozet.json) süzülmez.
    isler: (h.isler ?? []).map(x => (x.oturumlar === undefined ? x : { ...x, benim: x.oturumlar.includes(oturum) })),
  }
}

// Modül düzeyi durum: yeniden yüklemede sıfırlanır (gösterilen veri $.state'te kalır).
let sonImza = ''
let sonRet = 0
let calisiyor = false

async function yenile($: EngineInterface, zorla: boolean): Promise<void> {
  if (calisiyor) return
  calisiyor = true
  try {
    const st = await $.fs.stat(OZET).catch(() => undefined)
    if (st === undefined) {
      const acik = await $.fs.exists('.claude/orkestra').catch(() => false)
      await update($, veri, () => (acik
        ? { acik: true, hata: 'ozet.json henüz yok: bir tur bitince oluşur (ya da Bash: orkestra ui-ozet --yaz).' }
        : { acik: false }))
      return
    }
    const imza = `${st.mtimeMs}:${st.size}`
    if (!zorla && imza === sonImza) return
    sonImza = imza
    const metin = await $.fs.read(OZET)
    const ham = JSON.parse(metin) as HamOzet
    const o = donustur(ham, await $.session.id())
    const ret = o.sayac?.reddedildi ?? 0
    if (ret > sonRet) $.ui.toast(`Orkestra: denetçi ${ret - sonRet} işi reddetti — düzeltme ya da yükseltme gerekiyor.`)
    sonRet = ret
    await update($, veri, () => o)
  } catch (hata) {
    const mesaj = hata instanceof Error ? hata.message : String(hata)
    await update($, veri, eski => ({ ...(eski ?? { acik: true }), hata: `Veri okunamadı: ${kes(mesaj, 200)}` }))
  } finally {
    calisiyor = false
  }
}

async function webPaneli($: EngineInterface): Promise<string> {
  const betik = `${$.plugin.root}/../orkestra/scripts/orkestra.py`
  const r = await $.process.run(['python', betik, 'panel'], { timeoutMs: 20000 })
  const cikti = (r.stdout || r.stderr).trim()
  return r.exitCode === 0 ? `HTML canlı panel: ${cikti} — tarayıcıda aç (Claude tarayıcı paneli ya da Chrome).`
    : `HTML panel başlatılamadı (${r.exitCode}): ${kes(cikti, 300)}. Terminalde dene: orkestra panel`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'orkestra', description: 'Orkestra panelini aç: dikkat isteyen kartlar, çalışanlar, maliyet özeti, son olaylar' })
    await $.command.register({ name: 'orkestra-web', description: 'Orkestra HTML canlı panelini başlat ve adresini ver (zengin görünüm, tarayıcıda)' })
    await yenile($, true)
    $.clock.every(3000, () => void yenile($, false))
    return next(e)
  })

  on('command.run', { command: 'orkestra' }, async $ => {
    await yenile($, true)
    await $.ui.open({ id: PANE, title: 'Orkestra' })
    return { text: 'Orkestra paneli açıldı. Daha zengin canlı görünüm için /orkestra-web.' }
  })

  on('command.run', { command: 'orkestra-web' }, async $ => {
    try {
      return { text: await webPaneli($) }
    } catch (hata) {
      return { text: `HTML panel başlatılamadı: ${hata instanceof Error ? hata.message : String(hata)}. Terminalde dene: orkestra panel` }
    }
  })

  on('turn.complete', async ($, e, next) => {
    const sonuc = await next(e)
    await yenile($, true)
    return sonuc
  })

  // Pane: kimliği tam eşleşmeyebilir (düğmeden/komuttan açılış); "orkestra" içeren her örneği çiz, gerisini motora bırak.
  // Çizim hata verirse boş pencere yerine hatanın kendisi gösterilir (.catch: zaman aşımı / istisna).
  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (!String(e.requestId ?? '').includes(PANE)) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    try {
      return await paneCiz($, e)
    } catch (hata) {
      return (
        <Box flexDirection="column">
          <Text color="error">Panel çizilemedi: {kes(hata instanceof Error ? hata.message : String(hata), 300)}</Text>
          <Text dimColor>Canlı HTML panel çalışıyor: /orkestra-web</Text>
        </Box>
      )
    }
  }).catch(($, e, next) => {
    if (!String(e.requestId ?? '').includes(PANE)) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Text color="error">Panel zamanında çizilemedi ({next.error?.kind ?? 'hata'}).</Text>
        <Text dimColor>Canlı HTML panel çalışıyor: /orkestra-web</Text>
      </Box>
    )
  })

  // İstem kutusu bandı burada çizilmez: tek sahibi orkestra eklentisidir (orkestra/hooks/arka_plan_seridi.tsx, ADR-0073).
}

// Panel ağacı: bir bakışta özet (satırlar iç içe Text yerine Box içinde yan yana Text: her yüzeyde güvenli).
async function paneCiz($: EngineInterface, e: Parameters<EngineInterface['ui']['resolve']>[0] & { props: { bodyColumns?: number } }) {
  {
    const { Box, Text } = $.ui.resolve(e)
    const o = await read($, veri)
    const w = Math.max(40, e.props.bodyColumns ?? 80)
    if (o === null) {
      return <Box><Text dimColor>Orkestra verisi yükleniyor…</Text></Box>
    }
    if (!o.acik) {
      return (
        <Box flexDirection="column">
          <Text>Bu projede orkestra kapalı.</Text>
          <Text dimColor>/orkestra:baslat ile aç.</Text>
        </Box>
      )
    }
    if (o.kartlar === undefined && o.isler === undefined) {
      return (
        <Box flexDirection="column">
          <Text color="error">{o.hata ?? 'Veri yok.'}</Text>
        </Box>
      )
    }
    const isler = (o.isler ?? []).filter(x => x.toplam > 0)
    const biten = isler.reduce((a, x) => a + x.biten, 0)
    const toplam = isler.reduce((a, x) => a + x.toplam, 0)
    const yuzde = toplam === 0 ? 0 : Math.round((biten / toplam) * 100)
    const dolu = Math.round((yuzde / 100) * Math.min(30, w - 20))
    const cubuk = '█'.repeat(dolu) + '░'.repeat(Math.min(30, w - 20) - dolu)
    const yapilanlar = isler.filter(x => x.biten > 0)
    const yapilacaklar = isler.filter(x => x.acik.length > 0)
    const uretimSaat = (o.uretim ?? '').slice(11, 16)
    const yas = o.uretim !== undefined ? Date.now() - Date.parse(o.uretim) : 0
    const eski = Number.isFinite(yas) && yas > ESKI_DK * 60000
    return (
      <Box flexDirection="column">
        {o.hata !== undefined && <Text color="error" wrap="truncate">{o.hata}</Text>}
        <Text bold>{`Yapılan ${biten} / toplam ${toplam} iş · %${yuzde}`}</Text>
        <Text color="success">{cubuk}</Text>
        <Text> </Text>
        <Text bold color="success">{`Yapılanlar (${biten})`}</Text>
        {yapilanlar.length === 0 && <Text dimColor>Henüz biten madde yok</Text>}
        {yapilanlar.map(x => <Text wrap="truncate">{kes(`${x.biten}/${x.toplam}  ${x.ad}`, w)}</Text>)}
        <Text> </Text>
        <Text bold color="warning">{`Yapılacaklar (${toplam - biten})`}</Text>
        {yapilacaklar.length === 0 && <Text dimColor>Açık madde yok</Text>}
        {yapilacaklar.map(x => (
          <Box flexDirection="column">
            <Text bold wrap="truncate">{kes(`${x.ad} · ${x.toplam - x.biten} açık`, w)}</Text>
            {x.acik.slice(0, 3).map(m => <Text dimColor wrap="truncate">{kes(`  ○ ${m}`, w)}</Text>)}
          </Box>
        ))}
        <Text> </Text>
        <Box>
          <Text dimColor>{uretimSaat === '' ? 'Ayrıntı: /orkestra-web' : 'Ayrıntı: /orkestra-web · '}</Text>
          {uretimSaat === '' ? null : eski ? <Text color="warning">{`veri eski (${uretimSaat})`}</Text> : <Text dimColor>{`veri ${uretimSaat}`}</Text>}
        </Box>
      </Box>
    )
  }
}
