<template>
  <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
      <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
      <el-breadcrumb-item>权限</el-breadcrumb-item>
      <el-breadcrumb-item>角色与动作权限</el-breadcrumb-item>
    </el-breadcrumb>
    <div class="page-title">角色与动作权限</div>
    <p class="hint">菜单控制侧栏可见；动作码控制接口按钮（发货/退款等）。超级管理员固定全权限。</p>

    <el-table :data="roles" v-loading="loading" style="width: 100%">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="角色" width="140" />
      <el-table-column prop="desc" label="说明" min-width="160" show-overflow-tooltip />
      <el-table-column label="动作权限" min-width="220">
        <template #default="{ row }">
          <el-tag
            v-for="c in (row.perm_codes || []).slice(0, 6)"
            :key="c"
            size="small"
            class="tag"
          >{{ c }}</el-tag>
          <span v-if="!(row.perm_codes || []).length" class="muted">未配置（回退菜单推导）</span>
          <span v-if="(row.perm_codes || []).length > 6" class="muted"> +{{ row.perm_codes.length - 6 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑动作</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="编辑动作权限" width="640px">
      <div v-if="current" class="dlg-head">角色：{{ current.name }}</div>
      <el-checkbox-group v-model="checked">
        <el-row :gutter="8">
          <el-col :span="12" v-for="a in actionOptions" :key="a.code" class="chk">
            <el-checkbox :label="a.code">{{ a.label }} <span class="code">{{ a.code }}</span></el-checkbox>
          </el-col>
        </el-row>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'

const roles = ref([])
const actionOptions = ref([])
const loading = ref(false)
const visible = ref(false)
const saving = ref(false)
const current = ref(null)
const checked = ref([])

const load = async () => {
  loading.value = true
  try {
    const [r1, r2] = await Promise.all([api.get_roles(), api.get_action_codes()])
    if (r1?.data?.status === 200) roles.value = r1.data.data || []
    if (r2?.data?.status === 200) actionOptions.value = r2.data.data || []
  } finally {
    loading.value = false
  }
}

const openEdit = (row) => {
  current.value = row
  checked.value = [...(row.perm_codes || [])]
  visible.value = true
}

const save = async () => {
  if (!current.value) return
  saving.value = true
  try {
    const res = await api.update_role(current.value.id, {
      name: current.value.name,
      desc: current.value.desc,
      perm_codes: checked.value,
    })
    if (res?.data?.status === 200) {
      ElMessage.success('已保存，相关账号重新登录后生效更稳妥')
      visible.value = false
      load()
    } else {
      ElMessage.warning(res?.data?.msg || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.crumb { margin-bottom: 12px; }
.page-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.hint { color: #8a8f99; font-size: 13px; margin: 0 0 16px; }
.tag { margin: 0 4px 4px 0; }
.muted { color: #a0a4ae; font-size: 12px; }
.dlg-head { margin-bottom: 12px; font-weight: 600; }
.chk { margin-bottom: 6px; }
.code { color: #a0a4ae; font-size: 11px; margin-left: 4px; }
</style>
