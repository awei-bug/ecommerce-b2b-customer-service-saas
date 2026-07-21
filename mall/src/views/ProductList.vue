<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>全部商品</h2>
        <p class="hint">在电脑上浏览、搜索并购买</p>
      </div>
      <div class="search-box">
        <input
          v-model="keyword"
          type="search"
          placeholder="搜索商品名称或简介"
          @keyup.enter="load"
        />
        <button class="btn primary" type="button" @click="load">搜索</button>
        <button v-if="keyword" class="btn ghost" type="button" @click="clearSearch">清空</button>
      </div>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else-if="!list.length" class="empty">
      {{ keyword ? `没有找到「${keyword}」相关商品` : '店里暂时没有商品' }}
    </div>
    <div v-else class="product-grid">
      <article
        v-for="p in list"
        :key="p.id"
        class="product-card"
        @click="$router.push(`/product/${p.id}`)"
      >
        <div class="thumb">
          <img v-if="p.big_img || p.small_img" :src="imgUrl(p)" alt="" />
          <div v-else class="thumb-placeholder">暂无图</div>
        </div>
        <div class="body">
          <h3 class="name">{{ p.name }}</h3>
          <p class="intro">{{ p.introduce || '精选好物' }}</p>
          <div class="row">
            <span class="price">￥{{ formatPrice(p.price) }}</span>
            <span class="muted">库存 {{ p.number ?? 0 }}</span>
          </div>
          <button class="btn primary block" type="button" @click.stop="goDetail(p)">
            查看详情
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getProducts } from '@/api'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

function imgUrl(p) {
  const path = p.big_img || p.small_img
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `http://127.0.0.1:5000${path}`
}

function goDetail(p) {
  router.push(`/product/${p.id}`)
}

function clearSearch() {
  keyword.value = ''
  load()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = {}
    if (keyword.value.trim()) params.q = keyword.value.trim()
    const res = await getProducts(params)
    if (res.status !== 200) {
      error.value = res.msg || '加载失败'
      list.value = []
      return
    }
    list.value = res.data || []
  } catch (e) {
    error.value = e.message || '加载失败'
    list.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('mall:context-change', load)
})
onUnmounted(() => {
  window.removeEventListener('mall:context-change', load)
})
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.page-head h2 {
  margin: 0;
  font-size: 20px;
}
.hint {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.search-box {
  display: flex;
  gap: 8px;
  align-items: center;
}
.search-box input {
  width: 260px;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
}
.product-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.product-card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.15s;
  display: flex;
  flex-direction: column;
}
.product-card:hover {
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.1);
  transform: translateY(-2px);
}
.thumb {
  height: 180px;
  background: #f0f2f5;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  color: #c0c4cc;
  font-size: 13px;
}
.body {
  padding: 14px;
  display: grid;
  gap: 8px;
  flex: 1;
}
.name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.intro {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 34px;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.price {
  color: var(--danger);
  font-size: 18px;
  font-weight: 700;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
@media (max-width: 1100px) {
  .product-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 800px) {
  .product-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
