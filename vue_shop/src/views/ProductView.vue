<template>
    <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
        <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
        <el-breadcrumb-item>商品管理</el-breadcrumb-item>
        <el-breadcrumb-item>商品列表</el-breadcrumb-item>
    </el-breadcrumb>
    <div class="page-title-row">
        <div class="page-title">商品列表</div>
        <div class="title-actions">
            <el-button @click="openBatch" :disabled="!selected.length">批量改库存</el-button>
            <el-button type="success" plain @click="openCoverBatch">批量补主图</el-button>
            <el-button type="warning" @click="openPackImport">上传成品包上架</el-button>
            <el-button type="primary" @click="addProduct">添加商品</el-button>
        </div>
    </div>
        <el-row :gutter="12" class="toolbar">
            <el-col :span="8">
                <el-input v-model="productTable.searchKey" placeholder="请输入要搜索的商品" clearable @clear="getProductList">
                    <template #append>
                        <el-button :icon="Search" @click="getProductList" />
                    </template>
                </el-input>
            </el-col>
        </el-row>
        <el-row>
            <el-table
              :data="productTable.data"
              style="width: 100%; margin-top: 12px"
              v-loading="loading"
              @selection-change="onSelect"
            >
                <el-table-column type="selection" width="48" />
                <el-table-column type="index" width="50" />
                <el-table-column label="主图" width="72">
                    <template #default="{ row }">
                        <el-image
                          v-if="row.big_img || row.small_img"
                          :src="imgSrc(row.big_img || row.small_img)"
                          fit="cover"
                          class="list-thumb"
                          :preview-src-list="[imgSrc(row.big_img || row.small_img)]"
                          preview-teleported
                        />
                        <div v-else class="list-thumb empty">无图</div>
                    </template>
                </el-table-column>
                <el-table-column label="商品名称" prop="name" min-width="160" show-overflow-tooltip />
                <el-table-column label="价格" prop="price" width="90" />
                <el-table-column label="库存" width="100">
                    <template #default="{ row }">
                        {{ row.has_sku ? (row.stock_total ?? row.number) : row.number }}
                        <el-tag v-if="row.has_sku" size="small" type="info" style="margin-left:4px">SKU</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="状态" width="90">
                    <template #default="scope">
                        <el-tag v-if="scope.row.state === 2 || scope.row.state == null" type="success" size="small">上架</el-tag>
                        <el-tag v-else type="info" size="small">下架</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="操作" min-width="340" fixed="right">
                    <template #default="scope">
                        <el-button type="primary" size="small" @click="openEdit(scope.row)">编辑</el-button>
                        <el-button type="primary" plain size="small" @click="openSku(scope.row)">规格SKU</el-button>
                        <el-button
                          v-if="scope.row.state === 2 || scope.row.state == null"
                          type="warning"
                          size="small"
                          @click="toggleState(scope.row, 0)"
                        >下架</el-button>
                        <el-button
                          v-else
                          type="success"
                          size="small"
                          @click="toggleState(scope.row, 2)"
                        >上架</el-button>
                        <el-button type="danger" size="small" @click="removeProduct(scope.row)">删除</el-button>
                    </template>
                </el-table-column>
            </el-table>
        </el-row>

        <!-- 基础编辑 -->
        <el-dialog v-model="editVisible" title="编辑商品" width="640px" destroy-on-close>
            <el-form label-width="90px" :model="editForm">
                <el-form-item label="名称">
                    <el-input v-model="editForm.name" maxlength="128" show-word-limit />
                </el-form-item>
                <el-form-item label="价格">
                    <el-input-number v-model="editForm.price" :min="0" :precision="2" :step="1" style="width: 100%" />
                </el-form-item>
                <el-form-item label="库存" v-if="!editForm.has_sku">
                    <el-input-number v-model="editForm.number" :min="0" :step="1" style="width: 100%" />
                </el-form-item>
                <el-form-item label="库存" v-else>
                    <span class="muted-tip">多规格商品请在「规格SKU」中改库存</span>
                </el-form-item>
                <el-form-item label="状态">
                    <el-radio-group v-model="editForm.state">
                        <el-radio :value="2">上架</el-radio>
                        <el-radio :value="0">下架</el-radio>
                    </el-radio-group>
                </el-form-item>
                <el-form-item label="商品主图">
                    <ProductImageUpload v-model="editForm.big_img" v-model:pics="editForm.pics" :limit="5" />
                </el-form-item>
                <el-form-item label="重量kg">
                    <el-input-number v-model="editForm.weight" :min="0" :step="0.1" :precision="2" style="width:100%" />
                </el-form-item>
                <el-form-item label="卖点">
                    <el-input v-model="editForm.sell_points" type="textarea" :rows="2" />
                </el-form-item>
                <el-form-item label="简介">
                    <el-input v-model="editForm.introduce" type="textarea" :rows="4" />
                    <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
                      <el-button type="success" plain size="small" :loading="aiGen" @click="runContentAI(false)">AI生成内容</el-button>
                      <el-button type="warning" size="small" :loading="aiPub" @click="runContentAI(true)">AI生成并上架</el-button>
                    </div>
                    <p style="margin:6px 0 0;font-size:12px;color:#8a8478">「并上架」会回填字段、保存商品，并将状态设为上架（C 端立即可见）。</p>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="editVisible = false">取消</el-button>
                <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
            </template>
        </el-dialog>

        <!-- SKU 管理 -->
        <el-dialog v-model="skuVisible" :title="`规格SKU - ${skuProduct?.name || ''}`" width="760px" destroy-on-close>
            <div class="sku-toolbar">
                <el-button type="primary" size="small" @click="addSkuRow">新增规格</el-button>
                <span class="muted-tip">示例：颜色=红，尺码=L；库存按 SKU 扣减</span>
            </div>
            <el-table :data="skuRows" size="small" v-loading="skuLoading">
                <el-table-column label="编码" min-width="120">
                    <template #default="{ row }">
                        <el-input v-model="row.sku_code" size="small" placeholder="可空自动生成" />
                    </template>
                </el-table-column>
                <el-table-column label="规格(JSON/文本)" min-width="180">
                    <template #default="{ row }">
                        <el-input v-model="row.specsText" size="small" placeholder='颜色:红;尺码:L' />
                    </template>
                </el-table-column>
                <el-table-column label="价格" width="120">
                    <template #default="{ row }">
                        <el-input-number v-model="row.price" :min="0" :precision="2" size="small" controls-position="right" />
                    </template>
                </el-table-column>
                <el-table-column label="库存" width="110">
                    <template #default="{ row }">
                        <el-input-number v-model="row.stock" :min="0" size="small" controls-position="right" />
                    </template>
                </el-table-column>
                <el-table-column label="启用" width="70">
                    <template #default="{ row }">
                        <el-switch v-model="row.status" :active-value="1" :inactive-value="0" size="small" />
                    </template>
                </el-table-column>
                <el-table-column label="操作" width="140" fixed="right">
                    <template #default="{ row, $index }">
                        <el-button link type="primary" size="small" @click="saveSkuRow(row)">保存</el-button>
                        <el-button link type="danger" size="small" @click="removeSkuRow(row, $index)">删</el-button>
                    </template>
                </el-table-column>
            </el-table>
            <template #footer>
                <el-button @click="skuVisible = false">关闭</el-button>
            </template>
        </el-dialog>

        <!-- 批量改库存 -->
        <el-dialog v-model="batchVisible" title="批量改库存" width="520px">
            <el-alert type="info" :closable="false" show-icon title="仅对无 SKU 的商品生效；有多规格的请进「规格SKU」改" style="margin-bottom:12px" />
            <el-form label-width="100px">
                <el-form-item label="统一设为">
                    <el-input-number v-model="batchStock" :min="0" />
                </el-form-item>
                <el-form-item label="已选商品">
                    <div>{{ selected.map(s => s.name).join('、') }}</div>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="batchVisible = false">取消</el-button>
                <el-button type="primary" :loading="batchSaving" @click="saveBatch">确定</el-button>
            </template>
        </el-dialog>
    </div>

        <!-- 批量补主图 -->
        
        <!-- 批量补主图 -->
        <el-dialog v-model="coverBatchVisible" title="批量补主图" width="720px" destroy-on-close>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="为没有主图的商品快速上传封面；也可勾选商品后只处理选中项。"
              style="margin-bottom: 12px"
            />
            <div class="cover-batch-toolbar">
              <el-radio-group v-model="coverBatchScope" size="small" @change="refreshCoverBatchList">
                <el-radio-button value="missing">仅无主图</el-radio-button>
                <el-radio-button value="selected">仅已选中</el-radio-button>
              </el-radio-group>
              <el-button size="small" @click="refreshCoverBatchList">刷新列表</el-button>
            </div>
            <el-table :data="coverBatchRows" size="small" max-height="420" v-loading="coverBatchLoading">
              <el-table-column label="商品" min-width="160" prop="name" show-overflow-tooltip />
              <el-table-column label="当前主图" width="90">
                <template #default="{ row }">
                  <el-image v-if="row.big_img || row._cover" :src="imgSrc(row._cover || row.big_img)" class="list-thumb" fit="cover" />
                  <div v-else class="list-thumb empty">无图</div>
                </template>
              </el-table-column>
              <el-table-column label="上传主图" min-width="280">
                <template #default="{ row }">
                  <ProductImageUpload
                    v-model="row._cover"
                    :pics="row._cover ? [row._cover] : []"
                    :limit="1"
                  />
                </template>
              </el-table-column>
            </el-table>
            <template #footer>
              <el-button @click="coverBatchVisible = false">取消</el-button>
              <el-button type="primary" :loading="coverBatchSaving" @click="saveCoverBatch">保存已上传的主图</el-button>
            </template>
        </el-dialog>

        <el-dialog v-model="packVisible" title="上传成品包上架" width="680px" destroy-on-close>
            <el-alert type="success" :closable="false" show-icon style="margin-bottom:12px">
              <template #title>
                UI 把商品图片和信息打成一份 zip，店长在这里一次上传，系统自动填名称/价格/库存/主图并上架。
              </template>
            </el-alert>
            <p class="muted-tip" style="margin:0 0 10px">
              支持三种格式（单包 ≤ 30MB）：① 根目录 <code>products.json</code>；② <code>products.csv</code>（多图用 | 分隔）；③ 每个商品一个文件夹（<code>info.json</code> + 图片）。缺名称或价格的条目会跳过，不会瞎填价格。
            </p>
            <pre class="pack-example">{
  "publish": true,
  "products": [
    { "name": "纯棉T恤", "price": 89, "stock": 30, "introduce": "舒适透气", "images": ["images/a.jpg"] }
  ]
}</pre>
            <input ref="packFileRef" type="file" accept=".zip,application/zip" style="display:none" @change="onPackFile" />
            <div class="pack-file-row">
              <el-button @click="packFileRef && packFileRef.click()">选择 zip 文件</el-button>
              <el-button link type="primary" @click="downloadSamplePack">下载示例包</el-button>
              <span class="muted-tip">{{ packFile ? packFile.name : '未选择文件' }}</span>
            </div>
            <div v-if="packResult" class="pack-result">
              <el-alert
                :type="(packResult.data && packResult.data.created_count) ? 'success' : 'warning'"
                :closable="false"
                :title="packResult.msg || '导入完成'"
                style="margin:12px 0"
              />
              <el-table v-if="packResult.data && packResult.data.created && packResult.data.created.length" :data="packResult.data.created" size="small" max-height="220" style="margin-bottom:8px">
                <el-table-column label="已上架" prop="name" min-width="140" />
                <el-table-column label="价格" prop="price" width="80" />
                <el-table-column label="库存" prop="number" width="80" />
                <el-table-column label="主图" width="90">
                  <template #default="{ row }">
                    <el-image v-if="row.big_img" :src="imgSrc(row.big_img)" class="list-thumb" fit="cover" />
                    <div v-else class="list-thumb empty">无图</div>
                  </template>
                </el-table-column>
              </el-table>
              <el-table v-if="packResult.data && packResult.data.errors && packResult.data.errors.length" :data="packResult.data.errors" size="small" max-height="180">
                <el-table-column label="跳过/警告" prop="name" min-width="120" />
                <el-table-column label="原因" prop="reason" min-width="200" show-overflow-tooltip />
              </el-table>
            </div>
            <template #footer>
              <el-button @click="packVisible = false">关闭</el-button>
              <el-button type="warning" :loading="packSaving" @click="submitPack">开始上架</el-button>
            </template>
        </el-dialog>


