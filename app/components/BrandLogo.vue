<template>
  <span class="inline-flex items-center" :class="compact ? 'gap-2' : 'gap-2.5'">
    <svg
      :width="size"
      :height="size"
      viewBox="0 0 32 32"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      class="shrink-0"
    >
      <path d="M16 1.5 28.5 8.75v14.5L16 30.5 3.5 23.25V8.75Z" class="fill-brand-600" />
      <path
        d="M12 9.5h5.2c4.4 0 7.3 2.6 7.3 6.5s-2.9 6.5-7.3 6.5H12Zm4.9 9.6c2.4 0 4-1.2 4-3.1s-1.6-3.1-4-3.1h-1.5v6.2Z"
        class="fill-white"
      />
    </svg>
    <span v-if="!markOnly" class="flex flex-col leading-tight">
      <span class="font-semibold tracking-tight" :class="compact ? 'text-sm' : 'text-base'">{{ productName }}</span>
      <span
        v-if="!compact && tagline"
        class="text-[11px] uppercase tracking-wider text-faint"
      >{{ tagline }}</span>
    </span>
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: number
    markOnly?: boolean
    compact?: boolean
    productName?: string
    tagline?: string
  }>(),
  { size: 30, markOnly: false, compact: false, productName: 'DecOps', tagline: 'Interdec Operations' },
)
</script>
