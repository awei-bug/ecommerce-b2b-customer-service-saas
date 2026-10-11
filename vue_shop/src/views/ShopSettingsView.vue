<template>
  <div class="page-card">
    <div class="head">
      <div>
        <h2>店铺设置</h2>
        <p class="sub">店名、个人收款码、付款说明、皮肤与登录密码</p>
      </div>
      <el-tag :type="form.status === 1 ? 'success' : 'info'" effect="plain">
        {{ form.status === 1 ? '营业中' : '暂停营业' }}
      </el-tag>
    </div>

    <el-form label-width="120px" v-loading="loading" style="max-width: 760px">
      <el-divider content-position="left">基本信息</el-divider>
      <el-form-item label="店铺名称">
        <el-input v-model="form.name" maxlength="64" show-word-limit />
      </el-form-item>
      <el-form-item label="店铺标识">
        <el-input :model-value="form.slug" disabled />
      </el-form-item>
      <el-form-item label="营业状态">
        <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="营业中" inactive-text="暂停" />
      </el-form-item>
      <el-form-item label="联系电话">
        <el-input v-model="form.contact_phone" maxlength="32" placeholder="顾客联系电话" />
      </el-form-item>
      <el-form-item label="商城皮肤">
        <el-select v-model="form.theme" style="width: 100%">
          <el-option label="综合零售" value="retail" />
          <el-option label="茶饮滋补" value="tea" />
          <el-option label="服饰穿搭" value="fashion" />
          <el-option label="数码电器" value="digital" />
        </el-select>
      </el-form-item>

      <el-divider content-position="left">个人收款（无商户号）</el-divider>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="顾客扫码转账并备注订单号 → 订单里点「确认收款」→ 发货。勿宣传官方自动支付。"
      />
      <el-form-item label="微信收款码">
        <ProductImageUpload v-model="form.pay_qr_wechat" :limit="1" />
      </el-form-item>
      <el-form-item label="支付宝收款码">
        <ProductImageUpload v-model="form.pay_qr_alipay" :limit="1" />
      </el-form-item>
      <el-form-item label="付款说明">
        <el-input v-model="form.pay_guide" type="textarea" :rows="8" />
        <div class="field-tip">
          <el-button link type="primary" @click="applyDefaultGuide">填入推荐模板</el-button>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
        <el-button @click="load">重新加载</el-button>
        <el-button type="warning" plain @click="openPwd">修改登录密码</el-button>
      </el-form-item>
    </el-form>

    <el-dialog v-model="pwdVisible" title="修改登录密码" width="420px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_pwd" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_pwd" type="password" show-password placeholder="至少 6 位，不能是 123456" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="submitPwd">确定</el-button>
      </template>
    </el-dialog>

    <el-alert
      class="tip"
      type="warning"
      show-icon
      :closable="false"
      title="上线前"
      description="上传收款码、改掉默认密码，并定期执行 deploy/win/backup_mysql_local.bat 备份。"
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'
import ProductImageUpload from '@/components/ProductImageUpload.vue'

const DEFAULT_GUIDE = `【个人收款付款说明】
1. 请使用微信或支付宝扫描下方「店铺收款码」完成转账
2. 转账金额请与订单应付金额一致
3. 备注栏请务必填写「订单号」（下单成功页 / 订单详情可见）
4. 店长核对到账后，会将订单更新为已付款并安排发货
5. 如有疑问请联系店主（见页面客服电话）

说明：本店为人工确认收款，非微信/支付宝官方自动扣款。`

const loading = ref(false)
const saving = ref(false)
const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdForm = reactive({ old_pwd: '', new_pwd: '' })
const form = reactive({
  name: '',
  slug: '',
  contact_phone: '',
  pay_guide: '',
  status: 1,
  theme: 'retail',
  pay_qr_wechat: '',
  pay_qr_alipay: '',
})

const applyDefaultGuide = () => {
  form.pay_guide = DEFAULT_GUIDE
  ElMessage.success('已填入推荐模板')
}

const openPwd = () => {
  pwdForm.old_pwd = ''
  pwdForm.new_pwd = ''
  pwdVisible.value = true
}

const load = () => {
  loading.value = true
  api.get_shop_settings()
    .then((res) => {
      if (res?.data?.status === 200) {
        const d = res.data.data || {}
        form.name = d.name || ''
        form.slug = d.slug || ''
        form.contact_phone = d.contact_phone || ''
        form.pay_guide = d.pay_guide || DEFAULT_GUIDE
        form.theme = d.theme || 'retail'
        form.status = d.status === 0 ? 0 : 1
        form.pay_qr_wechat = d.pay_qr_wechat || ''
        form.pay_qr_alipay = d.pay_qr_alipay || ''
      } else ElMessage.warning(res?.data?.msg || '加载失败')
    })
    .finally(() => { loading.value = false })
}

const save = () => {
  if (!form.name) return ElMessage.warning('店铺名称不能为空')
  saving.value = true
  api.update_shop_settings({
    name: form.name,
    contact_phone: form.contact_phone,
    pay_guide: form.pay_guide,
    theme: form.theme || 'retail',
    status: form.status,
    pay_qr_wechat: form.pay_qr_wechat || '',
    pay_qr_alipay: form.pay_qr_alipay || '',
  })
    .then((res) => {
      if (res?.data?.status === 200) {
        ElMessage.success('保存成功')
        load()
      } else ElMessage.warning(res?.data?.msg || '保存失败')
    })
    .finally(() => { saving.value = false })
}

const submitPwd = async () => {
  if (!pwdForm.old_pwd || !pwdForm.new_pwd) return ElMessage.warning('请填写原密码和新密码')
  pwdSaving.value = true
  try {
    const res = await api.change_password({ old_pwd: pwdForm.old_pwd, new_pwd: pwdForm.new_pwd })
    const body = res?.data?.status != null ? res.data : res
    if (body?.status === 200) {
      ElMessage.success(body.msg || '密码已修改')
      try { sessionStorage.removeItem('password_is_default') } catch (_) {}
      pwdVisible.value = false
    } else ElMessage.warning(body?.msg || '修改失败')
  } finally {
    pwdSaving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
h2 { margin: 0 0 6px; font-size: 18px; }
.sub { margin: 0; color: #8a8f99; font-size: 13px; }
.field-tip { margin-top: 6px; color: #8a8f99; font-size: 12px; }
.tip { margin-top: 20px; max-width: 760px; }
</style>
