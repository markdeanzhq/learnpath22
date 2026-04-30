<template>
  <div class="graph-legend-wrap">
    <div class="legend-section">
      <span class="legend-title">节点颜色</span>
      <div class="legend-items">
        <span v-for="item in categoryLegend" :key="item.key" class="legend-chip">
          <span class="legend-dot" :style="{ backgroundColor: item.color }"></span>
          <span>{{ item.label }}</span>
        </span>
      </div>
    </div>

    <div class="legend-section">
      <span class="legend-title">关系说明</span>
      <div class="legend-items">
        <span v-for="item in relationLegend" :key="item.type" class="legend-chip legend-chip-edge">
          <span
            class="legend-line"
            :class="[
              item.lineStyle === 'dashed' ? 'legend-line-dashed' : 'legend-line-solid',
              item.hasArrow ? 'legend-line-arrow' : '',
            ]"
          ></span>
          <span>{{ item.label }}：{{ item.description }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type CategoryLegendItem = {
  key: string
  label: string
  color: string
}

type RelationLegendItem = {
  type: string
  label: string
  description: string
  lineStyle: 'solid' | 'dashed'
  hasArrow: boolean
}

defineProps<{
  categoryLegend: readonly CategoryLegendItem[]
  relationLegend: readonly RelationLegendItem[]
}>()
</script>

<style scoped>
.graph-legend-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}

.legend-section {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-title {
  color: #606266;
  font-size: 12px;
  font-weight: 600;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #ebeef5;
  border-radius: 999px;
  color: #606266;
  font-size: 12px;
  background: #fafafa;
}

.legend-chip-edge {
  max-width: 100%;
}

.legend-dot {
  flex: 0 0 auto;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  position: relative;
  display: inline-block;
  flex: 0 0 auto;
  width: 28px;
  height: 0;
  border-top: 2px solid #909399;
}

.legend-line-dashed {
  border-top-style: dashed;
}

.legend-line-solid {
  border-top-style: solid;
}

.legend-line-arrow::after {
  content: '';
  position: absolute;
  top: -5px;
  right: -2px;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 7px solid #909399;
}

@media (max-width: 768px) {
  .graph-legend-wrap {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
