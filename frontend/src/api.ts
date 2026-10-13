import { validationMessage } from "./presentation";
import { requestJson } from "./request";

export type User = {
  id: number;
  name: string;
  username?: string;
  workspace_id: number;
  is_guest: boolean;
  role: string;
  group_id: number | null;
  teacher_id: number | null;
  active: boolean;
};
export type Session = { user: User; csrf: string; expires_at: string; created?: boolean };
export type Entry = {
  id: number;
  name: string;
  active: boolean;
  size?: number;
  capacity?: number;
};
export type Schedule = {
  id: number;
  name: string;
  status: string;
  period_id: number;
};
export type Period = { id: number; name: string; start: string; end: string };
export type Lesson = {
  id: number;
  schedule_id: number;
  group_id: number;
  teacher_id: number;
  room_id: number;
  subject_id: number;
  starts: string;
  ends: string;
  status: string;
  reason: string;
  version: number;
  subject: string;
  group: string;
  teacher: string;
  room: string;
  schedule_status: string;
};
export type Conflict = {
  lesson_id: number;
  starts: string;
  ends: string;
  resources: string[];
};
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public conflicts: Conflict[] = [],
  ) {
    super(message);
  }
}
export async function api<T = unknown>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const { response, data } = await requestJson(import.meta.env.BASE_URL + "api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Requested-With": "schedule-app" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch((error) => {
    throw new ApiError(error.message, 0);
  });
  if (response.status === 401 && !path.startsWith("/auth/"))
    window.dispatchEvent(new Event("auth-expired"));
  if (!response.ok) {
    const d = data.detail;
    throw new ApiError(
      typeof d === "string"
        ? d
        : Array.isArray(d)
          ? d.map((x) => validationMessage(x.msg || "Проверьте введённые данные")).join("; ")
          : d?.message || "Не удалось выполнить запрос",
      response.status,
      d?.conflicts || [],
    );
  }
  return data;
}
export const localDate = (d: Date) =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Moscow" }).format(d);
export const clock = (s: string) =>
  new Intl.DateTimeFormat("ru", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(new Date(s));
export const dateLabel = (s: string) =>
  new Intl.DateTimeFormat("ru", {
    day: "numeric",
    month: "long",
    timeZone: "Europe/Moscow",
  }).format(new Date(s));
