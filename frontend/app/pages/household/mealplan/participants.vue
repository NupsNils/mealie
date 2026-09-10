<template>
  <v-container class="narrow-container">
    <BaseDialog
      v-model="participantDialog"
      :title="editingGuestOf
        ? $t('meal-plan.attendance.add-guest')
        : $t('meal-plan.attendance.add-person')"
      :icon="$globals.icons.accountPlusOutline"
      can-submit
      @submit="saveParticipant"
    >
      <v-card-text>
        <v-text-field
          v-model="participantForm.name"
          autofocus
          :label="$t('general.name')"
          variant="outlined"
          density="compact"
        />
        <v-checkbox
          v-model="participantForm.defaultAttending"
          hide-details
          :label="$t('meal-plan.attendance.default-attending')"
          :hint="$t('meal-plan.attendance.default-attending-hint')"
          persistent-hint
        />
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="absenceDialog"
      :title="$t('meal-plan.attendance.add-absence')"
      :icon="$globals.icons.calendarRemove"
      can-submit
      @submit="saveAbsence"
    >
      <v-card-text>
        <v-select
          v-model="absenceForm.participantId"
          :items="participants"
          item-title="name"
          item-value="id"
          :label="$t('meal-plan.attendance.participant')"
          variant="outlined"
          density="compact"
        />
        <v-select
          v-model="absenceForm.reason"
          :items="absenceReasons"
          item-title="text"
          item-value="value"
          :label="$t('meal-plan.attendance.reason')"
          variant="outlined"
          density="compact"
        />
        <v-text-field
          v-model="absenceForm.startDate"
          type="date"
          :label="$t('meal-plan.attendance.from')"
          variant="outlined"
          density="compact"
        />
        <v-text-field
          v-model="absenceForm.endDate"
          type="date"
          :label="$t('meal-plan.attendance.until')"
          variant="outlined"
          density="compact"
        />
      </v-card-text>
    </BaseDialog>

    <BasePageTitle divider>
      <template #header>
        <v-img
          width="100%"
          max-height="100"
          max-width="100"
          src="/svgs/manage-members.svg"
        />
      </template>
      <template #title>
        {{ $t("meal-plan.attendance.participants") }}
      </template>
      {{ $t("meal-plan.attendance.participants-description") }}
    </BasePageTitle>

    <v-card variant="outlined" class="mb-6" style="border-color: lightgray;">
      <v-card-title class="d-flex align-center ga-2">
        {{ $t("meal-plan.attendance.participants") }}
        <v-spacer />
        <BaseButton
          variant="text"
          :icon="$globals.icons.refresh"
          @click="syncFromUsers"
        >
          {{ $t("meal-plan.attendance.sync-from-members") }}
        </BaseButton>
        <BaseButton create @click="openParticipantDialog(null)" />
      </v-card-title>
      <v-divider class="mx-2" />

      <v-card-text>
        <v-alert
          v-if="!participants.length"
          type="info"
          variant="tonal"
          :text="$t('meal-plan.attendance.no-participants-hint')"
        />

        <div v-for="group in participantGroups" :key="group.person.id" class="mb-3">
          <div class="d-flex align-center ga-2 flex-wrap">
            <v-icon size="small" :icon="$globals.icons.user" />
            <span class="font-weight-medium">{{ group.person.name }}</span>
            <v-chip
              size="x-small"
              variant="tonal"
              :color="group.person.defaultAttending ? 'success' : undefined"
            >
              {{ group.person.defaultAttending
                ? $t("meal-plan.attendance.defaults-to-yes")
                : $t("meal-plan.attendance.defaults-to-no") }}
            </v-chip>

            <v-spacer />

            <BaseButtonGroup
              :buttons="[
                {
                  icon: $globals.icons.accountPlusOutline,
                  text: $t('meal-plan.attendance.add-guest'),
                  event: 'add-guest',
                },
                {
                  icon: $globals.icons.checkboxMarkedCircle,
                  text: $t('meal-plan.attendance.toggle-default'),
                  event: 'toggle-default',
                },
                {
                  icon: $globals.icons.delete,
                  text: $t('general.delete'),
                  event: 'delete',
                },
              ]"
              @add-guest="openParticipantDialog(group.person.id)"
              @toggle-default="toggleDefault(group.person)"
              @delete="deleteParticipant(group.person.id)"
            />
          </div>

          <div
            v-for="guest in group.guests"
            :key="guest.id"
            class="d-flex align-center ga-2 flex-wrap ml-8"
          >
            <span class="text-body-2 text-medium-emphasis">{{ guest.name }}</span>
            <v-chip
              size="x-small"
              variant="tonal"
              :color="guest.defaultAttending ? 'success' : undefined"
            >
              {{ guest.defaultAttending
                ? $t("meal-plan.attendance.defaults-to-yes")
                : $t("meal-plan.attendance.defaults-to-no") }}
            </v-chip>

            <v-spacer />

            <BaseButtonGroup
              :buttons="[
                {
                  icon: $globals.icons.checkboxMarkedCircle,
                  text: $t('meal-plan.attendance.toggle-default'),
                  event: 'toggle-default',
                },
                {
                  icon: $globals.icons.delete,
                  text: $t('general.delete'),
                  event: 'delete',
                },
              ]"
              @toggle-default="toggleDefault(guest)"
              @delete="deleteParticipant(guest.id)"
            />
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" style="border-color: lightgray;">
      <v-card-title class="d-flex align-center ga-2">
        {{ $t("meal-plan.attendance.absences") }}
        <v-spacer />
        <BaseButton create @click="openAbsenceDialog" />
      </v-card-title>
      <v-divider class="mx-2" />

      <v-card-text>
        {{ $t("meal-plan.attendance.absences-description") }}

        <v-alert
          v-if="!absences.length"
          type="info"
          variant="tonal"
          class="mt-3"
          :text="$t('meal-plan.attendance.no-absences')"
        />

        <div
          v-for="absence in absences"
          :key="absence.id"
          class="d-flex align-center ga-2 flex-wrap mt-3"
        >
          <v-icon size="small" :icon="$globals.icons.calendarRemove" />
          <span class="font-weight-medium">{{ participantName(absence.participantId) }}</span>
          <span class="text-body-2 text-medium-emphasis">
            {{ $d(new Date(absence.startDate), "short") }} &ndash;
            {{ $d(new Date(absence.endDate), "short") }}
          </span>
          <v-chip size="x-small" variant="tonal">
            {{ $t(`meal-plan.attendance.absence-reason.${absence.reason ?? "away"}`) }}
          </v-chip>

          <v-spacer />

          <BaseButtonGroup
            :buttons="[
              {
                icon: $globals.icons.delete,
                text: $t('general.delete'),
                event: 'delete',
              },
            ]"
            @delete="deleteAbsence(absence.id)"
          />
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { useMealplanParticipants } from "~/composables/use-mealplan-attendance";
import type { AbsenceReason, MealPlanParticipantOut } from "~/lib/api/types/meal-plan";

