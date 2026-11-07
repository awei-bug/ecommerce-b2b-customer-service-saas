<template>
  <div class="module-host">
    <div class="module-host__bar">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <div class="module-host__actions">
        <span class="module-host__state" :class="stateClass">{{ stateText }}</span>
        <button type="button" @click="reload">重新加载</button>
        <a :href="src" target="_blank" rel="noopener noreferrer">独立窗口打开</a>
      </div>
    </div>
    <iframe :src="src" :title="title" @load="loaded = true"></iframe>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  src: { type: String, required: true },
})

const loaded = ref(false)
const nonce = ref(0)

// Cache-busting query keeps a reload genuinely reloading, since assigning the
// same src to an iframe is a no-op in every browser.
const currentSrc = computed(() => (nonce.value ? `${props.src}?r=${nonce.value}` : props.src))
const stateText = computed(() => (loaded.value ? '模块已加载' : '正在加载'))
const stateClass = computed(() => (loaded.value ? 'is-ready' : 'is-loading'))

function reload() {
  loaded.value = false
  nonce.value = Date.now()
}

watch(
  () => props.src,
  () => {
    loaded.value = false
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
