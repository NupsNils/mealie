<template>
  <v-card variant="outlined" class="mb-4" style="border-color: lightgray;">
    <v-card-title class="d-flex flex-wrap align-center ga-2 py-3">
      <div>
        <div class="text-subtitle-1 font-weight-medium">
          {{ mealTitle }}
        </div>
        <div class="text-caption text-medium-emphasis">
          {{ $d(mealDate, "short") }} &middot; {{ $t(`meal-plan.${meal.entryType}`) }}
        </div>
      </div>

      <v-spacer />

      <v-chip
        v-if="meal.isLocked"
        size="small"
        color="error"
        variant="tonal"
        :prepend-icon="$globals.icons.lock"
      >
        {{ $t("meal-plan.attendance.closed") }}
      </v-chip>
      <v-chip
        v-else-if="meal.deadlineAt"
        size="small"
        :color="deadlineIsNear ? 'warning' : undefined"
        variant="tonal"
        :prepend-icon="$globals.icons.clockOutline"
      >
        {{ $t("meal-plan.attendance.answer-by", [$d(new Date(meal.deadlineAt), "medium")]) }}
      </v-chip>
    </v-card-title>

    <v-divider />

    <v-card-text>
      <!-- Portions: the whole point of collecting answers. -->
      <div class="d-flex flex-wrap ga-4 mb-4">
        <div>
          <div class="text-h6">
            {{ meal.attendeeCount ?? 0 }}
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ $t("meal-plan.attendance.confirmations") }}
          </div>
        </div>
        <div v-if="meal.recipeServings">
          <div class="text-h6">
            {{ formatScale(meal.scaleFactor ?? 1) }}&times;
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ $t("meal-plan.attendance.recipe-serves", [meal.recipeServings]) }}
          </div>
        </div>
        <div v-if="meal.pendingResponseCount">
          <div class="text-h6 text-warning">
            {{ meal.pendingResponseCount }}
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ $t("meal-plan.attendance.still-missing") }}
          </div>
        </div>
      </div>

      <v-alert
        v-if="!meal.recipeServings && meal.recipeId"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-4"
        :text="$t('meal-plan.attendance.no-recipe-yield')"
      />

      <!-- One block per person, with their guests underneath. -->
      <div v-for="group in attendeeGroups" :key="group.person.participantId" class="mb-2">
        <div class="d-flex align-center ga-2 flex-wrap">
          <v-icon size="small" :icon="$globals.icons.user" />
          <span class="font-weight-medium">{{ group.person.participantName }}</span>

          <v-chip
            v-if="group.person.isAbsent"
            size="x-small"
            variant="tonal"
            color="info"
          >
            {{ $t(`meal-plan.attendance.absence-reason.${group.person.absenceReason ?? "away"}`) }}
          </v-chip>
          <v-chip
            v-else-if="!group.person.hasResponded"
            size="x-small"
            variant="tonal"
            color="warning"
          >
            {{ $t("meal-plan.attendance.no-answer-yet") }}
          </v-chip>

          <v-spacer />

          <HouseholdMealAttendanceToggle
            :attendee="group.person"
            :disabled="meal.isLocked || !canAnswerFor(group.person)"
            @change="status => emitAnswer(group.person, status)"
          />
        </div>

        <div
          v-for="guest in group.guests"
          :key="guest.participantId"
          class="d-flex align-center ga-2 flex-wrap ml-8"
        >
          <span class="text-body-2 text-medium-emphasis">{{ guest.participantName }}</span>
          <v-chip
            v-if="guest.isAbsent"
            size="x-small"
            variant="tonal"
            color="info"
          >
            {{ $t(`meal-plan.attendance.absence-reason.${guest.absenceReason ?? "away"}`) }}
          </v-chip>

          <v-spacer />

          <HouseholdMealAttendanceToggle
            :attendee="guest"
            :disabled="meal.isLocked || !canAnswerFor(guest)"
            @change="status => emitAnswer(guest, status)"
          />
        </div>
      </div>

      <!-- Who cooks, who shops, and a manual portion count. Household managers only. -->
      <template v-if="canManage">
        <v-divider class="my-4" />

        <div class="d-flex flex-wrap ga-3">
          <v-select
            :model-value="meal.cookParticipantId"
            :items="participantOptions"
            item-title="name"
            item-value="id"
            :label="$t('meal-plan.attendance.who-cooks')"
            :prepend-inner-icon="$globals.icons.chefHat"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            style="min-width: 200px;"
            @update:model-value="value => emitDetails({ cookParticipantId: value ?? null })"
          />
          <v-select
            :model-value="meal.shopperParticipantId"
            :items="participantOptions"
            item-title="name"
            item-value="id"
            :label="$t('meal-plan.attendance.who-shops')"
            :prepend-inner-icon="$globals.icons.cartCheck"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            style="min-width: 200px;"
            @update:model-value="value => emitDetails({ shopperParticipantId: value ?? null })"
          />
          <v-number-input
            :model-value="meal.servingsOverride ?? undefined"
            :min="0"
            :label="$t('meal-plan.attendance.portion-override')"
            density="compact"
            variant="outlined"
            control-variant="stacked"
            hide-details
            clearable
            style="min-width: 180px;"
            @update:model-value="value => emitDetails({ servingsOverride: value ?? null })"
          />
        </div>
      </template>
    </v-card-text>

    <v-card-actions v-if="canManage">
      <v-spacer />
      <BaseButton
        v-if="meal.isLocked"
        variant="text"
        :icon="$globals.icons.refresh"
        @click="emit('unlock', meal.mealplanId)"
      >
        {{ $t("meal-plan.attendance.reopen") }}
      </BaseButton>
      <BaseButton
        v-else
        variant="text"
        :icon="$globals.icons.lock"
        @click="emit('lock', meal.mealplanId)"
      >
        {{ $t("meal-plan.attendance.close-now") }}
      </BaseButton>
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
import HouseholdMealAttendanceToggle from "./HouseholdMealAttendanceToggle.vue";
import { groupAttendees } from "~/composables/use-mealplan-attendance";
import type {
  AttendanceStatus,
  MealPlanAttendanceSummary,
  MealPlanAttendeeSummary,
  MealPlanEntryDetailsUpdate,
  MealPlanParticipantOut,
} from "~/lib/api/types/meal-plan";