</template>

<script setup>
import { ArrowRight, Search } from '@element-plus/icons-vue'
import { onMounted, reactive, ref, watch } from 'vue'
import api from '../api/index.js'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

const productTable = reactive({ data: [], searchKey: null })
const router = useRouter()
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const aiGen = ref(false)
const aiPub = ref(false)
const editForm = reactive({
    id: null, name: '', price: 0, number: 0, introduce: '', state: 2, has_sku: false,
    big_img: '', small_img: '', pics: [], weight: 0.3, sell_points: '',
})

const selected = ref([])
const batchVisible = ref(false)
const batchStock = ref(0)
const batchSaving = ref(false)
const coverBatchVisible = ref(false)
const coverBatchScope = ref('missing')
const coverBatchRows = ref([])
const coverBatchLoading = ref(false)
const coverBatchSaving = ref(false)
const packVisible = ref(false)
const packFileRef = ref(null)
const packFile = ref(null)
const packSaving = ref(false)
const packResult = ref(null)

const skuVisible = ref(false)
const skuLoading = ref(false)
const skuProduct = ref(null)
const skuRows = ref([])

const parseSpecs = (text) => {
    // 支持 JSON 或 颜色:红;尺码:L
    const t = (text || '').trim()
    if (!t) return {}
    if (t.startsWith('{')) {
        try { return JSON.parse(t) } catch { return {} }
    }
    const obj = {}
    t.split(/[;；,，]/).map(s => s.trim()).filter(Boolean).forEach((pair) => {
        const [k, ...rest] = pair.split(/[:：=]/)
        if (k && rest.length) obj[k.trim()] = rest.join(':').trim()
    })
    return obj
}

