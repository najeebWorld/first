<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ArrowDownUp, ArrowLeft, CarFront, Check, ChevronLeft, Clock3, Gauge, MapPin, RotateCcw, Search, SlidersHorizontal, X, CircleAlert, RefreshCw, ScanLine } from 'lucide-vue-next'

type Status = 'passed' | 'deferred' | 'rejected'
type Tab = Status | 'all'
interface Listing {
  external_id: string
  title: string
  description: string
  price_minor: number | null
  currency: string | null
  region: string | null
  main_photo: string | null
  fields: { make?: string; model?: string; year?: number; km?: number | null; hand?: number; seller_type?: string | null; transmission?: string }
}
interface ScanResult { listing: Listing; rule_result: { status: Status; reasons: string[] } }

const defaults = () => ({ text: '', make: '', yearMin: '', yearMax: '', priceMin: '', priceMax: '', kmMax: '', handMax: '', region: '', seller: '', include: '', exclude: '' })
const filters = reactive(defaults())
const elapsed = ref(120)
const results = ref<ScanResult[]>([])
const loading = ref(false)
const error = ref('')
const hasLoaded = ref(false)
const dirty = ref(false)
const tab = ref<Tab>('all')
const sort = ref('newest')
const mobileFilters = ref(false)
const selected = ref<ScanResult | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const lastUpdated = ref('')
let controller: AbortController | null = null
let requestId = 0

const labels: Record<Status, string> = { passed: 'עבר סינון', deferred: 'חסר מידע', rejected: 'לא מתאים' }
const regions: Record<string, string> = { center: 'מרכז', north: 'צפון', south: 'דרום' }
const reasons: Record<string, string> = { km: 'קילומטראז׳', year: 'שנת ייצור', hand: 'מספר ידיים', price: 'מחיר', currency: 'מטבע', region: 'אזור', seller_type: 'סוג מוכר', make: 'יצרן', model: 'דגם', include_keywords: 'מילים נדרשות', exclude_keywords: 'מילים להחרגה' }
const tabs: { value: Tab; label: string }[] = [
  { value: 'all', label: 'כל התוצאות' }, { value: 'passed', label: 'עברו סינון' },
  { value: 'deferred', label: 'חסר מידע' }, { value: 'rejected', label: 'לא מתאימות' },
]
const number = (value: number | null | undefined) => value == null ? 'לא נמסר' : new Intl.NumberFormat('he-IL').format(value)
const price = (listing: Listing) => listing.price_minor == null ? 'מחיר לא נמסר' : new Intl.NumberFormat('he-IL', { style: 'currency', currency: listing.currency || 'ILS', maximumFractionDigits: 0 }).format(listing.price_minor / 100)
const count = (status: Tab) => status === 'all' ? results.value.length : results.value.filter(item => item.rule_result.status === status).length
const visible = computed(() => {
  const items = results.value.filter(item => tab.value === 'all' || item.rule_result.status === tab.value)
  return [...items].sort((first, second) => {
    if (sort.value === 'price-low' || sort.value === 'price-high') {
      const firstPrice = first.listing.price_minor
      const secondPrice = second.listing.price_minor
      if (firstPrice == null) return secondPrice == null ? 0 : 1
      if (secondPrice == null) return -1
      return sort.value === 'price-low' ? firstPrice - secondPrice : secondPrice - firstPrice
    }
    if (sort.value === 'year') return (second.listing.fields.year || 0) - (first.listing.fields.year || 0)
    return second.listing.external_id.localeCompare(first.listing.external_id)
  })
})
const activeFilters = computed(() => Object.values(filters).filter(value => value.trim()).length)

