<template>
  <section class="service-shell" :class="{ 'mobile-detail': isMobile && mobilePane === 'detail' }">
    <aside class="queue-pane">
      <div class="queue-head">
        <div>
          <h1>客服工作台</h1>
          <p>{{ onlineSummary }}</p>
        </div>
        <el-button :icon="Refresh" circle :loading="loadingInbox" title="刷新会话" @click="refreshAll(false)" />
      </div>

      <el-tabs v-model="statusFilter" class="queue-tabs" stretch @tab-change="changeFilter">
        <el-tab-pane name="waiting">
          <template #label>待接待 <span class="tab-count">{{ counts.waiting || 0 }}</span></template>
        </el-tab-pane>
        <el-tab-pane name="active">
          <template #label>处理中 <span class="tab-count">{{ counts.active || 0 }}</span></template>
        </el-tab-pane>
        <el-tab-pane name="all">
          <template #label>全部 <span class="tab-count">{{ totalCount }}</span></template>
        </el-tab-pane>
      </el-tabs>

      <el-input
        v-model="query"
        clearable
        :prefix-icon="Search"
        placeholder="搜索顾客、主题或会话号"
        @keyup.enter="loadInbox(false)"
        @clear="loadInbox(false)"
      />

      <div v-loading="loadingInbox && !conversations.length" class="queue-list">
        <button
          v-for="item in conversations"
          :key="item.id"
          type="button"
          class="queue-item"
          :class="{ active: selectedId === item.id }"
          @click="selectConversation(item.id)"
        >
          <span class="avatar">{{ customerInitial(item) }}</span>
          <span class="queue-copy">
            <span class="queue-row">
              <strong>{{ customerName(item) }}</strong>
              <time>{{ compactTime(item.update_time) }}</time>
            </span>
            <span class="queue-row meta-row">
              <span>{{ item.subject || intentLabel(item.intent) }}</span>
              <el-tag v-if="item.priority !== 'normal'" :type="priorityType(item.priority)" size="small" effect="plain">
                {{ priorityLabel(item.priority) }}
              </el-tag>
            </span>
            <span class="preview">{{ item.last_message || '暂无消息' }}</span>
            <span v-if="item.status === 'waiting'" class="waiting-time">等待 {{ item.waiting_minutes || 0 }} 分钟</span>
          </span>
        </button>

        <el-empty v-if="!loadingInbox && !conversations.length" :image-size="72" description="当前没有会话" />
      </div>
    </aside>

    <main class="conversation-pane">
      <template v-if="detail.conversation">
        <header class="conversation-head">
          <div class="conversation-title">
            <el-button v-if="isMobile" :icon="ArrowLeft" text title="返回会话列表" @click="mobilePane = 'list'" />
            <span class="avatar large">{{ customerInitial(detail.conversation) }}</span>
            <div>
              <strong>{{ customerName(detail.conversation) }}</strong>
              <span>{{ statusLabel(detail.conversation.status) }} · {{ detail.conversation.session_id }}</span>
            </div>
          </div>
          <div class="conversation-actions">
            <el-button
              v-if="canClaim"
              type="primary"
              :loading="acting === 'claim'"
              @click="claimConversation"
            >接入会话</el-button>
            <el-button
              v-if="detail.conversation.status === 'active'"
              :icon="CircleCheck"
              :loading="acting === 'resolve'"
              @click="resolveConversation"
            >结束服务</el-button>
          </div>
        </header>

        <div ref="timelineRef" v-loading="loadingDetail" class="timeline">
          <div v-for="message in detail.messages" :key="message.id" class="message" :class="message.sender_type">
            <span class="message-who">{{ senderLabel(message.sender_type) }}</span>
            <div class="message-bubble">{{ message.content }}</div>
            <time>{{ fullTime(message.create_time) }}</time>
          </div>
          <el-empty v-if="!loadingDetail && !detail.messages.length" :image-size="72" description="暂无消息" />
        </div>

        <footer class="composer-wrap">
          <el-alert
            v-if="detail.conversation.status === 'waiting'"
            type="warning"
            :closable="false"
            show-icon
            title="接入后即可回复顾客"
          />
          <el-alert
            v-else-if="detail.conversation.status === 'resolved'"
            type="success"
            :closable="false"
            show-icon
            title="本次服务已结束"
          />
          <template v-else>
            <el-input
              v-model="replyText"
              type="textarea"
              resize="none"
              :rows="3"
              maxlength="1000"
              show-word-limit
              placeholder="输入回复内容"
              @keydown.ctrl.enter.prevent="sendReply"
              @keydown.meta.enter.prevent="sendReply"
            />
            <div class="composer-foot">
              <el-button type="primary" :icon="Promotion" :loading="acting === 'reply'" :disabled="!replyText.trim()" @click="sendReply">
                发送
              </el-button>
            </div>
          </template>
        </footer>
      </template>

      <el-empty v-else :image-size="96" description="选择一条会话开始处理" />
    </main>

    <aside v-if="detail.conversation" class="profile-pane">
      <section class="profile-section">
        <h2>顾客信息</h2>
        <dl>
          <dt>昵称</dt><dd>{{ customerName(detail.conversation) }}</dd>
          <dt>手机号</dt><dd>{{ detail.conversation.customer?.phone || '未登录顾客' }}</dd>
          <dt>会话来源</dt><dd>商城在线客服</dd>
          <dt>消息数</dt><dd>{{ detail.conversation.message_count || 0 }} 条</dd>
        </dl>
      </section>

      <section class="profile-section">
        <h2>会话处理</h2>
        <dl>
          <dt>识别意图</dt><dd>{{ intentLabel(detail.conversation.intent) }}</dd>
          <dt>当前客服</dt><dd>{{ assigneeName }}</dd>
          <dt>顾客评价</dt><dd>{{ satisfactionText }}</dd>
        </dl>
        <label class="field-label" for="support-priority">优先级</label>
        <el-select id="support-priority" v-model="priority" :disabled="acting === 'priority'" @change="updatePriority">
          <el-option label="普通" value="normal" />
          <el-option label="高" value="high" />
          <el-option label="紧急" value="urgent" />
        </el-select>
      </section>

      <section class="profile-section orders-section">
        <h2>最近订单</h2>
        <div v-if="detail.orders.length" class="order-list">
          <div v-for="order in detail.orders" :key="order.id" class="order-row">
            <span><strong>{{ order.order_no }}</strong><small>{{ orderStatus(order.status) }}</small></span>
            <b>¥{{ Number(order.price || 0).toFixed(2) }}</b>
          </div>
        </div>
        <el-empty v-else :image-size="56" description="暂无关联订单" />
      </section>
    </aside>
  </section>
