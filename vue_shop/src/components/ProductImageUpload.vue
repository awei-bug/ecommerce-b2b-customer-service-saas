<template>
  <div class="img-upload">
    <div class="tips">
      <strong>商品主图</strong>
      <span>建议 800×800，jpg/png/webp，单张 ≤ 5MB。第一张将作为商城封面。</span>
    </div>

    <el-upload
      class="uploader"
      drag
      list-type="picture-card"
      :action="uploadAction"
      :headers="uploadHeaders"
      :file-list="fileList"
      :limit="limit"
      :multiple="limit > 1"
      accept="image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp"
      :before-upload="beforeUpload"
      :on-success="onSuccess"
      :on-error="onError"
      :on-remove="onRemove"
      :on-preview="onPreview"
      :on-exceed="onExceed"
      :class="{ 'is-full': fileList.length >= limit }"
    >
      <div class="upload-inner">
        <el-icon class="el-icon--upload"><Plus /></el-icon>
        <div class="el-upload__text">拖拽到此处，或 <em>点击上传</em></div>
      </div>
      <template #tip>
        <div class="el-upload__tip">支持拖拽；上传成功后右侧可预览。无图时商城会显示「待上传主图」。</div>
      </template>
    </el-upload>

    <div v-if="modelValue" class="cover-row">
      <span class="label">当前封面</span>
      <el-image :src="displayUrl(modelValue)" fit="cover" class="cover-thumb">
        <template #error><div class="img-err">无预览</div></template>
      </el-image>
      <code class="path">{{ modelValue }}</code>
      <el-button link type="danger" @click="clearAll">清除</el-button>
    </div>

    <el-dialog v-model="previewVisible" title="图片预览" width="480px" append-to-body>
      <img v-if="previewUrl" :src="previewUrl" class="preview-img" alt="preview" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import base from '@/api/base'

const props = defineProps({
  /** 封面 path，如 /static/upload/1/xxx.jpg */
  modelValue: { type: String, default: '' },
  /** 附图 path 列表 */
  pics: { type: Array, default: () => [] },
  limit: { type: Number, default: 5 },
})
const emit = defineEmits(['update:modelValue', 'update:pics'])

const fileList = ref([])
const previewVisible = ref(false)
const previewUrl = ref('')

const uploadAction = computed(() => `${base.baseURL || ''}${base.upload_img}`)
const uploadHeaders = computed(() => {
  const token = sessionStorage.getItem('token') || ''
  return token ? { token } : {}
})

function displayUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return path
  // 开发环境走同域代理；生产同域
  return path.startsWith('/') ? path : `/${path}`
}

function syncFromProps() {
  const paths = []
  if (props.modelValue) paths.push(props.modelValue)
  for (const p of props.pics || []) {
    if (p && !paths.includes(p)) paths.push(p)
  }
  fileList.value = paths.map((p, i) => ({
    name: `img-${i + 1}`,
    url: displayUrl(p),
    status: 'success',
    path: p,
    response: { status: 200, data: { path: p, url: displayUrl(p) } },
  }))
}

watch(() => [props.modelValue, props.pics], syncFromProps, { immediate: true, deep: true })

function emitPaths(list) {
  const paths = list
    .map((f) => f.path || f.response?.data?.path)
    .filter(Boolean)
  emit('update:modelValue', paths[0] || '')
  emit('update:pics', paths)
}

function beforeUpload(file) {
  const okType = /image\/(jpeg|png|gif|webp)/i.test(file.type) || /\.(jpe?g|png|gif|webp)$/i.test(file.name)
  if (!okType) {
    ElMessage.warning('仅支持 jpg / png / gif / webp')
    return false
  }
  const max = 5 * 1024 * 1024
  if (file.size > max) {
    ElMessage.warning('单张图片不能超过 5MB')
    return false
  }
  return true
}

function onSuccess(response, uploadFile, uploadFiles) {
  const body = response || {}
  if (body.status !== 200) {
    ElMessage.warning(body.msg || '上传失败')
    // 从列表移除失败项
    const idx = uploadFiles.indexOf(uploadFile)
    if (idx >= 0) uploadFiles.splice(idx, 1)
    fileList.value = [...uploadFiles]
    return
  }
  const path = body.data?.path
  uploadFile.path = path
  uploadFile.url = displayUrl(body.data?.url || path)
  fileList.value = uploadFiles.map((f) => {
    const p = f.path || f.response?.data?.path
    return { ...f, path: p, url: displayUrl(f.url || f.response?.data?.url || p) }
  })
  emitPaths(fileList.value)
  ElMessage.success('上传成功')
}

function onError() {
  ElMessage.error('上传失败，请确认已登录且后端可用')
}

function onRemove(uploadFile, uploadFiles) {
  fileList.value = uploadFiles
  emitPaths(uploadFiles)
}

function onPreview(file) {
  previewUrl.value = file.url || displayUrl(file.path || file.response?.data?.path)
  previewVisible.value = true
}

function onExceed() {
  ElMessage.warning(`最多上传 ${props.limit} 张`)
}

function clearAll() {
  fileList.value = []
  emit('update:modelValue', '')
  emit('update:pics', [])
}
</script>

<style scoped>
.img-upload { width: 100%; }
.tips {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #64748b;
}
.tips strong { color: #0f766e; font-size: 14px; }
.uploader :deep(.el-upload-dragger) {
  padding: 16px;
  height: auto;
}
.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: #64748b;
}
.cover-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f0fdfa;
  border: 1px dashed #99f6e4;
  border-radius: 10px;
}
.cover-row .label { font-weight: 600; color: #0f766e; font-size: 13px; }
.cover-thumb { width: 56px; height: 56px; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; }
.path {
  font-size: 12px;
  color: #64748b;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-img { width: 100%; display: block; border-radius: 8px; }
.img-err {
  width: 56px; height: 56px; display: grid; place-items: center;
  background: #f1f5f9; color: #94a3b8; font-size: 12px;
}
.is-full :deep(.el-upload--picture-card) { display: none; }
</style>
