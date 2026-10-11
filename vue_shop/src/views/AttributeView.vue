<template>
    <el-breadcrumb :separator-icon="ArrowRight">
        <el-breadcrumb-item :to="{ path: '/' }">Home</el-breadcrumb-item>
        <el-breadcrumb-item>商品管理</el-breadcrumb-item>
        <el-breadcrumb-item>属性列表</el-breadcrumb-item>
    </el-breadcrumb>
    <el-card class="box-card">
        <el-alert title="分类属性只可以选择最后一级！" type="warning" />
        <div>
            <span class="attr_title">选择分类</span>
            <el-cascader
                :options="options.data"
                :props="props"
                separator="  >  "
                clearable
                class="cascader"
                v-model="options.selectID"
                @change="changeSelect"
            />
        </div>
        <div>
            <el-tabs v-model="activeName" class="demo-tabs" @tab-click="handleClick">
                <el-tab-pane label="静态属性" name="static">
                    <el-button type="primary" size="small" :disabled="isButtonVisible" @click="addDialogVisible=true">添加属性</el-button>
                    <el-table :data="attrData.static" >
                        <el-table-column type="index"></el-table-column>
                        <el-table-column label="属性名称" prop="name"></el-table-column>
                        <el-table-column label="属性值" prop="val"></el-table-column>
                        <el-table-column label="操作">
                            <template #default="scope">
                                <el-button type="primary" size="small">编辑</el-button>
                                <el-button type="danger" size="small">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-tab-pane>
                <el-tab-pane label="动态属性" name="dynamic">
                    <el-button type="primary" size="small" :disabled="isButtonVisible" @click="addDialogVisible=true">添加属性</el-button>
                    <el-table :data="attrData.dynamic" row-key="id">
                        <el-table-column type="expand">
                            <template #default="scope">
                                <el-tag class='e-tag' v-for="(v,i) in scope.row.val" closable @close="closeTag(scope.row.id,scope.row.val,i)">{{ v }}</el-tag>
                                <TagComponent @addTagEvent="getTagValue" :row="scope.row"/>
                            </template>
                        </el-table-column>
                        <el-table-column type="index"></el-table-column>
                        <el-table-column label="属性名称" prop="name"></el-table-column>
                        <el-table-column label="操作">
                            <template #default="scope">
                                <el-button type="primary" size="small">编辑</el-button>
                                <el-button type="danger" size="small">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-tab-pane>
            </el-tabs>
        </div>
    </el-card>
    <el-dialog
        :title="dialogTitle"
        width="30%"
        v-model="addDialogVisible"
        :before-close="addDialogClose"
    >
        <el-form :model="addForm" label-width="80px" :rules="addRules" ref="addRef">
            <el-form-item label="属性名" prop="name">
                <el-input v-model="addForm.name"></el-input>
            </el-form-item>
            <el-form-item>
                <el-button type="primary" @click="addAttr">确定</el-button>
                <el-button @click="addDialogVisible=false">取消</el-button>
            </el-form-item>
        </el-form>
    </el-dialog>
</template>

