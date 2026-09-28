<template>
  <v-container class="lg-container">
    <BaseDialog
      v-model="suggestDialog"
      :title="$t('meal-plan.rotation.suggest-recipe')"
      :icon="$globals.icons.silverwareForkKnife"
      width="800"
      can-confirm
      @confirm="submitSuggestion"
    >
      <v-card-text>
        <RecipeSelector
          ref="selector"
          v-model="suggestedRecipe"
          height="auto"
        />
        <v-text-field
          v-model="suggestionNote"
          class="mt-4"
          variant="outlined"
          density="compact"
          hide-details
          :label="$t('meal-plan.rotation.note')"
        />
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="fillDialog"
      :title="$t('meal-plan.rotation.fill-week')"
      :icon="$globals.icons.autoFix"
      can-confirm
      @confirm="fillWeek"
    >
      <v-card-text>
        {{ $t("meal-plan.rotation.fill-week-confirm") }}
      </v-card-text>
    </BaseDialog>

    <BasePageTitle divider>
      <template #header>
        <v-img
          width="100%"
          max-height="100"
          max-width="100"
          src="/svgs/manage-recipes.svg"
        />
      </template>
      <template #title>
        {{ $t("meal-plan.rotation.title") }}
      </template>
      {{ $t("meal-plan.rotation.description") }}
    </BasePageTitle>

    <!-- Suggestions: anyone may propose a recipe at any time. -->
    <section class="mb-8">
      <div class="d-flex flex-wrap align-center ga-2 mb-2">
        <h2 class="text-h6">
          {{ $t("meal-plan.rotation.suggestions") }}
        </h2>
        <v-spacer />
        <BaseButton create @click="openSuggestDialog">
          {{ $t("meal-plan.rotation.suggest-recipe") }}
        </BaseButton>
      </div>
      <p class="text-body-2 text-medium-emphasis mb-3">
        {{ $t("meal-plan.rotation.suggestions-description") }}
      </p>

      <v-alert
        v-if="!openSuggestions.length"
        type="info"
        variant="tonal"
        :text="$t('meal-plan.rotation.no-suggestions')"
      />
      <v-card
        v-else
        variant="outlined"
      >
        <v-list class="py-0">
          <v-list-item
            v-for="suggestion in openSuggestions"
            :key="suggestion.id"
            :to="recipeLink(suggestion.recipe?.slug)"
            :title="suggestion.recipe?.name ?? ''"
            :subtitle="suggestionSubtitle(suggestion)"
          >
            <template #append>
              <v-btn
                v-if="canManage && suggestion.createdById !== currentUserId"
                :icon="$globals.icons.close"
                :title="$t('meal-plan.rotation.reject')"
                variant="text"
                size="small"
                @click.prevent="reject(suggestion)"
              />
              <v-btn
                v-if="canManage || suggestion.createdById === currentUserId"
                :icon="$globals.icons.delete"
                :title="$t('meal-plan.rotation.withdraw')"
                variant="text"
                size="small"
                @click.prevent="withdraw(suggestion.id)"
              />
            </template>
          </v-list-item>
        </v-list>
      </v-card>
    </section>

    <!-- The rolling plan: ranked recipes for every open day of the week. -->
    <section>
      <h2 class="text-h6 mb-2">
        {{ $t("meal-plan.rotation.rolling-plan") }}
      </h2>
      <p class="text-body-2 text-medium-emphasis mb-3">
        {{ $t("meal-plan.rotation.rolling-plan-description") }}
      </p>

      <div class="d-flex flex-wrap align-center ga-2 mb-4">
        <v-btn
          :icon="$globals.icons.chevronLeft"
          flat
          rounded="md"
          density="comfortable"
          @click="weekOffset -= 1"
        />
        <span class="text-subtitle-1 font-weight-medium">
          {{ $d(range.start, "short") }} &ndash; {{ $d(range.end, "short") }}
        </span>
        <v-btn
          :icon="$globals.icons.chevronRight"
          flat
          rounded="md"
          density="comfortable"
          @click="weekOffset += 1"
        />

        <v-spacer />

        <BaseButton
          :loading="loading"
          :disabled="!hasCandidates"
          @click="fillDialog = true"
        >
          <template #icon>
            {{ $globals.icons.autoFix }}
          </template>
          {{ $t("meal-plan.rotation.fill-week") }}
        </BaseButton>
      </div>

      <div class="d-flex flex-wrap ga-3 mb-2">
        <v-select
          v-model="entryType"
          :items="planTypeOptions"
          item-title="text"
          item-value="value"
          variant="outlined"
          density="compact"
          hide-details
          :label="$t('meal-plan.meal-type')"
          style="max-width: 220px;"
        />
        <v-number-input
          v-model="cooldownWeeks"
          :min="0"
          :max="52"
          control-variant="stacked"
          variant="outlined"
          density="compact"
          hide-details
          :label="$t('meal-plan.rotation.cooldown-weeks')"
          style="max-width: 220px;"
        />
      </div>
      <p class="text-caption text-medium-emphasis mb-3">
        {{ $t("meal-plan.rotation.cooldown-weeks-hint") }}
      </p>

      <v-expansion-panels class="mb-4">
        <v-expansion-panel :title="$t('meal-plan.rotation.weights')">
          <v-expansion-panel-text>
            <p class="text-caption text-medium-emphasis mb-4">
              {{ $t("meal-plan.rotation.weights-hint") }}
            </p>
            <v-slider
              v-for="weight in weightSliders"
              :key="weight.key"
              v-model="weights[weight.key]"
              :label="weight.label"
              :min="0"
              :max="5"
              :step="0.5"
              thumb-label
              hide-details
              class="mb-2"
            />
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-alert
        v-if="proposal && !proposal.slots?.length"
        type="info"
        variant="tonal"
        :text="$t('meal-plan.rotation.no-open-days')"
      />

      <v-card
        v-for="slot in proposal?.slots ?? []"
        :key="`${slot.date}-${slot.entryType}`"
        variant="outlined"
        class="mb-3"
      >
        <v-card-title class="d-flex flex-wrap align-center ga-2">
          <span>{{ formatDay(slot.date) }}</span>
          <v-spacer />
          <v-chip
            v-if="slot.decider"
            size="small"
            variant="tonal"
            color="primary"
            :prepend-icon="$globals.icons.user"
          >
            {{ $t("meal-plan.rotation.decider", [slot.decider]) }}
          </v-chip>
        </v-card-title>
        <v-divider />

        <v-card-text
          v-if="!slot.candidates?.length"
          class="text-medium-emphasis"
        >
          {{ $t("meal-plan.rotation.no-candidates") }}
        </v-card-text>

        <v-list
          v-else
          class="py-0"
        >
          <v-list-item
            v-for="(candidate, index) in slot.candidates"
            :key="candidate.recipe.id ?? index"
          >
            <v-list-item-title class="d-flex align-center ga-2">
              <router-link :to="recipeLink(candidate.recipe.slug)">
                {{ candidate.recipe.name }}
              </router-link>
              <v-chip
                v-if="index === 0"
                size="x-small"
                color="success"
                variant="flat"
              >
                {{ $t("meal-plan.rotation.top-pick") }}
              </v-chip>
            </v-list-item-title>

            <div class="d-flex flex-wrap ga-1 mt-1">
              <v-chip
                v-for="reason in candidateReasons(slot.decider, candidate)"
                :key="reason.text"
                size="x-small"
                variant="tonal"
                :color="reason.color"
                :prepend-icon="reason.icon"
              >
                {{ reason.text }}
              </v-chip>
            </div>

            <template #append>
              <BaseButton
                small
                variant="text"
                @click="onPlan(slot, candidate)"
              >
                <template #icon>
                  {{ $globals.icons.calendarMultiselect }}
                </template>
                {{ $t("meal-plan.rotation.plan") }}
              </BaseButton>
            </template>
          </v-list-item>
        </v-list>
      </v-card>
    </section>
  </v-container>
