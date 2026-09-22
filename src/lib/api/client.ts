/**
 * The single place in the frontend that knows how to talk HTTP.
 *
 * Everything else in `src/lib/api/` describes *what* to ask for; this module
 * owns *how* the request is made, how failures are classified, and how the
 * backend's snake_case envelope is turned into something React can render.
 * Components never call `fetch` directly — that is what keeps error handling
 * consistent instead of reinvented per card.
 */

/** Wire shape of the backend's error envelope: `{"error": {"code", "message"}}`. */
interface ApiErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
  };
}

/**
 * A failed API call, carrying enough structure for the UI to distinguish
 * "the backend said no" from "the backend was not there at all".
 */
export class ApiError extends Error {
  readonly code: string;
  /** `0` when the request never produced a response (network/DNS/CORS failure). */
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }

  /** True when the backend is unreachable, as opposed to reachable and refusing. */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

/**
 * Base URL for the API, e.g. `http://localhost:8000/api/v1`.
 *
 * Read from the environment at build time so that a deployment can point the
 * same bundle at a different backend. The literal `process.env.NEXT_PUBLIC_*`
 * form is required — Next.js inlines these statically and cannot substitute a
 * dynamically computed key.
 */
const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

/** Guards against a hung backend holding a card in its loading state forever. */
const DEFAULT_TIMEOUT_MS = 8_000;

export interface RequestOptions {
  /** Caller-supplied cancellation, typically a React effect's cleanup signal. */
  signal?: AbortSignal;
  /** Overrides the default per-request timeout. */
  timeoutMs?: number;
}

function buildUrl(path: string, query?: Record<string, string | number>): string {
  const url = `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `${url}?${serialized}` : url;
}

/**
 * Extracts `error.code` / `error.message` from a non-2xx body.
 *
 * Falls back to the HTTP status when the body is absent or malformed, so a
 * proxy returning bare HTML still produces a usable message rather than a
 * `SyntaxError` thrown from the middle of the happy path.
 */
async function toApiError(response: Response): Promise<ApiError> {
  let code = "HTTP_ERROR";
  let message = `Request failed with status ${response.status}.`;

  try {
    const body: unknown = await response.json();
    const envelope = body as ApiErrorEnvelope;
    if (typeof envelope.error?.code === "string") code = envelope.error.code;
    if (typeof envelope.error?.message === "string") {
      message = envelope.error.message;
    }
  } catch {
    // A non-JSON error body is itself the diagnostic; the status-derived
    // default above already says everything we reliably know.
  }

  return new ApiError(message, code, response.status);
}

/**
 * Performs a JSON request and returns the parsed body.
 *
 * Every failure path — network, timeout, non-2xx, unparseable body — surfaces
 * as an `ApiError`, so callers need exactly one catch clause. Genuine
 * cancellations are re-thrown untouched so React effects can ignore them
 * instead of flashing an error for a request the user already navigated away
 * from.
 */
async function request<T>(
  path: string,
  init: RequestInit,
  options: RequestOptions = {},
  query?: Record<string, string | number>,
): Promise<T> {
  const { signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  // Compose the caller's signal with our timeout: whichever fires first aborts.
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const composedSignal = signal
    ? AbortSignal.any([signal, timeoutSignal])
    : timeoutSignal;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      signal: composedSignal,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    // The caller cancelled deliberately — not a failure worth reporting.
    if (signal?.aborted) throw error;

    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("The request timed out.", "TIMEOUT", 0);
    }
    throw new ApiError(
      "Could not reach the trading API.",
      "NETWORK_ERROR",
      0,
    );
  }

  if (!response.ok) throw await toApiError(response);

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "The API returned a malformed response.",
      "INVALID_RESPONSE",
      response.status,
    );
  }
}

export function apiGet<T>(
  path: string,
  options?: RequestOptions,
  query?: Record<string, string | number>,
): Promise<T> {
  return request<T>(path, { method: "GET" }, options, query);
}

export function apiPut<T>(
  path: string,
  body: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>(
    path,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    options,
  );
}