</template>

<script setup>
import { ArrowLeft, CircleCheck, Promotion, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import api from '@/api'

const conversations = ref([])
const counts = reactive({ bot: 0, waiting: 0, active: 0, resolved: 0 })
const detail = reactive({ conversation: null, messages: [], orders: [] })
const statusFilter = ref('waiting')
const query = ref('')
const selectedId = ref(null)
const loadingInbox = ref(false)
const loadingDetail = ref(false)
const acting = ref('')
const replyText = ref('')
const priority = ref('normal')
const satisfactionAverage = ref(null)
const timelineRef = ref(null)
const isMobile = ref(false)
const mobilePane = ref('list')
let pollTimer = null

const currentUser = (() => {
  try { return JSON.parse(sessionStorage.getItem('user') || '{}') || {} } catch (_) { return {} }
})()
const totalCount = computed(() => Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0))
const onlineSummary = computed(() => {
  const rating = satisfactionAverage.value == null ? '暂无评分' : `满意度 ${satisfactionAverage.value}/5`
  return `${counts.waiting || 0} 条待接待 · ${rating}`
})
const canClaim = computed(() => {
  const row = detail.conversation
  return row && row.status === 'waiting' && (!row.assignee_id || Number(row.assignee_id) === Number(currentUser.id))
})
const assigneeName = computed(() => {
  const user = detail.conversation?.assignee
  return user?.nick_name || user?.name || (detail.conversation?.status === 'waiting' ? '待分配' : 'AI 客服')
})
const satisfactionText = computed(() => {
  const value = detail.conversation?.satisfaction
  return value ? `${value} / 5` : '未评价'
})

function responseBody(response) {
  return response?.data?.status != null ? response.data : response
}

async function loadInbox(quiet = true) {
  if (loadingInbox.value) return
  loadingInbox.value = true
  try {
    const body = responseBody(await api.support_inbox({ status: statusFilter.value, q: query.value.trim() }))
    if (body.status !== 200) throw new Error(body.msg || '会话列表加载失败')
    conversations.value = body.data?.items || []
    Object.assign(counts, body.data?.counts || {})
    satisfactionAverage.value = body.data?.satisfaction ?? null
    if (!selectedId.value && conversations.value.length && !isMobile.value) {
      await selectConversation(conversations.value[0].id, false)
    }
  } catch (error) {
    if (!quiet) ElMessage.error(error.message || '会话列表加载失败')
  } finally {
    loadingInbox.value = false
  }
}

