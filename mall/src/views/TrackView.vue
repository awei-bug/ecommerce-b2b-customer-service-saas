<template>
  <div class="track-page">
    <div class="hero page-card">
      <div class="hero-top">
        <h2>{{ t('trackTitle') }}</h2>
        <div class="lang-switch" role="group" :aria-label="'Language'">
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'zh' }"
            @click="switchLang('zh')"
          >{{ t('langZh') }}</button>
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'en' }"
            @click="switchLang('en')"
          >{{ t('langEn') }}</button>
        </div>
      </div>
      <p class="hint">{{ t('trackHint') }}</p>
      <div class="search-row">
        <input
          v-model="no"
          type="text"
          class="input"
          :placeholder="t('placeholder')"
          @keyup.enter="search"
        />
        <button class="btn primary" type="button" :disabled="loading" @click="search">
          {{ loading ? t('searching') : t('search') }}
        </button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <template v-if="data">
      <section class="page-card">
        <div class="status-line">
          <span class="badge" :class="badgeClass">{{ displayStatus }}</span>
          <span class="no">{{ data.shipment_no }}</span>
        </div>
        <div class="route">
          <div class="port">
            <div class="lab">{{ t('origin') }}</div>
            <div class="val">{{ data.origin || '—' }}</div>
          </div>
          <div class="arrow">→</div>
          <div class="port">
            <div class="lab">{{ t('destination') }}</div>
            <div class="val">{{ data.destination || '—' }}</div>
          </div>
        </div>
        <div class="meta-grid">
          <div>
            <span class="k">{{ t('mode') }}</span>
            <span>{{ modeLabel(data.transport_mode, locale) }}</span>
          </div>
          <div>
            <span class="k">{{ t('incoterm') }}</span>
            <span>{{ data.incoterm || '—' }}</span>
          </div>
          <div>
            <span class="k">{{ t('blNo') }}</span>
            <span>{{ data.bl_no || '—' }}</span>
          </div>
          <div>
            <span class="k">{{ t('cargoStats') }}</span>
            <span>{{ data.packages || 0 }} / {{ data.weight_kg || 0 }}kg / {{ data.volume_cbm || 0 }}cbm</span>
          </div>
          <div class="full" v-if="data.cargo_desc">
            <span class="k">{{ t('cargoDesc') }}</span>
            <span>{{ data.cargo_desc }}</span>
          </div>
          <div class="full" v-if="data.customer_name">
            <span class="k">{{ t('customer') }}</span>
            <span>{{ data.customer_name }}</span>
          </div>
        </div>
      </section>

      <section class="page-card">
        <h3 class="sec-title">{{ t('timeline') }}</h3>
        <div v-if="events.length" class="timeline">
          <div v-for="(e, i) in events" :key="e.id || i" class="tl-item">
            <div class="dot" :class="{ first: i === 0 }" />
            <div class="tl-body">
              <div class="tl-time">{{ e.event_time || '' }}</div>
              <div class="tl-content">
                <strong v-if="e.location">[{{ e.location }}]</strong>
                {{ e.content }}
              </div>
            </div>
          </div>
        </div>
        <p v-else class="empty">{{ t('noEvents') }}</p>
      </section>

      <section class="page-card" v-if="docs.length">
        <h3 class="sec-title">{{ t('documents') }}</h3>
        <ul class="doc-list">
          <li v-for="d in docs" :key="d.id">
            <span class="dtype">{{ docTypeLabel(d.doc_type, locale) }}</span>
            <a class="dlink" :href="docUrl(d)" target="_blank" rel="noopener">
              {{ d.title || d.file_name || '—' }}
            </a>
            <span class="dsize">{{ formatSize(d.size) }}</span>
          </li>
        </ul>
      </section>
    </template>

    <section v-else-if="searched && !loading" class="page-card empty-card">
      {{ t('notFound') }}
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { trackShipment } from '@/api'
import {
  docTypeLabel,
  getLocale,
  modeLabel,
  setLocale,
  statusLabel,
  t as tr,
} from '@/utils/i18n'

const route = useRoute()
const router = useRouter()

const locale = ref(getLocale())
const no = ref('')
const loading = ref(false)
const error = ref('')
const data = ref(null)
const searched = ref(false)

const t = (key) => tr(key, locale.value)

const events = computed(() => {
  const list = data.value?.events || []
  return [...list].reverse()
})
const docs = computed(() => data.value?.documents || [])

const displayStatus = computed(() => {
  if (!data.value) return ''
  return statusLabel(data.value.status, locale.value) || data.value.status_label || data.value.status
})

