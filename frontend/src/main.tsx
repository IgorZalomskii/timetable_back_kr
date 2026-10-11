import React, { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  ApiError,
  setCsrf,
  User,
  Session,
  Entry,
  Schedule,
  Period,
  Lesson,
  Conflict,
  localDate,
  clock,
  dateLabel,
} from "./api";
import "./style.css";
import "./qa";
import { lessonCount } from "./presentation";

const roles: Record<string, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  teacher: "Преподаватель",
  student: "Студент",
};
const statuses: Record<string, string> = {
  planned: "По плану",
  moved: "Перенесено",
  cancelled: "Отменено",
  draft: "Черновик",
  published: "Опубликовано",
};
const dirs: Record<string, string> = {
  groups: "Группы",
  teachers: "Преподаватели",
  rooms: "Аудитории",
  subjects: "Дисциплины",
};
type Directories = Record<string, Entry[]>;
function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2" />
      </>
    ),
    edit: (
      <>
        <path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3" />
      </>
    ),
  };
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden="true"
    >
      {paths[name] || paths.calendar}
    </svg>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>{statuses[status] || status}</span>
  );
}
function ErrorBox({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div className="notice error" role="alert">
      <strong>{error.message}</strong>
      {error instanceof ApiError &&
        error.conflicts.map((c, i) => (
          <p key={i}>
            {dateLabel(c.starts)}, {clock(c.starts)}–{clock(c.ends)} ·{" "}
            {c.resources.join(", ")} · занятие №{c.lesson_id}
          </p>
        ))}
    </div>
  );
}
function DirectorySelect({
  label,
  kind,
  value,
  onChange,
  all = false,
  data,
}: {
  label: string;
  kind: string;
  value: string;
  onChange: (v: string) => void;
  all?: boolean;
  data: Directories;
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={!all}
      >
        <option value="">{all ? "Все" : "Выберите"}</option>
        {(data[kind] || [])
          .filter((x) => all || x.active)
          .map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
              {!x.active ? " · архив" : ""}
            </option>
          ))}
      </select>
    </Field>
  );
}