<script setup>
    import { ArrowRight } from '@element-plus/icons-vue'
    import { reactive,onMounted,ref,computed  } from 'vue'
    import api from '../api'

    import TagComponent from '../components/TagComponent.vue'

    const options = reactive({
        data: [],
        selectID:null
    })
    const props = {
        expandTrigger: 'hover',
        label:'name',
        value:'id'
    }
    const activeName = ref('static')

    const attrData = reactive({
        static:[],
        dynamic:[]
    })
    const flag = reactive({
        static:false,  // 静态属性不可以获取
        dynamic:false // 动态属性不可以获取
    })
    const addForm = reactive({
        name:'',
    })
    const addDialogVisible = ref(false)
    const dialogTitle = ref('添加静态属性')
    const addRules = reactive({
        name:[
            {required:true,message:'请输入属性名',trigger:'blur'}
        ]
    })
    const addRef = ref(null)
    let isButtonVisible = computed(()=>{
        //根据级联选择器的值，判断是否可以使用按钮
        if (options.selectID){
            // 判断选择的分类是否为第3级
            if (options.selectID.length === 3){
                return false
            }
        }
        return true
    })

    onMounted(()=>{
        get_category()
    })
    const get_category = () =>{
        api.get_category(3).then(res=>{
            options.data = res.data.data
        })
    }  
    const handleClick = (tab, event) => {
        if (tab.props.name == 'static'){
            dialogTitle.value = '添加静态属性'
        }else if (tab.props.name == 'dynamic'){
            dialogTitle.value = '添加动态属性'
        }
        if (options.selectID){
            if(options.selectID.length === 3){
                let selectKey = options.selectID[2]
                let _type = tab.props.name
                // 根据flag标识判断是否可以获取属性数据
                if (_type == 'static' && !flag.static) return
                if (_type == 'dynamic' && !flag.dynamic) return
                // api.get_attr_by_category(selectKey,_type).then(res=>{
                //     attrData.static = res.data.data
                // })
                get_attr(selectKey,_type)
            }
        }
    }
    const changeSelect = (value) =>{
        if (value){
            if (value.length === 3){
                let selectKey = value[2]
                let _type = activeName.value
                // 设置静态属性可以获取
                flag.static = true
                // 设置动态属性可以获取
                flag.dynamic = true
                get_attr(selectKey,_type)
            }else{
                attrData.static = []
                attrData.dynamic = []   
            }
        }else{
            attrData.static = []
            attrData.dynamic = []
        }  
    }
    const get_attr = (s_key,s_type) =>{
        // console.log(s_key,s_type)
        if (s_type == 'static'){
            console.log('static')
            api.get_attr_by_category(s_key,s_type).then(res=>{
                attrData.static = res.data.data
                // 设置静态属性不可以获取
                flag.static = false
                // console.log(attrData.static)
            })
        }else if (s_type == 'dynamic'){
            // console.log('dynamic')
            api.get_attr_by_category(s_key,s_type).then(res=>{
                // 遍历每个动态属性的值
                res.data.data.forEach(item=>{
                    //  将动态属性的值转换为数组
                    item.val = item.val?item.val.split(','):[]
                })
                attrData.dynamic = res.data.data
                // 设置动态属性不可以获取
                flag.dynamic = false

            })
        }
    }
    const addDialogClose = () =>{
        addRef.value.resetFields()
        addDialogVisible.value = false
    }
    const addAttr = () =>{
        // 获取表单数据
        let params = {
            "name":addForm.name,        // 属性名
            "_type":activeName.value,   // 属性类型
            "cid":options.selectID[2]   // 分类id
        }
        // 调用添加属性接口
        api.add_attribute(params).then(res=>{
            get_attr(options.selectID[2],activeName.value)
            addDialogClose()
        })
    }
    const getTagValue = (val) =>{
        // 属性的类型
        // console.log(activeName.value)
        // // 属性的ID
        // console.log(val.row.id)
        // // 属性的值
        // console.log(val.inputValue)
        // 将新输入的输增加到原来的数组中
        val.row.val.push(val.inputValue)
        // 封装接口所需数据
        let params = {
            '_type':activeName.value,
            'val':val.row.val.join(",")
        }
        // 调用接口
        api.update_attr_value(val.row.id,params).then(res=>{
            ElMessage({
                type:'success',
                message:res.data.msg
            })
        })
    }
    const closeTag = (id,tagList,i) =>{
        // 要更新的属性ID
        // console.log(id)
        // 要更新属性值列表
        // console.log(tagList)
        // 要删除的索引
        // console.log(i)
        // 在列表中删除指定的数据
        tagList.splice(i,1)
        // console.log(tagList)
        // 封装接口所需数据
        let params = {
            "val":tagList.join(',')
        }
        // 调用接口
        api.update_attr_value(id,params).then(res=>{
            ElMessage({
                type:'success',
                message:res.data.msg
            })
        })
    }
</script>
<style scoped>
    .box-card{
            margin-top: 20px;
    }
    .attr_title{
        margin-right: 10px;
    }

    .demo-tabs > .el-tabs__content {
        padding: 32px;
        color: #6b778c;
        font-size: 32px;
        font-weight: 600;
    }
    .e-tag{
        margin: 5px;
    }
</style>