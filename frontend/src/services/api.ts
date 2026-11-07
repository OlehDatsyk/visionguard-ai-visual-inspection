/** REST client. The token is kept in sessionStorage and is never logged. */
// vite.config.ts refuses a production build without VITE_API_BASE_URL, so the fallback is development-only.
// "/" means the API is on the same origin as the page, as in the single-service Docker image.
const BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010").replace(/\/+$/, "");
const PREFIX = `${BASE}/api/v1`;
const TOKEN_KEY = "visionguard.token";

export class ApiError extends Error {
  constructor(message: string, public status: number, public fields?: { field: string; message: string }[]) {
    super(message);
  }
}

let token: string | null = readToken();
let onUnauthorized: () => void = () => undefined;

function readToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Private mode: the session simply lasts until the page closes. */
  }
}

export const hasToken = (): boolean => token !== null;
export const setUnauthorizedHandler = (handler: () => void): void => { onUnauthorized = handler; };

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("The server could not be reached. Check that the backend is running.", 0);
  }
  if (response.ok) return response;
  if (response.status === 401 && token) {
    setToken(null);
    onUnauthorized();
  }
  let message = `Request failed (${response.status}).`;
  let fields;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    fields = body.errors;
    if (fields?.length) message = `${fields[0].field ? `${fields[0].field}: ` : ""}${fields[0].message}`;
  } catch {
    /* Keep the generic message. */
  }
  if (response.status === 429) message = "Too many requests. Please wait a moment and try again.";
  throw new ApiError(message, response.status, fields);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T = void>(path: string) => api<T>(path, { method: "DELETE" });
export const postForm = <T>(path: string, form: FormData) => api<T>(path, { method: "POST", body: form });

export async function fetchBlob(path: string): Promise<Blob> {
  return (await request(path)).blob();
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await fetchBlob(path));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
