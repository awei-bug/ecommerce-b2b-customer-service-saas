<template>
    <el-breadcrumb :separator-icon="ArrowRight">
        <el-breadcrumb-item :to="{ path: '/' }">Home</el-breadcrumb-item>
        <el-breadcrumb-item>商品管理</el-breadcrumb-item>
        <el-breadcrumb-item>添加商品</el-breadcrumb-item>
    </el-breadcrumb>
    <el-card class="box-card">
        <el-alert type="success" show-icon :closable="false" style="margin-bottom:12px">
          <template #title>
            也可以让运营助手一句话上架：上架纯棉T恤，89元，库存30
            <el-button type="primary" link @click="$router.push('/agent_ops')">去运营助手</el-button>
            ；图片和文案已经打成 zip 成品包，去商品列表一次上传自动上架。
            <el-button type="primary" link @click="$router.push('/product_list')">去上传成品包</el-button>
          </template>
        </el-alert>
        <el-alert title="下面输入要《添加商品》的信息" type="info" center show-icon />
        <el-steps :active="active" finish-status="success" align-center>
            <el-step title="基本信息" />
            <el-step title="商品静态属性" />
            <el-step title="商品动态属性" />
            <el-step title="商品图片" />
            <el-step title="商品内容" />
            <el-step title="完成" />
        </el-steps>

        <el-tabs tab-position="left" class="el-tabs" v-model="active" :before-leave="beforeLeave">
            <el-form :model="addForm" ref="addFormRef" :rules="addFormRules">
                <el-tab-pane label="基本信息" :name="0">
                    <el-form-item label="商品名称" prop="name">
                        <el-input v-model="addForm.name" />
                    </el-form-item>
                    <el-form-item label="商品价格" prop="price">
                        <el-input v-model="addForm.price" />
                    </el-form-item>
                    <el-form-item label="商品库存" prop="number">
                        <el-input v-model="addForm.number" />
                    </el-form-item>
                    <el-form-item label="商品权重" prop="weight">
                        <el-input v-model="addForm.weight" />
                    </el-form-item>
                    <el-form-item label="商品分类">
                        <el-cascader
                            :options="options.data"
                            :props="props"
                            separator="  >  "
                            clearable
                            v-model="options.selectID"
                            @change="changeSelect"
                            style="width: 300px;"
                        />
                    </el-form-item>
                </el-tab-pane>
                <el-tab-pane label="商品静态属性" :name="1">
                    <el-form-item :label="s.name"  v-for="s in attrData.static" :key="s.id">
                        <el-input v-model="s.val" />
                    </el-form-item>
                </el-tab-pane>
                <el-tab-pane label="商品动态属性" :name="2">
                    <el-form-item :label="d.name"  v-for="d in attrData.dynamic" :key="d.id">
                        <el-checkbox-group v-model="d.val">
                            <el-checkbox :label="v" name="type" v-for="(v,i) in d.val" :key="i" border/>
                        </el-checkbox-group>
                    </el-form-item>
                </el-tab-pane>
                <el-tab-pane label="商品图片" :name="3">
                    <ProductImageUpload v-model="addForm.big_img" v-model:pics="addForm.pics" :limit="6" />
                </el-tab-pane>
                <el-tab-pane label="商品内容" :name="4">
                    <EditorComponent @onDataEvent="getDataHandler"></EditorComponent>
                    <el-button type="primary" @click="addProduct">添加商品</el-button>
                </el-tab-pane>
            </el-form>
        </el-tabs>
    </el-card>
    <el-dialog 
        title="图片预览"  
        v-model="preDialogVisible"
        width="30%">
        <img :src="preImageSrc" class="pre-image">
    </el-dialog>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { ref,reactive,onMounted  } from 'vue'
import api from '../api/index.js'
import base from '@/api/base';
import EditorComponent from '@/components/EditorComponent.vue';
import ProductImageUpload from '@/components/ProductImageUpload.vue'
import { useRouter } from 'vue-router';

const active = ref(0)
// 定义一个表单对象
const addForm = reactive({
    name: '',
    price: '',
    number: '',
    weight: '',
    cid_one:null,
    cid_two:null,
    cid_three:null,
    pics:[],
    big_img: '',
    small_img: '',
    introduce:null,
    attr_static:[],
    attr_dynamic:[]
})
// 定义表单验证规则
const addFormRules = reactive({
    name: [
        { required: true, message: '请输入商品名称', trigger: 'blur' },
        { min: 2, max: 10, message: '长度在 2 到 10 个字符', trigger: 'blur' }
    ],
    price: [
        { required: true, message: '请输入商品价格', trigger: 'blur' },
        { type: 'number', message: '请输入数字值', trigger: 'blur',transform: (value) => Number(value) }
    ],
    number: [
        { required: true, message: '请输入商品库存', trigger: 'blur' },
        { type: 'number', message: '请输入数字值', trigger: 'blur',transform: (value) => Number(value)  }
    ],
    weight: [
        { required: true, message: '请输入商品权重', trigger: 'blur' },
        { type: 'number', message: '请输入数字值', trigger: 'blur',transform: (value) => Number(value)  }
    ]
})
// 创建表单对象
const addFormRef = ref(null)
// 创建一个级联选择器的数据对象
const options = reactive({
        data: [],
        selectID:null
    })