</template>

<script setup lang="ts">
import { addDays, format, parseISO, startOfWeek } from "date-fns";
import RecipeSelector from "~/components/Domain/Recipe/RecipeSelector.vue";
import { useUserApi } from "~/composables/api";
import { usePlanTypeOptions } from "~/composables/use-group-mealplan";
import { useHouseholdSelf } from "~/composables/use-households";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import {
  useMealplanAttendanceSettings,
  useMealplanRotation,
  useMealplanSuggestions,
} from "~/composables/use-mealplan-attendance";
import { alert } from "~/composables/use-toast";
import type {
  MealPlanRotationCandidate,
  MealPlanRotationRequest,
  MealPlanRotationSlot,
  MealPlanSuggestionOut,
  PlanEntryType,
} from "~/lib/api/types/meal-plan";
import type { RecipeSummary } from "~/lib/api/types/recipe";

const api = useUserApi();
const i18n = useI18n();
const route = useRoute();
const auth = useMealieAuth();
const { $globals } = useNuxtApp();
const { household } = useHouseholdSelf();
const { settings, refresh: refreshSettings } = useMealplanAttendanceSettings();
const planTypeOptions = usePlanTypeOptions();

useSeoMeta({
  title: i18n.t("meal-plan.rotation.title"),
});

const currentUserId = computed(() => auth.user.value?.id);
const canManage = computed(() => !!auth.user.value?.canManageHousehold);
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");

