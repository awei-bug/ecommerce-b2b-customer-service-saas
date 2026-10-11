<template>
  <div class="page-card">
  <el-breadcrumb :separator-icon="ArrowRight" class="crumb">
    <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
    <el-breadcrumb-item>员工与权限</el-breadcrumb-item>
    <el-breadcrumb-item>员工列表</el-breadcrumb-item>
  </el-breadcrumb>
  <div class="page-title">员工列表</div>
    <el-row :gutter="12" class="toolbar">
      <el-col :span="8">
        <el-input
            v-model="user_data.queryName"
            placeholder="输入要搜索的账号"
            class="input-with-select"
          >
            <template #append>
              <el-button :icon="Search" @click="searchUser"/>
            </template>
          </el-input>
      </el-col>
      <el-col :span="1">
        <el-button type="primary" :icon="CirclePlus" @click="addDialogVisible=true">增加用户</el-button>
      </el-col>
    </el-row>
    <el-row>
      <el-table :data="user_data.tableData" stripe class="table">
        <el-table-column prop="id" label="id" width="50" />
        <el-table-column prop="name" label="账号" width="100" />
        <el-table-column prop="nick_name" label="昵称" width="100"/>
        <el-table-column prop="phone" label="手机号" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="role_name" label="角色"/>
        <el-table-column label="操作">
          <template #default="scope">
            <el-button 
              size="small" 
              @click="handleEdit(scope.$index, scope.row)"
              >Edit
              </el-button>
            <el-button
              size="small"
              type="danger"
              @click="handleDelete(scope.$index, scope.row)"
              >Delete
              </el-button>
            <el-button
              size="small"
              type="success"
              @click="handleRest(scope.$index, scope.row)"
              >Reset
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-row>

    <el-pagination
        v-model:current-page="user_data.pageNum"
        v-model:page-size="user_data.pageSize"
        :page-sizes="pageSizes"
        :small="small"
        :disabled="disabled"
        :background="background"
        layout="total, sizes, prev, pager, next, jumper"
        :total="user_data.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
        class="table"
      />
  </div>
  <!-- 增加用户对话框 -->
  <el-dialog v-model="addDialogVisible" title="增加用户" :before-close="addFormRest">
    <el-form :model="user_form" :rules="user_rules" ref="addFormRef">
      <el-form-item label="用户名" :label-width="formLabelWidth" prop="name">
        <el-input v-model="user_form.name" autocomplete="off" />
      </el-form-item>
      <el-form-item label="密码" :label-width="formLabelWidth" prop="pwd">
        <el-input v-model="user_form.pwd" autocomplete="off" />
      </el-form-item>
      <el-form-item label="确认密码" :label-width="formLabelWidth" prop="real_pwd">
        <el-input v-model="user_form.real_pwd" autocomplete="off" />
      </el-form-item>
      <el-form-item label="昵称" :label-width="formLabelWidth" prop="nick_name">
        <el-input v-model="user_form.nick_name" autocomplete="off" />
      </el-form-item>
      <el-form-item label="手机号" :label-width="formLabelWidth" prop="phone">
        <el-input v-model="user_form.phone" autocomplete="off" />
      </el-form-item>
      <el-form-item label="邮箱" :label-width="formLabelWidth" prop="email">
        <el-input v-model="user_form.email" autocomplete="off" />
      </el-form-item>
      <el-form-item label="角色" :label-width="formLabelWidth" prop="rold_id">
        <el-select v-model="user_form.role_id" placeholder="请选择角色">
          <el-option :label="r.name" :value="r.id" v-for="r in roles" :key="r.id"/>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="addFormRest">取消</el-button>
        <el-button type="primary" @click="addUser(addFormRef)">
          确定
        </el-button>
      </span>
    </template>
  </el-dialog>
  <!-- 编辑用户 -->
  <el-dialog v-model="editDialogVisible" title="修改用户">
    <el-form :model="edit_form" ref="editFormRef">
      <el-form-item label="用户名" :label-width="formLabelWidth" prop="name">
        <el-input v-model="edit_form.name" autocomplete="off" disabled  />
      </el-form-item>
      <el-form-item label="昵称" :label-width="formLabelWidth" prop="nick_name">
        <el-input v-model="edit_form.nick_name" autocomplete="off" />
      </el-form-item>
      <el-form-item label="手机号" :label-width="formLabelWidth" prop="phone">
        <el-input v-model="edit_form.phone" autocomplete="off" />
      </el-form-item>
      <el-form-item label="邮箱" :label-width="formLabelWidth" prop="email">
        <el-input v-model="edit_form.email" autocomplete="off" />
      </el-form-item>
      <el-form-item label="角色" :label-width="formLabelWidth" prop="rold_id">
        <el-select v-model="edit_form.role_id" placeholder="请选择角色">
          <el-option :label="r.name" :value="r.id" v-for="r in roles" :key="r.id"/>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="editDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="editUser">
          确定
        </el-button>
      </span>
    </template>
  </el-dialog>
  <!-- 删除用户 -->
  <el-dialog v-model="deleteDialogVisible" title="删除用户">
    <span>确定删除账号:{{ remove_user.name }}, 昵称:{{ remove_user.nick_name  }} 的用户吗？</span>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="deleteDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="deleteUser">
          确定
        </el-button>
      </span>
    </template>
  </el-dialog>
  <!-- 重置密码 -->
  <el-dialog v-model="resetDialogVisible" title="????" @closed="tempPassword=''">
    <div v-if="!tempPassword">
      <p>?????? <b>{{ reset_user.name }}</b>?{{ reset_user.nick_name }}?????</p>
      <p style="color:#909399;font-size:13px;margin-top:8px">?????????????????????????????</p>
    </div>
    <div v-else>
      <p>????????????</p>
      <el-input :model-value="tempPassword" readonly style="margin-top:8px">
        <template #append>
          <el-button @click="copyTempPassword">??</el-button>
        </template>
      </el-input>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="resetDialogVisible=false">{{ tempPassword ? '??' : '??' }}</el-button>
        <el-button v-if="!tempPassword" type="primary" :loading="resetLoading" @click="resetPassword">
          ????
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ArrowRight,Search,CirclePlus  } from '@element-plus/icons-vue'
import api from '@/api/index.js'
import { onMounted,reactive,ref } from 'vue';

