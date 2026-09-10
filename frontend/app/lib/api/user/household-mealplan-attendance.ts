import { BaseAPI, BaseCRUDAPI } from "../base/base-clients";
import type {
  MealPlanAbsenceCreate,
  MealPlanAbsenceOut,
  MealPlanAbsenceUpdate,
  MealPlanAttendanceBulkUpdate,
  MealPlanAttendanceOverview,
  MealPlanAttendanceSettingsOut,
  MealPlanAttendanceSettingsUpdate,
  MealPlanAttendanceShoppingListRequest,
  MealPlanAttendanceShoppingListResult,
  MealPlanAttendanceSummary,
  MealPlanAttendanceUpdate,
  MealPlanEntryDetailsUpdate,
  MealPlanParticipantCreate,
  MealPlanParticipantOut,
  MealPlanParticipantUpdate,
  MealPlanRotationProposal,
  MealPlanRotationRequest,
  MealPlanSuggestionCreate,
  MealPlanSuggestionOut,
  MealPlanSuggestionUpdate,
} from "~/lib/api/types/meal-plan";

const prefix = "/api";

const routes = {
  attendance: `${prefix}/households/mealplan-attendance`,
  settings: `${prefix}/households/mealplan-attendance/settings`,
  shoppingList: `${prefix}/households/mealplan-attendance/shopping-list`,

  participants: `${prefix}/households/mealplan-participants`,
  participantId: (id: string | number) => `${prefix}/households/mealplan-participants/${id}`,
  participantSync: `${prefix}/households/mealplan-participants/sync`,

  absences: `${prefix}/households/mealplan-absences`,
  absenceId: (id: string | number) => `${prefix}/households/mealplan-absences/${id}`,

  suggestions: `${prefix}/households/mealplan-suggestions`,
  suggestionId: (id: string | number) => `${prefix}/households/mealplan-suggestions/${id}`,
  rotation: `${prefix}/households/mealplan-suggestions/rotation`,

  mealAttendance: (mealplanId: number) => `${prefix}/households/mealplans/${mealplanId}/attendance`,
  mealAttendanceParticipant: (mealplanId: number, participantId: string) =>
    `${prefix}/households/mealplans/${mealplanId}/attendance/${participantId}`,
  mealDetails: (mealplanId: number) => `${prefix}/households/mealplans/${mealplanId}/attendance-details`,
  mealLock: (mealplanId: number) => `${prefix}/households/mealplans/${mealplanId}/attendance/lock`,
  mealUnlock: (mealplanId: number) => `${prefix}/households/mealplans/${mealplanId}/attendance/unlock`,
};

export class MealPlanParticipantsAPI extends BaseCRUDAPI<
  MealPlanParticipantCreate,
  MealPlanParticipantOut,
  MealPlanParticipantUpdate
> {
  baseRoute = routes.participants;
  itemRoute = routes.participantId;

  /** Create a participant for every household member that does not have one yet. */
  async syncFromUsers() {
    return await this.requests.post<MealPlanParticipantOut[]>(routes.participantSync, {});
  }
}

export class MealPlanAbsencesAPI extends BaseCRUDAPI<
  MealPlanAbsenceCreate,
  MealPlanAbsenceOut,
  MealPlanAbsenceUpdate
> {
  baseRoute = routes.absences;
  itemRoute = routes.absenceId;
}

export class MealPlanSuggestionsAPI extends BaseCRUDAPI<
  MealPlanSuggestionCreate,
  MealPlanSuggestionOut,
  MealPlanSuggestionUpdate
> {
  baseRoute = routes.suggestions;
  itemRoute = routes.suggestionId;

  /** Ranked proposals for the open slots in a date range. */
  async getRotation(payload: MealPlanRotationRequest) {
    return await this.requests.post<MealPlanRotationProposal>(routes.rotation, payload);
  }
}

export class MealPlanAttendanceAPI extends BaseAPI {
  public participants: MealPlanParticipantsAPI;
  public absences: MealPlanAbsencesAPI;
  public suggestions: MealPlanSuggestionsAPI;

  constructor(requests: ConstructorParameters<typeof BaseAPI>[0]) {
    super(requests);
    this.participants = new MealPlanParticipantsAPI(requests, routes.participants, routes.participantId);
    this.absences = new MealPlanAbsencesAPI(requests, routes.absences, routes.absenceId);
    this.suggestions = new MealPlanSuggestionsAPI(requests, routes.suggestions, routes.suggestionId);
  }

  async getSettings() {
    return await this.requests.get<MealPlanAttendanceSettingsOut>(routes.settings);
  }

  async updateSettings(payload: MealPlanAttendanceSettingsUpdate) {
    return await this.requests.put<MealPlanAttendanceSettingsOut, MealPlanAttendanceSettingsUpdate>(
      routes.settings,
      payload,
    );
  }

  /** Every meal in the range together with who is eating along. */
  async getOverview(startDate: string, endDate: string) {
    return await this.requests.get<MealPlanAttendanceOverview>(
      `${routes.attendance}?start_date=${startDate}&end_date=${endDate}`,
    );
  }

  async getMeal(mealplanId: number) {
    return await this.requests.get<MealPlanAttendanceSummary>(routes.mealAttendance(mealplanId));
  }

  async setAttendance(mealplanId: number, participantId: string, payload: MealPlanAttendanceUpdate) {
    return await this.requests.put<MealPlanAttendanceSummary, MealPlanAttendanceUpdate>(
      routes.mealAttendanceParticipant(mealplanId, participantId),
      payload,
    );
  }

  /** Answer for several participants at once, e.g. for yourself and your partner. */
  async setAttendanceBulk(mealplanId: number, payload: MealPlanAttendanceBulkUpdate[]) {
    return await this.requests.put<MealPlanAttendanceSummary, MealPlanAttendanceBulkUpdate[]>(
      routes.mealAttendance(mealplanId),
      payload,
    );
  }

  async updateMealDetails(mealplanId: number, payload: MealPlanEntryDetailsUpdate) {
    return await this.requests.put<MealPlanAttendanceSummary, MealPlanEntryDetailsUpdate>(
      routes.mealDetails(mealplanId),
      payload,
    );
  }

  async lockMeal(mealplanId: number) {
    return await this.requests.post<MealPlanAttendanceSummary>(routes.mealLock(mealplanId), {});
  }

  async unlockMeal(mealplanId: number, deadlineAt?: string) {
    const query = deadlineAt ? `?deadline_at=${encodeURIComponent(deadlineAt)}` : "";
    return await this.requests.post<MealPlanAttendanceSummary>(`${routes.mealUnlock(mealplanId)}${query}`, {});
  }

  async addToShoppingList(payload: MealPlanAttendanceShoppingListRequest) {
    return await this.requests.post<MealPlanAttendanceShoppingListResult, MealPlanAttendanceShoppingListRequest>(
      routes.shoppingList,
      payload,
    );
  }
}