definePageMeta({
  middleware: ["can-manage-household-only"],
});

const i18n = useI18n();
const {
  participants,
  absences,
  refresh,
  syncFromUsers,
  createParticipant,
  updateParticipant,
  deleteParticipant,
  createAbsence,
  deleteAbsence,
} = useMealplanParticipants();

useSeoMeta({
  title: i18n.t("meal-plan.attendance.participants"),
});

onMounted(refresh);

/** People first, each followed by the guests that belong to them. */
const participantGroups = computed(() => {
  const people = participants.value.filter(participant => !participant.parentId);
  return people.map(person => ({
    person,
    guests: participants.value.filter(participant => participant.parentId === person.id),
  }));
});

function participantName(id: string): string {
  return participants.value.find(participant => participant.id === id)?.name ?? "";
}

// Participants
const participantDialog = ref(false);
const editingGuestOf = ref<string | null>(null);
const participantForm = reactive({ name: "", defaultAttending: true });

function openParticipantDialog(parentId: string | null) {
  editingGuestOf.value = parentId;
  participantForm.name = "";
  // A guest such as a partner does not eat along by default; a household member does.
  participantForm.defaultAttending = parentId === null;
  participantDialog.value = true;
}

async function saveParticipant() {
  if (!participantForm.name.trim()) {
    return;
  }

  await createParticipant({
    name: participantForm.name.trim(),
    parentId: editingGuestOf.value,
    defaultAttending: participantForm.defaultAttending,
  });
}

async function toggleDefault(participant: MealPlanParticipantOut) {
  await updateParticipant({ ...participant, defaultAttending: !participant.defaultAttending });
}

// Absences
const absenceDialog = ref(false);
const absenceForm = reactive({
  participantId: "",
  reason: "vacation" as AbsenceReason,
  startDate: format(new Date(), "yyyy-MM-dd"),
  endDate: format(new Date(), "yyyy-MM-dd"),
});

const absenceReasons = computed(() => [
  { text: i18n.t("meal-plan.attendance.absence-reason.vacation"), value: "vacation" },
  { text: i18n.t("meal-plan.attendance.absence-reason.business_trip"), value: "business_trip" },
  { text: i18n.t("meal-plan.attendance.absence-reason.away"), value: "away" },
  { text: i18n.t("meal-plan.attendance.absence-reason.other"), value: "other" },
]);

function openAbsenceDialog() {
  absenceForm.participantId = participants.value[0]?.id ?? "";
  absenceDialog.value = true;
}

async function saveAbsence() {
  if (!absenceForm.participantId) {
    return;
  }

  await createAbsence({
    participantId: absenceForm.participantId,
    reason: absenceForm.reason,
    startDate: absenceForm.startDate,
    endDate: absenceForm.endDate,
  });
}
</script>