const specsToText = (specs) => {
    if (!specs || typeof specs !== 'object') return ''
    return Object.entries(specs).map(([k, v]) => `${k}:${v}`).join(';')
}

const getProductList = () => {
    loading.value = true
    api.get_product_list(productTable.searchKey)
        .then((res) => {
            if (res?.data?.status === 200) productTable.data = res.data.data || []
            else ElMessage.warning(res?.data?.msg || '获取商品失败')
        })
        .finally(() => { loading.value = false })
}

const onSelect = (rows) => { selected.value = rows || [] }

const imgSrc = (path) => {
    if (!path) return ''
    if (/^https?:\/\//i.test(path)) return path
    return path.startsWith('/') ? path : `/${path}`
}

const openEdit = (row) => {
    editForm.id = row.id
    editForm.name = row.name || ''
    editForm.price = Number(row.price || 0)
    editForm.number = Number(row.number || 0)
    editForm.introduce = row.introduce || ''
    editForm.state = row.state === 0 ? 0 : 2
    editForm.has_sku = Boolean(row.has_sku)
    editForm.big_img = row.big_img || row.small_img || ''
    editForm.small_img = row.small_img || row.big_img || ''
    editForm.pics = row.big_img || row.small_img ? [row.big_img || row.small_img] : []
    editForm.weight = Number(row.weight || 0.3)
    editForm.sell_points = row.sell_points || ''
    editVisible.value = true
}

const saveEdit = async () => {
    if (!editForm.name) return ElMessage.warning('商品名称不能为空')
    saving.value = true
    try {
        const payload = {
            name: editForm.name,
            price: editForm.price,
            introduce: editForm.introduce,
            state: editForm.state,
            big_img: editForm.big_img || '',
            small_img: editForm.small_img || editForm.big_img || '',
            weight: editForm.weight,
            sell_points: editForm.sell_points,
        }
        if (!editForm.has_sku) payload.number = editForm.number
        const res = await api.update_product(editForm.id, payload)
        if (res?.data?.status === 200) {
            ElMessage.success('保存成功')
            editVisible.value = false
            getProductList()
        } else ElMessage.warning(res?.data?.msg || '保存失败')
    } finally { saving.value = false }
}

const openSku = async (row) => {
    skuProduct.value = row
    skuVisible.value = true
    skuLoading.value = true
    try {
        const res = await api.list_skus(row.id)
        if (res?.data?.status === 200) {
            skuRows.value = (res.data.data || []).map((s) => ({
                ...s,
                specsText: specsToText(s.specs),
            }))
        } else {
            skuRows.value = []
            ElMessage.warning(res?.data?.msg || '加载 SKU 失败')
        }
    } finally { skuLoading.value = false }
}

const addSkuRow = () => {
    skuRows.value.push({
        id: null,
        sku_code: '',
        specsText: '',
        price: Number(skuProduct.value?.price || 0),
        stock: 0,
        status: 1,
    })
}

const saveSkuRow = async (row) => {
    if (!skuProduct.value) return
    const specs = parseSpecs(row.specsText)
    const payload = {
        sku_code: row.sku_code || undefined,
        specs,
        price: row.price,
        stock: row.stock,
        status: row.status,
    }
    let res
    if (row.id) res = await api.update_sku(skuProduct.value.id, row.id, payload)
    else res = await api.create_sku(skuProduct.value.id, payload)
    if (res?.data?.status === 200) {
        ElMessage.success('SKU 已保存')
        openSku(skuProduct.value)
        getProductList()
    } else ElMessage.warning(res?.data?.msg || '保存失败')
}

const removeSkuRow = async (row, index) => {
    if (!row.id) {
        skuRows.value.splice(index, 1)
        return
    }
    try {
        await ElMessageBox.confirm('确认删除该 SKU？', '删除')
    } catch { return }
    const res = await api.delete_sku(skuProduct.value.id, row.id)
    if (res?.data?.status === 200) {
        ElMessage.success('已删除')
        openSku(skuProduct.value)
        getProductList()
    } else ElMessage.warning(res?.data?.msg || '删除失败')
}

const openBatch = () => {
    if (!selected.value.length) return
    batchStock.value = 0
    batchVisible.value = true
}

const saveBatch = async () => {
    batchSaving.value = true
    try {
        const items = selected.value
            .filter((p) => !p.has_sku)
            .map((p) => ({ product_id: p.id, stock: batchStock.value }))
        if (!items.length) {
            ElMessage.warning('所选商品均含 SKU，请到规格里改库存')
            return
        }
        const res = await api.batch_stock(items)
        if (res?.data?.status === 200 || res?.data?.status === 207) {
            ElMessage.success(res.data.msg || '已更新')
            batchVisible.value = false
            getProductList()
            if (res.data.data?.errors?.length) {
                ElMessage.warning(`部分失败 ${res.data.data.errors.length} 条`)
            }
        } else ElMessage.warning(res?.data?.msg || '失败')
    } finally { batchSaving.value = false }
}

const toggleState = (row, state) => {
    api.set_product_state(row.id, state).then((res) => {
        if (res?.data?.status === 200) {
            ElMessage.success(state === 2 ? '已上架' : '已下架')
            getProductList()
        } else ElMessage.warning(res?.data?.msg || '操作失败')
    })
}

const removeProduct = (row) => {
    ElMessageBox.confirm('是否要删除「' + row.name + '」？', '删除商品', {
        confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    }).then(() => {
        api.delete_product(row.id).then((res) => {
            if (res?.data?.status == 200) {
                ElMessage.success(res.data.msg || '已删除')
                getProductList()
            } else ElMessage.warning(res?.data?.msg || '删除失败')
        })
    }).catch(() => ElMessage.info('已取消删除'))
}

const addProduct = () => router.push('/add_product')

const openPackImport = () => {
  packFile.value = null
  packResult.value = null
  packVisible.value = true
}

const onPackFile = (e) => {
  const f = e.target.files && e.target.files[0]
  packFile.value = f || null
  packResult.value = null
  e.target.value = ''
}

const submitPack = async () => {
  if (!packFile.value) {
    ElMessage.warning('请先选择 zip 成品包')
    return
  }
  packSaving.value = true
  try {
    const res = await api.import_product_pack(packFile.value)
    const body = res?.data?.status != null ? res.data : res
    packResult.value = body
    if (body?.status === 200) {
      ElMessage.success(body.msg || '导入完成')
      getProductList()
    } else {
      ElMessage.warning(body?.msg || '导入失败')
    }
  } catch (err) {
    ElMessage.error(err?.message || '上传失败')
  } finally {
    packSaving.value = false
  }
}

const downloadSamplePack = async () => {
  try {
    const res = await api.download_listing_pack_sample()
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data])
    if (blob.type && blob.type.includes('json')) {
      ElMessage.warning('下载示例包失败，请确认已登录')
      return
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'listing_pack_sample.zip'
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    ElMessage.error(err?.message || '下载失败')
  }
}


