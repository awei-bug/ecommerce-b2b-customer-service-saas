<template>
  <section class="knowledge-page">
    <header class="page-head">
      <div>
        <h1>客服知识库</h1>
        <p>店铺规则、售后政策与常见问题</p>
      </div>
      <div v-if="canManage" class="head-actions">
        <el-button :icon="Download" @click="downloadTemplate">下载模板</el-button>
        <el-button :icon="Upload" :loading="importing" @click="chooseImport">导入 CSV</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增知识</el-button>
        <input ref="fileInput" class="file-input" type="file" accept=".csv,text/csv" @change="importCsv" />
      </div>
    </header>

    <div class="summary-strip" aria-label="知识状态汇总">
      <button type="button" :class="{ active: filters.status === '' }" @click="setStatus('')">
        <span>全部</span><strong>{{ totalCount }}</strong>
      </button>
      <button type="button" :class="{ active: filters.status === 'published' }" @click="setStatus('published')">
        <span>已发布</span><strong>{{ counts.published }}</strong>
      </button>
      <button type="button" :class="{ active: filters.status === 'draft' }" @click="setStatus('draft')">
        <span>草稿</span><strong>{{ counts.draft }}</strong>
      </button>
      <button type="button" :class="{ active: filters.status === 'disabled' }" @click="setStatus('disabled')">
        <span>已停用</span><strong>{{ counts.disabled }}</strong>
      </button>
    </div>

    <div class="toolbar">
      <el-input
        v-model="filters.q"
        clearable
        :prefix-icon="Search"
        placeholder="搜索标题、问题或内容"
        @keyup.enter="load"
        @clear="load"
      />
      <el-select v-model="filters.category" clearable placeholder="全部分类" @change="load">
        <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button :icon="Search" @click="load">搜索</el-button>
      <el-button :icon="Refresh" circle title="刷新知识列表" @click="load" />
    </div>

    <el-alert
      v-if="importResult"
      class="import-result"
      :type="importResult.error_count ? 'warning' : 'success'"
      show-icon
      closable
      @close="importResult = null"
    >
      <template #title>
        导入完成：新增 {{ importResult.created }} 条，更新 {{ importResult.updated }} 条，失败 {{ importResult.error_count }} 条
      </template>
      <div v-if="importResult.errors?.length" class="import-errors">
        <span v-for="error in importResult.errors.slice(0, 8)" :key="`${error.row}-${error.title}`">
          第 {{ error.row }} 行{{ error.title ? `「${error.title}」` : '' }}：{{ error.reason }}
        </span>
      </div>
    </el-alert>

    <div class="table-shell" v-loading="loading">
      <el-table v-if="items.length" :data="items" row-key="id" table-layout="fixed">
        <el-table-column label="知识标题" min-width="220">
          <template #default="{ row }">
            <div class="title-cell">
              <strong>{{ row.title }}</strong>
              <span>{{ row.question || row.content }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="108">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="关键词" min-width="170">
          <template #default="{ row }">
            <div v-if="row.keywords?.length" class="keyword-list">
              <el-tag v-for="keyword in row.keywords.slice(0, 3)" :key="keyword" size="small" effect="plain">{{ keyword }}</el-tag>
              <span v-if="row.keywords.length > 3">+{{ row.keywords.length - 3 }}</span>
            </div>
            <span v-else class="muted">未设置</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center" />
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ compactTime(row.update_time) }}</template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="96" fixed="right" align="right">
          <template #default="{ row }">
            <el-tooltip content="编辑知识" placement="top">
              <el-button :icon="Edit" circle size="small" @click="openEdit(row)" />
            </el-tooltip>
            <el-tooltip content="删除知识" placement="top">
              <el-button :icon="Delete" circle size="small" type="danger" plain @click="remove(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!loading" :image-size="88" description="暂无知识条目">
        <el-button v-if="canManage" type="primary" :icon="Plus" @click="openCreate">新增第一条知识</el-button>
      </el-empty>
    </div>

    <el-dialog v-model="editorOpen" :title="form.id ? '编辑知识' : '新增知识'" width="min(680px, 94vw)" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="标题" prop="title">
            <el-input v-model="form.title" maxlength="128" show-word-limit placeholder="例如：七天无理由退货规则" />
          </el-form-item>
          <el-form-item label="分类" prop="category">
            <el-select v-model="form.category">
              <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="顾客可能的问法" prop="question">
          <el-input v-model="form.question" maxlength="500" show-word-limit placeholder="例如：商品不合适可以退吗" />
        </el-form-item>
        <el-form-item label="已确认的规则内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="6" resize="vertical" maxlength="8000" show-word-limit />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keywordsText" maxlength="400" placeholder="多个关键词用逗号分隔" />
        </el-form-item>
        <div class="form-grid compact-grid">
          <el-form-item label="状态" prop="status">
            <el-radio-group v-model="form.status">
              <el-radio-button label="draft">草稿</el-radio-button>
              <el-radio-button label="published">发布</el-radio-button>
              <el-radio-button label="disabled">停用</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="优先级" prop="priority">
            <el-input-number v-model="form.priority" :min="0" :max="100" controls-position="right" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="editorOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { Delete, Download, Edit, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/api'
