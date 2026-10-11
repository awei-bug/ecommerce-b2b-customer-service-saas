<template>
  <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
      <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
      <el-breadcrumb-item>店铺</el-breadcrumb-item>
      <el-breadcrumb-item>运费模板</el-breadcrumb-item>
    </el-breadcrumb>
    <div class="page-title-row">
      <div class="page-title">运费模板</div>
      <el-button type="primary" @click="openCreate">新建模板</el-button>
    </div>

    <el-table :data="list" v-loading="loading" style="width: 100%">
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="计费方式" width="110">
        <template #default="{ row }">{{ typeLabel(row.charge_type) }}</template>
      </el-table-column>
      <el-table-column label="费用说明" min-width="180">
        <template #default="{ row }">{{ feeDesc(row) }}</template>
      </el-table-column>
      <el-table-column label="满额包邮" width="100">
        <template #default="{ row }">{{ row.free_amount > 0 ? `满${row.free_amount}` : '—' }}</template>
      </el-table-column>
      <el-table-column label="默认" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑模板' : '新建模板'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="计费方式">
          <el-select v-model="form.charge_type" style="width: 100%">
            <el-option label="包邮" value="free" />
            <el-option label="固定运费" value="fixed" />
            <el-option label="按件计费" value="by_piece" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.charge_type === 'fixed'" label="固定运费">
          <el-input-number v-model="form.fixed_fee" :min="0" :step="0.5" />
        </el-form-item>
        <template v-if="form.charge_type === 'by_piece'">
          <el-form-item label="首件数量">
            <el-input-number v-model="form.first_piece" :min="1" />
          </el-form-item>
          <el-form-item label="首件运费">
            <el-input-number v-model="form.first_fee" :min="0" :step="0.5" />
          </el-form-item>
          <el-form-item label="续件数量">
            <el-input-number v-model="form.additional_piece" :min="1" />
          </el-form-item>
          <el-form-item label="续件运费">
            <el-input-number v-model="form.additional_fee" :min="0" :step="0.5" />
          </el-form-item>
        </template>
        <el-form-item label="满额包邮">
          <el-input-number v-model="form.free_amount" :min="0" :step="10" />
          <span class="tip">0 表示不启用</span>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api/index.js'

const list = ref([])
const loading = ref(false)
const visible = ref(false)
const saving = ref(false)
const form = reactive({
  id: null,
  name: '',
  charge_type: 'fixed',
  fixed_fee: 10,
  first_piece: 1,
  first_fee: 10,
  additional_piece: 1,
  additional_fee: 2,
  free_amount: 0,
  is_default: 0,
})

const typeLabel = (t) => ({ free: '包邮', fixed: '固定', by_piece: '按件' }[t] || t)
const feeDesc = (row) => {
  if (row.charge_type === 'free') return '包邮'
  if (row.charge_type === 'fixed') return `固定 ￥${row.fixed_fee}`
  return `首${row.first_piece}件￥${row.first_fee}，续${row.additional_piece}件￥${row.additional_fee}`
}

const load = () => {
  loading.value = true
  api.get_freight_templates()
    .then((res) => {
      if (res?.data?.status === 200) list.value = res.data.data || []
      else ElMessage.warning(res?.data?.msg || '加载失败')
    })
    .finally(() => { loading.value = false })
}

const resetForm = () => {
  Object.assign(form, {
    id: null,
    name: '',
    charge_type: 'fixed',
    fixed_fee: 10,
    first_piece: 1,
    first_fee: 10,
    additional_piece: 1,
    additional_fee: 2,
    free_amount: 0,
    is_default: 0,
  })
}

const openCreate = () => {
  resetForm()
  visible.value = true
}

const openEdit = (row) => {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    charge_type: row.charge_type,
    fixed_fee: row.fixed_fee,
    first_piece: row.first_piece,
    first_fee: row.first_fee,
    additional_piece: row.additional_piece,
    additional_fee: row.additional_fee,
    free_amount: row.free_amount,
    is_default: row.is_default ? 1 : 0,
  })
  visible.value = true
}

const save = async () => {
  if (!form.name) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    const res = form.id
      ? await api.update_freight_template(form.id, payload)
      : await api.create_freight_template(payload)
    if (res?.data?.status === 200) {
      ElMessage.success(res.data.msg || '保存成功')
      visible.value = false
      load()
    } else {
      ElMessage.warning(res?.data?.msg || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  try {
    await ElMessageBox.confirm(`删除模板「${row.name}」？`, '提示')
  } catch {
    return
  }
  const res = await api.delete_freight_template(row.id)
  if (res?.data?.status === 200) {
    ElMessage.success('已删除')
    load()
  } else {
    ElMessage.warning(res?.data?.msg || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.crumb { margin-bottom: 12px; }
.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title { font-size: 18px; font-weight: 600; }
.tip { margin-left: 8px; color: #8a8f99; font-size: 12px; }
</style>