async function scan() {
  controller?.abort()
  controller = new AbortController()
  const currentRequest = ++requestId
  const timeout = window.setTimeout(() => controller?.abort(), 15000)
  loading.value = true
  error.value = ''
  const payload: Record<string, unknown> = {}
  const numeric = [
    ['year_min', filters.yearMin, 1], ['year_max', filters.yearMax, 1],
    ['price_min_minor', filters.priceMin, 100], ['price_max_minor', filters.priceMax, 100],
    ['km_max', filters.kmMax, 1], ['hand_max', filters.handMax, 1],
  ] as const
  for (const [key, value, multiplier] of numeric) if (value !== '') payload[key] = Math.round(Number(value) * multiplier)
  if (filters.make) payload.make = filters.make
  if (filters.region) payload.regions = [filters.region]
  if (filters.seller) payload.seller_types = [filters.seller]
  const keywords = (text: string) => text.split(',').map(value => value.trim()).filter(Boolean)
  if (filters.include.trim()) payload.include_keywords = keywords(filters.include)
  if (filters.exclude.trim()) payload.exclude_keywords = keywords(filters.exclude)
  try {
    const response = await fetch('/demo-api/scan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ elapsed_seconds: Number(elapsed.value), text: filters.text, filters: payload }),
    })
    if (!response.ok) throw new Error(response.status === 422 ? 'יש לבדוק את טווחי הסינון. ערך המינימום לא יכול להיות גדול מהמקסימום.' : 'שרת ההדגמה אינו זמין כרגע. אפשר לנסות שוב.')
    const data = await response.json() as { results: ScanResult[] }
    if (currentRequest !== requestId) return
    results.value = data.results
    hasLoaded.value = true
    dirty.value = false
    mobileFilters.value = false
    lastUpdated.value = new Intl.DateTimeFormat('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date())
  } catch (caught) {
    if (currentRequest !== requestId) return
    error.value = caught instanceof Error && caught.name !== 'AbortError' ? caught.message : 'הבקשה ארכה יותר מדי. אפשר לנסות שוב.'
    results.value = []
  } finally {
    window.clearTimeout(timeout)
    if (currentRequest === requestId) loading.value = false
  }
}

function reset() {
  Object.assign(filters, defaults())
  tab.value = 'all'
  void scan()
}

function openDetails(item: ScanResult) {
  selected.value = item
  dialog.value?.showModal()
}

function closeDetails() {
  dialog.value?.close()
  selected.value = null
}

onMounted(scan)
onUnmounted(() => { requestId++; controller?.abort() })
</script>

