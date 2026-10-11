<template>
    <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
        <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
        <el-breadcrumb-item>订单中心</el-breadcrumb-item>
    </el-breadcrumb>

    <div class="page-title-row">
            <div>
                <div class="page-title">{{ pageTitle }}</div>
                <div class="page-sub">人工确认收款：线上单或「代客下单」→ 待支付确认收款 → 发货</div>
                <div class="page-sub" v-if="query.status === 'paid'">
                    当前为已付款待发货，处理完可切换其它状态
                </div>
            </div>
            <div class="title-actions">
                <el-button
                    v-if="canShip && query.status === 'paid' && orderTable.data.length"
                    type="warning"
                    @click="focusFirstShip"
                >处理下一单发货</el-button>
                <el-button v-if="canExport" @click="doExport" :loading="exporting">导出订单</el-button>
                <el-button v-if="canExport" type="primary" plain @click="doExportPayments" :loading="exportingPay">对账导出</el-button>
                <el-button v-if="canCreate" type="success" @click="openCreateDialog">代客下单</el-button>
            </div>
        </div>

        <el-alert
            v-if="query.status === 'paid'"
            class="ship-alert"
            type="warning"
            show-icon
            :closable="false"
            :title="shipAlertTitle"
        />

        <div class="status-chips">
            <el-check-tag
                :checked="query.status === 'paid'"
                @change="quickStatus('paid')"
            >待发货 {{ summary.pending_ship }}</el-check-tag>
            <el-check-tag
                :checked="query.status === 'pending_pay'"
                @change="quickStatus('pending_pay')"
            >待支付 {{ summary.pending_pay }}</el-check-tag>
            <el-check-tag
                :checked="Number(query.claimed) === 1"
                @change="quickClaimed"
            >已报付款</el-check-tag>
            <el-check-tag
                :checked="query.status === 'refunding'"
                @change="quickStatus('refunding')"
            >售后中 {{ summary.refunding }}</el-check-tag>
            <el-check-tag
                :checked="!query.status"
                @change="quickStatus('')"
            >全部 {{ summary.total }}</el-check-tag>
        </div>

        <el-row :gutter="12" class="toolbar">
            <el-col :span="6">
                <el-input
                    v-model="query.order_no"
                    placeholder="订单号"
                    clearable
                    @keyup.enter="getOrderList"
                />
            </el-col>
            <el-col :span="5">
                <el-select v-model="query.status" placeholder="订单状态" clearable style="width: 100%" @change="getOrderList">
                    <el-option
                        v-for="s in statusOptions"
                        :key="s.value"
                        :label="s.label"
                        :value="s.value"
                    />
                </el-select>
            </el-col>
            <el-col :span="5">
                <el-input
                    v-model="query.name"
                    placeholder="地址关键字"
                    clearable
                    @keyup.enter="getOrderList"
                />
            </el-col>
            <el-col :span="8">
                <el-button type="primary" :icon="Search" @click="getOrderList">搜索</el-button>
                <el-button @click="resetQuery">重置</el-button>
            </el-col>
        </el-row>

        <el-table :data="orderTable.data" v-loading="loading" style="width: 100%; margin-top: 12px">
            <el-table-column type="index" width="50" />
            <el-table-column label="订单号" prop="order_no" min-width="160" show-overflow-tooltip />
            <el-table-column label="用户" prop="user" width="100" />
            <el-table-column label="金额" prop="price" width="90" />
            <el-table-column label="数量" prop="number" width="70" />
            <el-table-column label="状态" width="110">
                <template #default="{ row }">
                    <el-tag :type="statusTagType(row.status)" effect="light">
                        {{ row.status_label || row.status || '-' }}
                    </el-tag>
                    <el-tag
                        v-if="row.buyer_paid_claimed && row.status === 'pending_pay'"
                        type="warning"
                        effect="light"
                        style="margin-left:6px"
                    >已报付款</el-tag>
                </template>
            </el-table-column>
            <el-table-column label="地址" prop="address" min-width="140" show-overflow-tooltip />
            <el-table-column label="操作" min-width="320" fixed="right">
                <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="showDetail(row)">详情</el-button>
                    <el-button
                        v-if="canMarkPaid && row.status === 'pending_pay'"
                        link
                        type="success"
                        size="small"
                        @click="doMarkPaid(row)"
                    >标记已付款</el-button>
                    <el-button
                        v-if="canCreate && allowMockPay && row.status === 'pending_pay'"
                        link
                        type="info"
                        size="small"
                        @click="doMockPay(row)"
                    >模拟支付(开发)</el-button>
                    <el-button
                        v-if="canCancel && row.status === 'pending_pay'"
                        link
                        type="danger"
                        size="small"
                        @click="doCancel(row)"
                    >取消</el-button>
                    <el-button
                        v-if="canShip && row.status === 'paid'"
                        link
                        type="warning"
                        size="small"
                        @click="openShipDialog(row)"
                    >发货</el-button>
                    <el-button
                        v-if="canComplete && row.status === 'shipped'"
                        link
                        type="success"
                        size="small"
                        @click="doComplete(row)"
                    >完成</el-button>
                    <el-button
                        v-if="canRefund && ['paid', 'shipped', 'completed'].includes(row.status)"
                        link
                        type="warning"
                        size="small"
                        @click="doRefundApply(row)"
                    >申请售后</el-button>
                    <el-button
                        v-if="canRefund && row.status === 'refunding'"
                        link
                        type="success"
                        size="small"
                        @click="doRefundApprove(row)"
                    >同意退款</el-button>
                    <el-button
                        v-if="canRefund && row.status === 'refunding'"
                        link
                        type="info"
                        size="small"
                        @click="doRefundReject(row)"
                    >拒绝</el-button>
                    <el-button link type="primary" size="small" @click="showExpress(row.id)">物流</el-button>
                </template>
            </el-table-column>
        </el-table>
        <div style="margin-top:12px;display:flex;justify-content:flex-end">
            <el-pagination
                background
                layout="total, prev, pager, next, sizes"
                :total="orderTotal"
                v-model:current-page="query.pageNum"
                v-model:page-size="query.pageSize"
                :page-sizes="[10,20,50,100]"
                @current-change="getOrderList"
                @size-change="() => { query.pageNum = 1; getOrderList() }"
            />
        </div>
    </div>

    <!-- 物流 -->
    <el-dialog title="物流信息" v-model="expressDialogVisible" width="480px">
        <el-timeline v-if="expressInfo.data.length">
            <el-timeline-item
                v-for="(exp, index) in expressInfo.data"
                :key="index"
                :timestamp="exp.update_time"
            >
                {{ exp.content }}
            </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无物流信息" />
    </el-dialog>

    <!-- 详情 -->
    <el-dialog title="订单详情" v-model="detailVisible" width="640px">
        <template v-if="detail">
            <el-descriptions :column="2" border>
                <el-descriptions-item label="订单号">{{ detail.order_no }}</el-descriptions-item>
                <el-descriptions-item label="状态">{{ detail.status_label }}</el-descriptions-item>
                <el-descriptions-item label="商品金额">
                  ￥{{ Number(detail.goods_amount ?? detail.price ?? 0).toFixed(2) }}
                </el-descriptions-item>
                <el-descriptions-item label="运费">
                  ￥{{ Number(detail.freight_amount ?? 0).toFixed(2) }}
                </el-descriptions-item>
                <el-descriptions-item label="应付合计">
                  <span style="color:#f56c6c;font-weight:600">
                    ￥{{ Number(detail.price ?? 0).toFixed(2) }}
                  </span>
                </el-descriptions-item>
                <el-descriptions-item label="数量">{{ detail.number }}</el-descriptions-item>
                <el-descriptions-item label="地址" :span="2">{{ detail.address }}</el-descriptions-item>
                <el-descriptions-item label="支付时间">{{ detail.paid_at || '-' }}</el-descriptions-item>
                <el-descriptions-item label="发货时间">{{ detail.shipped_at || '-' }}</el-descriptions-item>
                <el-descriptions-item label="顾客申报">{{ detail.buyer_paid_claimed ? '已报付款' : '-' }}</el-descriptions-item>
                <el-descriptions-item label="申报备注">{{ detail.buyer_paid_note || '-' }}</el-descriptions-item>
                <el-descriptions-item v-if="detail.buyer_paid_proof" label="付款截图" :span="2">
                    <img :src="mediaUrl(detail.buyer_paid_proof)" alt="付款截图" style="max-width:100%;max-height:240px;border-radius:8px" />
                </el-descriptions-item>
            </el-descriptions>
            <h4 style="margin-top: 16px">明细</h4>
            <el-table :data="detail.details || []" size="small">
                <el-table-column prop="pid" label="商品ID" width="90" />
                <el-table-column prop="number" label="数量" width="80" />
                <el-table-column prop="price" label="单价" />
                <el-table-column prop="total_price" label="小计" />
            </el-table>
            <h4 style="margin-top: 16px">支付单</h4>
            <el-table :data="detail.payments || []" size="small">
                <el-table-column prop="out_trade_no" label="支付单号" min-width="160" />
                <el-table-column prop="channel" label="渠道" width="80" />
                <el-table-column prop="amount" label="金额" width="80" />
                <el-table-column prop="status" label="状态" width="90" />
            </el-table>
        </template>
    </el-dialog>

    <!-- 发货 -->
    <el-dialog title="填写物流" v-model="shipVisible" width="420px">
        <el-input v-model="shipForm.content" type="textarea" :rows="3" placeholder="如：顺丰 SF123456 已揽收" />
        <template #footer>
            <el-button @click="shipVisible = false">取消</el-button>
            <el-button type="primary" :loading="acting" @click="doShip">确认发货</el-button>
        </template>
    </el-dialog>

    <!-- 演示下单 -->
    <el-dialog title="代客下单（微信/电话成交后录入）" v-model="createVisible" width="480px">
        <el-form label-width="90px">
            <el-form-item label="客户手机" required>
                <el-input v-model="createForm.phone" maxlength="11" placeholder="11 位手机号，用于绑定买家" />
            </el-form-item>
            <el-form-item label="客户昵称">
                <el-input v-model="createForm.nickname" maxlength="20" placeholder="可选" />
            </el-form-item>
            <el-form-item label="收件人">
                <el-input v-model="createForm.contact_name" placeholder="可选，默认用昵称" />
            </el-form-item>
            <el-form-item label="商品" required>
                <el-select v-model="createForm.pid" placeholder="选择商品" filterable style="width: 100%">
                    <el-option
                        v-for="p in productOptions"
                        :key="p.id"
                        :label="`${p.name}（库存${p.number} ￥${p.price}）`"
                        :value="p.id"
                    />
                </el-select>
            </el-form-item>
            <el-form-item label="数量">
                <el-input-number v-model="createForm.number" :min="1" />
            </el-form-item>
            <el-form-item label="收货地址" required>
                <el-input v-model="createForm.address" type="textarea" :rows="2" placeholder="省市区 + 详细地址" />
            </el-form-item>
            <el-alert type="info" :closable="false" show-icon title="创建后进入「待支付」；客户已转账则再点「确认收款」" />
        </el-form>
        <template #footer>
            <el-button @click="createVisible = false">取消</el-button>
            <el-button type="primary" :loading="acting" @click="doCreateOrder">创建待支付订单</el-button>
        </template>
    </el-dialog>