function recipeLink(slug?: string | null) {
  return slug ? `/g/${groupSlug.value}/r/${slug}` : undefined;
}

function formatDay(value: string) {
  // parseISO reads `yyyy-MM-dd` as a local day; `new Date()` would read it as UTC midnight.
  return parseISO(value).toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" });
}

// Household members, to show who suggested what.
const memberNames = ref<Record<string, string>>({});

async function loadMembers() {
  const { data } = await api.households.fetchMembers();
  memberNames.value = Object.fromEntries(
    (data?.items ?? []).map(member => [member.id, member.fullName || member.username || ""]),
  );
}

// Suggestions
const { openSuggestions, refresh: refreshSuggestions, suggest, withdraw: withdrawSuggestion, reject: rejectSuggestion }
  = useMealplanSuggestions();

const suggestDialog = ref(false);
const suggestedRecipe = ref<RecipeSummary | null>(null);
const suggestionNote = ref("");
const selector = ref<{ reset: () => void } | null>(null);

function suggestionSubtitle(suggestion: MealPlanSuggestionOut) {
  const name = suggestion.createdById ? memberNames.value[suggestion.createdById] : undefined;
  const parts = [name ? i18n.t("meal-plan.rotation.suggested-by", [name]) : i18n.t("meal-plan.rotation.suggested")];
  if (suggestion.note) {
    parts.push(suggestion.note);
  }
  return parts.join(" · ");
}

function openSuggestDialog() {
  suggestedRecipe.value = null;
  suggestionNote.value = "";
  selector.value?.reset();
  suggestDialog.value = true;
}

async function submitSuggestion() {
  if (!suggestedRecipe.value?.id) {
    alert.warning(i18n.t("meal-plan.rotation.pick-a-recipe"));
    return;
  }

  const added = await suggest({ recipeId: suggestedRecipe.value.id, note: suggestionNote.value || null });
  if (added) {
    await refreshRotation();
  }
}

async function withdraw(id: string) {
  await withdrawSuggestion(id);
  await refreshRotation();
}

async function reject(suggestion: MealPlanSuggestionOut) {
  await rejectSuggestion(suggestion);
  await refreshRotation();
}

// Rolling plan
const weekStartsOn = computed(
  () => (household.value?.preferences?.firstDayOfWeek ?? 0) as 0 | 1 | 2 | 3 | 4 | 5 | 6,
);

