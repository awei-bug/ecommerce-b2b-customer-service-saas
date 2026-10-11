<template>
  <div class="page home-mall">
    <div class="top-bar page-card">
      <div class="search-wrap">
        <input
          v-model="keyword"
          type="search"
          placeholder="搜索本店商品"
          @keyup.enter="load"
        />
        <button class="btn primary" type="button" @click="load">搜索</button>
      </div>
      <div class="top-links">
        <router-link to="/cart">购物车</router-link>
        <router-link to="/orders">我的订单</router-link>
      </div>
    </div>

    <div class="mall-layout">
      <aside class="cat-aside page-card">
        <div class="cat-title">全部分类</div>
        <button
          type="button"
          class="cat-item"
          :class="{ active: !activeCid }"
          @click="selectCat(null)"
        >
          <span>全部商品</span>
          <em>{{ totalCount }}</em>
        </button>
        <button
          v-for="c in categories"
          :key="c.id"
          type="button"
          class="cat-item"
          :class="{ active: activeCid === c.id }"
          @click="selectCat(c.id)"
        >
          <span>{{ c.name }}</span>
          <em>{{ c.product_count ?? 0 }}</em>
        </button>
        <div v-if="!categories.length && !catLoading" class="cat-empty">暂无分类</div>
      </aside>

      <section class="mall-main">
        <div v-if="hotList.length" class="banner page-card">
          <div class="banner-stage">
            <div
              class="banner-track"
              :style="{ transform: `translateX(-${bannerIndex * 100}%)` }"
            >
              <div
                v-for="p in hotList"
                :key="p.id"
                class="banner-slide"
                @click="$router.push(`/product/${p.id}`)"
              >
                <img
                  class="banner-img"
                  :src="hasProductImage(p) ? imgUrl(p) : placeholderForProduct(p)"
                  :alt="p.name"
                />
                <div class="banner-mask">
                  <div class="b-tag">热销推荐</div>
                  <div class="b-name">{{ p.name }}</div>
                  <div class="b-price">¥{{ formatPrice(p.price) }}</div>
                </div>
              </div>
            </div>
            <button type="button" class="b-nav prev" @click.stop="prevBanner">‹</button>
            <button type="button" class="b-nav next" @click.stop="nextBanner">›</button>
            <div class="b-dots">
              <button
                v-for="(p, i) in hotList"
                :key="'d' + p.id"
                type="button"
                :class="{ on: i === bannerIndex }"
                @click.stop="bannerIndex = i"
              />
            </div>
          </div>
        </div>

        <div id="goods" class="goods-head">
          <h2>{{ currentCatName }}</h2>
          <p class="hint">共 {{ list.length }} 件</p>
        </div>

        <div v-if="loading" class="empty">商品加载中…</div>
        <div v-else-if="error" class="empty empty-card error">
          <div class="empty-title">加载失败</div>
          <p class="hint">{{ error }}</p>
          <button class="btn primary" type="button" @click="load">重试</button>
        </div>
        <div v-else-if="!list.length" class="empty empty-card">
          <div class="empty-title">该分类暂无商品</div>
          <p class="hint">换个分类看看，或清除筛选。</p>
          <button class="btn ghost" type="button" @click="selectCat(null)">查看全部</button>
        </div>
        <div v-else class="product-grid">
          <article
            v-for="p in list"
            :key="p.id"
            class="product-card"
            @click="$router.push(`/product/${p.id}`)"
          >
            <div class="thumb">
              <img
                v-if="hasProductImage(p)"
                :src="imgUrl(p)"
                :alt="p.name"
                loading="lazy"
              />
              <img
                v-else
                class="thumb-ph-img"
                :src="placeholderForProduct(p)"
                :alt="(p.name || '商品') + ' 占位图'"
                loading="lazy"
              />
              <span v-if="Number(p.number || 0) <= 0" class="stock-badge out">缺货</span>
              <span v-else-if="!hasProductImage(p)" class="stock-badge muted">待传主图</span>
              <span v-else class="stock-badge">现货</span>
            </div>
            <div class="body">
              <h3 class="name">{{ p.name }}</h3>
              <p class="intro">{{ p.introduce || '店铺精选' }}</p>
              <div class="row">
                <span class="price">¥{{ formatPrice(p.price) }}</span>
                <span class="muted">库存 {{ p.number ?? 0 }}</span>
              </div>
              <button
                class="btn primary block"
                type="button"
                @click.stop="$router.push(`/product/${p.id}`)"
              >
                {{ Number(p.number || 0) > 0 ? '查看并购买' : '查看详情' }}
              </button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getCategories, getProducts } from '@/api'
