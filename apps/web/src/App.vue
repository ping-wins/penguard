<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from './stores/useThemeStore'

const themeStore = useThemeStore()

onMounted(() => {
  themeStore.applyTheme()
})
</script>

<template>
  <router-view />
</template>
