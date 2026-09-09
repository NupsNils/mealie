/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type PlanEntryType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert";
export type AbsenceReason = "vacation" | "business_trip" | "away" | "other";
export type AttendanceStatus = "attending" | "declined" | "undecided";
export type DeadlineMode = "weekly" | "relative" | "manual";
export type SuggestionStatus = "open" | "planned" | "rejected";
export type PlanRulesDay = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday" | "unset";
export type PlanRulesType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert" | "unset";
export type LogicalOperator = "AND" | "OR";
export type RelationalKeyword = "IS" | "IS NOT" | "IN" | "NOT IN" | "CONTAINS ALL" | "LIKE" | "NOT LIKE";
export type RelationalOperator = "=" | "<>" | ">" | "<" | ">=" | "<=";

export interface CreatePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
}
export interface CreateRandomEntry {
  date: string;
  entryType?: PlanEntryType;
}
export interface ListItem {
  title?: string | null;
  text?: string;
  quantity?: number;
  checked?: boolean;
}
export interface MealPlanAbsenceCreate {
  participantId: string;
  startDate: string;
  endDate: string;
  reason?: AbsenceReason;
  note?: string | null;
}
export interface MealPlanAbsenceOut {
  participantId: string;
  startDate: string;
  endDate: string;
  reason?: AbsenceReason;
  note?: string | null;
  groupId: string;
  householdId: string;
  id: string;
}
export interface MealPlanAbsenceSave {
  participantId: string;
  startDate: string;
  endDate: string;
  reason?: AbsenceReason;
  note?: string | null;
  groupId: string;
  householdId: string;
}
export interface MealPlanAbsenceUpdate {
  participantId: string;
  startDate: string;
  endDate: string;
  reason?: AbsenceReason;
  note?: string | null;
  id: string;
}
export interface MealPlanAttendanceBulkUpdate {
  participantId: string;
  status: AttendanceStatus;
  guestCount?: number;
  note?: string | null;
}
export interface MealPlanAttendanceOut {
  status: AttendanceStatus;
  guestCount?: number;
  note?: string | null;
  groupId: string;
  householdId: string;
  mealplanId: number;
  participantId: string;
  respondedAt?: string | null;
  id: string;
}
export interface MealPlanAttendanceOverview {
  startDate: string;
  endDate: string;
  settings: MealPlanAttendanceSettingsOut;
  participants?: MealPlanParticipantOut[];
  absences?: MealPlanAbsenceOut[];
  meals?: MealPlanAttendanceSummary[];
}
export interface MealPlanAttendanceSettingsOut {
  enabled?: boolean;
  deadlineMode?: DeadlineMode;
  deadlineWeekday?: number;
  deadlineTime?: string;
  deadlineLeadDays?: number;
  timezone?: string;
  autoLock?: boolean;
  reminderEnabled?: boolean;
  reminderHoursBefore?: number;
  entryTypes?: PlanEntryType2[];
  groupId: string;
  householdId: string;
  id: string;
}
export interface MealPlanParticipantOut {
  name: string;
  userId?: string | null;
  parentId?: string | null;
  defaultAttending?: boolean;
  active?: boolean;
  groupId: string;
  householdId: string;
  id: string;
}
export interface MealPlanAttendanceSummary {
  mealplanId: number;
  date: string;
  entryType: PlanEntryType;
  title?: string;
  recipeId?: string | null;
  recipeName?: string | null;
  recipeSlug?: string | null;
  deadlineAt?: string | null;
  isLocked?: boolean;
  deadlinePassed?: boolean;
  attendeeCount?: number;
  pendingResponseCount?: number;
  servings?: number;
  servingsOverride?: number | null;
  recipeServings?: number;
  scaleFactor?: number;
  cookParticipantId?: string | null;
  shopperParticipantId?: string | null;
  attendees?: MealPlanAttendeeSummary[];
}
export interface MealPlanAttendeeSummary {
  participantId: string;
  participantName: string;
  userId?: string | null;
  parentId?: string | null;
  isGuest?: boolean;
  status?: AttendanceStatus;
  guestCount?: number;
  note?: string | null;
  hasResponded?: boolean;
  isAbsent?: boolean;
  absenceReason?: AbsenceReason4 | null;
}
export interface MealPlanAttendanceSave {
  status: AttendanceStatus;
  guestCount?: number;
  note?: string | null;
  groupId: string;
  householdId: string;
  mealplanId: number;
  participantId: string;
  respondedAt?: string | null;
}
export interface MealPlanAttendanceSettingsSave {
  enabled?: boolean;
  deadlineMode?: DeadlineMode;
  deadlineWeekday?: number;
  deadlineTime?: string;
  deadlineLeadDays?: number;
  timezone?: string;
  autoLock?: boolean;
  reminderEnabled?: boolean;
  reminderHoursBefore?: number;
  entryTypes?: PlanEntryType2[];
  groupId: string;
  householdId: string;
}
export interface MealPlanAttendanceSettingsUpdate {
  enabled?: boolean;
  deadlineMode?: DeadlineMode;
  deadlineWeekday?: number;
  deadlineTime?: string;
  deadlineLeadDays?: number;
  timezone?: string;
  autoLock?: boolean;
  reminderEnabled?: boolean;
  reminderHoursBefore?: number;
  entryTypes?: PlanEntryType2[];
}
export interface MealPlanAttendanceShoppingListEntry {
  mealplanId: number;
  recipeId: string;
  recipeName?: string | null;
  servings: number;
  scaleFactor: number;
}
export interface MealPlanAttendanceShoppingListRequest {
  shoppingListId: string;
  startDate: string;
  endDate: string;
  onlyLocked?: boolean;
}
export interface MealPlanAttendanceShoppingListResult {
  shoppingListId: string;
  added?: MealPlanAttendanceShoppingListEntry[];
  skipped?: string[];
}
export interface MealPlanAttendanceUpdate {
  status: AttendanceStatus;
  guestCount?: number;
  note?: string | null;
}
export interface MealPlanEntryDetailsOut {
  deadlineAt?: string | null;
  locked?: boolean;
  servingsOverride?: number | null;
  cookParticipantId?: string | null;
  shopperParticipantId?: string | null;
  groupId: string;
  householdId: string;
  mealplanId: number;
  reminderSentAt?: string | null;
  id: string;
}
export interface MealPlanEntryDetailsSave {
  deadlineAt?: string | null;
  locked?: boolean;
  servingsOverride?: number | null;
  cookParticipantId?: string | null;
  shopperParticipantId?: string | null;
  groupId: string;
  householdId: string;
  mealplanId: number;
  reminderSentAt?: string | null;
}
export interface MealPlanEntryDetailsUpdate {
  deadlineAt?: string | null;
  locked?: boolean;
  servingsOverride?: number | null;
  cookParticipantId?: string | null;
  shopperParticipantId?: string | null;
}
export interface MealPlanParticipantCreate {
  name: string;
  userId?: string | null;
  parentId?: string | null;
  defaultAttending?: boolean;
  active?: boolean;
}
export interface MealPlanParticipantSave {
  name: string;
  userId?: string | null;
  parentId?: string | null;
  defaultAttending?: boolean;
  active?: boolean;
  groupId: string;
  householdId: string;
}
export interface MealPlanParticipantUpdate {
  name: string;
  userId?: string | null;
  parentId?: string | null;
  defaultAttending?: boolean;
  active?: boolean;
  id: string;
}
export interface MealPlanRotationCandidate {
  recipe: RecipeSummary;
  score: number;
  lastPlannedOn?: string | null;
  daysSinceLast?: number | null;
  favoriteCount?: number;
  isSuggested?: boolean;
  suggestedBy?: string[];
  lastChosenBy?: string | null;
  reasons?: string[];
}
export interface RecipeSummary {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  lastMade?: string | null;
}
export interface RecipeCategory {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTag {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTool {
  id: string;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
  householdsWithTool?: string[];
}
export interface MealPlanRotationProposal {
  cooldownWeeks: number;
  slots?: MealPlanRotationSlot[];
}
export interface MealPlanRotationSlot {
  date: string;
  entryType: PlanEntryType;
  candidates?: MealPlanRotationCandidate[];
}
export interface MealPlanRotationRequest {
  startDate: string;
  endDate: string;
  entryType?: PlanEntryType;
  cooldownWeeks?: number;
  favoriteWeight?: number;
  suggestionWeight?: number;
  fairnessWeight?: number;
  limit?: number;
}
export interface MealPlanSuggestionCreate {
  recipeId: string;
  note?: string | null;
}
export interface MealPlanSuggestionOut {
  recipeId: string;
  note?: string | null;
  groupId: string;
  householdId: string;
  createdById?: string | null;
  status?: SuggestionStatus;
  id: string;
  recipe?: RecipeSummary | null;
}
export interface MealPlanSuggestionSave {
  recipeId: string;
  note?: string | null;
  groupId: string;
  householdId: string;
  createdById?: string | null;
  status?: SuggestionStatus;
}
export interface MealPlanSuggestionUpdate {
  id: string;
  status?: SuggestionStatus;
  note?: string | null;
}
export interface PlanRulesCreate {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
}
export interface PlanRulesOut {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
  groupId: string;
  householdId: string;
  id: string;
  queryFilter?: QueryFilterJSON;
}
export interface QueryFilterJSON {
  parts?: QueryFilterJSONPart[];
}
export interface QueryFilterJSONPart {
  leftParenthesis?: string | null;
  rightParenthesis?: string | null;
  logicalOperator?: LogicalOperator | null;
  attributeName?: string | null;
  relationalOperator?: RelationalKeyword | RelationalOperator | null;
  value?: string | string[] | null;
  [k: string]: unknown;
}
export interface PlanRulesSave {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
  groupId: string;
  householdId: string;
}
export interface ReadPlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  id: number;
  groupId: string;
  userId: string;
  householdId: string;
  recipe?: RecipeSummary | null;
}
export interface SavePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  groupId: string;
  userId: string;
}
export interface ShoppingListIn {
  name: string;
  group?: string | null;
  items: ListItem[];
}
export interface ShoppingListOut {
  name: string;
  group?: string | null;
  items: ListItem[];
  id: number;
}
export interface UpdatePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  id: number;
  groupId: string;
  userId: string;
}