async function loadDetail(id = selectedId.value, quiet = true) {
  if (!id || loadingDetail.value) return
  loadingDetail.value = true
  const previousMessageId = detail.messages[detail.messages.length - 1]?.id
  try {
    const body = responseBody(await api.support_conversation(id))
    if (body.status !== 200) throw new Error(body.msg || '会话加载失败')
    detail.conversation = body.data?.conversation || null
    detail.messages = body.data?.messages || []
    detail.orders = body.data?.orders || []
    priority.value = detail.conversation?.priority || 'normal'
    const nextMessageId = detail.messages[detail.messages.length - 1]?.id
    if (nextMessageId !== previousMessageId) await scrollToBottom()
  } catch (error) {
    if (!quiet) ElMessage.error(error.message || '会话加载失败')
  } finally {
    loadingDetail.value = false
  }
}

async function selectConversation(id, switchPane = true) {
  selectedId.value = id
  if (isMobile.value && switchPane) mobilePane.value = 'detail'
  await loadDetail(id, false)
}

async function refreshAll(quiet = true) {
  await loadInbox(quiet)
  if (selectedId.value) await loadDetail(selectedId.value, quiet)
}

async function changeFilter() {
  selectedId.value = null
  detail.conversation = null
  detail.messages = []
  detail.orders = []
  await loadInbox(false)
}

async function perform(action, call, successText) {
  acting.value = action
  try {
    const body = responseBody(await call())
    if (body.status !== 200) throw new Error(body.msg || '操作失败')
    ElMessage.success(successText || body.msg)
    await refreshAll(true)
    return true
  } catch (error) {
    ElMessage.error(error.message || '操作失败')
    await refreshAll(true)
    return false
  } finally {
    acting.value = ''
  }
}

function claimConversation() {
  return perform('claim', () => api.support_claim(selectedId.value), '已接入会话')
}

async function sendReply() {
  const content = replyText.value.trim()
  if (!content || acting.value) return
  const sent = await perform('reply', () => api.support_reply(selectedId.value, content), '回复已发送')
  if (sent) replyText.value = ''
}

async function resolveConversation() {
  try {
    await ElMessageBox.confirm('结束后顾客可以评价本次服务。', '结束本次服务', {
      confirmButtonText: '确认结束',
      cancelButtonText: '继续服务',
      type: 'warning',
    })
  } catch (_) {
    return
  }
  await perform('resolve', () => api.support_resolve(selectedId.value), '服务已结束')
}

async function updatePriority(value) {
  await perform('priority', () => api.support_priority(selectedId.value, value), '优先级已更新')
}

function syncViewport() {
  isMobile.value = window.innerWidth <= 900
  if (!isMobile.value) mobilePane.value = 'list'
}

async function scrollToBottom() {
  await nextTick()
  if (timelineRef.value) timelineRef.value.scrollTop = timelineRef.value.scrollHeight
}

