<template>
  <div class="page agent-page">
    <AgentPanel variant="page" :show-head="true" />
  </div>
</template>

<script setup>
import AgentPanel from '@/components/AgentPanel.vue'
</script>

<style scoped>
.agent-page {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  min-height: 70vh;
}
</style>