const refreshCoverBatchList = () => {
  let rows = productTable.data || []
  if (coverBatchScope.value === 'selected') {
    const ids = new Set((selected.value || []).map((r) => r.id))
    rows = rows.filter((r) => ids.has(r.id))
  } else {
    rows = rows.filter((r) => !(r.big_img || r.small_img))
  }
  coverBatchRows.value = rows.map((r) => ({
    id: r.id,
    name: r.name,
    big_img: r.big_img || r.small_img || '',
    _cover: r.big_img || r.small_img || '',
  }))
}

const openCoverBatch = () => {
  coverBatchVisible.value = true
  coverBatchScope.value = (selected.value && selected.value.length) ? 'selected' : 'missing'
  refreshCoverBatchList()
}

const saveCoverBatch = async () => {
  const items = (coverBatchRows.value || [])
    .filter((r) => r._cover)
    .map((r) => ({ product_id: r.id, big_img: r._cover, small_img: r._cover }))
  if (!items.length) {
    ElMessage.warning('请先至少上传一张主图')
    return
  }
  coverBatchSaving.value = true
  try {
    const res = await api.batch_product_covers(items)
    const body = res?.data?.status != null ? res.data : res
    if (body?.status === 200) {
      ElMessage.success(body.msg || '主图已保存')
      coverBatchVisible.value = false
      getProductList()
    } else {
      ElMessage.warning(body?.msg || '保存失败')
    }
  } finally {
    coverBatchSaving.value = false
  }
}