import { mediaUrl } from '@/utils/shop'
import { hasProductImage, placeholderForProduct } from '@/utils/placeholders'

const list = ref([])
const hotList = ref([])
const categories = ref([])
const loading = ref(false)
const catLoading = ref(false)
const error = ref('')
const keyword = ref('')
const activeCid = ref(null)
const bannerIndex = ref(0)
const totalCount = ref(0)
let timer = null

const currentCatName = computed(() => {
  if (!activeCid.value) return '全部商品'
  const c = categories.value.find((x) => x.id === activeCid.value)
  return c?.name || '商品列表'
})

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
function imgUrl(p) {
  return mediaUrl(p.big_img || p.small_img)
}

async function loadCats() {
  catLoading.value = true
  try {
    const res = await getCategories()
    if (res.status === 200) categories.value = res.data || []
  } catch (_) {
    categories.value = []
  } finally {
    catLoading.value = false
  }
}

async function loadHot() {
  try {
    const res = await getProducts({ hot: 1, limit: 6 })
    if (res.status === 200) {
      let next = (res.data || []).slice(0, 6)
      if (!next.length) {
        const r2 = await getProducts({ limit: 5 })
        next = (r2.data || []).slice(0, 5)
      }
      const signature = (rows) => rows.map((p) => `${p.id}:${p.big_img || ''}:${p.small_img || ''}`).join('|')
      if (signature(next) !== signature(hotList.value)) {
        hotList.value = next
        bannerIndex.value = 0
      }
    }
  } catch (_) {
    hotList.value = []
  }
}

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const params = {}
    if (keyword.value.trim()) params.q = keyword.value.trim()
    if (activeCid.value) params.cid = activeCid.value
    const res = await getProducts(params)
    if (res.status !== 200) {
      error.value = res.msg || '加载失败'
      list.value = []
      return
    }
    list.value = res.data || []
    if (!activeCid.value && !keyword.value.trim()) {
      totalCount.value = list.value.length
    }
  } catch (e) {
    error.value = e.message || '无法连接服务器'
    list.value = []
  } finally {
    if (!silent) loading.value = false
  }
}

function selectCat(id) {
  activeCid.value = id
  keyword.value = ''
  load()
}

function nextBanner() {
  if (!hotList.value.length) return
  bannerIndex.value = (bannerIndex.value + 1) % hotList.value.length
}
function prevBanner() {
  if (!hotList.value.length) return
  bannerIndex.value = (bannerIndex.value - 1 + hotList.value.length) % hotList.value.length
}

function startAuto() {
  stopAuto()
  timer = setInterval(() => {
    if (hotList.value.length > 1) nextBanner()
  }, 4200)
}
function stopAuto() {
  if (timer) clearInterval(timer)
  timer = null
}

let syncTimer = null
let syncing = false
async function refreshCatalog() {
  if (syncing || document.visibilityState === 'hidden') return
  syncing = true
  try {
    await Promise.all([loadCats(), loadHot(), load({ silent: true })])
  } finally {
    syncing = false
  }
}
function startCatalogSync() {
  if (syncTimer) clearInterval(syncTimer)
  syncTimer = window.setInterval(refreshCatalog, 5000)
  window.addEventListener('focus', refreshCatalog)
  document.addEventListener('visibilitychange', refreshCatalog)
}
function stopCatalogSync() {
  if (syncTimer) clearInterval(syncTimer)
  syncTimer = null
  window.removeEventListener('focus', refreshCatalog)
  document.removeEventListener('visibilitychange', refreshCatalog)
}

onMounted(async () => {
  await Promise.all([loadCats(), loadHot(), load()])
  if (!totalCount.value) totalCount.value = list.value.length
  startAuto()
  startCatalogSync()
})
onUnmounted(() => {
  stopAuto()
  stopCatalogSync()
})
watch(hotList, () => {
  bannerIndex.value = 0
})
</script>

<style scoped>
.home-mall {
  width: 100%;
  max-width: 100%;
  margin: 0;
  box-sizing: border-box;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 10px;
}
.search-wrap {
  display: flex;
  gap: 8px;
  flex: 1;
  max-width: none;
}
.search-wrap input {
  flex: 1;
  height: 40px;
  border: 1px solid #e7e5e4;
  border-radius: 10px;
  padding: 0 12px;
}
.top-links {
  display: flex;
  gap: 14px;
  font-size: 13px;
}
.top-links a {
  color: #0f766e;
  font-weight: 600;
  text-decoration: none;
}