const user_data = reactive({
  tableData:[],
  total:10,
  pageNum:1,
  pageSize:3,
  queryName:'',
})
const user_form = reactive({
  name: null,
  pwd: null,
  real_pwd: null,
  nick_name: null,
  phone: null,
  email: null,
  rold_id:null,
})
let edit_form = reactive({
  id: null,
  name: null,
  nick_name: null,
  phone: null,
  email: null,
  role_id:null,
})
let remove_user = reactive({
  id: null,
  name: null,
  nick_name:null
})

let reset_user = reactive({
  id: null,
  name: null,
  nick_name:null
})

// 定义验证确认密码的规则
const validatePass2 = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请输入确认密码'))
  } else if (value !== user_form.pwd) {
    callback(new Error("2次密码不匹配!"))
  } else {
    callback()
  }
}

const validatePhone = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请输入手机号'))
  } else if (!/^1[3456789]\d{9}$/.test(value)) {
    callback(new Error("手机号格式不正确!"))
  } else {
    callback()
  }
}

const validateEmail = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请输入邮箱'))
  } else if (!/^([a-zA-Z0-9_-])+@([a-zA-Z0-9_-])+(.[a-zA-Z0-9_-])+/i.test(value)) {
    callback(new Error("邮箱格式不正确!"))
  } else {
    callback()
  }
}
// 用来校验用户表单数据
const user_rules = reactive({
  name:[
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 5, message: '长度在 3 到 5 个字符', trigger: 'blur' }
  ],
  pwd:[
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 3, max: 5, message: '长度在 3 到 5 个字符', trigger: 'blur' }
  ],
  real_pwd:[
    { required: true, message: '请输入确认密码', trigger:   'blur' },
    { validator: validatePass2, trigger: 'blur' }
  ],
  nick_name:[
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 5, message: '长度在 1 到 5 个字符', trigger: 'blur' }
  ],
  phone:[
    { validator: validatePhone, trigger: 'blur' }
  ],
  email:[
    { validator: validateEmail, trigger: 'blur' }
      ],
    })
    let pageSizes =ref([1,2,5,10])
const small = ref(false)
const background = ref(false)
const disabled = ref(false)
const addDialogVisible = ref(false)
const formLabelWidth = '80px'
const addFormRef = ref(null)
const editDialogVisible =ref(false)
const editFormRef = ref(null)
let userID = ref(0)
const deleteDialogVisible = ref(false)
const resetDialogVisible = ref(false)
let roles = ref([])

