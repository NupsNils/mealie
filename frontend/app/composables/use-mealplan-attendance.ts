import { format } from "date-fns";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type {
  MealPlanAbsenceCreate,
  MealPlanAbsenceOut,
  MealPlanAttendanceBulkUpdate,
  MealPlanAttendanceOverview,
  MealPlanAttendanceSettingsOut,
  MealPlanAttendanceSettingsUpdate,
  MealPlanAttendanceSummary,
  MealPlanAttendeeSummary,
  MealPlanEntryDetailsUpdate,
  MealPlanParticipantCreate,
  MealPlanParticipantOut,
} from "~/lib/api/types/meal-plan";

export interface AttendanceDateRange {
  start: Date;
  end: Date;
}

/** A participant together with the guests that belong to them, for rendering one block per person. */
export interface AttendeeGroup {
  person: MealPlanAttendeeSummary;
  guests: MealPlanAttendeeSummary[];
}

/**
 * Groups a meal's attendees so each person is shown with their own guests underneath,
 * which is how the household thinks about it: "me and my partner".
 */
export function groupAttendees(attendees: MealPlanAttendeeSummary[]): AttendeeGroup[] {
  const people = attendees.filter(attendee => !attendee.parentId);
  const guestsByParent = new Map<string, MealPlanAttendeeSummary[]>();

  for (const attendee of attendees) {
    if (!attendee.parentId) {
      continue;
    }
    const existing = guestsByParent.get(attendee.parentId) ?? [];
    existing.push(attendee);
    guestsByParent.set(attendee.parentId, existing);
  }

  return people.map(person => ({
    person,
    guests: guestsByParent.get(person.participantId) ?? [],
  }));
}

/** How many people a meal has to cook for, including the extra guests somebody brings along. */
export function countConfirmations(attendees: MealPlanAttendeeSummary[]): number {
  return attendees
    .filter(attendee => attendee.status === "attending")
    .reduce((total, attendee) => total + 1 + (attendee.guestCount ?? 0), 0);
}

export const useMealplanAttendance = function (range: Ref<AttendanceDateRange>) {
  const api = useUserApi();
  const i18n = useI18n();

  const overview = ref<MealPlanAttendanceOverview | null>(null);
  const loading = ref(false);

  async function refresh() {
    loading.value = true;
    const { data } = await api.mealplanAttendance.getOverview(
      format(range.value.start, "yyyy-MM-dd"),
      format(range.value.end, "yyyy-MM-dd"),
    );

    if (data) {
      overview.value = data;
    }
    loading.value = false;
  }

  /** Replaces one meal in place so answering does not reload the whole week. */
  function applySummary(summary: MealPlanAttendanceSummary) {
    if (!overview.value?.meals) {
      return;
    }

    const index = overview.value.meals.findIndex(meal => meal.mealplanId === summary.mealplanId);
    if (index >= 0) {
      overview.value.meals[index] = summary;
    }
  }

  async function setAttendance(mealplanId: number, updates: MealPlanAttendanceBulkUpdate[]) {
    loading.value = true;
    const { data, error } = await api.mealplanAttendance.setAttendanceBulk(mealplanId, updates);
    loading.value = false;

    if (data) {
      applySummary(data);
      return true;
    }

    // 423 means the deadline passed while the page was open. That deserves a clearer
    // message than a generic failure, plus a reload so the meal shows as closed.
    if (error?.response?.status === 423) {
      alert.error(i18n.t("meal-plan.attendance.deadline-has-passed"));
      await refresh();
    }
    return false;
  }

  async function updateDetails(mealplanId: number, payload: MealPlanEntryDetailsUpdate) {
    loading.value = true;
    const { data } = await api.mealplanAttendance.updateMealDetails(mealplanId, payload);
    loading.value = false;

    if (data) {
      applySummary(data);
      return true;
    }
    return false;
  }

  async function lock(mealplanId: number) {
    const { data } = await api.mealplanAttendance.lockMeal(mealplanId);
    if (data) {
      applySummary(data);
    }
  }

  async function unlock(mealplanId: number) {
    const { data } = await api.mealplanAttendance.unlockMeal(mealplanId);
    if (data) {
      applySummary(data);
      alert.success(i18n.t("meal-plan.attendance.reopened"));
    }
  }

  watch(range, refresh);

  return { overview, loading, refresh, setAttendance, updateDetails, lock, unlock };
};

export const useMealplanParticipants = function () {
  const api = useUserApi();
  const i18n = useI18n();

  const participants = ref<MealPlanParticipantOut[]>([]);
  const absences = ref<MealPlanAbsenceOut[]>([]);
  const loading = ref(false);

  async function refresh() {
    loading.value = true;
    const [participantResult, absenceResult] = await Promise.all([
      api.mealplanAttendance.participants.getAll(),
      api.mealplanAttendance.absences.getAll(),
    ]);

    participants.value = participantResult.data?.items ?? [];
    absences.value = absenceResult.data?.items ?? [];
    loading.value = false;
  }

  /** Creates a participant for every household member that does not have one yet. */
  async function syncFromUsers() {
    loading.value = true;
    const { data } = await api.mealplanAttendance.participants.syncFromUsers();
    loading.value = false;

    if (data) {
      await refresh();
      alert.success(i18n.t("meal-plan.attendance.participants-synced"));
    }
  }

  async function createParticipant(payload: MealPlanParticipantCreate) {
    const { data } = await api.mealplanAttendance.participants.createOne(payload);
    if (data) {
      await refresh();
    }
    return data;
  }

  async function updateParticipant(participant: MealPlanParticipantOut) {
    const { data } = await api.mealplanAttendance.participants.updateOne(participant.id, participant);
    if (data) {
      await refresh();
    }
    return data;
  }

  async function deleteParticipant(id: string) {
    await api.mealplanAttendance.participants.deleteOne(id);
    await refresh();
  }

  async function createAbsence(payload: MealPlanAbsenceCreate) {
    const { data } = await api.mealplanAttendance.absences.createOne(payload);
    if (data) {
      await refresh();
    }
    return data;
  }

  async function deleteAbsence(id: string) {
    await api.mealplanAttendance.absences.deleteOne(id);
    await refresh();
  }

  return {
    participants,
    absences,
    loading,
    refresh,
    syncFromUsers,
    createParticipant,
    updateParticipant,
    deleteParticipant,
    createAbsence,
    deleteAbsence,
  };
};

export const useMealplanAttendanceSettings = function () {
  const api = useUserApi();
  const i18n = useI18n();

  const settings = ref<MealPlanAttendanceSettingsOut | null>(null);
  const loading = ref(false);

  async function refresh() {
    loading.value = true;
    const { data } = await api.mealplanAttendance.getSettings();
    if (data) {
      settings.value = data;
    }
    loading.value = false;
  }

  async function save(payload: MealPlanAttendanceSettingsUpdate) {
    loading.value = true;
    const { data } = await api.mealplanAttendance.updateSettings(payload);
    loading.value = false;

    if (data) {
      settings.value = data;
      alert.success(i18n.t("settings.settings-updated"));
      return true;
    }

    alert.error(i18n.t("settings.settings-update-failed"));
    return false;
  }

  return { settings, loading, refresh, save };
};