</template>

<script setup>
import { ArrowRight, Search } from '@element-plus/icons-vue'
import { onMounted, reactive, ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'
import { hasAction } from '@/utils/permission.js'

const route = useRoute()
const canExport = computed(() => hasAction('order:export'))
const canCreate = computed(() => hasAction('order:create'))
const canMarkPaid = computed(() => hasAction('order:mark_paid'))
const canCancel = computed(() => hasAction('order:cancel'))
const canShip = computed(() => hasAction('order:ship'))
const canComplete = computed(() => hasAction('order:complete'))
const canRefund = computed(() => hasAction('order:refund'))
// 仅开发：探测后端是否允许 mock（失败则隐藏模拟支付）
const allowMockPay = ref(false)

const statusOptions = [
    { value: 'paid', label: '待发货(已支付)' },
    { value: 'pending_pay', label: '待支付' },
    { value: 'shipped', label: '已发货' },
    { value: 'completed', label: '已完成' },
    { value: 'closed', label: '已关闭' },
    { value: 'refunding', label: '售后中' },
    { value: 'refunded', label: '已退款' },
]

// 默认进入「待发货」工作台；URL ?status= 可覆盖
const query = reactive({
    order_no: '',
    status: 'paid',
    name: '',
    claimed: 0,
    pageNum: 1,
    pageSize: 20,
})
const orderTotal = ref(0)

const pageTitle = computed(() => {
    if (query.status === 'paid') return '待发货工作台'
    if (Number(query.claimed) === 1) return '待核对付款'
    if (query.status === 'pending_pay') return '待支付订单'
    if (query.status === 'refunding') return '售后处理'
    if (!query.status) return '全部订单'
    return '订单中心'
})

const shipAlertTitle = computed(() => {
    const n = summary.pending_ship || orderTable.data.length || 0
    if (n > 0) return `当前有 ${n} 笔待发货，请尽快填写物流单号并发货`
    return '暂无待发货订单，可切换到「全部 / 待支付」查看其它状态'
})

const orderTable = reactive({ data: [] })
const loading = ref(false)
const acting = ref(false)
const exporting = ref(false)
const exportingPay = ref(false)
const summary = reactive({
    total: 0,
    pending_ship: 0,
    pending_pay: 0,
    refunding: 0,
})

const expressDialogVisible = ref(false)
const expressInfo = reactive({ data: [] })

const detailVisible = ref(false)
const detail = ref(null)

const shipVisible = ref(false)
const shipForm = reactive({ id: null, content: '' })

const createVisible = ref(false)
const productOptions = ref([])
const createForm = reactive({
    pid: null,
    number: 1,
    phone: '',
    nickname: '',
    contact_name: '',
    address: '',
})

const statusTagType = (status) => {
    const map = {
        pending_pay: 'info',
        paid: 'success',
        shipped: 'warning',
        completed: 'success',
        closed: 'info',
        refunding: 'warning',
        refunded: 'danger',
    }
    return map[status] || ''
}

const toast = (res, okMsg) => {
    if (res?.data?.status === 200) {
        ElMessage.success(okMsg || res.data.msg || '成功')
        return true
    }
    ElMessage.warning(res?.data?.msg || '操作失败')
    return false
}

const loadSummary = () => {
    api.orders_summary().then((res) => {
        if (res?.data?.status === 200) {
            Object.assign(summary, res.data.data || {})
        }
    }).catch(() => {})
}

const getOrderList = () => {
    loading.value = true
    const params = {
        pageNum: query.pageNum || 1,
        pageSize: query.pageSize || 20,
    }
    if (query.order_no) params.order_no = query.order_no
    if (query.status) params.status = query.status
    if (query.name) params.name = query.name
    if (Number(query.claimed) === 1) params.claimed = 1
    api.get_orders(params)
        .then((res) => {
            if (res?.data?.status === 200) {
                orderTable.data = res.data.data || []
                orderTotal.value = res.data.total != null ? res.data.total : (res.data.data || []).length
            } else {
                ElMessage.warning(res?.data?.msg || '??????')
            }
        })
        .finally(() => {
            loading.value = false
        })
    loadSummary()
}

const quickStatus = (status) => {
    query.status = status
    query.claimed = 0
    query.pageNum = 1 || ''
    getOrderList()
}
const quickClaimed = (on) => {
    query.claimed = on ? 1 : 0
    if (on) query.status = 'pending_pay'
    query.pageNum = 1
    getOrderList()
}

const resetQuery = () => {
    query.order_no = ''
    query.status = 'paid' // 重置仍回到待发货台
    query.name = ''
    getOrderList()
}

const focusFirstShip = () => {
    const row = (orderTable.data || []).find((o) => o.status === 'paid')
    if (!row) {
        ElMessage.info('当前没有待发货订单')
        return
    }
    openShipDialog(row)
}

const doExport = async () => {
    exporting.value = true
    try {
        const params = {}
        if (query.order_no) params.order_no = query.order_no
        if (query.status) params.status = query.status
        if (query.name) params.name = query.name
        const res = await api.export_orders(params)
        const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `orders_${Date.now()}.csv`
        a.click()
        window.URL.revokeObjectURL(url)
        ElMessage.success('订单导出成功')
    } catch (e) {
        ElMessage.error('导出失败，请确认已登录且后端可用')
    } finally {
        exporting.value = false
    }
}

const doExportPayments = async () => {
    exportingPay.value = true
    try {
        const res = await api.export_payments({ days: 30 })
        const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `payments_${Date.now()}.csv`
        a.click()
        window.URL.revokeObjectURL(url)
        ElMessage.success('对账流水导出成功（近30天）')
    } catch (e) {
        ElMessage.error('对账导出失败，请确认权限 order:export')
    } finally {
        exportingPay.value = false
    }
}

const showExpress = (id) => {
    expressDialogVisible.value = true
    expressInfo.data = []
    api.get_express(id).then((res) => {
        if (res?.data?.status === 200) {
            expressInfo.data = res.data.data || []
        }
    })
}

function mediaUrl(path) {
    if (!path) return ''
    const s = String(path)
    if (s.startsWith('http://') || s.startsWith('https://')) return s
    const base = (process.env.VUE_APP_API || '').replace(/\/$/, '')
    return base + (s.startsWith('/') ? s : '/' + s)
}
const showDetail = (row) => {
    api.get_order(row.id).then((res) => {
        if (toast(res, '已加载详情')) {
            detail.value = res.data.data
            detailVisible.value = true
        }
    })
}

const doMarkPaid = async (row) => {
    try {
        const { value } = await ElMessageBox.prompt(
            '请确认已收到该订单款项（微信/支付宝转账等）。可填写备注（如转账后四位）。',
            '标记已付款',
            {
                confirmButtonText: '确认已收款',
                cancelButtonText: '取消',
                inputPlaceholder: '备注（可选）',
                inputValue: '',
            }
        )
        acting.value = true
        const res = await api.mark_order_paid(row.id, { note: value || '' })
        if (toast(res, '已标记为已付款')) {
            getOrderList()
            loadSummary()
        }
    } catch {
        // cancel
    } finally {
        acting.value = false
    }
}

const doMockPay = async (row) => {
    try {
        await ElMessageBox.confirm(
            `开发专用：对订单 ${row.order_no || row.id} 模拟支付？生产环境应关闭。`,
            '模拟支付'
        )
    } catch {
        return
    }
    acting.value = true
    try {
        const createRes = await api.pay_create({ order_id: row.id, channel: 'mock' })
        if (createRes?.data?.status !== 200) {
            ElMessage.warning(createRes?.data?.msg || '创建支付单失败')
            return
        }
        const outTradeNo = createRes.data.data.payment.out_trade_no
        const notifyRes = await api.pay_mock_notify({ out_trade_no: outTradeNo, result: 'success' })
        if (toast(notifyRes, '支付成功')) {
            getOrderList()
            loadSummary()
        }
    } finally {
        acting.value = false
    }
}

const doCancel = async (row) => {
    try {
        await ElMessageBox.confirm('确认取消该待支付订单？库存将回滚。', '取消订单')
    } catch {
        return
    }
    const res = await api.cancel_order(row.id, { reason: '商户后台取消' })
    if (toast(res, '已取消')) getOrderList()
}

const openShipDialog = (row) => {
    shipForm.id = row.id
    shipForm.content = ''
    shipVisible.value = true
}

const doShip = async () => {
    if (!shipForm.content) {
        ElMessage.warning('请填写物流信息')
        return
    }
    acting.value = true
    try {
        const res = await api.ship_order(shipForm.id, { content: shipForm.content })
        if (toast(res, '发货成功')) {
            shipVisible.value = false
            getOrderList()
        }
    } finally {
        acting.value = false
    }
}

const doComplete = async (row) => {
    const res = await api.complete_order(row.id)
    if (toast(res, '订单已完成')) getOrderList()
}

const doRefundApply = async (row) => {
    const res = await api.refund_apply(row.id)
    if (toast(res, '已进入售后')) getOrderList()
}

const doRefundApprove = async (row) => {
    try {
        await ElMessageBox.confirm('确认同意退款？（模拟退款成功并回滚库存）', '同意退款')
    } catch {
        return
    }
    const res = await api.refund_approve(row.id, { reason: '商户同意退款' })
    if (toast(res, '退款成功')) getOrderList()
}

const doRefundReject = async (row) => {
    const res = await api.refund_reject(row.id)
    if (toast(res, '已拒绝售后')) getOrderList()
}

const openCreateDialog = () => {
    createVisible.value = true
    createForm.pid = null
    createForm.number = 1
    createForm.phone = ''
    createForm.nickname = ''
    createForm.contact_name = ''
    createForm.address = ''
    api.get_product_list().then((res) => {
        // 兼容 axios 拦截器是否解包
        const body = res?.data?.status != null ? res.data : res
        if (body?.status === 200) {
            const d = body.data
            productOptions.value = Array.isArray(d) ? d : (d?.products || d?.items || d?.list || [])
        }
    }).catch(() => {
        ElMessage.error('加载商品失败')
    })
}

const doCreateOrder = async () => {
    const phone = String(createForm.phone || '').trim()
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        ElMessage.warning('请填写正确的客户手机号')
        return
    }
    if (!createForm.pid) {
        ElMessage.warning('请选择商品')
        return
    }
    if (!String(createForm.address || '').trim()) {
        ElMessage.warning('请填写收货地址')
        return
    }
    acting.value = true
    try {
        const res = await api.create_order({
            customer_phone: phone,
            customer_nickname: createForm.nickname || undefined,
            contact_name: createForm.contact_name || createForm.nickname || undefined,
            contact_phone: phone,
            address: String(createForm.address).trim(),
            items: [{ pid: createForm.pid, number: createForm.number }],
        })
        if (toast(res, '代客订单已创建（待支付）')) {
            createVisible.value = false
            query.status = 'pending_pay'
            getOrderList()
            loadSummary()
        }
    } finally {
        acting.value = false
    }
}

