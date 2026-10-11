<template>
  <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
      <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
      <el-breadcrumb-item>权限管理</el-breadcrumb-item>
      <el-breadcrumb-item>角色菜单</el-breadcrumb-item>
    </el-breadcrumb>
    <div class="page-title-row">
      <div class="page-title">角色与菜单权限</div>
    </div>

    <el-table :data="tableData.authorList" stripe v-loading="loading" style="width: 100%">
      <el-table-column type="expand">
        <template #default="scope">
          <div v-if="!(scope.row.menus || []).length" class="empty-tip">暂无菜单权限</div>
          <el-row
            v-for="(m, i) in (scope.row.menus || [])"
            :key="m.id"
            :class="['menu-row', i === 0 ? 'top' : '']"
          >
            <el-col :span="4">
              <el-tag class="tag" closable @close="removeMenu(scope.row, m.id)">{{ m.name }}</el-tag>
            </el-col>
            <el-col :span="20">
              <el-tag
                v-for="cm in (m.children || [])"
                :key="cm.id"
                class="tag"
                type="success"
                closable
                @close="removeMenu(scope.row, cm.id)"
              >{{ cm.name }}</el-tag>
            </el-col>
          </el-row>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="desc" label="说明" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="scope">
          <el-button type="primary" size="small" @click="showMenuDialog(scope.row)">分配菜单</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="menuDialogVisible" title="分配菜单权限" width="480px" destroy-on-close>
      <el-tree
        ref="treeRef"
        show-checkbox
        :data="menuList"
        :props="menuProps"
        node-key="id"
        :default-expand-all="true"
      />
      <template #footer>
        <el-button @click="menuDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitMenu">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api/index.js'

const loading = ref(false)
const saving = ref(false)
const tableData = reactive({ authorList: [] })
const menuDialogVisible = ref(false)
const menuList = ref([])
const menuProps = { children: 'children', label: 'name' }
const keyList = ref([])
const treeRef = ref(null)
const rid = ref(null)

const get_author_list = async () => {
  loading.value = true
  try {
    const res = await api.get_roles()
    tableData.authorList = res?.data?.data || []
  } catch (e) {
    ElMessage.error(e?.message || '加载角色失败')
  } finally {
    loading.value = false
  }
}

const getMenuList = async () => {
  try {
    const res = await api.get_menu()
    menuList.value = res?.data?.data || []
  } catch (e) {
    menuList.value = []
  }
}

const removeMenu = async (row, mid) => {
  try {
    await ElMessageBox.confirm('确认删除该角色的此菜单权限？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await api.del_role_menu(row.id, mid)
    if (res?.data?.status === 200) {
      ElMessage.success('已删除')
      get_author_list()
    } else {
      ElMessage.warning(res?.data?.msg || '删除失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '删除失败')
  }
}

const showMenuDialog = (row) => {
  rid.value = row.id
  keyList.value = []
  ;(row.menus || []).forEach((item) => {
    if (item?.id) keyList.value.push(item.id)
    ;(item.children || []).forEach((c) => {
      if (c?.id) keyList.value.push(c.id)
    })
  })
  menuDialogVisible.value = true
  nextTick(() => {
    treeRef.value?.setCheckedKeys?.(keyList.value)
  })
}

const submitMenu = async () => {
  if (!treeRef.value || !rid.value) return
  saving.value = true
  try {
    const mids = [
      ...(treeRef.value.getCheckedKeys?.() || []),
      ...(treeRef.value.getHalfCheckedKeys?.() || []),
    ].join(',')
    const res = await api.set_menu(rid.value, { mids })
    if (res?.data?.status === 200) {
      ElMessage.success('分配成功')
      menuDialogVisible.value = false
      get_author_list()
    } else {
      ElMessage.warning(res?.data?.msg || '分配失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '分配失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  get_author_list()
  getMenuList()
})
</script>

<style scoped>
.page-title-row { margin: 8px 0 14px; }
.empty-tip { color: #8a8478; padding: 8px 16px; font-size: 13px; }
.menu-row { padding: 6px 12px 6px 24px; border-bottom: 1px solid #f0ebe3; }
.menu-row.top { border-top: 1px solid #f0ebe3; }
.tag { margin: 4px 6px 4px 0; }
</style>