// 定义级联选择器的props
const props = {
    expandTrigger: 'hover',
    label:'name',
    value:'id'
}
// 定义一个属性来存储属性
const attrData = reactive({
    static:[],
    dynamic:[]
})
// 定义一个上传图片的数据对象
const fileList = ref([
])

// 定义一个图片预览是否显示的参数
let preDialogVisible = ref(false)
// 定义一个图片预览的地址
let preImageSrc = ref('')
// 定义路由对象
const router = useRouter()
// 页面加载时获取商品分类数据
onMounted(()=>{
    get_category()
})

// 定义级联选择器的change事件
const changeSelect = (value) => {
    // 判断是否选择了商品分类
    if(options.selectID){
        // 判断选择的分类是否是最后一级
        if(options.selectID.length==3){
            // 更新表单分类的ID
            addForm.cid_one = options.selectID[0]
            addForm.cid_two = options.selectID[1]
            addForm.cid_three = options.selectID[2]
        }
    }
    // 测试addForm的数据
    // console.log(addForm)
  
}
// 获取商品分类数据
const get_category = () =>{
    api.get_category(3).then(res=>{
        options.data = res.data.data
    })
} 
// 定义标签切换时的事件
const beforeLeave = (activeName, oldActiveName) =>{
    // 判断是否选择了第3级分类
    if(options.selectID){
        if (options.selectID.length ==3){
            // 获取静态属性
            getAttr(options.selectID[2],'static')
            getAttr(options.selectID[2],'dynamic')
            return true
        }
    }
    // 提示没有选中分类
    ElMessage({
        type:'warning',
        message:'请选择商品分类'
    })
    return false

}

const getAttr = (s_key,s_type) =>{
    if (s_type == 'static'){
        api.get_attr_by_category(s_key,s_type).then(res=>{
            attrData.static = res.data.data
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
        })
    }
}

const handleSuccess = (response,uploadFile,uploadFiles) =>{
    // console.log(response,uploadFile,uploadFiles)
    if(response.status == 200){
        // 提示上传成功
        ElMessage({
            type:'success',
            message:'上传图片成功'
        })
        // 将图片地址添加到addForm中
        addForm.pics.push(response.data.path)
    }else{
        // 提示上传失败
        ElMessage({
            type:'warning',
            message:'上传图片失败'
        })
    }
}
// 定义删除图片的事件
const handleRemove = (uploadFile, uploadFiles) =>{
   // 要删除的图片的path
   let removePath = uploadFile.response.data.path
   // 获取要删除的图片的索引
   let index = addForm.pics.indexOf(removePath)
   // 要删除的索引
   console.log('删除前的列表:',addForm.pics)
   console.log('要删除的索引:',index)
   //删除addForm中的图片,要删除的索引,要删除的个数
   addForm.pics.splice(index,1)
   console.log('删除后的列表:',addForm.pics)
}

// 定义图片预览的事件
const handlePreview = (uploadFile) =>{
    // console.log(uploadFile)
    // 显示预览框
    preDialogVisible.value = true
    // 修改预览图片的地址
    preImageSrc.value = uploadFile.response.data.url
}
// 定义获取富文本编辑器的内容
const getDataHandler = (value) =>{
    // 将富文本编辑器的内容赋值给addForm
    addForm.introduce = value
}
// 定义提交表单的事件
const addProduct = () => {
    // 将属性信息绑定到addForm中
    addForm.attr_dynamic = attrData.dynamic
    addForm.attr_static = attrData.static
    console.log(addForm)
    // 提交表单
    if (addForm.big_img && !(addForm.pics || []).includes(addForm.big_img)) {
        addForm.pics = [addForm.big_img, ...(addForm.pics || [])]
    }
    if (addForm.big_img) addForm.small_img = addForm.big_img
    api.add_product(addForm).then(res=>{
        console.log(res)
        if(res.data.status == 200){
            // 提示添加成功
            ElMessage({
                type:'success',
                message:res.data.msg
            })
            // 跳转到商品列表页面
            router.push('/product_list')
        }else{
            // 提示添加失败
            ElMessage({
                type:'warning',
                message:'添加商品失败'
            })
        }
    })
}

</script>

<style scoped>
.box-card {
    margin-top: 20px;
}
.el-tabs{
    margin-top: 20px;
}
.pre-image{
    width: 100%;
}
</style>