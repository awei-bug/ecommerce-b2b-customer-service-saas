<template>
  <div class="page result-page">
    <div class="shell">
      <div class="top">
        <div class="badge">订单已提交</div>
        <h1>请完成付款</h1>
        <p class="lead">扫码转账后，店主确认到账就会发货</p>
      </div>

      <PayGuidePanel
        class="panel"
        :order-no="orderNo"
        :amount="amount"
      />

      <div class="actions">
        <button class="btn primary" type="button" @click="$router.replace('/orders')">我已付款，查看订单</button>
        <button class="btn ghost" type="button" @click="$router.replace('/')">返回首页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PayGuidePanel from '@/components/PayGuidePanel.vue'
import { loadShop } from '@/utils/shop'

const route = useRoute()
const orderNo = computed(() => String(route.query.order_no || ''))
const amount = computed(() => route.query.amount || '')

onMounted(() => {
  loadShop()
})
</script>

<style scoped>
.result-page {
  min-height: 70vh;
  padding: 20px 12px 40px;
  display: flex;
  justify-content: center;
}
.shell {
  width: min(440px, 100%);
}
.top {
  text-align: center;
  margin-bottom: 14px;
}
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #047857;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
h1 {
  margin: 0 0 6px;
  font-size: 24px;
  color: #1c1917;
}
.lead {
  margin: 0;
  color: #78716c;
  font-size: 14px;
}
.panel { margin-bottom: 16px; }
.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.actions .btn {
  width: 100%;
  min-height: 44px;
}
</style>
