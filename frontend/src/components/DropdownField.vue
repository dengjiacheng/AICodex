<template>
  <label class="dropdown-field">
    <span>{{ label }}</span>
    <div class="dropdown-wrapper" :title="tooltip">
      <select :value="value" @change="$emit('update', ($event.target as HTMLSelectElement).value)">
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    </div>
  </label>
</template>

<script lang="ts" setup>
interface OptionItem {
  value: string;
  label: string;
}

defineProps<{
  label: string;
  value: string;
  options: OptionItem[];
  tooltip?: string;
}>();

defineEmits<{
  (event: 'update', value: string): void;
}>();
</script>

<style scoped>
.dropdown-field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

select {
  border-radius: 8px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  padding: 10px;
  background: transparent;
  color: inherit;
}
</style>