onMounted(() => {
    get_user_list()
    get_author_list()
})
const get_user_list = () => {
    let params = {
      pageNum: user_data.pageNum,
      pageSize: user_data.pageSize,
      name: user_data.queryName
    }
    api.get_user_list({params}).then(res => {
        //更新用户列表数据
        user_data.tableData = res?.data?.data || []
        //更新分页数据总数
        user_data.total = res?.data?.total || (Array.isArray(res?.data?.data) ? res.data.data.length : 0)
    })
}

const handleSizeChange = (val) => {
  // 修改每页显示多少条数据
  user_data.pageSize = val
  // 重新获取用户列表数据
  get_user_list()
}
const handleCurrentChange = (val) => {
  //修改显示第几页数据
  user_data.pageNum = val
  // 重新获取用户列表数据
  get_user_list()
}

const searchUser = () => {
  //初始化页码
  user_data.pageNum = 1
  // 重新获取用户列表数据
  get_user_list()
}

const addFormRest = () => {
    // 重置表单
    addFormRef.value.resetFields()
    // 关闭对话框
    addDialogVisible.value = false
}

// 添加用户
const addUser = (formRef) => {
  formRef.validate((valid) => {
        if (valid) {
            console.log('验证通过，可以提交')
            api.add_user(user_form).then(res => {
                //根据响应的结果进行处理
                if (res.data.status == 200){
                    ElMessage({
                        message: res.data.msg,
                        type: 'success',
                    })
                    // 重置表单
                    addFormRest()
                    // 重新获取数据
                    get_user_list()
                }else{
                    ElMessage.warning(res.data.msg)
                }
            })
        } else {
            console.log('验证失败')
            return false
        }
    })
}

// 编辑用户
const handleEdit = (index,row) => {
    // 显示编辑对话框
    editDialogVisible.value = true
    // edit_form = row //把当前行的数据赋值给编辑表单
    // 从数据库获取当前用户的数据
    api.get_user_by_id(row.id).then(res => {
        // 把当前行的数据赋值给编辑表单
        // edit_form = res.data.data
        edit_form.name = res.data.data.name
        edit_form.nick_name = res.data.data.nick_name
        edit_form.phone = res.data.data.phone
        edit_form.email = res.data.data.email
        edit_form.role_id = res.data.data.role_id
    })
    userID.value = row.id
} 

// 编辑用户
const editUser= () => {
    api.edit_user(userID.value,edit_form).then(res => {
       if(res.status ==200){
          ElMessage({
                        message: res.data.msg,
                        type: 'success',
          })
          editDialogVisible.value = false
          get_user_list()
       }else{
          ElMessage.warning(res.data.msg)
       }
    })
}

// 删除用户控制器
const handleDelete =(index,row) =>{
  remove_user.id = row.id
  remove_user.name = row.name
  remove_user.nick_name = row.nick_name
  deleteDialogVisible.value = true
}
// 删除用户操作
const deleteUser = () =>{
  // 请求删除用户的API调用
  api.delete_user(remove_user.id).then(res => {
    if(res.status == 200){
      ElMessage({
        message: res.data.msg,
        type: 'success',
      })
      deleteDialogVisible.value = false
      get_user_list()
    }else{
      ElMessage.warning(res.data.msg)
    }
  })
}

// 显示重置密码对话框
const handleRest = (index,row) =>{
  tempPassword.value = ''
  resetDialogVisible.value = true
  reset_user.id = row.id
  reset_user.name = row.name
  reset_user.nick_name = row.nick_name
}
// 重置密码操作
const resetPassword = () => {
  resetLoading.value = true
  api.reset_user_password(reset_user.id).then(res => {
    if (res.status == 200) {
      const pwd = res.data?.data?.temp_password || res.data?.data?.password || ''
      tempPassword.value = pwd
      ElMessage({
        message: pwd ? '??????????????' : (res.data.msg || '????'),
        type: 'success',
      })
      get_user_list()
    } else {
      ElMessage.warning(res.data.msg)
    }
  }).finally(() => {
    resetLoading.value = false
  })
}
const copyTempPassword = async () => {
  try {
    await navigator.clipboard.writeText(tempPassword.value || '')
    ElMessage.success('???????')
  } catch (e) {
    ElMessage.warning('????????????')
  }
}
// 获取角色列表
const get_author_list = () => {
    api.get_roles().then(res => {
      roles.value = res?.data?.data || []
    })
}
</script>

<style scoped>
  .crumb { margin-bottom: 12px; }
  .page-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
  .toolbar { margin-bottom: 4px; }
  .table{
    margin-top: 10px;
  }
</style>