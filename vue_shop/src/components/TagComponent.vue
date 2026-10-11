<template>
       <el-input
            v-if="inputVisible"
            ref="InputRef"
            v-model="inputValue"
            class="input-tag"
            size="small"
            @blur="handleInputConfirm"
        />
        <el-button v-else class="button-new-tag ml-1" size="small" @click="showInput">
            + 添加值
        </el-button>
</template>

<script setup>
    import { ref, nextTick } from 'vue'

    const inputValue = ref('')
    const inputVisible = ref(false)
    const InputRef = ref(null)
    // 定义事件
    const emit = defineEmits(['addTagEvent'])
    // 定义接收父组件接收参数的值
    const props = defineProps({
        // 传递的参数
        row: {
            type: Object,   // 传递数据的类型
            default: () => Object // 默认值
        }
    })
    const showInput = () => {
        inputVisible.value = true
        nextTick(() => {
            InputRef.value.input.focus() // 获取焦点
        })
    }
    const handleInputConfirm = () => {
        // 触发事件
        emit('addTagEvent', {'inputValue':inputValue.value,'row':props.row})
        // console.log(inputValue.value)
        inputVisible.value = false
        inputValue.value = ''
    }
</script>

<style scoped>
    .input-tag{
        width: 100px;
    }
</style>