const props = defineProps<{
  meal: MealPlanAttendanceSummary;
  participants: MealPlanParticipantOut[];
  /** The signed-in user, so people can only answer for themselves and their own guests. */
  currentUserId: string | undefined;
  canManage: boolean;
}>();

const emit = defineEmits<{
  answer: [mealplanId: number, participantId: string, status: AttendanceStatus];
  details: [mealplanId: number, payload: MealPlanEntryDetailsUpdate];
  lock: [mealplanId: number];
  unlock: [mealplanId: number];
}>();

const i18n = useI18n();

const mealDate = computed(() => new Date(props.meal.date));

const mealTitle = computed(
  () => props.meal.recipeName || props.meal.title || i18n.t(`meal-plan.${props.meal.entryType}`),
);

const attendeeGroups = computed(() => groupAttendees(props.meal.attendees ?? []));

const participantOptions = computed(() => props.participants.filter(participant => participant.active !== false));

const deadlineIsNear = computed(() => {
  if (!props.meal.deadlineAt) {
    return false;
  }
  const hoursLeft = (new Date(props.meal.deadlineAt).getTime() - Date.now()) / 3_600_000;
  return hoursLeft <= 24;
});

/**
 * Everyone answers for themselves and for the guests they own. Household managers may
 * fill in for anybody, which is what happens when somebody phones it in.
 */
function canAnswerFor(attendee: MealPlanAttendeeSummary): boolean {
  if (props.canManage) {
    return true;
  }
  if (attendee.userId && attendee.userId === props.currentUserId) {
    return true;
  }
  if (!attendee.parentId) {
    return false;
  }

  const owner = props.participants.find(participant => participant.id === attendee.parentId);
  return !!owner?.userId && owner.userId === props.currentUserId;
}

function emitAnswer(attendee: MealPlanAttendeeSummary, status: AttendanceStatus) {
  emit("answer", props.meal.mealplanId, attendee.participantId, status);
}

function emitDetails(payload: MealPlanEntryDetailsUpdate) {
  emit("details", props.meal.mealplanId, {
    deadlineAt: props.meal.deadlineAt,
    locked: props.meal.isLocked,
    servingsOverride: props.meal.servingsOverride,
    cookParticipantId: props.meal.cookParticipantId,
    shopperParticipantId: props.meal.shopperParticipantId,
    ...payload,
  });
}

/** 1.75 rather than 1.7500000000000002, and a plain 2 rather than 2.00. */
function formatScale(value: number): string {
  return Number(value.toFixed(2)).toString();
}
</script>
