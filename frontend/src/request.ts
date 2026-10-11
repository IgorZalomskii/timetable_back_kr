export class RequestFailure extends Error {
  kind: "timeout" | "network" | "invalid";
  constructor(kind: "timeout" | "network" | "invalid", message: string) {
    super(message);
    this.kind = kind;
  }
}

// Bound the whole response, including its body. Never retry a mutation implicitly:
// a lost response does not prove that the server rolled the transaction back.
export async function requestJson(url: string, init: RequestInit, timeoutMs = 15000) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new RequestFailure("timeout", "Сервер не ответил вовремя. Проверьте состояние данных перед повторным сохранением: действие могло выполниться."));
      controller.abort();
    }, timeoutMs);
  });
  const work = async () => {
    const response = await fetch(url, { ...init, signal: controller.signal });
    let data;
    try {
      data = await response.json();
    } catch (e) {
      if (controller.signal.aborted) throw e;
      if (response.ok) throw new RequestFailure("invalid", "Не удалось прочитать ответ сервера. Проверьте состояние данных.");
      data = { detail: response.status === 429 ? "Слишком много запросов. Подождите немного и повторите." : "Сервер временно недоступен. Повторите запрос." };
    }
    return { response, data };
  };
  try {
    return await Promise.race([work(), timeout]);
  } catch (e) {
    if (e instanceof RequestFailure) throw e;
    throw new RequestFailure("network", "Нет связи с сервером. Проверьте подключение. Перед повторным сохранением проверьте состояние данных.");
  } finally {
    clearTimeout(timer);
  }
}
