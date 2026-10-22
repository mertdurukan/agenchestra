export type KartOzeti = {
  id: string
  baslik: string
  durum: string
  basamak: string
  isci: number
  denetim: string
  usd: number
}

export type IsTodosu = { id: string; ad: string; biten: number; toplam: number; acik: string[] }

export type DefterSatiri = { saat: string; gorev: string; metin: string }

// Panelin gösterdiği, bu oturumun gözünden veri.
export type UiOzet = {
  acik: boolean
  hata?: string
  uretim?: string
  kartlar?: KartOzeti[]
  sayac?: Record<string, number>
  maliyet?: { bugun: number; oturum: number }
  // Bu sohbetin gözünden süren arka plan işi sayısı (sohbetin görevleri + perspektif koşusu + onay uygulaması); bant yalnız > 0 iken çıkar.
  arka?: number
  // Teslim edilmiş kartlar yalnız sayı olarak; son teslim "açık iş yok" satırı için.
  teslim?: { sayi: number; sonId?: string; sonSaat?: string }
  defter?: DefterSatiri[]  // olay olmayan, temiz son 3 satır
  isler?: IsTodosu[]       // açık işlerin todo durumu: panelin tek gösterimi
  perspektif?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

// Çekirdeğin yazdığı ham anlık görüntü (.claude/orkestra/ozet.json, surum 2).
export type HamOzet = {
  surum: number
  acik: boolean
  uretim: string
  proje: string
  kartlar?: (KartOzeti & { oturum?: string; bagimli?: string[]; guncelleme?: string })[]
  sayac?: Record<string, number>
  maliyet?: {
    bugun: number
    toplam: number
    surec: Record<string, number>
    model: Record<string, number>
    oturumlar?: Record<string, { usd: number; surec: Record<string, number>; model: Record<string, number> }>
  }
  sohbetler?: { oturum: string; baslik: string; usd: number; kaynak: 'motor' | 'defter'; son: string }[]
  defter?: { zaman?: string; gorev: string; surec: string; ajan: string; metin: string; oturum?: string | null; olay?: boolean }[]
  isler?: IsTodosu[]
  perspektif?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }  // eski anahtar (geriye uyum)
  arka_plan?: { oturumlar?: Record<string, number>; perspektif?: boolean; uygulama?: boolean }
}

declare module 'claude-code' {
  interface PluginState {
    'orkestra-ui': { veri: UiOzet | null }
  }
}
