<template>
  <div class="page">
    <button class="back" type="button" @click="$router.push('/')">← 返回商品列表</button>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else-if="product" class="detail-layout page-card">
      <div class="hero-img">
        <img v-if="product.big_img || product.small_img" :src="imgUrl(product)" alt="" />
        <div v-else class="thumb-placeholder">暂无图片</div>
      </div>

      <div class="panel">
        <h1 class="title">{{ product.name }}</h1>
        <div class="price">￥{{ formatPrice(product.price) }}</div>
        <p class="stock">库存 {{ product.number ?? 0 }} 件</p>
        <p class="desc">{{ product.introduce || '暂无详细介绍' }}</p>

        <div class="qty-row">
          <span>购买数量</span>
          <div class="qty">
            <button type="button" @click="qty = Math.max(1, qty - 1)">−</button>
            <span>{{ qty }}</span>
            <button type="button" @click="qty = Math.min(maxQty, qty + 1)">+</button>
          </div>
        </div>

        <div class="sum-row">
          小计 <strong>￥{{ formatPrice(product.price * qty) }}</strong>
        </div>

        <button class="btn primary buy" type="button" :disabled="!canBuy" @click="onBuy">
          {{ canBuy ? '立即购买' : '暂时缺货' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProduct } from '@/api'
import { isLoggedIn } from '@/utils/session'

const route = useRoute()
const router = useRouter()
const product = ref(null)
const loading = ref(false)
const error = ref('')
const qty = ref(1)

const maxQty = computed(() => Math.max(1, Number(product.value?.number || 1)))
const canBuy = computed(() => Number(product.value?.number || 0) > 0)

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

function imgUrl(p) {
  const path = p.big_img || p.small_img
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `http://127.0.0.1:5000${path}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getProduct(route.params.id)
    if (res.status !== 200) {
      error.value = res.msg || '商品不存在'
      return
    }
    product.value = res.data
    qty.value = 1
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function onBuy() {
  if (!canBuy.value) return
  if (!isLoggedIn()) {
    router.push({
      path: '/login',
      query: { redirect: `/checkout?pid=${product.value.id}&qty=${qty.value}` },
    })
    return
  }
  router.push({
    path: '/checkout',
    query: { pid: product.value.id, qty: qty.value },
  })
}

onMounted(load)
</script>

<style scoped>
.back {
  border: none;
  background: transparent;
  color: var(--primary);
  font-size: 14px;
  padding: 0 0 12px;
  cursor: pointer;
}
.detail-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  align-items: start;
}
.hero-img {
  min-height: 360px;
  border-radius: 8px;
  overflow: hidden;
  background: #f0f2f5;
}
.hero-img img {
  width: 100%;
  height: 100%;
  min-height: 360px;
  object-fit: cover;
  display: block;
}
.thumb-placeholder {
  min-height: 360px;
  display: grid;
  place-items: center;
  color: #c0c4cc;
}
.price {
  color: var(--danger);
  font-size: 28px;
  font-weight: 700;
  margin-top: 12px;
}
.title {
  margin: 0;
  font-size: 22px;
  line-height: 1.35;
}
.stock {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.desc {
  margin: 16px 0 0;
  color: #4e5969;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.qty-row {
  margin-top: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  max-width: 280px;
}
.qty {
  display: inline-flex;
  align-items: center;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  overflow: hidden;
}
.qty button {
  width: 36px;
  height: 34px;
  border: none;
  background: #f7f8fa;
  font-size: 16px;
  cursor: pointer;
}
.qty span {
  min-width: 40px;
  text-align: center;
}
.sum-row {
  margin-top: 16px;
  font-size: 14px;
  color: var(--muted);
}
.sum-row strong {
  color: var(--danger);
  font-size: 20px;
  margin-left: 8px;
}
.buy {
  margin-top: 20px;
  min-width: 200px;
  padding: 12px 24px;
  font-size: 15px;
}
@media (max-width: 800px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }
}
</style>
