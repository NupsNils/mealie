<template>
  <v-container class="lg-container">
    <BaseDialog
      v-model="shoppingListDialog"
      :title="$t('meal-plan.attendance.add-to-shopping-list')"
      :icon="$globals.icons.cartCheck"
      can-confirm
      @confirm="addToShoppingList"
    >
      <v-card-text>
        <v-select
          v-model="selectedShoppingListId"
          :items="shoppingLists ?? []"
          item-title="name"
          item-value="id"
          :label="$t('shopping-list.shopping-list')"
          variant="outlined"
          density="compact"
        />
        <v-checkbox
          v-model="onlyLocked"
          hide-details
          :label="$t('meal-plan.attendance.only-closed-meals')"
          :hint="$t('meal-plan.attendance.only-closed-meals-hint')"
          persistent-hint
        />
      </v-card-text>
    </BaseDialog>

    <BasePageTitle divider>
      <template #header>
        <v-img
          width="100%"
          max-height="100"
          max-width="100"
          src="/svgs/manage-cookbooks.svg"
        />
      </template>
      <template #title>
        {{ $t("meal-plan.attendance.meal-attendance") }}
      </template>
      {{ $t("meal-plan.attendance.meal-attendance-description") }}
    </BasePageTitle>

    <!-- Week navigation -->
    <div class="d-flex flex-wrap align-center ga-2 mb-4">
      <v-btn
        :icon="$globals.icons.chevronLeft"
        flat
        rounded="md"
        density="comfortable"
        @click="changeWeek(-1)"
      />
      <v-btn color="primary" variant="tonal">
        <v-icon start>
          {{ $globals.icons.calendar }}
        </v-icon>
        {{ $d(range.start, "short") }} &ndash; {{ $d(range.end, "short") }}
      </v-btn>
      <v-btn
        :icon="$globals.icons.chevronRight"
        flat
        rounded="md"
        density="comfortable"
        @click="changeWeek(1)"
      />

      <v-spacer />

      <BaseButtonGroup
        :buttons="[
          {
            icon: $globals.icons.cartCheck,
            text: $t('meal-plan.attendance.add-to-shopping-list'),
            event: 'shopping-list',
            disabled: !hasMeals,
          },
          {
            icon: $globals.icons.user,
            text: $t('meal-plan.attendance.participants'),
            event: 'participants',
          },
          {
            icon: $globals.icons.cog,
            text: $t('general.settings'),
            event: 'settings',
          },
        ]"
        @shopping-list="openShoppingListDialog"
        @participants="router.push('/household/mealplan/participants')"
        @settings="router.push('/household/mealplan/attendance-settings')"
      />
    </div>

    <v-alert
      v-if="overview && !overview.settings.enabled"
      type="info"
      variant="tonal"
      class="mb-4"
    >
      {{ $t("meal-plan.attendance.module-disabled") }}
      <template #append>
        <BaseButton
          variant="text"
          @click="router.push('/household/mealplan/attendance-settings')"
        >
          {{ $t("general.settings") }}
        </BaseButton>
      </template>
    </v-alert>

    <v-alert
      v-else-if="overview && !overview.participants?.length"
      type="warning"
      variant="tonal"
      class="mb-4"
    >
      {{ $t("meal-plan.attendance.no-participants") }}
      <template #append>
        <BaseButton
          variant="text"
          @click="router.push('/household/mealplan/participants')"
        >
          {{ $t("meal-plan.attendance.participants") }}
        </BaseButton>
      </template>
    </v-alert>

    <AppLoader v-if="loading && !overview" :loading="true" />

    <v-alert
      v-else-if="!hasMeals"
      type="info"
      variant="tonal"
      :text="$t('meal-plan.attendance.no-meals-in-range')"
    />

    <HouseholdMealAttendanceCard
      v-for="meal in overview?.meals ?? []"
      :key="meal.mealplanId"
      :meal="meal"
      :participants="overview?.participants ?? []"
      :current-user-id="currentUserId"
      :can-manage="canManage"
      @answer="onAnswer"
      @details="onDetails"
      @lock="onLock"
      @unlock="onUnlock"
    />
  </v-container>
