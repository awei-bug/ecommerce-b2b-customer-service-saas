<template>
  <div class="page">
    <h2>购物车</h2>
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!items.length" class="empty empty-card">
      <div class="empty-title">购物车是空的</div>
      <button class="btn primary" @click="$router.push('/')">去选购</button>
    </div>
    <div v-else class="list">
      <div v-for="it in items" :key="it.id" class="row page-card">
        <div class="info">
          <div class="name">{{ it.product?.name }}</div>
          <div class="meta">¥{{ Number(it.product?.price||0).toFixed(2) }} ×
            <input type="number" min="1" :value="it.quantity" @change="onQty(it, $event)" style="width:56px" />
          </div>
        </div>
        <div class="right">
          <div class="amt">¥{{ Number(it.line_amount||0).toFixed(2) }}</div>
          <button class="btn ghost" @click="remove(it)">删除</button>
        </div>
      </div>
      <div class="sum page-card" v-if="preview">
        <div>商品金额 ¥{{ Number(preview.goods_amount||0).toFixed(2) }}</div>
        <div>预估运费 ¥{{ Number(preview.freight_amount||0).toFixed(2) }}</div>
        <div class="pay">应付 ¥{{ Number(preview.payable||0).toFixed(2) }}</div>
        <button class="btn primary block" @click="goCheckout">去结算</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getCart, updateCartItem, removeCartItem, checkoutPreview } from '@/api'
import { isLoggedIn } from '@/utils/session'
const router = useRouter()
const items = ref([])
const loading = ref(false)
const preview = ref(null)
async function load() {
  if (!isLoggedIn()) { router.push({ path: '/login', query: { redirect: '/cart' } }); return }
  loading.value = true
  try {
    const res = await getCart()
    items.value = res.status === 200 ? (res.data || []) : []
    await loadPreview()
  } finally { loading.value = false }
}
async function loadPreview() {
  if (!items.value.length) { preview.value = null; return }
  const res = await checkoutPreview({ items: items.value.map(i => ({ pid: i.product_id, number: i.quantity })) })
  preview.value = res.status === 200 ? res.data : null
}
async function onQty(it, e) {
  const q = Math.max(1, Number(e.target.value || 1))
  await updateCartItem(it.id, { quantity: q })
  await load()
}
async function remove(it) {
  await removeCartItem(it.id)
  await load()
}
function goCheckout() {
  // 简化：跳到第一个商品购买弹窗链路——或 checkout 多商品
  if (!items.value.length) return
  const first = items.value[0]
  router.push({ path: `/product/${first.product_id}` })
}
onMounted(load)
</script>
<style scoped>
.row { display:flex; justify-content:space-between; gap:12px; padding:14px; margin-bottom:10px; }
.name { font-weight:700; }
.meta { font-size:12.5px; color:#78716c; margin-top:4px; }
.amt { font-weight:800; color:#c2410c; margin-bottom:8px; }
.sum { padding:14px; margin-top:12px; }
.pay { font-size:18px; font-weight:800; margin:8px 0; color:#c2410c; }
.empty-card { text-align:center; padding:40px 12px; }
</style>
