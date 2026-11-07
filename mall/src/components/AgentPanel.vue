<template>
  <div class="agent-panel" :class="variant">
    <div v-if="showHead" class="head">
      <h2>导购客服</h2>
      <p class="sub">选品、付款、查单都可以问。点「立即购买」会打开确认弹窗；助手不会改库存或标记已付款。</p>
    </div>

    <div class="chat" ref="boxRef">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">
          <div class="who">{{ messageAuthor(m.role) }}</div>
          <pre class="text">{{ m.text }}</pre>
          <div v-if="variant === 'page' && m.agents && m.agents.length" class="agents">协作：{{ m.agents.join(' → ') }}</div>

          <div v-if="m.citations && m.citations.length" class="citations">
            <div class="citation-label">回答依据</div>
            <ul>
              <li v-for="citation in m.citations.slice(0, 3)" :key="citation.id">
                <strong>{{ citation.id }}</strong>
                <span>{{ citation.title }}</span>
                <small>{{ citation.source }}</small>
              </li>
            </ul>
          </div>

          <div v-if="m.products && m.products.length" class="products">
            <div v-for="p in m.products" :key="p.id" class="p-card">
              <button type="button" class="p-main" @click="go('/product/' + p.id)">
                <div class="pn">{{ p.name }}</div>
                <div class="pp">¥{{ Number(p.price).toFixed(2) }}</div>
              </button>
              <button
                v-if="isInStock(p)"
                type="button"
                class="btn primary p-buy"
                @click="go('/product/' + p.id + '?buy=1')"
              >立即购买</button>
            </div>
            <div class="products-note">价格和库存以商品详情页为准</div>
          </div>

          <div v-if="m.needHuman" class="human">已转人工客服核对</div>

          <button
            v-if="m.loginRequired && !hasActionType(m, 'login')"
            type="button"
            class="btn primary draft-btn"
            @click="go('/login?redirect=/orders')"
          >去登录</button>

          <div v-if="visibleActions(m).length" class="acts">
            <button
              v-for="(a, j) in visibleActions(m)"
              :key="j"
              type="button"
              class="act"
              :class="a.type"
              @click="onAction(a)"
            >{{ a.label }}</button>
          </div>

          <button
            v-if="showDraft(m)"
            type="button"
            class="btn primary draft-btn"
            @click="go(m.draft.path)"
          >立即购买：{{ m.draft.name }}</button>
        </div>
      </div>
    </div>

    <div v-if="supportStateText" class="support-state" :class="supportState.status">
      <span class="state-dot"></span>
      <span>{{ supportStateText }}</span>
    </div>

    <div v-if="showRating" class="rating">
      <span>{{ ratedScore ? '感谢评价' : '请为本次人工服务评分' }}</span>
      <div class="rating-buttons" role="group" aria-label="人工服务评分">
        <button
          v-for="score in 5"
          :key="score"
          type="button"
          :class="{ selected: ratedScore === score }"
          :disabled="ratingSubmitting || !!ratedScore"
          :aria-label="`${score} 分`"
          @click="submitRating(score)"
        >{{ score }}</button>
      </div>
    </div>

    <div v-if="supportState?.status !== 'active'" class="suggest">
      <button v-for="s in suggests" :key="s" type="button" @click="send(s)">{{ s }}</button>
    </div>

    <form class="composer" @submit.prevent="send()">
      <input v-model="input" :placeholder="placeholder" maxlength="200" />
      <button class="btn primary" type="submit" :disabled="loading || !input.trim()">
        {{ loading ? '协作中…' : '发送' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { agentChat, getSupportMessages, rateSupportSession } from '@/api'
import { loadShop } from '@/utils/shop'

const props = defineProps({
  variant: { type: String, default: 'page' },
  showHead: { type: Boolean, default: true },
})
const emit = defineEmits(['navigate'])

const router = useRouter()
const input = ref('')
const loading = ref(false)
const boxRef = ref(null)
const supportState = ref(null)
const supportSessionId = ref('')
const lastSupportMessageId = ref(0)
const ratingSubmitting = ref(false)
const ratedScore = ref(null)
let supportTimer = null
let historyRequest = null
let disposed = false
let pendingSequence = 0
let contextVersion = 0
const welcomeMessages = () => [
  {
    role: 'assistant',
    text: '你好，我是店里的导购客服，可以帮你：\n· 有什么货\n· 怎么付钱\n· 我的单到哪了\n· 转店长',
    agents: ['orchestrator'],
  },
]
const messages = ref(welcomeMessages())
const suggests = ref(['有什么货', '怎么付钱', '我的单到哪了', '转店长'])
const placeholder = '例如：有什么货 / 怎么付钱 / 我的单到哪了'
const supportStateText = computed(() => ({
  waiting: '已进入人工客服队列，请稍候',
  active: '人工客服已接入',
  resolved: '本次人工服务已结束',
})[supportState.value?.status] || '')
const showRating = computed(() => supportState.value?.status === 'resolved')

function messageAuthor(role) {
  return ({ user: '我', assistant: 'AI 助手', staff: '人工客服', system: '服务通知' })[role] || '助手'
}

function isInStock(p) {
  if (!p) return false
  if (p.in_stock === false) return false
  if (p.in_stock === true) return true
  return Number(p.stock || p.number || 0) > 0
}

function hasActionType(m, type) {
  return (m.actions || []).some((a) => a && a.type === type)
}

function visibleActions(m) {
  const acts = m.actions || []
  const pids = new Set((m.products || []).map((p) => p.id))
  return acts.filter((a) => {
    if (!a) return false
    if (a.type === 'buy' && pids.size && a.product_id && pids.has(a.product_id)) return false
    return true
  })
}

function showDraft(m) {
  return !!(m.draft && m.draft.path && !(m.products && m.products.length))
}

function go(path) {
  if (!path) return
  const s = String(path)
  if (s.startsWith('tel:')) {
    window.location.href = s
    return
  }
  router.push(s)
  emit('navigate')
}

function onAction(a) {
  if (!a || !a.path) return
  go(a.path)
}

async function send(text) {
  const t = (text ?? input.value).trim()
  if (!t || loading.value) return
  input.value = ''
  const pendingId = ++pendingSequence
  const requestContext = contextVersion
  messages.value.push({ role: 'user', text: t, pendingId })
  loading.value = true
  await scrollBottom()
  try {
    const res = await agentChat(t)
    if (disposed || requestContext !== contextVersion || res?.stale) return
    if (!res || res.status !== 200) {
      messages.value.push({ role: 'system', text: (res && res.msg) || '服务暂不可用，请检查会话后重试。' })
    } else {
      const d = res.data || {}
      const reply = {
        role: 'assistant',
        text: d.reply || '好的',
        agents: d.agents_ran || [],
        products: d.products || [],
        citations: d.citations || [],
        needHuman: !!d.need_human,
        draft: d.draft_order_hint || null,
        actions: d.actions || [],
        loginRequired: !!d.login_required,
      }
      if (d.suggested_replies && d.suggested_replies.length) {
        suggests.value = d.suggested_replies
      }
      if (d.session_id) supportSessionId.value = d.session_id
      if (d.customer_message_id) {
        messages.value = messages.value.filter((item) => item.pendingId !== pendingId)
        mergeSupportMessage({ id: d.customer_message_id, sender_type: 'customer', content: t })
      }
      if (d.ai_message_id) {
        mergeSupportMessage({ id: d.ai_message_id, sender_type: 'ai', content: reply.text }, reply)
      } else if (!d.customer_message_id) {
        messages.value.push(reply)
      }
      if (d.session_id) {
        if (historyRequest) await historyRequest.catch(() => {})
        await pollSupportMessages()
      }
      else if (d.support) updateSupportState(d.support)
    }
  } catch (e) {
    if (disposed || requestContext !== contextVersion) return
    messages.value.push({ role: 'system', text: '连接中断，消息是否送达尚未确认，请检查会话后再重试。' })
  } finally {
    if (!disposed && requestContext === contextVersion) {
      loading.value = false
      await scrollBottom()
    }
  }
}

function updateSupportState(state) {
  supportState.value = state || null
  if (state?.satisfaction) ratedScore.value = Number(state.satisfaction)
  if (['waiting', 'active'].includes(state?.status)) startSupportPolling()
  else stopSupportPolling()
}

function startSupportPolling() {
  if (supportTimer || !supportSessionId.value) return
  pollSupportMessages()
  supportTimer = window.setInterval(pollSupportMessages, 4000)
}

function stopSupportPolling() {
  if (!supportTimer) return
  window.clearInterval(supportTimer)
  supportTimer = null
}

async function pollSupportMessages() {
  if (!supportSessionId.value) return
  if (historyRequest) {
    try { await historyRequest } catch (_) {}
    return
  }
  const sessionId = supportSessionId.value
  const request = syncSupportMessages(sessionId, contextVersion)
  historyRequest = request
  try {
    await request
  } catch (_) {
    // 轮询失败不打断顾客输入，下一轮会自动重试。
  } finally {
    if (historyRequest === request) historyRequest = null
  }
}

function mergeSupportMessage(item, details = {}) {
  const id = Number(item.id)
  if (!id) return
  const extra = item.extra || {}
  const replay = item.sender_type === 'ai' && Array.isArray(extra.products) ? {
    products: extra.products,
    draft: extra.draft_order_hint || null,
    actions: extra.actions || [],
    loginRequired: !!extra.login_required,
    agents: extra.agents_ran || [],
    needHuman: !!extra.need_human,
    replayFresh: true,
  } : {}
  const existing = messages.value.find((message) => message.id === id)
  if (existing) {
    const current = existing.replayFresh && !replay.replayFresh ? {
      products: existing.products,
      draft: existing.draft,
      actions: existing.actions,
      loginRequired: existing.loginRequired,
    } : {}
    Object.assign(existing, details, replay, current)
    return
  }
  const message = {
    id,
    role: item.sender_type === 'customer' ? 'user' : item.sender_type === 'ai' ? 'assistant' : item.sender_type,
    text: item.content,
    citations: item.extra?.citations || [],
    ...details,
    ...replay,
  }
  const next = messages.value.findIndex((entry) => entry.id && entry.id > id)
  if (next < 0) {
    const pending = messages.value.findIndex((entry) => entry.pendingId)
    if (pending < 0) messages.value.push(message)
    else messages.value.splice(pending, 0, message)
  } else messages.value.splice(next, 0, message)
}

async function syncSupportMessages(sessionId, requestContext) {
  let more = true
  while (more && !disposed && requestContext === contextVersion && supportSessionId.value === sessionId) {
    const response = await getSupportMessages(sessionId, lastSupportMessageId.value)
    if (disposed || requestContext !== contextVersion || supportSessionId.value !== sessionId || response?.status !== 200) return
    const data = response.data || {}
    const items = data.messages || []
    for (const item of items) {
      mergeSupportMessage(item)
      lastSupportMessageId.value = Math.max(lastSupportMessageId.value, Number(item.id) || 0)
    }
    updateSupportState(data.conversation)
    more = !!data.has_more && items.length > 0
  }
  await scrollBottom()
}

async function submitRating(score) {
  if (!supportSessionId.value || ratingSubmitting.value || ratedScore.value) return
  const requestContext = contextVersion
  ratingSubmitting.value = true
  try {
    const response = await rateSupportSession(supportSessionId.value, score)
    if (disposed || requestContext !== contextVersion) return
    if (response?.status !== 200) throw new Error(response?.msg || '评价提交失败')
    ratedScore.value = score
    updateSupportState(response.data)
  } catch (error) {
    if (disposed || requestContext !== contextVersion) return
    messages.value.push({ role: 'system', text: error.message || '评价提交失败，请稍后重试' })
  } finally {
    if (!disposed && requestContext === contextVersion) {
      ratingSubmitting.value = false
      await scrollBottom()
    }
  }
}

function resetConversationContext() {
  contextVersion += 1
  stopSupportPolling()
  historyRequest = null
  supportState.value = null
  lastSupportMessageId.value = 0
  ratedScore.value = null
  ratingSubmitting.value = false
  loading.value = false
  input.value = ''
  messages.value = welcomeMessages()
  try { supportSessionId.value = localStorage.getItem('agent_session_id') || '' } catch (_) { supportSessionId.value = '' }
  if (supportSessionId.value) pollSupportMessages()
}

async function scrollBottom() {
  await nextTick()
  if (boxRef.value) boxRef.value.scrollTop = boxRef.value.scrollHeight
}

onMounted(() => {
  window.addEventListener('mall:auth-change', resetConversationContext)
  loadShop()
  try { supportSessionId.value = localStorage.getItem('agent_session_id') || '' } catch (_) {}
  if (supportSessionId.value) pollSupportMessages()
})

onBeforeUnmount(() => {
  disposed = true
  stopSupportPolling()
  window.removeEventListener('mall:auth-change', resetConversationContext)
})
</script>

<style scoped>
.agent-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
.agent-panel.page {
  max-width: 720px;
  margin: 0 auto;
  min-height: 70vh;
  width: 100%;
}
.head h2 { margin: 0 0 4px; font-size: 22px; }
.sub { margin: 0 0 12px; color: #78716c; font-size: 13px; line-height: 1.5; }
.chat {
  flex: 1;
  background: #fff;
  border: 1px solid #eee7de;
  border-radius: 16px;
  padding: 14px;
  overflow-y: auto;
  min-height: 180px;
}
.page .chat { max-height: 52vh; }
.compact .chat {
  border: 0;
  border-radius: 0;
  padding: 10px;
  background: #fafaf9;
}
.msg { display: flex; margin: 10px 0; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 88%;
  background: #f8fafc;
  border-radius: 14px;
  padding: 10px 12px;
  border: 1px solid #eef2f7;
}
.msg.user .bubble {
  background: #ecfdf5;
  border-color: #a7f3d0;
}
.who {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 4px;
  font-weight: 700;
}
.text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.55;
  color: #1f2937;
}
.compact .text { font-size: 13px; }
.agents { margin-top: 8px; font-size: 11px; color: #64748b; }
.citations { margin-top: 9px; padding-top: 8px; border-top: 1px solid #e7e5e4; color: #57534e; }
.citation-label { margin-bottom: 4px; font-size: 11px; font-weight: 700; color: #78716c; }
.citations ul { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.citations li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 6px; align-items: baseline; font-size: 12px; line-height: 1.35; }
.citations strong { color: #0f766e; font-size: 11px; }
.citations span { min-width: 0; overflow-wrap: anywhere; }
.citations small { grid-column: 2; color: #a8a29e; font-size: 10px; }
.human { margin-top: 8px; font-size: 12px; color: #c2410c; font-weight: 700; }
.support-state {
  display: flex; align-items: center; gap: 8px; min-height: 34px; margin: 10px 0 8px; padding: 7px 10px;
  border: 1px solid #fed7aa; background: #fff7ed; color: #9a3412; font-size: 12.5px; font-weight: 650;
}
.compact .support-state { margin: 8px; }
.support-state.active { border-color: #99f6e4; background: #ecfdf5; color: #0f766e; }
.support-state.resolved { border-color: #d6d3d1; background: #f5f5f4; color: #57534e; }
.state-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.rating {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px;
  border: 1px solid #e7e5e4; background: #fff; color: #57534e; font-size: 12.5px;
}
.compact .rating { margin: 0 8px 8px; }
.rating-buttons { display: flex; gap: 5px; }
.rating-buttons button {
  width: 30px; height: 30px; border: 1px solid #d6d3d1; border-radius: 50%; background: #fff; color: #44403c;
  cursor: pointer; font-weight: 700;
}
.rating-buttons button:hover:not(:disabled), .rating-buttons button.selected { border-color: #0f766e; background: #0f766e; color: #fff; }
.rating-buttons button:disabled { cursor: default; opacity: .72; }
.products { display: grid; gap: 8px; margin-top: 10px; }
.products-note { font-size: 12px; color: #57534e; }
.p-card {
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.p-main {
  text-align: left;
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
}
.pn { font-weight: 700; font-size: 13px; color: #1f2937; }
.pp { color: #c2410c; font-weight: 800; margin-top: 2px; }
.p-buy { min-height: 34px; width: 100%; border-radius: 10px; }
.acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.act {
  border: 1px solid #d6d3d1;
  background: #fff;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
  font-weight: 600;
  color: #1f2937;
}
.act.buy, .act.login, .act.ops_queue { border-color: #99f6e4; background: #ecfdf5; color: #0f766e; }
.act.human { border-color: #fed7aa; background: #fff7ed; color: #c2410c; }
.suggest { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 8px; }
.compact .suggest { margin: 8px; }
.suggest button {
  border: 1px solid #e7e5e4;
  background: #fff;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
}
.composer { display: flex; gap: 8px; }
.compact .composer { padding: 0 8px 8px; }
.draft-btn { margin-top: 10px; width: 100%; min-height: 40px; }
.composer input {
  flex: 1;
  height: 44px;
  border-radius: 12px;
  border: 1px solid #e7e5e4;
  padding: 0 12px;
}
.compact .composer input { height: 40px; }
</style>
