<template>
  <div class="claim" v-if="orderId">
    <div v-if="claimed" class="done">
      已通知店长核对收款<template v-if="note">（备注：{{ note }}）</template>
      <div v-if="proof" class="proof"><img :src="proofSrc" alt="付款截图" /></div>
    </div>
    <form v-else class="form" @submit.prevent="submit">
      <p class="lead">扫码转账后点这里告诉店长，订单仍要等店长确认到账才会发货。</p>
      <label>转账备注 / 后四位（选填）</label>
      <input v-model="localNote" maxlength="64" placeholder="例如微信转账单号后四位" />
      <label>付款截图（选填）</label>
      <input type="file" accept="image/*" @change="onFile" />
      <p v-if="err" class="err">{{ err }}</p>
      <button class="btn primary" type="submit" :disabled="submitting">
        {{ submitting ? '提交中…' : '我已付款，通知店长' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { claimPaid } from '@/api'
import { mediaUrl } from '@/utils/shop'

const props = defineProps({
  orderId: { type: [String, Number], default: '' },
  claimed: { type: Boolean, default: false },
  note: { type: String, default: '' },
  proof: { type: String, default: '' },
})
const emit = defineEmits(['done'])

const localNote = ref('')
const file = ref(null)
const submitting = ref(false)
const err = ref('')

watch(
  () => props.note,
  (v) => { localNote.value = v || '' },
  { immediate: true },
)

const proofSrc = computed(() => mediaUrl(props.proof))

function onFile(e) {
  file.value = e?.target?.files?.[0] || null
}

async function submit() {
  err.value = ''
  if (!props.orderId) {
    err.value = '缺少订单'
    return
  }
  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('note', String(localNote.value || '').trim())
    if (file.value) fd.append('file', file.value)
    const res = await claimPaid(props.orderId, fd)
    if (!res || res.status !== 200) {
      err.value = (res && res.msg) || '提交失败'
      return
    }
    emit('done', res.data || {})
  } catch (e) {
    err.value = e.message || '提交失败'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.claim { margin-top: 14px; text-align: left; }
.lead { margin: 0 0 10px; font-size: 13px; color: #57534e; line-height: 1.5; }
.form label { display: block; font-size: 12px; font-weight: 700; color: #44403c; margin: 10px 0 6px; }
.form input[type='text'], .form input:not([type='file']) {
  width: 100%; height: 40px; border: 1px solid #e7e5e4; border-radius: 10px; padding: 0 12px; box-sizing: border-box;
}
.form input[type='file'] { font-size: 12px; }
.err { color: #b91c1c; font-size: 12px; margin: 8px 0 0; }
.done { background: #ecfdf5; color: #047857; border-radius: 12px; padding: 12px; font-size: 13px; font-weight: 700; }
.proof { margin-top: 8px; }
.proof img { max-width: 100%; border-radius: 10px; }
.btn { margin-top: 12px; width: 100%; min-height: 44px; }
</style>