function applyRouteQuery() {
    const qs = route.query?.status
    if (typeof qs === 'string') {
        query.status = qs
    }
    const ono = route.query?.order_no
    if (typeof ono === 'string') {
        query.order_no = ono
    }
    if (route.query?.claimed === '1' || route.query?.claimed === 1) {
        query.claimed = 1
        if (!query.status) query.status = 'pending_pay'
    }
}

watch(
    () => [route.query.status, route.query.order_no],
    () => {
        applyRouteQuery()
        query.pageNum = 1
        getOrderList()
    },
)

onMounted(() => {
    // URL 显式带 status / order_no 时覆盖；无参数保持默认 paid（待发货台）
    applyRouteQuery()
    getOrderList()
    loadSummary()
    api.pay_channel_status().then((res) => {
        if (res?.data?.status === 200) {
            allowMockPay.value = Boolean(res.data.data?.allow_mock_pay)
        }
    }).catch(() => {
        allowMockPay.value = false
    })
})
</script>

<style scoped>
.crumb {
    margin-bottom: 12px;
}
.page-title-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
    gap: 12px;
}
.page-title {
    font-size: 18px;
    font-weight: 600;
}
.page-sub {
    margin-top: 4px;
    font-size: 12px;
    color: #8a8f99;
}
.title-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.ship-alert {
    margin-bottom: 12px;
}
.status-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
}
.toolbar {
    margin-bottom: 4px;
}
</style>
