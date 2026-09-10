<template>
  <v-container v-if="form" class="narrow-container">
    <BasePageTitle divider>
      <template #header>
        <v-img
          width="100%"
          max-height="100"
          max-width="100"
          src="/svgs/manage-group-settings.svg"
        />
      </template>
      <template #title>
        {{ $t("meal-plan.attendance.settings-title") }}
      </template>
      {{ $t("meal-plan.attendance.settings-description") }}
    </BasePageTitle>

    <v-form @submit.prevent="handleSubmit">
      <v-card variant="outlined" class="mb-4" style="border-color: lightgray;">
        <v-card-text>
          <v-checkbox
            v-model="form.enabled"
            hide-details
            :label="$t('meal-plan.attendance.enable-module')"
            :hint="$t('meal-plan.attendance.enable-module-hint')"
            persistent-hint
          />

          <v-select
            v-model="form.entryTypes"
            class="mt-6"
            :items="entryTypeOptions"
            item-title="text"
            item-value="value"
            multiple
            chips
            variant="outlined"
            density="compact"
            :label="$t('meal-plan.attendance.relevant-meal-types')"
            :hint="$t('meal-plan.attendance.relevant-meal-types-hint')"
            persistent-hint
          />
        </v-card-text>
      </v-card>

      <v-card variant="outlined" class="mb-4" style="border-color: lightgray;">
        <v-card-title class="text-subtitle-1">
          {{ $t("meal-plan.attendance.deadline") }}
        </v-card-title>
        <v-divider class="mx-2" />
        <v-card-text>
          <v-select
            v-model="form.deadlineMode"
            :items="deadlineModeOptions"
            item-title="text"
            item-value="value"
            variant="outlined"
            density="compact"
            :label="$t('meal-plan.attendance.deadline-mode')"
            :hint="deadlineModeHint"
            persistent-hint
          />

          <template v-if="form.deadlineMode === 'weekly'">
            <v-select
              v-model="form.deadlineWeekday"
              class="mt-6"
              :items="weekdayOptions"
              item-title="text"
              item-value="value"
              variant="outlined"
              density="compact"
              :label="$t('meal-plan.attendance.deadline-weekday')"
            />
          </template>

          <template v-else-if="form.deadlineMode === 'relative'">
            <v-number-input
              v-model="form.deadlineLeadDays"
              class="mt-6"
              :min="0"
              :max="60"
              control-variant="stacked"
              variant="outlined"
              density="compact"
              :label="$t('meal-plan.attendance.deadline-lead-days')"
            />
          </template>

          <v-text-field
            v-if="form.deadlineMode !== 'manual'"
            v-model="deadlineTimeInput"
            class="mt-6"
            type="time"
            variant="outlined"
            density="compact"
            :label="$t('meal-plan.attendance.deadline-time')"
          />

          <v-text-field
            v-if="form.deadlineMode !== 'manual'"
            v-model="form.timezone"
            class="mt-6"
            variant="outlined"
            density="compact"
            :label="$t('meal-plan.attendance.timezone')"
            :hint="$t('meal-plan.attendance.timezone-hint')"
            persistent-hint
          />

          <v-checkbox
            v-model="form.autoLock"
            class="mt-4"
            hide-details
            :label="$t('meal-plan.attendance.auto-lock')"
            :hint="$t('meal-plan.attendance.auto-lock-hint')"
            persistent-hint
          />
        </v-card-text>
      </v-card>

      <v-card variant="outlined" style="border-color: lightgray;">
        <v-card-title class="text-subtitle-1">
          {{ $t("meal-plan.attendance.reminders") }}
        </v-card-title>
        <v-divider class="mx-2" />
        <v-card-text>
          <v-checkbox
            v-model="form.reminderEnabled"
            hide-details
            :label="$t('meal-plan.attendance.reminder-enabled')"
            :hint="$t('meal-plan.attendance.reminder-enabled-hint')"
            persistent-hint
          />
          <v-number-input
            v-model="form.reminderHoursBefore"
            class="mt-6"
            :min="1"
            :max="336"
            control-variant="stacked"
            variant="outlined"
            density="compact"
            :disabled="!form.reminderEnabled"
            :label="$t('meal-plan.attendance.reminder-hours-before')"
          />
        </v-card-text>
      </v-card>

      <div class="d-flex pa-2">
        <BaseButton type="submit" edit class="ml-auto" :loading="loading">
          {{ $t("general.update") }}
        </BaseButton>
      </div>
    </v-form>
  </v-container>
</template>

<script setup lang="ts">
import { useMealplanAttendanceSettings } from "~/composables/use-mealplan-attendance";
import type { MealPlanAttendanceSettingsUpdate, PlanEntryType } from "~/lib/api/types/meal-plan";

definePageMeta({
  middleware: ["can-manage-household-only"],
});

const i18n = useI18n();
const { settings, loading, refresh, save } = useMealplanAttendanceSettings();

useSeoMeta({
  title: i18n.t("meal-plan.attendance.settings-title"),
});

const form = ref<MealPlanAttendanceSettingsUpdate | null>(null);

onMounted(async () => {
  await refresh();
});

watch(settings, (value) => {
  if (!value) {
    return;
  }

  const { groupId: _groupId, householdId: _householdId, id: _id, ...rest } = value;
  form.value = { ...rest };
}, { immediate: true });

/**
 * The API works with `HH:MM:SS` while `<input type="time">` wants `HH:MM`, so the two are
 * kept in sync rather than exposing seconds nobody wants to set.
 */
const deadlineTimeInput = computed({
  get: () => (form.value?.deadlineTime ?? "20:00:00").slice(0, 5),
  set: (value: string) => {
    if (form.value) {
      form.value.deadlineTime = `${value}:00`;
    }
  },
});

const deadlineModeHint = computed(() => {
  switch (form.value?.deadlineMode) {
    case "relative":
      return i18n.t("meal-plan.attendance.deadline-mode-relative-hint");
    case "manual":
      return i18n.t("meal-plan.attendance.deadline-mode-manual-hint");
    default:
      return i18n.t("meal-plan.attendance.deadline-mode-weekly-hint");
  }
});

const deadlineModeOptions = computed(() => [
  { text: i18n.t("meal-plan.attendance.deadline-mode-weekly"), value: "weekly" },
  { text: i18n.t("meal-plan.attendance.deadline-mode-relative"), value: "relative" },
  { text: i18n.t("meal-plan.attendance.deadline-mode-manual"), value: "manual" },
]);

// Monday is 0, matching the backend, which follows `datetime.date.weekday()`.
const weekdayOptions = computed(() => [
  { text: i18n.t("general.monday"), value: 0 },
  { text: i18n.t("general.tuesday"), value: 1 },
  { text: i18n.t("general.wednesday"), value: 2 },
  { text: i18n.t("general.thursday"), value: 3 },
  { text: i18n.t("general.friday"), value: 4 },
  { text: i18n.t("general.saturday"), value: 5 },
  { text: i18n.t("general.sunday"), value: 6 },
]);

const entryTypeOptions = computed(() =>
  (["breakfast", "lunch", "dinner", "side", "snack", "drink", "dessert"] as PlanEntryType[]).map(
    value => ({ text: i18n.t(`meal-plan.${value}`), value }),
  ),
);

async function handleSubmit() {
  if (form.value) {
    await save(form.value);
  }
}
</script>
