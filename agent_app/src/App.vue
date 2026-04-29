<template>
  <div class="app-root">
    <router-view v-slot="{ Component, route }">
      <transition name="fade" mode="out-in">
        <component v-if="Component" :is="Component" :key="route.fullPath" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
</script>

<style scoped>
.app-root {
  width: var(--desktop-canvas-width);
  min-width: var(--desktop-canvas-width);
  max-width: var(--desktop-canvas-width);
  height: var(--desktop-canvas-height);
  min-height: var(--desktop-canvas-height);
  max-height: var(--desktop-canvas-height);
  position: relative;
  isolation: isolate;
  overflow: hidden;
}

.app-root::before {
  content: '';
  position: fixed;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.26), rgba(255, 255, 255, 0.06) 30%, rgba(255, 255, 255, 0.14) 100%);
  pointer-events: none;
  z-index: -1;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