import { hasAction } from '@/utils/permission.js'

const categories = [
  { value: 'faq', label: '常见问题' },
  { value: 'payment', label: '付款开票' },
  { value: 'shipping', label: '配送发货' },
  { value: 'refund', label: '退换售后' },
  { value: 'product', label: '商品说明' },
  { value: 'other', label: '其他' },
]
const items = ref([])
const counts = reactive({ published: 0, draft: 0, disabled: 0 })
const filters = reactive({ q: '', category: '', status: '' })
const loading = ref(false)
const saving = ref(false)
const importing = ref(false)
const importResult = ref(null)
const editorOpen = ref(false)
const fileInput = ref(null)
const formRef = ref(null)
const canManage = computed(() => hasAction('service:manage'))
const totalCount = computed(() => Number(counts.published) + Number(counts.draft) + Number(counts.disabled))
const form = reactive(emptyForm())
const rules = {
  title: [{ required: true, message: '请输入知识标题', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  content: [{ required: true, message: '请输入已确认的规则内容', trigger: 'blur' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

function emptyForm() {
  return { id: null, title: '', category: 'faq', question: '', content: '', keywordsText: '', status: 'draft', priority: 50 }
}

function responseBody(response) {
  return response?.data?.status != null ? response.data : response
}

async function load() {
  loading.value = true
  try {
    const body = responseBody(await api.store_knowledge({ ...filters }))
    if (body.status !== 200) throw new Error(body.msg || '知识列表加载失败')
    items.value = body.data?.items || []
    Object.assign(counts, body.data?.counts || {})
  } catch (error) {
    ElMessage.error(error.message || '知识列表加载失败')
  } finally {
    loading.value = false
  }
}

function setStatus(status) {
  filters.status = status
  load()
}

function openCreate() {
  Object.assign(form, emptyForm())
  editorOpen.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    title: row.title || '',
    category: row.category || 'faq',
    question: row.question || '',
    content: row.content || '',
    keywordsText: (row.keywords || []).join('，'),
    status: row.status || 'draft',
    priority: Number(row.priority || 0),
  })
  editorOpen.value = true
}

async function save() {
  try {
    await formRef.value?.validate()
  } catch (_) {
    return
  }
  saving.value = true
  const payload = {
    title: form.title.trim(),
    category: form.category,
    question: form.question.trim(),
    content: form.content.trim(),
    keywords: form.keywordsText,
    status: form.status,
    priority: form.priority,
  }
  try {
    const response = form.id
      ? await api.update_store_knowledge(form.id, payload)
      : await api.create_store_knowledge(payload)
    const body = responseBody(response)
    if (body.status !== 200) throw new Error(body.msg || '保存失败')
    ElMessage.success(body.msg || '已保存')
    editorOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.title}」？`, '删除知识', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    const body = responseBody(await api.delete_store_knowledge(row.id))
    if (body.status !== 200) throw new Error(body.msg || '删除失败')
    ElMessage.success('知识已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error.message || '删除失败')
  }
}

function chooseImport() {
  if (fileInput.value) {
    fileInput.value.value = ''
    fileInput.value.click()
  }
}

async function importCsv(event) {
  const file = event.target.files?.[0]
  if (!file) return
  importing.value = true
  try {
    const body = responseBody(await api.import_store_knowledge(file))
    if (body.status !== 200) throw new Error(body.msg || '导入失败')
    importResult.value = body.data || null
    ElMessage.success('CSV 导入完成')
    await load()
  } catch (error) {
    ElMessage.error(error.message || '导入失败')
  } finally {
    importing.value = false
  }
}

async function downloadTemplate() {
  try {
    const response = await api.download_store_knowledge_template()
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'store_knowledge_template.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.message || '模板下载失败')
  }
}

function categoryLabel(value) {
  return categories.find((item) => item.value === value)?.label || '其他'
}

function statusLabel(value) {
  return ({ published: '已发布', draft: '草稿', disabled: '已停用' })[value] || value
}

function statusType(value) {
  return ({ published: 'success', draft: 'warning', disabled: 'info' })[value] || 'info'
}

function compactTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

onMounted(load)
</script>

<style scoped>
.knowledge-page { min-width: 0; color: #24211d; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 14px; }
.page-head h1 { margin: 0; font-size: 20px; line-height: 1.4; letter-spacing: 0; }
.page-head p { margin: 4px 0 0; color: #777168; font-size: 13px; }
.head-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.file-input { display: none; }
.summary-strip { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr)); border: 1px solid #ddd8cf; border-radius: 6px; background: #fff; overflow: hidden; }
.summary-strip button { min-height: 66px; padding: 10px 16px; border: 0; border-right: 1px solid #e9e5dd; background: #fff; color: #746e65; text-align: left; cursor: pointer; }
.summary-strip button:last-child { border-right: 0; }
.summary-strip button:hover, .summary-strip button.active { background: #f0f7f5; color: #0f766e; }
.summary-strip span, .summary-strip strong { display: block; }
.summary-strip span { font-size: 12px; }
.summary-strip strong { margin-top: 3px; font-size: 22px; line-height: 1.2; }
.toolbar { display: grid; grid-template-columns: minmax(240px, 1fr) 180px auto auto; gap: 8px; align-items: center; margin: 14px 0 10px; }
.import-result { margin-bottom: 10px; }
.import-errors { display: grid; gap: 3px; margin-top: 6px; font-size: 12px; }
.table-shell { min-height: 300px; overflow-x: auto; border: 1px solid #ddd8cf; border-radius: 6px; background: #fff; }
.table-shell :deep(.el-table) { min-width: 980px; }
.table-shell :deep(.el-table__header th) { background: #f7f5f1; color: #5d574f; font-weight: 650; }
.title-cell { min-width: 0; }
.title-cell strong, .title-cell span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.title-cell strong { color: #29251f; }
.title-cell span { margin-top: 4px; color: #898279; font-size: 12px; }
.keyword-list { display: flex; align-items: center; gap: 5px; overflow: hidden; }
.keyword-list > span { color: #817a70; font-size: 12px; white-space: nowrap; }
.muted { color: #a19a90; font-size: 12px; }
.form-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(160px, 1fr); gap: 14px; }
.compact-grid { grid-template-columns: minmax(300px, 2fr) minmax(130px, 1fr); }
.form-grid :deep(.el-select), .form-grid :deep(.el-input-number) { width: 100%; }
@media (max-width: 760px) {
  .page-head { display: block; }
  .head-actions { justify-content: flex-start; margin-top: 12px; }
  .summary-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .summary-strip button:nth-child(2) { border-right: 0; }
  .summary-strip button:nth-child(-n+2) { border-bottom: 1px solid #e9e5dd; }
  .toolbar { grid-template-columns: minmax(0, 1fr) 132px auto; }
  .toolbar > :first-child { grid-column: 1 / -1; }
  .toolbar > :last-child { display: none; }
  .form-grid, .compact-grid { grid-template-columns: 1fr; gap: 0; }
}
</style>