function formatSize(n) {
  const b = Number(n || 0)
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

function docUrl(d) {
  const path = d.path || d.url || ''
  if (path.startsWith('http')) return path
  const apiOrigin = import.meta.env.DEV ? 'http://127.0.0.1:5000' : window.location.origin
  return `${apiOrigin}${path}`
}

const badgeClass = computed(() => {
  const s = data.value?.status
  if (['delivered', 'closed', 'arrived'].includes(s)) return 'ok'
  if (['in_transit', 'booked'].includes(s)) return 'warn'
  if (s === 'cancelled') return 'bad'
  return ''
})

function switchLang(loc) {
  locale.value = setLocale(loc)
  // refresh error message language if any
  if (error.value && !data.value && searched.value) {
    error.value = ''
  }
  document.documentElement.lang = loc === 'en' ? 'en' : 'zh-CN'
}

async function search() {
  const n = (no.value || '').trim()
  if (!n) {
    error.value = t('needNo')
    return
  }
  loading.value = true
  error.value = ''
  searched.value = true
  data.value = null
  try {
    const res = await trackShipment(n)
    if (res.status === 200 && res.data) {
      data.value = res.data
      const q = { ...route.query, no: n }
      router.replace({ path: '/track', query: q })
    } else {
      error.value = res.msg || t('notFound')
    }
  } catch (e) {
    error.value = e.message || t('queryFail')
  } finally {
    loading.value = false
  }
}

function onLocaleEvent(e) {
  locale.value = e.detail === 'en' ? 'en' : 'zh'
}

onMounted(() => {
  // URL ?lang=en
  const lang = route.query.lang
  if (lang === 'en' || lang === 'zh') {
    switchLang(lang)
  } else {
    document.documentElement.lang = locale.value === 'en' ? 'en' : 'zh-CN'
  }
  window.addEventListener('mall:locale-change', onLocaleEvent)
  const q = route.query.no || route.query.shipment_no
  if (q) {
    no.value = String(q)
    search()
  }
})

onUnmounted(() => {
  window.removeEventListener('mall:locale-change', onLocaleEvent)
})
</script>

<style scoped>
.track-page {
  max-width: 720px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}
.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 6px;
}
.hero h2 {
  margin: 0;
  font-size: 20px;
}
.lang-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
}
.lang-btn {
  border: none;
  background: #fff;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  color: #4e5969;
}
.lang-btn.active {
  background: var(--primary);
  color: #fff;
}
.hint {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 13px;
}
.search-row {
  display: flex;
  gap: 10px;
}
.input {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
}
.error {
  margin: 10px 0 0;
  color: var(--danger);
  font-size: 13px;
}
.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: #f0f0f0;
  color: #595959;
}
.badge.ok { background: #f6ffed; color: #52c41a; }
.badge.warn { background: #fff7e6; color: #fa8c16; }
.badge.bad { background: #fff2f0; color: #ff4d4f; }
.no {
  font-family: ui-monospace, monospace;
  font-size: 14px;
  color: #4e5969;
}
.route {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f7f8fa;
  border-radius: 10px;
  margin-bottom: 12px;
}
.port { flex: 1; min-width: 0; }
.lab { font-size: 12px; color: var(--muted); }
.val { font-weight: 600; margin-top: 4px; word-break: break-all; }
.arrow { color: var(--primary); font-weight: 700; }
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  font-size: 13px;
}
.meta-grid .full { grid-column: 1 / -1; }
.meta-grid .k {
  display: inline-block;
  min-width: 72px;
  color: var(--muted);
  margin-right: 8px;
}
.sec-title {
  margin: 0 0 12px;
  font-size: 15px;
}
.timeline { display: grid; }
.tl-item {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 10px;
  position: relative;
  padding-bottom: 14px;
}
.tl-item:not(:last-child) .dot::after {
  content: '';
  position: absolute;
  left: 7px;
  top: 14px;
  bottom: 0;
  width: 2px;
  background: #e5e6eb;
}
.dot {
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border-radius: 50%;
  background: #c9cdd4;
  position: relative;
  z-index: 1;
}
.dot.first { background: var(--primary); }
.tl-time { font-size: 12px; color: var(--muted); }
.tl-content { margin-top: 2px; font-size: 14px; line-height: 1.5; }
.doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.doc-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}
.dtype {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 4px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 12px;
}
.dlink {
  flex: 1;
  color: var(--primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dsize { color: var(--muted); flex-shrink: 0; }
.empty, .empty-card {
  color: var(--muted);
  font-size: 13px;
  text-align: center;
  padding: 12px 0;
}
.page-card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 20px;
}
@media (max-width: 600px) {
  .meta-grid { grid-template-columns: 1fr; }
  .search-row { flex-direction: column; }
}
</style>