const runContentAI = async (autoPublish = false) => {
  if (autoPublish) aiPub.value = true
  else aiGen.value = true
  try {
    const res = await api.agent_product_content({
      id: editForm.id,
      product_id: editForm.id,
      name: editForm.name,
      price: editForm.price,
      number: editForm.number,
      introduce: editForm.introduce,
      weight: editForm.weight,
      apply: !!autoPublish,
      publish: !!autoPublish,
      create_new: !editForm.id && !!autoPublish,
    })
    const body = res?.data?.status != null ? res.data : res
    if (body?.status === 200 && body.data) {
      const d = body.data
      const fill = d.product || d
      if (d.title || fill.name) editForm.name = d.title || fill.name
      if (d.sell_points || fill.sell_points) {
        editForm.sell_points = d.sell_points || fill.sell_points
        editForm.introduce = d.sell_points || fill.sell_points || editForm.introduce
      }
      if (d.description && !editForm.introduce) editForm.introduce = d.description
      if (fill.id) editForm.id = fill.id
      if (d.published || fill.state === 2) editForm.state = 2
      if (autoPublish && d.applied) {
        ElMessage.success(body.msg || '已生成并上架，商城端可立即看到')
        getProductList()
      } else {
        ElMessage.success('已生成并回填，请确认后点保存')
      }
    } else {
      ElMessage.warning(body?.msg || '生成失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '请求失败')
  } finally {
    aiGen.value = false
    aiPub.value = false
  }
}

onMounted(getProductList)
</script>

<style scoped>
.crumb { margin-bottom: 12px; }
.page-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px;
}
.page-title { font-size: 18px; font-weight: 600; }
.title-actions { display: flex; gap: 8px; }
.toolbar { margin-bottom: 4px; }
.sku-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; gap: 8px;
}
.muted-tip { color: #8a8f99; font-size: 12px; }

.list-thumb {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: cover;
}
.list-thumb.empty {
  display: grid;
  place-items: center;
  background: #f1f5f9;
  color: #94a3b8;
  font-size: 11px;
  border: 1px dashed #cbd5e1;
}

.cover-batch-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.pack-example {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.45;
  overflow: auto;
  margin: 0 0 12px;
}
.pack-file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.pack-result { margin-top: 4px; }
</style>