function customerName(row) { return row?.customer?.nickname || (row?.customer_id ? `顾客 #${row.customer_id}` : '访客') }
function customerInitial(row) { return customerName(row).slice(0, 1).toUpperCase() }
function intentLabel(value) {
  const labels = { cs: '人工咨询', refund: '退款售后', order: '订单查询', catalog: '商品咨询', promo: '优惠咨询', risk: '风险咨询' }
  return labels[value] || value || '一般咨询'
}
function statusLabel(value) { return ({ bot: 'AI 接待中', waiting: '等待人工', active: '人工服务中', resolved: '服务已结束' })[value] || value }
function priorityLabel(value) { return ({ normal: '普通', high: '高', urgent: '紧急' })[value] || value }
function priorityType(value) { return value === 'urgent' ? 'danger' : 'warning' }
function senderLabel(value) { return ({ customer: '顾客', ai: 'AI 客服', staff: '人工客服', system: '系统' })[value] || value }
function orderStatus(value) { return ({ pending_pay: '待付款', paid: '已付款', shipped: '已发货', completed: '已完成', cancelled: '已取消', refund_pending: '退款中', refunded: '已退款' })[value] || value }
function compactTime(value) {
  if (!value) return ''
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
function fullTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  syncViewport()
  window.addEventListener('resize', syncViewport)
  await loadInbox(false)
  pollTimer = window.setInterval(() => refreshAll(true), 5000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewport)
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.service-shell {
  display: grid;
  grid-template-columns: 300px minmax(420px, 1fr) 280px;
  min-height: 620px;
  height: calc(100vh - 88px);
  background: #fff;
  border: 1px solid #e3ded5;
  overflow: hidden;
}
.queue-pane, .profile-pane { min-width: 0; background: #fbfaf8; }
.queue-pane { display: flex; flex-direction: column; padding: 16px 14px 0; border-right: 1px solid #e8e4dc; }
.queue-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.queue-head h1 { margin: 0; font-size: 18px; line-height: 1.3; color: #191714; letter-spacing: 0; }
.queue-head p { margin: 4px 0 0; color: #79736a; font-size: 12px; }
.queue-tabs { margin-top: 12px; }
.queue-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.tab-count { margin-left: 3px; color: #8b857c; font-size: 11px; }
.queue-list { flex: 1; min-height: 0; overflow-y: auto; margin: 10px -14px 0; }
.queue-item {
  width: 100%; display: flex; gap: 10px; padding: 13px 14px; border: 0; border-bottom: 1px solid #eeeae3;
  background: transparent; text-align: left; cursor: pointer; color: inherit;
}
.queue-item:hover { background: #f4f1eb; }
.queue-item.active { background: #e8f3f0; box-shadow: inset 3px 0 #0f766e; }
.avatar {
  flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  background: #dceee9; color: #0f665f; font-weight: 700; font-size: 13px;
}
.avatar.large { width: 38px; height: 38px; }
.queue-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.queue-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.queue-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.queue-row time { flex: 0 0 auto; color: #918b82; font-size: 11px; }
.meta-row { color: #6d675e; font-size: 12px; }
.meta-row > span:first-child, .preview { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview { display: block; color: #8a847b; font-size: 12px; }
.waiting-time { color: #b45309; font-size: 11px; font-weight: 600; }
.conversation-pane { min-width: 0; min-height: 0; height: 100%; overflow: hidden; display: flex; flex-direction: column; background: #fff; }
.conversation-head { min-height: 68px; padding: 10px 16px; border-bottom: 1px solid #e8e4dc; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.conversation-title { min-width: 0; display: flex; align-items: center; gap: 10px; }
.conversation-title > div { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.conversation-title strong { font-size: 15px; color: #191714; }
.conversation-title span { color: #817b72; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conversation-actions { flex: 0 0 auto; display: flex; gap: 8px; }
.timeline { flex: 1; min-height: 0; overflow-y: auto; padding: 20px clamp(16px, 4vw, 52px); background: #f8f7f4; }
.message { max-width: 78%; margin: 0 0 18px; display: flex; flex-direction: column; align-items: flex-start; }
.message.customer { margin-left: auto; align-items: flex-end; }
.message.system { margin-left: auto; margin-right: auto; align-items: center; max-width: 100%; }
.message-who, .message time { margin: 0 4px 4px; color: #8a847b; font-size: 11px; }
.message time { margin-top: 4px; }
.message-bubble { padding: 10px 12px; border: 1px solid #e2ddd5; background: #fff; color: #292622; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.message.customer .message-bubble { background: #0f766e; border-color: #0f766e; color: #fff; }
.message.system .message-bubble { padding: 5px 10px; border: 0; background: #ebe8e1; color: #746e65; font-size: 12px; }
.composer-wrap { flex: 0 0 auto; min-height: 132px; padding: 12px 16px; border-top: 1px solid #e8e4dc; background: #fff; }
.composer-foot { display: flex; align-items: center; justify-content: flex-end; margin-top: 8px; }
.profile-pane { overflow-y: auto; border-left: 1px solid #e8e4dc; }
.profile-section { padding: 18px 16px; border-bottom: 1px solid #e8e4dc; }
.profile-section h2 { margin: 0 0 14px; font-size: 14px; color: #24211d; letter-spacing: 0; }
.profile-section dl { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 10px 8px; margin: 0; font-size: 12px; }
.profile-section dt { color: #8b857c; }
.profile-section dd { margin: 0; color: #3e3933; overflow-wrap: anywhere; }
.field-label { display: block; margin: 16px 0 6px; color: #8b857c; font-size: 12px; }
.profile-section :deep(.el-select) { width: 100%; }
.order-list { display: flex; flex-direction: column; gap: 10px; }
.order-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; font-size: 12px; }
.order-row span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.order-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.order-row small { color: #8b857c; }
.order-row b { flex: 0 0 auto; color: #b45309; }

@media (max-width: 1180px) {
  .service-shell { grid-template-columns: 280px minmax(380px, 1fr) 240px; }
}

@media (max-width: 900px) {
  .service-shell { display: block; height: calc(100vh - 74px); min-height: 520px; }
  .queue-pane, .conversation-pane { width: 100%; height: 100%; }
  .conversation-pane { display: none; }
  .profile-pane { display: none; }
  .service-shell.mobile-detail .queue-pane { display: none; }
  .service-shell.mobile-detail .conversation-pane { display: flex; }
  .conversation-head { padding: 8px 10px; }
  .conversation-actions .el-button { padding-left: 10px; padding-right: 10px; }
  .timeline { padding: 16px 12px; }
  .message { max-width: 88%; }
}
</style>