// Track individual forms: saving one form must not discard another draft.
const dirtyForms = new Set<HTMLFormElement>();
function hasUnsavedChanges() {
  for (const form of dirtyForms) if (!form.isConnected) dirtyForms.delete(form);
  return dirtyForms.size > 0;
}
type ConfirmationRequest = {
  message: string;
  resolve: (answer: boolean) => void;
};
function confirmAction(message: string): Promise<boolean> {
  return new Promise((resolve) =>
    window.dispatchEvent(
      new CustomEvent<ConfirmationRequest>("confirm-action", {
        detail: { message, resolve },
      }),
    ),
  );
}
function Confirmation() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [request, setRequest] = useState<ConfirmationRequest | null>(null);
  const pending = useRef<ConfirmationRequest | null>(null);
  useEffect(() => {
    const receive = (event: Event) => {
      const next = (event as CustomEvent<ConfirmationRequest>).detail;
      if (pending.current) {
        next.resolve(false);
        return;
      }
      pending.current = next;
      setRequest(next);
    };
    window.addEventListener("confirm-action", receive);
    return () => {
      window.removeEventListener("confirm-action", receive);
      pending.current?.resolve(false);
    };
  }, []);
  useEffect(() => {
    if (request) dialog.current?.showModal();
  }, [request]);
  const finish = (answer: boolean) => {
    dialog.current?.close();
    pending.current?.resolve(answer);
    pending.current = null;
    setRequest(null);
  };
  return (
    <dialog
      ref={dialog}
      className="confirmation"
      aria-labelledby="confirmation-title"
      aria-describedby="confirmation-message"
      onCancel={(event) => {
        event.preventDefault();
        finish(false);
      }}
    >
      <h2 id="confirmation-title">Подтвердите действие</h2>
      <p id="confirmation-message">{request?.message}</p>
      <div className="row">
        <button autoFocus onClick={() => finish(false)}>
          Остаться
        </button>
        <button className="primary" onClick={() => finish(true)}>
          Продолжить
        </button>
      </div>
    </dialog>
  );
}
async function discardChanges() {
  if (
    hasUnsavedChanges() &&
    !(await confirmAction(
      "Есть несохранённые изменения. Продолжить без сохранения?",
    ))
  )
    return false;
  dirtyForms.clear();
  return true;
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [initial, setInitial] = useState(true),
    [error, setError] = useState<Error | null>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [expired, setExpired] = useState(false);
  const [ready, setReady] = useState(false);
  const epoch = useRef(0);
  const booting = useRef(false);
  const actionPending = useRef(false);
  const [route, setRoute] = useState(location.hash.slice(1) || "schedule");
  const currentRoute = useRef(route);
  const [data, setData] = useState<Directories>({}),
    [schedules, setSchedules] = useState<Schedule[]>([]),
    [periods, setPeriods] = useState<Period[]>([]),
    [rev, setRev] = useState(0);
  useEffect(() => {
    const change = async () => {
      const next = location.hash.slice(1) || "schedule";
      if (next === currentRoute.current) return;
      if (!(await discardChanges())) {
        history.replaceState(null, "", "#" + currentRoute.current);
        return;
      }
      currentRoute.current = next;
      setRoute(next);
      setError(null);
      setNotice("");
      window.scrollTo(0, 0);
    };
    const edit = (e: Event) => {
      const form = (e.target as HTMLElement).closest<HTMLFormElement>(
        ".content form",
      );
      if (form) dirtyForms.add(form);
    };
    const leave = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("hashchange", change);
    document.addEventListener("input", edit);
    document.addEventListener("change", edit);
    window.addEventListener("beforeunload", leave);
    return () => {
      window.removeEventListener("hashchange", change);
      document.removeEventListener("input", edit);
      document.removeEventListener("change", edit);
      window.removeEventListener("beforeunload", leave);
    };
  }, []);
  function acceptSession(x: Session) {
    epoch.current += 1;
    setReady(false);
    setData({});
    setSchedules([]);
    setPeriods([]);
    setCsrf(x.csrf);
    setExpiresAt(x.expires_at);
    setUser(x.user);
    setExpired(false);
  }
  async function bootstrap() {
    if (booting.current) return;
    booting.current = true;
    setInitial(true);
    setError(null);
    try {
      acceptSession(await api<Session>("/auth/guest", "POST", {}));
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Не удалось открыть расписание"));
    } finally {
      setInitial(false);
      booting.current = false;
    }
  }
  useEffect(() => { void bootstrap(); }, []);
  async function refresh() {
    const generation = epoch.current;
    const [entries, nextSchedules, nextPeriods] = await Promise.all([
      Promise.all(
        Object.keys(dirs).map((k) => api<Entry[]>("/directories/" + k)),
      ),
      api<Schedule[]>("/schedules"),
      api<Period[]>("/periods"),
    ]);
    if (generation !== epoch.current) return;
    setData(
      Object.fromEntries(Object.keys(dirs).map((k, i) => [k, entries[i]])),
    );
    setSchedules(nextSchedules);
    setPeriods(nextPeriods);
    setRev((r) => r + 1);
    setReady(true);
  }
  useEffect(() => {
    let live = true;
    if (user) refresh().catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [user]);
  useEffect(() => {
    const expired = () => {
      epoch.current += 1;
      dirtyForms.clear();
      setUser(null);
      setReady(false);
      setData({});
      setSchedules([]);
      setPeriods([]);
      setCsrf("");
      setExpired(true);
      setError(new Error("Сессия завершена. Можно открыть новое личное демо."));
    };
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, []);
  useEffect(() => {
    if (
      user &&
      ((route === "directories" &&
        user.role !== "admin") ||
        (route === "editor" && !["admin", "dispatcher"].includes(user.role)))
    ) {
      dirtyForms.clear();
      location.hash = "schedule";
    }
  }, [user, route]);
  async function action(
    fn: () => Promise<void>,
    message = "",
    savedForm?: HTMLFormElement,
  ) {
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await fn();
      if (message) {
        if (savedForm) dirtyForms.delete(savedForm);
        setNotice(message);
        window.scrollTo(0, 0);
      }
    } catch (e) {
      setError(e as Error);
      window.scrollTo(0, 0);
      if (e instanceof ApiError && e.status === 401) {
        window.dispatchEvent(new Event("auth-expired"));
      }
    } finally {
      actionPending.current = false;
      setBusy(false);
    }
  }
  const canEdit = user && ["admin", "dispatcher"].includes(user.role);
  const nav = [
    { key: "schedule", title: "Расписание", icon: "calendar" },
    ...(canEdit ? [{ key: "editor", title: "Редактор", icon: "edit" }] : []),
    ...(user?.role === "admin"
      ? [
          { key: "directories", title: "Справочники", icon: "grid" },
        ]
      : []),
    { key: "profile", title: "Роль и профиль", icon: "users" },
  ];
  if (initial)
    return (
      <main className="loading" role="status">
        Открываем расписание…
      </main>
    );
  if (!user)
    return (
      <main className="session-screen">
        <section className="panel session-card">
          <div className="brand"><Icon name="calendar" /> Расписание</div>
          <h1>{expired ? "Открыть новое демо" : "Не удалось подключиться"}</h1>
          <p className="muted">{expired
            ? "Доступ привязан к этому браузеру и действует 7 дней. После завершения сессии создаётся новое пространство."
            : "Проверьте подключение и повторите попытку. Если сессия ещё действует, ваши изменения сохранятся."}</p>
          <ErrorBox error={error} />
          <button className="primary" onClick={() => void bootstrap()}>
            {expired ? "Начать новое демо" : "Повторить подключение"}
          </button>
        </section>
      </main>
    );
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="#schedule">
          <Icon name="calendar" /> Расписание
          <span className="brand-dot" />
        </a>
        <div className="workspace-label">УЧЕБНОЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация">
          {nav.map((n) => (
            <a
              href={"#" + n.key}
              key={n.key}
              className={route === n.key ? "active" : ""}
              aria-current={route === n.key ? "page" : undefined}
            >
              <Icon name={n.icon} />
              {n.title}
            </a>
          ))}
        </nav>
        <div className="profile">
          <div className="avatar">{user.name[0]}</div>
          <div>
            <strong>{user.name}</strong>
            <small>{roles[user.role]}</small>
          </div>
          <a className="text-button role-link" href="#profile">Сменить роль</a>
        </div>
      </aside>
      <main className="content">
        <header>
          <div>
            <h1>
              {nav.find((n) => n.key === route)?.title || "Раздел не найден"}
            </h1>
          </div>
          <span className="timezone">Москва · UTC+3</span>
        </header>
        <div className="demo-strip">
          <span><strong>Личное демо</strong> · изменения видны только вам</span>
          <a href="#profile">{roles[user.role]} <span aria-hidden="true">↗</span></a>
        </div>
        <ErrorBox error={error} />
        {error instanceof ApiError && [0, 503].includes(error.status) && (
          <button disabled={busy} onClick={async () => {
            if (!(await discardChanges())) return;
            await action(async () => acceptSession(await api<Session>("/auth/me")), "Состояние сверено с сервером");
          }}>Проверить состояние</button>
        )}
        {notice && (
          <div className="notice success" role="status">
            {notice}
          </div>
        )}
        {!ready ? (
          <section className="panel" aria-live="polite">
            <p>{error ? "Данные пока не загружены." : "Загружаем ваше расписание…"}</p>
            {error && <button disabled={busy} onClick={() => action(refresh)}>Повторить загрузку</button>}
          </section>
        ) : route === "schedule" ? (
          <SchedulePage
            key={`${user.id}:${user.role}:${user.group_id}:${user.teacher_id}`}
            user={user}
            data={data}
            rev={rev}
            action={action}
            busy={busy}
            refresh={refresh}
          />
        ) : route === "editor" && canEdit ? (
          <Editor
            data={data}
            schedules={schedules}
            periods={periods}
            action={action}
            busy={busy}
            refresh={refresh}
          />
        ) : route === "directories" && user.role === "admin" ? (
          <DirectoriesPage
            data={data}
            action={action}
            busy={busy}
            refresh={refresh}
            clearFeedback={() => { setError(null); setNotice(""); }}
          />
        ) : route === "profile" ? (
          <ProfilePage key={`${user.id}:${user.role}:${user.group_id}:${user.teacher_id}`} user={user} expiresAt={expiresAt}
            data={data} action={action} busy={busy} acceptSession={acceptSession} />
        ) : (
          <p>
            Этот раздел недоступен. <a href="#schedule">Открыть расписание</a>
          </p>
        )}
      </main>
    </div>
  );
}
type Action = (
  fn: () => Promise<void>,
  message?: string,
  savedForm?: HTMLFormElement,
) => Promise<void>;
function SchedulePage({
  user,
  data,
  rev,
  action,
  busy,
  refresh,
}: {
  user: User;
  data: Directories;
  rev: number;
  action: Action;
  busy: boolean;
  refresh: () => Promise<void>;
}) {
  const [day, setDay] = useState(localDate(new Date())),
    [group, setGroup] = useState(user.group_id?.toString() || ""),
    [teacher, setTeacher] = useState(user.teacher_id?.toString() || ""),
    [room, setRoom] = useState("");
  const lessonOpener = useRef<HTMLButtonElement | null>(null);
  const weekHeading = useRef<HTMLHeadingElement>(null);
  const [items, setItems] = useState<Lesson[]>([]),
    [total, setTotal] = useState(0),
    [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState<Error | null>(null),
    [reload, setReload] = useState(0),
    [selected, setSelected] = useState<Lesson | null>(null);
  const start = new Date(day + "T12:00:00+03:00");
  const weekDay = start.getUTCDay();
  start.setUTCDate(start.getUTCDate() - ((weekDay + 6) % 7));
  const dates = Array.from({ length: 7 }, (_, i) =>
    localDate(new Date(start.getTime() + i * 86400000)),
  );
  useEffect(() => {
    let live = true;
    setLoading(true);
    setLoadError(null);
    const q = new URLSearchParams({
      start: dates[0],
      end: dates[6],
      limit: "500",
    });
    if (group) q.set("group_id", group);
    if (teacher) q.set("teacher_id", teacher);
    if (room) q.set("room_id", room);
    api<{ items: Lesson[]; total: number }>("/lessons?" + q)
      .then((x) => {
        if (live) {
          setItems(x.items);
          setTotal(x.total);
        }
      })
      .catch((e) => {
        if (live) {
          setLoadError(e);
          setItems([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [dates[0], group, teacher, room, rev, reload]);
  const edit = ["admin", "dispatcher"].includes(user.role);
  return (
    <>
      <section className="toolbar panel">
        <div className="week-heading">
          <div aria-live="polite" aria-atomic="true">
            <h2 ref={weekHeading} tabIndex={-1}>
              {dateLabel(dates[0])} — {dateLabel(dates[6])}
            </h2>
            <p className="muted">
              {loading ? "Обновляем…" : loadError ? "Не удалось загрузить расписание" : lessonCount(total)}
            </p>
          </div>
          <div className="row">
            <button
              aria-label="Предыдущая неделя"
              onClick={() =>
                setDay(localDate(new Date(start.getTime() - 7 * 86400000)))
              }
            >
              ←
            </button>
            <button onClick={() => setDay(localDate(new Date()))}>
              Сегодня
            </button>
            <button
              aria-label="Следующая неделя"
              onClick={() =>
                setDay(localDate(new Date(start.getTime() + 7 * 86400000)))
              }
            >
              →
            </button>
          </div>
        </div>
        <details className="filter-disclosure">
          <summary>
            Дата и фильтры
            {[group, teacher, room].filter(Boolean).length > 0 &&
              ` · выбрано ${[group, teacher, room].filter(Boolean).length}`}
          </summary>
          <div className="filters">
            <Field label="Дата">
              <input
                type="date"
                value={day}
                required
                min="2000-01-03"
                max="2099-12-27"
                onChange={(e) => {
                  if (e.target.validity.valid && e.target.value)
                    setDay(e.target.value);
                }}
              />
            </Field>
            <DirectorySelect
              label="Группа"
              kind="groups"
              data={data}
              all
              value={group}
              onChange={setGroup}
            />
            <DirectorySelect
              label="Преподаватель"
              kind="teachers"
              data={data}
              all
              value={teacher}
              onChange={setTeacher}
            />
            <DirectorySelect
              label="Аудитория"
              kind="rooms"
              data={data}
              all
              value={room}
              onChange={setRoom}
            />
          </div>
          {(group || teacher || room) && (
            <button
              className="filter-reset"
              onClick={() => {
                setGroup("");
                setTeacher("");
                setRoom("");
              }}
            >
              Сбросить фильтры
            </button>
          )}
        </details>
      </section>
      <ErrorBox error={loadError} />
      {loadError && <button disabled={loading} onClick={() => setReload((n) => n + 1)}>Повторить загрузку расписания</button>}
      {selected && (
        <LessonDetails
          key={selected.id}
          lesson={selected}
          data={data}
          edit={edit}
          action={action}
          busy={busy}
          onClose={async () => {
            if (await discardChanges()) {
              setSelected(null);
              lessonOpener.current?.focus();
            }
          }}
          onSaved={async () => {
            setSelected(null);
            await refresh();
            weekHeading.current?.focus({ preventScroll: true });
          }}
        />
      )}
      <div className="schedule-summary">
        <span>
          <span className="legend-dot" /> Расписание занятий
        </span>
        {edit && (
          <a className="button primary" href="#editor">
            + Добавить занятие
          </a>
        )}
      </div>
      {total > 500 && (
        <p role="status">Показаны первые 500 занятий. Уточните фильтры.</p>
      )}
      <section
        className="week-grid"
        aria-label="Занятия по дням"
        aria-busy={loading}
      >
        {loadError ? <p className="calendar-loading">Данные недоступны. Повторите загрузку кнопкой выше.</p> : loading && items.length === 0 ? <p className="calendar-loading" role="status">Загружаем занятия…</p> : dates.map((d) => {
          const lessons = items.filter(
            (x) => localDate(new Date(x.starts)) === d,
          );
          return (
            <section
              className={"day " + (d === localDate(new Date()) ? "today" : "")}
              key={d}
            >
              <div className="day-title">
                <span>
                  {new Date(d + "T12:00:00+03:00").toLocaleDateString("ru", {
                    weekday: "short",
                  })}
                </span>
                <strong>{new Date(d + "T12:00:00+03:00").getDate()}</strong>
                {d === localDate(new Date()) && <small>Сегодня</small>}
              </div>
              <div className="day-lessons">
                {lessons.length ? (
                  lessons.map((x) => (
                    <button
                      className={"lesson " + x.status}
                      key={x.id}
                      onClick={async (event) => {
                        const opener = event.currentTarget;
                        if (selected?.id !== x.id && !(await discardChanges()))
                          return;
                        lessonOpener.current = opener;
                        setSelected(x);
                      }}
                    >
                      <span className="lesson-time">
                        {clock(x.starts)} — {clock(x.ends)}
                      </span>
                      <strong>{x.subject}</strong>
                      <span>{x.group}</span>
                      <span className="muted">{x.teacher}</span>
                      <div className="lesson-bottom">
                        <span className="room">{x.room}</span>
                        <Badge
                          status={
                            x.schedule_status === "draft" ? "draft" : x.status
                          }
                        />
                      </div>
                    </button>
                  ))
                ) : (
                  <p className="empty-day">{loading ? "…" : "Нет занятий"}</p>
                )}
              </div>
            </section>
          );
        })}
      </section>
    </>
  );
}
type Hist = {
  id: number;
  action: string;
  reason: string;
  created: string;
  actor: string;
  before: Partial<Lesson>;
  after: Partial<Lesson>;
};
function LessonDetails({
  lesson,
  data,
  edit,
  action,
  busy,
  onClose,
  onSaved,
}: {
  lesson: Lesson;
  data: Directories;
  edit: boolean;
  action: Action;
  busy: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [history, setHistory] = useState<Hist[]>([]),
    [historyLoading, setHistoryLoading] = useState(true),
    [historyRetry, setHistoryRetry] = useState(0),
    [error, setError] = useState<Error | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    detailHeading.current?.focus({ preventScroll: true });
    detailHeading.current?.closest("section")?.scrollIntoView({ block: "start", behavior: "instant" });
  }, []);
  useEffect(() => {
    let live = true;
    setHistoryLoading(true);
    setError(null);
    api<Hist[]>("/lessons/" + lesson.id + "/history")
      .then((items) => { if (live) setHistory(items); })
      .catch((e) => { if (live) setError(e); })
      .finally(() => { if (live) setHistoryLoading(false); });
    return () => { live = false; };
  }, [lesson.id, historyRetry]);
  return (
    <section className="panel detail">
      <div className="week-heading">
        <div>
          <h2 ref={detailHeading} tabIndex={-1}>
            {lesson.subject}
          </h2>
        </div>
        <button onClick={onClose}>Закрыть</button>
      </div>
      <p>
        {dateLabel(lesson.starts)} · {clock(lesson.starts)}–{clock(lesson.ends)}{" "}
        · {lesson.room} · <Badge status={lesson.status} />
      </p>
      {lesson.reason && <p>Причина: {lesson.reason}</p>}
      {edit && lesson.status !== "cancelled" && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = new FormData(form);
            const submit = (e.nativeEvent as SubmitEvent)
              .submitter as HTMLButtonElement;
            if (
              submit.value === "cancel" &&
              !(await confirmAction(
                "Отменить это занятие? Оно останется в расписании с причиной отмены.",
              ))
            )
              return;
            action(
              async () => {
                if (submit.value === "cancel") {
                  await api("/lessons/" + lesson.id + "/cancel", "POST", {
                    reason: f.get("reason"),
                    version: lesson.version,
                  });
                } else {
                  await api("/lessons/" + lesson.id, "PUT", {
                    ...lesson,
                    starts: f.get("date") + "T" + f.get("start") + ":00+03:00",
                    ends: f.get("date") + "T" + f.get("end") + ":00+03:00",
                    room_id: Number(f.get("room")),
                    reason: f.get("reason"),
                    version: lesson.version,
                  });
                }
                await onSaved();
              },
              "Изменение сохранено",
              form,
            );
          }}
        >
          <fieldset disabled={busy}>
            <div className="form-grid">
              <Field label="Дата переноса">
                <input
                  name="date"
                  type="date"
                  defaultValue={localDate(new Date(lesson.starts))}
                  required
                />
              </Field>
              <Field label="Начало">
                <input
                  name="start"
                  type="time"
                  defaultValue={clock(lesson.starts)}
                  required
                />
              </Field>
              <Field label="Окончание">
                <input
                  name="end"
                  type="time"
                  defaultValue={clock(lesson.ends)}
                  required
                />
              </Field>
              <Field label="Аудитория">
                <select name="room" defaultValue={lesson.room_id}>
                  {data.rooms
                    ?.filter((x) => x.active)
                    .map((x) => (
                      <option value={x.id} key={x.id}>
                        {x.name}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
            <Field label="Причина изменения или отмены">
              <input
                name="reason"
                required
                minLength={3}
                maxLength={500}
                placeholder="Например, замена аудитории"
              />
            </Field>
            <div className="row">
              <button className="primary" type="submit" value="move">
                Сохранить перенос
              </button>
              <button className="danger" type="submit" value="cancel">
                Отменить занятие
              </button>
            </div>
          </fieldset>
        </form>
      )}
      <h3>История изменений</h3>
      <ErrorBox error={error} />
      {error && <button disabled={historyLoading} onClick={() => setHistoryRetry((n) => n + 1)}>Повторить загрузку истории</button>}
      {historyLoading ? <p role="status">Загружаем историю…</p> : !error && history.length === 0 && <p>Изменений пока нет.</p>}
      <ul className="history">
        {history.map((h) => (
          <li key={h.id}>
            <strong>
              {{
                created: "Создано",
                moved: "Перенесено",
                cancelled: "Отменено",
              }[h.action] || h.action}
            </strong>
            <span>
              {dateLabel(h.created)}, {clock(h.created)} · {h.actor}
            </span>
            {h.reason && <p>{h.reason}</p>}
            {h.before.starts && h.after.starts && (h.before.starts !== h.after.starts || h.before.ends !== h.after.ends) && (
              <small>
                {dateLabel(h.before.starts)} {clock(h.before.starts)}{h.before.ends && `–${clock(h.before.ends)}`} →{" "}
                {dateLabel(h.after.starts)} {clock(h.after.starts)}{h.after.ends && `–${clock(h.after.ends)}`}
              </small>
            )}
            {h.before.room_id && h.after.room_id && h.before.room_id !== h.after.room_id && (
              <small>Аудитория: {data.rooms?.find((x) => x.id === h.before.room_id)?.name || `№${h.before.room_id}`} → {data.rooms?.find((x) => x.id === h.after.room_id)?.name || `№${h.after.room_id}`}</small>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Editor({
  data,
  schedules,
  periods,
  action,
  busy,
  refresh,
}: {
  data: Directories;
  schedules: Schedule[];
  periods: Period[];
  action: Action;
  busy: boolean;
  refresh: () => Promise<void>;
}) {
  const [schedule, setSchedule] = useState(""),
    [preview, setPreview] = useState<{
      items: { starts: string; ends: string; conflicts: Conflict[] }[];
      can_save: boolean;
    } | null>(null),
    [key, setKey] = useState(crypto.randomUUID()),
    [repeat, setRepeat] = useState(false),
    [repeatStart, setRepeatStart] = useState(localDate(new Date()));
  const active = schedules.find((x) => String(x.id) === schedule);
  function body(form: HTMLFormElement) {
    const f = new FormData(form);
    return {
      schedule_id: Number(f.get("schedule_id")),
      group_id: Number(f.get("group_id")),
      teacher_id: Number(f.get("teacher_id")),
      room_id: Number(f.get("room_id")),
      subject_id: Number(f.get("subject_id")),
      starts: f.get("date") + "T" + f.get("start") + ":00+03:00",
      ends: f.get("date") + "T" + f.get("end") + ":00+03:00",
      until: f.get("until"),
      interval_weeks: Number(f.get("interval")),
      request_key: key,
    };
  }
  return (
    <div className="editor-grid">
      <div>
        <section className="panel">
          <h2>Рабочее расписание</h2>
          <Field label="Выберите расписание">
            <select
              value={schedule}
              disabled={busy}
              onChange={(e) => {
                setSchedule(e.target.value);
                setPreview(null);
                setKey(crypto.randomUUID());
              }}
            >
              <option value="">Выберите</option>
              {schedules.map((x) => (
                <option value={x.id} key={x.id}>
                  {x.name} · {statuses[x.status]}
                </option>
              ))}
            </select>
          </Field>
          {active && (
            <div className="publish-line">
              <Badge status={active.status} />
              {active.status === "draft" ? (
                <button
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api("/schedules/" + active.id + "/publish", "POST");
                      await refresh();
                    }, "Расписание опубликовано")
                  }
                >
                  Опубликовать
                </button>
              ) : (
                <small>Изменения сразу видны пользователям</small>
              )}
            </div>
          )}
          <details>
            <summary>Создать учебный период и расписание</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const f = new FormData(form);
                action(
                  async () => {
                    await api("/periods", "POST", Object.fromEntries(f));
                    await refresh();
                    form.reset();
                  },
                  "Учебный период создан",
                  form,
                );
              }}
            >
              <fieldset disabled={busy}>
                <Field label="Название периода">
                  <input
                    name="name"
                    required
                    maxLength={150}
                    placeholder="Осенний семестр 2026"
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Начало периода">
                    <input type="date" name="start" required />
                  </Field>
                  <Field label="Конец периода">
                    <input type="date" name="end" required />
                  </Field>
                </div>
                <button>Создать период</button>
              </fieldset>
            </form>
            <hr />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const f = new FormData(form);
                action(
                  async () => {
                    const x = await api<Schedule>("/schedules", "POST", {
                      name: f.get("name"),
                      period_id: Number(f.get("period_id")),
                    });
                    await refresh();
                    setSchedule(String(x.id));
                    form.reset();
                  },
                  "Черновик создан",
                  form,
                );
              }}
            >
              <fieldset disabled={busy}>
                <Field label="Название расписания">
                  <input name="name" required maxLength={150} />
                </Field>
                <Field label="Учебный период">
                  <select name="period_id" required>
                    <option value="">Выберите</option>
                    {periods.map((x) => (
                      <option value={x.id} key={x.id}>
                        {x.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <button>Создать черновик</button>
              </fieldset>
            </form>
          </details>
        </section>
        <section className="panel">
          <h2>Добавить занятие</h2>
          {!schedule && (
            <p className="muted">Сначала выберите рабочее расписание выше.</p>
          )}
          <form
            onChange={() => {
              setPreview(null);
              setKey(crypto.randomUUID());
            }}
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const payload = body(form);
              const f = new FormData(form);
              const submit = (e.nativeEvent as SubmitEvent)
                .submitter as HTMLButtonElement;
              action(
                async () => {
                  if (submit.value === "preview") {
                    setPreview(await api("/series/preview", "POST", payload));
                    return;
                  }
                  if (f.get("repeat") === "yes") {
                    await api("/series", "POST", payload);
                  } else {
                    await api("/lessons", "POST", payload);
                  }
                  setPreview(null);
                  setKey(crypto.randomUUID());
                  await refresh();
                  form.reset();
                  setRepeat(false);
                },
                submit.value === "preview" ? "" : "Занятия сохранены",
                submit.value === "preview" ? undefined : form,
              );
            }}
          >
            <fieldset disabled={busy || !schedule}>
              <input type="hidden" name="schedule_id" value={schedule} />
              <div className="form-grid">
                {[
                  ["subject_id", "subjects", "Дисциплина"],
                  ["group_id", "groups", "Группа"],
                  ["teacher_id", "teachers", "Преподаватель"],
                  ["room_id", "rooms", "Аудитория"],
                ].map(([name, kind, label]) => (
                  <Field label={label} key={name}>
                    <select name={name} required>
                      <option value="">Выберите</option>
                      {data[kind]
                        ?.filter((x) => x.active)
                        .map((x) => (
                          <option value={x.id} key={x.id}>
                            {x.name}
                          </option>
                        ))}
                    </select>
                  </Field>
                ))}
                <Field label="Дата занятия">
                  <input
                    type="date"
                    name="date"
                    defaultValue={localDate(new Date())}
                    required
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Начало">
                    <input
                      type="time"
                      name="start"
                      defaultValue="09:00"
                      required
                    />
                  </Field>
                  <Field label="Окончание">
                    <input
                      type="time"
                      name="end"
                      defaultValue="10:30"
                      required
                    />
                  </Field>
                </div>
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  name="repeat"
                  value="yes"
                  checked={repeat}
                  onChange={(e) => {
                    const date = e.target.form?.elements.namedItem("date") as HTMLInputElement | null;
                    setRepeatStart(date?.value || localDate(new Date()));
                    setRepeat(e.target.checked);
                  }}
                />{" "}
                Повторять занятие
              </label>
              {repeat && (
                <>
                  <div className="form-grid">
                    <Field label="Повторение до">
                      <input
                        type="date"
                        name="until"
                        defaultValue={repeatStart}
                        required
                      />
                    </Field>
                    <Field label="Частота">
                      <select name="interval">
                        <option value="1">Каждую неделю</option>
                        <option value="2">Через неделю</option>
                      </select>
                    </Field>
                  </div>
                  <p className="muted small">
                    Повторение идёт в день недели первого занятия. Предпросмотр
                    проверяет все даты; сохранение повторно проверяет занятость.
                  </p>
                </>
              )}
              <div className="row">
                {repeat && <button value="preview">Предпросмотр серии</button>}
                <button value="save" className="primary">
                  {busy ? "Сохраняем…" : "Сохранить"}
                </button>
              </div>
            </fieldset>
          </form>
        </section>
      </div>
      <section className="panel preview">
        <h2>Занятость и повторения</h2>
        {preview ? (
          <>
            <div
              className={"notice " + (preview.can_save ? "success" : "error")}
            >
              {preview.can_save
                ? "Пересечений нет — можно сохранить"
                : "Есть пересечения. Измените параметры."}
            </div>
            <ul className="history">
              {preview.items.map((x, i) => (
                <li key={i}>
                  <strong>{dateLabel(x.starts)}</strong>
                  <span>
                    {clock(x.starts)}–{clock(x.ends)}
                  </span>
                  {x.conflicts.map((c, j) => (
                    <p className="error-text" key={j}>
                      {c.resources.join(", ")} заняты · занятие №{c.lesson_id}
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="empty-state">
            <Icon name="calendar" />
            <h3>Сначала задайте параметры</h3>
            <p>Здесь появятся даты серии и обнаруженные пересечения.</p>
          </div>
        )}
        <div className="hint">
          <strong>Проверяем три ресурса</strong>
          <p>
            Группу, преподавателя и аудиторию. При конфликте вся серия останется
            несохранённой.
          </p>
        </div>
      </section>
    </div>
  );
}

function DirectoriesPage({
  data,
  action,
  busy,
  refresh,
  clearFeedback,
}: {
  data: Directories;
  action: Action;
  busy: boolean;
  refresh: () => Promise<void>;
  clearFeedback: () => void;
}) {
  const [kind, setKind] = useState("groups"),
    [selected, setSelected] = useState<Entry | null>(null);
  return (
    <>
      <div className="tabs">
        {Object.entries(dirs).map(([k, label]) => (
          <button
            key={k}
            aria-pressed={kind === k}
            className={kind === k ? "selected" : ""}
            onClick={async () => {
              if (kind === k || !(await discardChanges())) return;
              setKind(k);
              setSelected(null);
              clearFeedback();
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="editor-grid">
        <section className="panel">
          <h2>{dirs[kind]}</h2>
          <div className="directory-list">
            {data[kind]?.map((x) => (
              <div className="directory-row" key={x.id}>
                <div>
                  <strong>{x.name}</strong>
                  <small>
                    {x.size
                      ? `${x.size} человек`
                      : x.capacity
                        ? `${x.capacity} мест`
                        : ""}{" "}
                    {!x.active ? " · В архиве" : ""}
                  </small>
                </div>
                <button
                  onClick={async () => {
                    if (selected?.id !== x.id && (await discardChanges()))
                      setSelected(x);
                  }}
                >
                  Изменить
                </button>
              </div>
            ))}
            {!data[kind]?.length && <p>Пока нет записей. Добавьте первую.</p>}
          </div>
        </section>
        <section className="panel">
          <h2>{selected ? "Изменить запись" : "Новая запись"}</h2>
          <form
            key={kind + ":" + selected?.id}
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const f = new FormData(form);
              action(
                async () => {
                  const payload = {
                    name: f.get("name"),
                    active: f.get("active") === "yes",
                    size: Number(f.get("size") || 20),
                    capacity: Number(f.get("capacity") || 30),
                  };
                  await api(
                    "/directories/" +
                      kind +
                      (selected ? "/" + selected.id : ""),
                    selected ? "PUT" : "POST",
                    payload,
                  );
                  await refresh();
                  setSelected(null);
                  form.reset();
                },
                "Справочник обновлён",
                form,
              );
            }}
          >
            <fieldset disabled={busy}>
              <Field label="Название">
                <input
                  name="name"
                  defaultValue={selected?.name || ""}
                  required
                  maxLength={100}
                />
              </Field>
              {kind === "groups" && (
                <Field label="Численность">
                  <input
                    name="size"
                    type="number"
                    min="1"
                    max="1000"
                    defaultValue={selected?.size || 20}
                    required
                  />
                </Field>
              )}
              {kind === "rooms" && (
                <Field label="Вместимость">
                  <input
                    name="capacity"
                    type="number"
                    min="1"
                    max="1000"
                    defaultValue={selected?.capacity || 30}
                    required
                  />
                </Field>
              )}
              <label className="check">
                <input
                  name="active"
                  type="checkbox"
                  value="yes"
                  defaultChecked={selected?.active ?? true}
                />{" "}
                Активная запись
              </label>
              <div className="row">
                <button className="primary">Сохранить</button>
                {selected && (
                  <button
                    type="button"
                    onClick={async () => {
                      if (await discardChanges()) setSelected(null);
                    }}
                  >
                    Отмена
                  </button>
                )}
              </div>
            </fieldset>
          </form>
          <p className="muted small">
            Архивные записи сохраняют историю. Запись с будущими занятиями
            нельзя отправить в архив.
          </p>
        </section>
      </div>
    </>
  );
}
const roleDescriptions: Record<string, { icon: string; summary: string; detail: string }> = {
  student: { icon: "calendar", summary: "Расписание своей группы", detail: "Смотрите опубликованные занятия, аудитории, переносы и отмены. Группа задаёт начальный фильтр." },
  teacher: { icon: "users", summary: "Занятия преподавателя", detail: "Смотрите опубликованные занятия выбранного преподавателя и историю изменений. Редактирование недоступно." },
  dispatcher: { icon: "edit", summary: "Составление расписания", detail: "Создавайте периоды и черновики, добавляйте и переносите занятия, проверяйте конфликты и публикуйте расписание." },
  admin: { icon: "grid", summary: "Расписание и справочники", detail: "Все возможности диспетчера, а также управление группами, преподавателями, аудиториями и дисциплинами вашего демо." },
};
function ProfilePage({ user, expiresAt, data, action, busy, acceptSession }: {
  user: User; expiresAt: string; data: Directories; action: Action; busy: boolean; acceptSession: (session: Session) => void;
}) {
  const [role, setRole] = useState(user.role);
  const [name, setName] = useState(user.name);
  const [group, setGroup] = useState(user.group_id?.toString() || data.groups?.find(x => x.active)?.id.toString() || "");
  const [teacher, setTeacher] = useState(user.teacher_id?.toString() || data.teachers?.find(x => x.active)?.id.toString() || "");
  const profileForm = useRef<HTMLFormElement>(null);
  const changed = role !== user.role || name.trim() !== user.name ||
    (role === "student" && Number(group) !== user.group_id) ||
    (role === "teacher" && Number(teacher) !== user.teacher_id);
  useEffect(() => {
    const form = profileForm.current;
    if (!form) return;
    if (changed) dirtyForms.add(form);
    else dirtyForms.delete(form);
    return () => { dirtyForms.delete(form); };
  }, [changed]);
  return (
    <div className="profile-page">
      <section className="panel">
        <h2>Попробуйте расписание в разных ролях</h2>
        <p className="muted">Аккаунт создан автоматически. Выберите роль и примените её: занятия и ваши изменения останутся на месте.</p>
        <form ref={profileForm} onSubmit={e => {
          e.preventDefault();
          const form = e.currentTarget;
          action(async () => {
            const payload: Record<string, unknown> = { role, name: name.trim() };
            if (role === "student" && group) payload.group_id = Number(group);
            if (role === "teacher" && teacher) payload.teacher_id = Number(teacher);
            const session = await api<Session>("/auth/profile", "PUT", payload);
            dirtyForms.delete(form);
            acceptSession(session);
          }, "Роль и профиль сохранены", form);
        }}>
          <fieldset disabled={busy}>
            <legend className="field-legend">Роль в демо</legend>
            <div className="role-cards">
              {Object.entries(roleDescriptions).map(([key, info]) => (
                <label key={key} className={"role-card " + (role === key ? "selected" : "")}>
                  <input type="radio" name="role" value={key} checked={role === key} onChange={() => setRole(key)} />
                  <span className="role-card-icon"><Icon name={info.icon} /></span>
                  <span><strong>{roles[key]}</strong><small>{info.summary}</small></span>
                  {user.role === key && <span className="role-current">Сейчас</span>}
                </label>
              ))}
            </div>
            <p className="role-explanation" aria-live="polite">{roleDescriptions[role].detail}</p>
            <div className="profile-fields">
              <Field label="Как к вам обращаться">
                <input name="name" value={name} onChange={e => setName(e.target.value)} required maxLength={80} autoComplete="nickname" />
              </Field>
              {role === "student" && <DirectorySelect label="Ваша группа" kind="groups" data={data} value={group} onChange={setGroup} />}
              {role === "teacher" && <DirectorySelect label="Преподаватель" kind="teachers" data={data} value={teacher} onChange={setTeacher} />}
            </div>
            <div className="row profile-actions">
              <button className="primary" disabled={!changed || !name.trim()}>{busy ? "Сохраняем…" : "Применить роль и профиль"}</button>
              <a className="button" href="#schedule">К расписанию</a>
            </div>
          </fieldset>
        </form>
      </section>
      <section className="panel session-info">
        <div>
          <h2>Доступ в этом браузере</h2>
          <p className="muted">Сессия действует 7 дней{expiresAt ? ", до " + dateLabel(expiresAt) + ", " + clock(expiresAt) : ""}. Очистка cookies или другой браузер создадут отдельное демо. Пароль и регистрация не нужны.</p>
          <p className="small muted">«Начать заново» удалит занятия и изменения только в вашем пространстве и восстановит учебный пример.</p>
        </div>
        <button disabled={busy} onClick={async () => {
          if (!(await confirmAction("Начать заново? Все занятия, справочники и несохранённые изменения вашего личного демо будут удалены. Будет создан новый учебный пример. Отменить это действие нельзя."))) return;
          action(async () => {
            const session = await api<Session>("/auth/guest/reset", "POST", {});
            dirtyForms.clear();
            acceptSession(session);
            location.hash = "schedule";
          }, "Новое личное демо готово");
        }}>Начать заново</button>
      </section>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <>
    <Confirmation />
    <App />
  </>,
);