</template>

<script setup lang="ts">
import { addDays, format, startOfWeek } from "date-fns";
import HouseholdMealAttendanceCard from "~/components/Domain/Household/HouseholdMealAttendanceCard.vue";
import { useUserApi } from "~/composables/api";
import { useHouseholdSelf } from "~/composables/use-households";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import { useMealplanAttendance } from "~/composables/use-mealplan-attendance";
import { useAddToShoppingListDialog } from "~/composables/shopping-list-page/use-add-to-shopping-list-dialog";
import { alert } from "~/composables/use-toast";
import type { AttendanceStatus, MealPlanEntryDetailsUpdate } from "~/lib/api/types/meal-plan";

const api = useUserApi();
const i18n = useI18n();
const router = useRouter();
const auth = useMealieAuth();
const { household } = useHouseholdSelf();
const { shoppingLists, getShoppingLists } = useAddToShoppingListDialog();

useSeoMeta({
  title: i18n.t("meal-plan.attendance.meal-attendance"),
});

const currentUserId = computed(() => auth.user.value?.id);
const canManage = computed(() => !!auth.user.value?.canManageHousehold);

const weekStartsOn = computed(
  () => (household.value?.preferences?.firstDayOfWeek ?? 0) as 0 | 1 | 2 | 3 | 4 | 5 | 6,
);

const weekOffset = ref(0);
const range = computed(() => {
  const start = addDays(
    startOfWeek(new Date(), { weekStartsOn: weekStartsOn.value }),
    weekOffset.value * 7,
  );
  return { start, end: addDays(start, 6) };
});

const { overview, loading, refresh, setAttendance, updateDetails, lock, unlock }
  = useMealplanAttendance(range);

const hasMeals = computed(() => !!overview.value?.meals?.length);

onMounted(refresh);

function changeWeek(step: number) {
  weekOffset.value += step;
}

async function onAnswer(mealplanId: number, participantId: string, status: AttendanceStatus) {
  await setAttendance(mealplanId, [{ participantId, status }]);
}

async function onDetails(mealplanId: number, payload: MealPlanEntryDetailsUpdate) {
  await updateDetails(mealplanId, payload);
}

async function onLock(mealplanId: number) {
  await lock(mealplanId);
}

async function onUnlock(mealplanId: number) {
  await unlock(mealplanId);
}

// Shopping list
const shoppingListDialog = ref(false);
const selectedShoppingListId = ref<string | undefined>();
const onlyLocked = ref(true);

async function openShoppingListDialog() {
  await getShoppingLists();
  selectedShoppingListId.value = shoppingLists.value?.[0]?.id;
  shoppingListDialog.value = true;
}

async function addToShoppingList() {
  if (!selectedShoppingListId.value) {
    return;
  }

  const { data } = await api.mealplanAttendance.addToShoppingList({
    shoppingListId: selectedShoppingListId.value,
    // Formatted locally rather than via toISOString(), which would shift the day for
    // anyone whose offset pushes the date across midnight UTC.
    startDate: format(range.value.start, "yyyy-MM-dd"),
    endDate: format(range.value.end, "yyyy-MM-dd"),
    onlyLocked: onlyLocked.value,
  });

  if (!data) {
    alert.error(i18n.t("meal-plan.attendance.shopping-list-failed"));
    return;
  }

  const added = data.added?.length ?? 0;
  if (added) {
    alert.success(i18n.t("meal-plan.attendance.recipes-added", [added]));
  }
  else {
    // Every meal was skipped; the reasons come back from the API so say why rather than
    // silently doing nothing.
    alert.warning(data.skipped?.[0] ?? i18n.t("meal-plan.attendance.nothing-to-add"));
  }
}
</script>
