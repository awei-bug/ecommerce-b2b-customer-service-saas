<template>
  <div class="page-card">
    <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
      <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
      <el-breadcrumb-item>权限管理</el-breadcrumb-item>
      <el-breadcrumb-item>菜单列表</el-breadcrumb-item>
    </el-breadcrumb>
    <div class="page-title">菜单列表</div>
    <el-table :data="tableData.menuList" stripe v-loading="loading" style="width: 100%; margin-top: 12px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="path" label="路径" min-width="160" />
      <el-table-column prop="level" label="等级" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.level == 1">一级</el-tag>
          <el-tag v-else type="success">二级</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'

const loading = ref(false)
const tableData = reactive({
  menuList: [],
})

const get_menu_list = async () => {
  loading.value = true
  try {
    const res = await api.get_menu_list()
    if (res?.data?.status === 200) {
      tableData.menuList = res.data.data || []
    } else {
      ElMessage.warning(res?.data?.msg || '获取菜单失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '网络错误')
  } finally {
    loading.value = false
  }
}

onMounted(get_menu_list)
</script>
