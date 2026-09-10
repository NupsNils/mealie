<template>
  <v-btn-toggle
    :model-value="attendee.status"
    :disabled="disabled"
    density="compact"
    variant="outlined"
    divided
    mandatory
    @update:model-value="value => value && emit('change', value as AttendanceStatus)"
  >
    <v-btn value="attending" size="small" color="success">
      <v-icon :icon="$globals.icons.check" />
      <v-tooltip activator="parent" location="top">
        {{ $t("meal-plan.attendance.eating-along") }}
      </v-tooltip>
    </v-btn>
    <v-btn value="declined" size="small" color="error">
      <v-icon :icon="$globals.icons.close" />
      <v-tooltip activator="parent" location="top">
        {{ $t("meal-plan.attendance.not-eating-along") }}
      </v-tooltip>
    </v-btn>
    <v-btn value="undecided" size="small">
      <v-icon :icon="$globals.icons.help" />
      <v-tooltip activator="parent" location="top">
        {{ $t("meal-plan.attendance.undecided") }}
      </v-tooltip>
    </v-btn>
  </v-btn-toggle>
</template>

<script setup lang="ts">
import type { AttendanceStatus, MealPlanAttendeeSummary } from "~/lib/api/types/meal-plan";

defineProps<{
  attendee: MealPlanAttendeeSummary;
  disabled: boolean;
}>();

const emit = defineEmits<{
  change: [status: AttendanceStatus];
}>();
</script>