.mall-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}
.cat-aside {
  padding: 10px 0;
  position: sticky;
  top: 64px;
  max-height: calc(100vh - 80px);
  overflow: auto;
}
.cat-title {
  padding: 8px 16px 10px;
  font-weight: 800;
  font-size: 14px;
  color: #1c1917;
  border-bottom: 1px solid #f0ebe3;
  margin-bottom: 6px;
}
.cat-item {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 0;
  background: transparent;
  padding: 12px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #44403c;
  text-align: left;
}
.cat-item:hover {
  background: #f0fdfa;
  color: #0f766e;
}
.cat-item.active {
  background: linear-gradient(90deg, #ecfdf5, transparent);
  color: #0f766e;
  font-weight: 700;
  border-right: 3px solid #0f766e;
}
.cat-item em {
  font-style: normal;
  font-size: 12px;
  color: #a8a29e;
  background: #f5f5f4;
  padding: 1px 7px;
  border-radius: 999px;
}
.cat-empty {
  padding: 16px;
  font-size: 12px;
  color: #a8a29e;
  text-align: center;
}

.banner {
  padding: 0;
  overflow: hidden;
  margin-bottom: 14px;
}
.banner-stage {
  position: relative;
  height: clamp(240px, 28vw, 380px);
  min-height: 240px;
  overflow: hidden;
  border-radius: 14px;
}
.banner-track {
  display: flex;
  height: 100%;
  transition: transform 0.45s ease;
}
.banner-slide {
  min-width: 100%;
  height: 100%;
  position: relative;
  cursor: pointer;
  background: #1c1917;
}
.banner-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0.92;
}
.banner-mask {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 28px 24px 20px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  color: #fff;
}
.b-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  background: #f97316;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 8px;
}
.b-name {
  font-size: 22px;
  font-weight: 800;
  margin-bottom: 4px;
}
.b-price {
  font-size: 20px;
  font-weight: 800;
  color: #fdba74;
}
.b-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
  color: #1c1917;
}
.b-nav.prev {
  left: 10px;
}
.b-nav.next {
  right: 10px;
}
.b-dots {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 10px;
  display: flex;
  justify-content: center;
  gap: 6px;
  z-index: 2;
}
.b-dots button {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 0;
  background: rgba(255, 255, 255, 0.45);
  cursor: pointer;
}
.b-dots button.on {
  background: #fff;
  width: 18px;
  border-radius: 999px;
}

.goods-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 4px 0 12px;
}
.goods-head h2 {
  margin: 0;
  font-size: 18px;
}
.hint {
  margin: 0;
  color: #a8a29e;
  font-size: 13px;
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
.product-card {
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--line, #e8e0d4);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
}
.product-card:hover {
  box-shadow: 0 10px 28px rgba(28, 25, 23, 0.08);
  transform: translateY(-2px);
}
.thumb {
  position: relative;
  aspect-ratio: 1;
  background: #f5f2ec;
}
.thumb img,
.thumb-ph-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.stock-badge {
  position: absolute;
  left: 8px;
  top: 8px;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.92);
  color: #fff;
}
.stock-badge.out {
  background: rgba(120, 113, 108, 0.9);
}
.stock-badge.muted {
  background: rgba(180, 83, 9, 0.9);
}
.body {
  padding: 10px 12px 12px;
}
.name {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 700;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.intro {
  margin: 0 0 8px;
  font-size: 12px;
  color: #a8a29e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.price {
  color: #c2410c;
  font-weight: 800;
  font-size: 16px;
}
.muted {
  font-size: 12px;
  color: #a8a29e;
}

.empty-card {
  padding: 36px 16px;
  text-align: center;
}
.empty-title {
  font-weight: 800;
  margin-bottom: 8px;
}
.empty-card .hint {
  max-width: 280px;
  margin: 0 auto 14px;
}

@media (max-width: 860px) {
  .mall-layout {
    grid-template-columns: 1fr;
  }
  .cat-aside {
    position: static;
    max-height: none;
    display: flex;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding: 8px;
    gap: 6px;
  }
  .cat-title {
    display: none;
  }
  .cat-item {
    width: auto;
    flex: 0 0 auto;
    border: 1px solid #e7e5e4;
    border-radius: 999px;
    padding: 6px 12px;
  }
  .cat-item.active {
    border-color: #0f766e;
    border-right-width: 1px;
  }
  .banner-stage {
    height: 200px;
    min-height: 200px;
  }
  .b-name {
    font-size: 16px;
  }
  .top-bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
