export type Profile = {
  role: string;
  name: string;
  group_id?: number;
  teacher_id?: number;
};

type ProfileSession = {
  user: { id: number; role: string; name: string; group_id?: number | null; teacher_id?: number | null };
};

function matches(session: ProfileSession, userId: number, profile: Profile) {
  const user = session.user;
  return user.id === userId && user.role === profile.role && user.name === profile.name &&
    (profile.role !== "student" || user.group_id === profile.group_id) &&
    (profile.role !== "teacher" || user.teacher_id === profile.teacher_id);
}

// A lost PUT response is ambiguous. Read back this same account before reporting
// failure, but never replay a write: another tab may already have changed it.
export async function saveProfile<T extends ProfileSession>(
  userId: number,
  profile: Profile,
  write: () => Promise<T>,
  read: () => Promise<T>,
  checking: () => void,
): Promise<T> {
  try {
    return await write();
  } catch (error) {
    const status = (error as { status?: number })?.status;
    if (status !== 0 && !(status !== undefined && status >= 500)) throw error;
    checking();
    let actual: T;
    try {
      actual = await read();
    } catch (readError) {
      if ((readError as { status?: number })?.status === 401) throw readError;
      throw error;
    }
    if (matches(actual, userId, profile)) return actual;
    if (error instanceof Error) {
      error.message = "Сохранение не подтверждено: на сервере другие настройки профиля. Ваш выбор оставлен в форме. Примените роль повторно или нажмите «Проверить состояние», чтобы загрузить настройки с сервера.";
    }
    throw error;
  }
}
