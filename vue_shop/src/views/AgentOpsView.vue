<template>
  <div class="page-card ops-agent">
    <div class="head">
      <div>
        <h2>运营助手</h2>
        <p class="sub">可问经营待办；也可以说「上架纯棉T恤，89元，库存30」。不代替确认收款/发货。</p>
      </div>
      <el-button type="primary" @click="ask('今日经营情况')">一键经营速览</el-button>
    </div>
    <div class="chat" ref="box">
      <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
        <div class="bubble">
          <div class="who">{{ m.role === 'user' ? '我' : '运营 Agent' }}</div>
          <pre class="text">{{ m.text }}</pre>
          <div v-if="m.agents && m.agents.length" class="agents">{{ m.agents.join(' → ') }}</div>

          <div v-if="m.queues" class="queues">
            <div v-if="(m.queues.pending_pay || []).length" class="q-col">
              <div class="q-h">待确认收款</div>
              <button
                v-for="o in m.queues.pending_pay"
                :key="'pay-' + o.id"
                type="button"
                class="q-item"
                @click="go(o.path)"
              >{{ o.order_no }} · ¥{{ Number(o.price || 0).toFixed(2) }}</button>
            </div>
            <div v-if="(m.queues.pending_ship || []).length" class="q-col">
              <div class="q-h">待发货</div>
              <button
                v-for="o in m.queues.pending_ship"
                :key="'ship-' + o.id"
                type="button"
                class="q-item"
                @click="go(o.path)"
              >{{ o.order_no }} · ¥{{ Number(o.price || 0).toFixed(2) }}</button>
            </div>
            <div v-if="(m.queues.low_stock || []).length" class="q-col">
              <div class="q-h">低库存</div>
              <button
                v-for="p in m.queues.low_stock"
                :key="'sku-' + p.id"
                type="button"
                class="q-item"
                @click="go(p.path || '/product_list')"
              >{{ p.name }} · 库存{{ p.stock }}</button>
            </div>
          </div>

          <div v-if="m.actions && m.actions.length" class="acts">
            <el-button
              v-for="(a, j) in m.actions"
              :key="j"
              size="small"
              type="primary"
              plain
              @click="go(a.path)"
            >{{ a.label }}</el-button>
          </div>
        </div>
      </div>
    </div>
    <div class="suggest">
      <el-button v-for="s in suggests" :key="s" size="small" @click="ask(s)">{{ s }}</el-button>
    </div>
    <div class="composer">
      <el-input v-model="input" placeholder="例如：上架纯棉T恤，89元，库存30" @keyup.enter="ask()" />
      <el-button type="primary" :loading="loading" @click="ask()">发送</el-button>
    </div>
  </div>
</template>
<script setup>
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'

const router = useRouter()
const input = ref('')
const loading = ref(false)
const box = ref(null)
const messages = ref([{ role: 'assistant', text: '你好，我是后台运营助手。可问待付款、待发货、低库存等。点下方卡片可直接去处理。', agents: ['orchestrator'] }])
const suggests = ref(['今日经营情况', '待发货订单', '库存预警', '上架纯棉T恤，89元，库存30'])

function go(path) {
  if (!path) return
  router.push(path)
}

async function ask(text) {
  const t = (text ?? input.value).trim()
  if (!t || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', text: t })
  loading.value = true
  await scroll()
  try {
    const res = await api.agent_ops({ text: t })
    const body = res?.data?.status != null ? res.data : res
    if (body?.status !== 200) {
      ElMessage.warning(body?.msg || '请求失败')
      messages.value.push({ role: 'assistant', text: body?.msg || '失败' })
    } else {
      const d = body.data || {}
      const ops = d.ops || {}
      messages.value.push({
        role: 'assistant',
        text: d.reply || '好的',
        agents: d.agents_ran || [],
        queues: ops.queues || null,
        actions: d.actions || ops.actions || [],
      })
    }
  } catch (e) {
    const message = e?.userMessage || e?.response?.data?.msg || '运营助手请求失败'
    messages.value.push({ role: 'assistant', text: message })
    ElMessage.error(message)
  } finally {
    loading.value = false
    await scroll()
  }
}
async function scroll() {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
}
</script>
<style scoped>
.ops-agent { max-width: 860px; }
.head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; }
h2 { margin:0 0 4px; font-size:18px; }
.sub { margin:0; color:#8a8478; font-size:13px; }
.chat { height:420px; overflow:auto; border:1px solid #e8e4db; border-radius:12px; padding:12px; background:#fafaf8; }
.row { display:flex; margin:10px 0; }
.row.user { justify-content:flex-end; }
.bubble { max-width:80%; background:#fff; border:1px solid #eee; border-radius:12px; padding:10px 12px; }
.row.user .bubble { background:#ecfdf5; border-color:#a7f3d0; }
.who { font-size:11px; color:#9a958c; font-weight:700; margin-bottom:4px; }
.text { margin:0; white-space:pre-wrap; font-family:inherit; font-size:13.5px; line-height:1.55; }
.agents { margin-top:6px; font-size:11px; color:#7a756c; }
.queues { display:grid; gap:10px; margin-top:10px; }
.q-h { font-size:12px; font-weight:700; color:#57534e; margin-bottom:6px; }
.q-item {
  display:block; width:100%; text-align:left; margin-bottom:6px;
  border:1px solid #e7e5e4; background:#fafaf9; border-radius:8px;
  padding:8px 10px; cursor:pointer; font-size:13px;
}
.q-item:hover { border-color:#0f766e; background:#ecfdf5; }
.acts { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.suggest { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
.composer { display:flex; gap:8px; }
</style>
