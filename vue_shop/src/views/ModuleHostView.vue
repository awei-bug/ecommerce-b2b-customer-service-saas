<template>
  <div class="module-host">
    <div class="module-host__bar">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <div class="module-host__actions">
        <span v-if="childTitle" class="module-host__child">当前页面 · {{ childTitle }}</span>
        <span class="module-host__state" :class="stateClass">{{ stateText }}</span>
        <button type="button" @click="reload">重新加载</button>
        <a :href="src" target="_blank" rel="noopener noreferrer">独立窗口打开</a>
      </div>
    </div>
    <iframe
      ref="frame"
      :src="currentSrc"
      :title="title"
      @load="onFrameLoad"
    ></iframe>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  src: { type: String, required: true },
})

const router = useRouter()
const route = useRoute()
const frame = ref(null)
const loaded = ref(false)
const nonce = ref(0)
const childTitle = ref('')

// 只接受三个被承载模块的来源，避免任意页面伪造宿主消息。
const ALLOWED_ORIGINS = [
  'http://127.0.0.1:5174',
  'http://127.0.0.1:5175',
  'http://127.0.0.1:8090',
]

const baseSrc = computed(() => {
  const state = route.query.module_state
  if (typeof state !== 'string' || !state.startsWith('/')) return props.src
  try {
    const target = new URL(props.src)
    const [path, query] = state.split('?')
    target.pathname = path
    target.search = query ? `?${query}` : ''
    return target.toString()
  } catch (_) {
    return props.src
  }
})

const currentSrc = computed(() => {
  if (!nonce.value) return baseSrc.value
  try {
    const target = new URL(baseSrc.value)
    target.searchParams.set('r', String(nonce.value))
    return target.toString()
  } catch (_) {
    return baseSrc.value
  }
})
const stateText = computed(() => (loaded.value ? '模块已加载' : '正在加载'))
const stateClass = computed(() => (loaded.value ? 'is-ready' : 'is-loading'))

function postToFrame(message) {
  const target = frame.value?.contentWindow
  if (!target) return
  try {
    target.postMessage(message, new URL(props.src).origin)
  } catch (_) {
    // 子页面尚未就绪时忽略，下次 load 会重发
  }
}

function onFrameLoad() {
  loaded.value = true
  const token = sessionStorage.getItem('token')
  if (token) postToFrame({ type: 'unified:session', token })
}

function onHostMessage(event) {
  if (!ALLOWED_ORIGINS.includes(event.origin)) return
  const data = event.data
  if (!data || typeof data !== 'object') return
  if (data.type === 'unified:route' && typeof data.title === 'string') {
    childTitle.value = data.title
  }
  if (data.type === 'unified:need-login') {
    router.push({ path: '/login', query: { redirect: '/module_cross' } })
  }
}

function reload() {
  loaded.value = false
  childTitle.value = ''
  nonce.value = Date.now()
}

onMounted(() => window.addEventListener('message', onHostMessage))
onBeforeUnmount(() => window.removeEventListener('message', onHostMessage))

watch(
  () => props.src,
  () => {
    loaded.value = false
    childTitle.value = ''
    nonce.value = 0
  },
)
</script>

<style scoped>
.module-host {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 88px);
  background: #fff;
  border: 1px solid #e8e4db;
  border-radius: 16px;
  overflow: hidden;
}
.module-host__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid #e8e4db;
  background: #fffcf7;
}
.module-host__bar h2 {
  margin: 0;
  font-size: 16px;
  color: #14120f;
}
.module-host__bar p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #8a8478;
}
.module-host__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.module-host__child {
  font-size: 12px;
  color: #0f766e;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.module-host__state {
  font-size: 12px;
  color: #8a8478;
}
.module-host__state.is-ready {
  color: #0f766e;
}
.module-host__actions button,
.module-host__actions a {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #d9d3c7;
  background: #fff;
  color: #3d3a34;
  cursor: pointer;
  text-decoration: none;
}
.module-host__actions button:hover,
.module-host__actions a:hover {
  border-color: #0f766e;
  color: #0f766e;
}
iframe {
  flex: 1;
  width: 100%;
  border: 0;
}
</style>