<template>
  <div class="demo-app" dir="rtl">
    <a class="skip-link" href="#results">דילוג לתוצאות</a>
    <header class="topbar">
      <a class="brand" href="/demo.html" aria-label="איתור רכב, עמוד הבית">
        <span class="brand-mark"><ScanLine :size="24" /></span>
        <span>איתור<span class="brand-light">רכב</span></span>
      </a>
      <div class="topbar-section"><CarFront :size="17" /> סביבת רכבים <ChevronLeft :size="14" /><span>חיפוש מודעות</span></div>
      <span class="demo-label"><span class="status-dot"></span> הדגמה מקומית</span>
    </header>

    <main class="workspace">
      <section class="page-heading">
        <div><p class="eyebrow">סביבת עבודה / רכבים</p><h1>הרכב הבא, בתנאים שלך.</h1><p class="subtitle">מודעות פיקטיביות בלבד · ללא חיבור לאתרי מודעות</p></div>
        <div class="sync-block"><span class="sync-dot"></span><span>{{ lastUpdated ? `עודכן ב־${lastUpdated}` : 'ממתין לסריקה' }}</span><button class="icon-button" type="button" title="רענון תוצאות" aria-label="רענון תוצאות" :disabled="loading" @click="scan"><RefreshCw :size="17" :class="{ spinning: loading }" /></button></div>
      </section>

      <section class="overview" aria-label="סיכום סריקה">
        <div class="metric"><span>מודעות בסריקה</span><strong>{{ hasLoaded && !error ? results.length.toString().padStart(2, '0') : '—' }}</strong><CarFront :size="22" /></div>
        <div class="metric metric-green"><span>עברו את הסינון</span><strong>{{ hasLoaded && !error ? count('passed').toString().padStart(2, '0') : '—' }}</strong><Check :size="22" /></div>
        <div class="metric metric-amber"><span>דורשות מידע נוסף</span><strong>{{ hasLoaded && !error ? count('deferred').toString().padStart(2, '0') : '—' }}</strong><CircleAlert :size="22" /></div>
        <div class="timeline"><label for="timeline"><Clock3 :size="17" /> נקודת זמן בדמו</label><select id="timeline" v-model="elapsed" :disabled="loading" @change="scan"><option :value="0">תחילת הסריקה · 0 שניות</option><option :value="60">אחרי דקה · 60 שניות</option><option :value="120">אחרי שתי דקות · 120 שניות</option></select></div>
      </section>

      <div class="work-grid">
        <button class="mobile-filter-button secondary-button" type="button" :aria-expanded="mobileFilters" aria-controls="filter-panel" @click="mobileFilters = !mobileFilters"><SlidersHorizontal :size="18" /> מסננים <span v-if="activeFilters">({{ activeFilters }})</span></button>
        <aside id="filter-panel" class="filter-panel" :class="{ 'mobile-open': mobileFilters }" aria-label="מסנני חיפוש">
          <div class="panel-title"><h2><SlidersHorizontal :size="18" /> מיקוד החיפוש</h2><button class="icon-button" type="button" title="איפוס מסננים" aria-label="איפוס מסננים" :disabled="loading" @click="reset"><RotateCcw :size="16" /></button></div>
          <form @submit.prevent="scan" @input="dirty = true" @change="dirty = true">
            <fieldset :disabled="loading">
              <label for="query">חיפוש חופשי</label><div class="search-input"><Search :size="17" /><input id="query" v-model="filters.text" maxlength="500" placeholder="יצרן, דגם או מילה במודעה" /></div>
              <label for="make">יצרן</label><select id="make" v-model="filters.make"><option value="">כל היצרנים</option><option value="hyundai">יונדאי</option><option value="toyota">טויוטה</option></select>
              <div class="field-row"><div><label for="year-min">משנת</label><input id="year-min" v-model="filters.yearMin" type="number" min="1886" max="2100" step="1" placeholder="2018" /></div><div><label for="year-max">עד שנת</label><input id="year-max" v-model="filters.yearMax" type="number" min="1886" max="2100" step="1" placeholder="2024" /></div></div>
              <div class="field-row"><div><label for="price-min">מחיר מ־ (₪)</label><input id="price-min" v-model="filters.priceMin" type="number" min="0" max="100000000" step="1" placeholder="ללא מינימום" /></div><div><label for="price-max">מחיר עד (₪)</label><input id="price-max" v-model="filters.priceMax" type="number" min="0" max="100000000" step="1" placeholder="ללא מקסימום" /></div></div>
              <div class="field-row"><div><label for="km-max">ק״מ עד</label><input id="km-max" v-model="filters.kmMax" type="number" min="0" max="10000000" step="1" placeholder="80,000" /></div><div><label for="hand-max">יד עד</label><select id="hand-max" v-model="filters.handMax"><option value="">ללא הגבלה</option value=""><option value="1">יד 1</option><option value="2">יד 2</option><option value="3">יד 3</option><option value="4">יד 4</option></select></div></div>
              <label for="region">אזור בארץ</label><select id="region" v-model="filters.region"><option value="">כל האזורים</option><option value="center">מרכז</option><option value="north">צפון</option><option value="south">דרום</option></select>
              <label for="seller">סוג מוכר</label><select id="seller" v-model="filters.seller"><option value="">כל המוכרים</option><option value="private">פרטי</option><option value="dealer">סוחר</option></select>
              <details class="advanced"><summary>מילות מפתח</summary><label for="include">מילים נדרשות, מופרדות בפסיקים</label><input id="include" v-model="filters.include" maxlength="3000" placeholder="אוטומטי, טיפולים" /><label for="exclude">מילים להחרגה, מופרדות בפסיקים</label><input id="exclude" v-model="filters.exclude" maxlength="3000" placeholder="תאונה, תיקון" /></details>
              <button class="primary-button apply-button" type="submit"><Search :size="17" /> {{ loading ? 'סורק מודעות…' : 'הצגת תוצאות' }}<ArrowLeft :size="17" /></button>
              <p v-if="dirty" class="pending-note">יש שינויים שטרם הוחלו</p>
            </fieldset>
          </form>
        </aside>

        <section id="results" class="results" tabindex="-1" :aria-busy="loading">
          <div class="results-header"><div><h2>תוצאות החיפוש <span class="result-count">{{ visible.length }}</span></h2><p>התאמה לפי מסננים בלבד · ללא ניתוח AI</p></div><div class="sort-control"><ArrowDownUp :size="16" /><label class="sr-only" for="sort">מיון תוצאות</label><select id="sort" v-model="sort"><option value="newest">נוספו לאחרונה</option><option value="price-low">מחיר: מהנמוך לגבוה</option><option value="price-high">מחיר: מהגבוה לנמוך</option><option value="year">שנתון: מהחדש לישן</option></select></div></div>
          <div class="status-tabs" aria-label="סינון לפי סטטוס"><button v-for="item in tabs" :key="item.value" type="button" :class="{ active: tab === item.value }" :aria-pressed="tab === item.value" @click="tab = item.value">{{ item.label }}<span>{{ count(item.value) }}</span></button></div>
          <div v-if="loading" class="state-panel" role="status"><RefreshCw class="spinning" :size="30" /><h3>טוען מודעות…</h3></div>
          <div v-else-if="error" class="state-panel error-state" role="alert"><CircleAlert :size="32" /><h3>לא ניתן להשלים את הסריקה</h3><p>{{ error }}</p><button class="secondary-button" type="button" @click="scan"><RefreshCw :size="16" /> ניסיון נוסף</button></div>
          <div v-else-if="!visible.length" class="state-panel"><Search :size="32" /><h3>אין מודעות בתצוגה הזאת</h3><p>לא נמצאו תוצאות עבור החיפוש והסטטוס שנבחרו.</p><button class="secondary-button" type="button" @click="reset"><RotateCcw :size="16" /> איפוס החיפוש</button></div>
          <div v-else class="listing-grid">
            <article v-for="(item, index) in visible" :key="item.listing.external_id" class="listing" :style="{ '--reveal-order': index }" :data-listing-id="item.listing.external_id">
              <div class="listing-media"><img :src="item.listing.main_photo || '/static/demo/vehicle-placeholder.svg'" alt="איור רכב פיקטיבי להדגמה" width="640" height="360" /><span class="fiction-badge">מודעה פיקטיבית</span><span class="listing-id">{{ item.listing.external_id }}</span></div>
              <div class="listing-body"><div class="listing-topline"><span class="status-badge" :class="item.rule_result.status"><Check v-if="item.rule_result.status === 'passed'" :size="13" /><CircleAlert v-else :size="13" />{{ labels[item.rule_result.status] }}</span><span class="location"><MapPin :size="13" />{{ regions[item.listing.region || ''] || 'אזור לא נמסר' }}</span></div>
                <h3>{{ item.listing.title }}</h3><div class="listing-specs"><span>{{ item.listing.fields.year || 'שנה לא נמסרה' }}</span><span><Gauge :size="14" />{{ number(item.listing.fields.km) }}{{ item.listing.fields.km != null ? ' ק״מ' : '' }}</span><span>יד {{ item.listing.fields.hand || 'לא נמסרה' }}</span></div>
                <p class="rule-note" :class="item.rule_result.status">{{ item.rule_result.status === 'passed' ? 'עומד בתנאי הסינון שנבחרו' : `${item.rule_result.status === 'deferred' ? 'מידע חסר' : 'אי־התאמה'}: ${item.rule_result.reasons.map(reason => reasons[reason] || reason).join(', ')}` }}</p>
                <div class="listing-bottom"><strong class="price">{{ price(item.listing) }}</strong><button class="details-button" type="button" :aria-label="`פרטי ${item.listing.title}`" @click="openDetails(item)">פרטי הרכב <ArrowLeft :size="16" /></button></div>
              </div>
            </article>
          </div>
          <footer class="results-footer"><span><span class="status-dot"></span> מקור: דמו מקומי</span><span>אין מודעות חיות · אין שליחת התראות</span></footer>
        </section>
      </div>
    </main>

    <dialog ref="dialog" class="detail-dialog" aria-labelledby="detail-title" @close="selected = null" @click="event => { if (event.target === dialog) closeDetails() }">
      <template v-if="selected"><div class="dialog-header"><span class="eyebrow">פרטי מודעת הדגמה</span><button class="icon-button" type="button" title="סגירה" aria-label="סגירת פרטי הרכב" @click="closeDetails"><X :size="20" /></button></div><img class="detail-image" :src="selected.listing.main_photo || '/static/demo/vehicle-placeholder.svg'" alt="איור רכב פיקטיבי" width="640" height="360" /><h2 id="detail-title">{{ selected.listing.title }}</h2><strong class="detail-price">{{ price(selected.listing) }}</strong><span class="status-badge" :class="selected.rule_result.status">{{ labels[selected.rule_result.status] }}</span><dl class="detail-facts"><div><dt>שנת ייצור</dt><dd>{{ selected.listing.fields.year || 'לא נמסר' }}</dd></div><div><dt>קילומטראז׳</dt><dd>{{ number(selected.listing.fields.km) }}</dd></div><div><dt>יד</dt><dd>{{ selected.listing.fields.hand || 'לא נמסר' }}</dd></div><div><dt>אזור</dt><dd>{{ regions[selected.listing.region || ''] || 'לא נמסר' }}</dd></div><div><dt>מוכר</dt><dd>{{ selected.listing.fields.seller_type === 'private' ? 'פרטי' : selected.listing.fields.seller_type === 'dealer' ? 'סוחר' : 'לא נמסר' }}</dd></div><div><dt>תיבת הילוכים</dt><dd>{{ selected.listing.fields.transmission === 'automatic' ? 'אוטומטית' : 'לא נמסר' }}</dd></div></dl><h3>תיאור המודעה</h3><p class="detail-description">{{ selected.listing.description }}</p><p class="detail-disclaimer">מודעה פיקטיבית. אין מוכר אמיתי או קישור למודעה חיצונית.</p></template>
    </dialog>
  </div>
</template>