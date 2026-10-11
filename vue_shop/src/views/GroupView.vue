<template>
    <el-breadcrumb :separator-icon="ArrowRight">
        <el-breadcrumb-item :to="{ path: '/' }">Home</el-breadcrumb-item>
        <el-breadcrumb-item>商品管理</el-breadcrumb-item>
        <el-breadcrumb-item>分类列表</el-breadcrumb-item>
    </el-breadcrumb>
    <el-card class="box-card">
        <el-row>
            <el-button type="primary" icon="CirclePlus" @click="addCateDialog">添加分类</el-button>
        </el-row>
        <el-row>
            <el-table
                :data="tableData.data"
                style="width: 100%; margin-bottom: 20px"
                row-key="id"
                border
                >
                <el-table-column prop="id" label="ID" sortable />
                <el-table-column prop="name" label="分类名称" sortable />
                <el-table-column prop="level" label="分类等级" sortable>
                    <template #default="scope">
                        <el-tag v-if="scope.row.level == 1" type="success">一级分类</el-tag>
                        <el-tag v-else-if="scope.row.level ==2" type="primary">二级分类</el-tag>
                        <el-tag v-else-if="scope.row.level ==3" type="warning">三级分类</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="操作">
                    <template #default="scope">
                        <el-button type="primary" size="small" :icon="Edit">编辑</el-button>
                        <el-button type="danger" size="small" :icon="Delete">删除</el-button>
                    </template>
                </el-table-column>
            </el-table>
        </el-row>
    </el-card>
    <!-- 增加分类-->
    <el-dialog v-model="addDialogVisible" title="增加分类">
        <el-form :model="addForm" :rules="addRules" ref="addFormRef">
            <el-form-item label="分类名称" prop="name">
                <el-input v-model="addForm.name"></el-input>
            </el-form-item>
            <el-form-item label="父类节点" prop="pid">
                <el-cascader
                    v-model="value"
                    :options="options.data"
                    :props="props"
                    @change="handleChange"
                    separator="  >  "
                    clearable
                />
            </el-form-item>
            <el-form-item>
                <el-button type="primary" @click="addCate">确定</el-button>
                <el-button @click="addDialogVisible = false">取消</el-button>
            </el-form-item>
        </el-form>

    </el-dialog>
</template>

<script setup>
    import { ArrowRight } from '@element-plus/icons-vue'
    import { reactive,onMounted,ref } from 'vue'
    import { Delete, Edit } from '@element-plus/icons-vue'

    import api from '@/api/index.js'
    
    const tableData= reactive({
        data:[]
    })
    onMounted(()=>{
        get_category()
        get_options()
    })
    let addDialogVisible = ref(false)
    const addForm = reactive({
        name: '',
        pid: 0,
        level:1,
    })
    let addRules = reactive({
        name: [
            { required: true, message: '请输入分类名称', trigger: 'blur' },
        ],
    })
    const value = ref([])
    const props = {
        expandTrigger: 'hover',
        label:'name',
        value:'id',
        checkStrictly: true,
    }
    const options = reactive({
        data:[]
    })
    const get_category = () => {
        api.get_category(3).then(res=>{
            tableData.data = res.data.data
            console.log(tableData.data)
        })
    } 
    const addCateDialog = () => {
        addDialogVisible.value = true
    }
    const handleChange = (value) => {
        if (value){
            if(value.length==1){
                addForm.pid = value[0]
                addForm.level= 2
            }else if(value.length==2){
                addForm.pid = value[1]
                addForm.level = 3
            }
        }else{
            addForm.pid=0
            addForm.level = 1
        }
        console.log(addForm)
    }
    const get_options = () => {
        api.get_category(2).then(res=>{
            options.data  = res.data.data
        })
    }
    const addCate = () => {
        api.add_category(addForm).then(res=>{
            addDialogVisible.value = false
            get_category()
            get_options()
        })
    }
</script>
<style scoped>
    .box-card{
        margin-top: 20px;
    }
</style>