const weekOffset = ref(0);
const range = computed(() => {
  const start = addDays(startOfWeek(new Date(), { weekStartsOn: weekStartsOn.value }), weekOffset.value * 7);
  return { start, end: addDays(start, 6) };
});

const entryType = ref<PlanEntryType>("dinner");
const cooldownWeeks = ref(6);
const weights = reactive({ favoriteWeight: 1, suggestionWeight: 1.5, fairnessWeight: 1 });

const weightSliders = computed(() => [
  { key: "favoriteWeight" as const, label: i18n.t("meal-plan.rotation.favorite-weight") },
  { key: "suggestionWeight" as const, label: i18n.t("meal-plan.rotation.suggestion-weight") },
  { key: "fairnessWeight" as const, label: i18n.t("meal-plan.rotation.fairness-weight") },
]);

const request = computed<MealPlanRotationRequest>(() => ({
  // Formatted locally rather than via toISOString(), which would shift the day for anyone
  // whose offset pushes the date across midnight UTC.
  startDate: format(range.value.start, "yyyy-MM-dd"),
  endDate: format(range.value.end, "yyyy-MM-dd"),
  entryType: entryType.value,
  cooldownWeeks: cooldownWeeks.value ?? 0,
  ...weights,
}));

const { proposal, loading, refresh: refreshRotation, plan, fill } = useMealplanRotation(request);

const hasCandidates = computed(() => !!proposal.value?.slots?.some(slot => slot.candidates?.length));

const fillDialog = ref(false);

async function fillWeek() {
  await fill();
  await refreshSuggestions();
}

interface Reason {
  text: string;
  icon: string;
  color?: string;
}

/** The ranking explained in chips, built from the structured fields so they follow the UI language. */
function candidateReasons(decider: string | null | undefined, candidate: MealPlanRotationCandidate): Reason[] {
  const reasons: Reason[] = [];

  if (candidate.wishOfDecider && decider) {
    reasons.push({ text: i18n.t("meal-plan.rotation.wish-of-decider", [decider]), icon: $globals.icons.user, color: "primary" });
  }
  if (candidate.favoritedBy?.length) {
    reasons.push({ text: i18n.t("meal-plan.rotation.favorite-of", [candidate.favoritedBy.join(", ")]), icon: $globals.icons.heart, color: "error" });
  }
  if (candidate.isSuggested) {
    const text = candidate.suggestedBy?.length
      ? i18n.t("meal-plan.rotation.suggested-by", [candidate.suggestedBy.join(", ")])
      : i18n.t("meal-plan.rotation.suggested");
    reasons.push({ text, icon: $globals.icons.silverwareForkKnife, color: "info" });
  }
  if (candidate.daysSinceLast === null || candidate.daysSinceLast === undefined) {
    reasons.push({ text: i18n.t("meal-plan.rotation.never-cooked"), icon: $globals.icons.star });
  }
  else {
    reasons.push({ text: i18n.t("meal-plan.rotation.last-cooked", candidate.daysSinceLast), icon: $globals.icons.clockOutline });
  }
  if (candidate.chosenByBusiest && candidate.lastChosenBy) {
    reasons.push({ text: i18n.t("meal-plan.rotation.chosen-by-busiest", [candidate.lastChosenBy]), icon: $globals.icons.alert, color: "warning" });
  }

  return reasons;
}

async function onPlan(slot: MealPlanRotationSlot, candidate: MealPlanRotationCandidate) {
  if (await plan(slot, candidate)) {
    await refreshSuggestions();
  }
}

onMounted(async () => {
  // Start from the household's own rest period; changing it re-ranks through the watcher.
  await Promise.all([loadMembers(), refreshSuggestions(), refreshSettings()]);
  if (settings.value?.rotationCooldownWeeks !== undefined && settings.value.rotationCooldownWeeks !== cooldownWeeks.value) {
    cooldownWeeks.value = settings.value.rotationCooldownWeeks;
  }
  else {
    await refreshRotation();
  }
});
</script>
