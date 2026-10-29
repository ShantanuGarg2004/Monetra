/** Structured API errors for status-aware UI handling. */

export class ApiError extends Error {
  constructor({ message, status = 0, code = "server_error", details = null, retryAfter = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
  }
}

function codeFromStatus(status) {
  if (status === 401) return "unauthorized";
  if (status === 400) return "validation_error";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limit_exceeded";
  if (status === 502 || status === 503 || status === 504) return "upstream_error";
  if (status >= 500) return "server_error";
  return "server_error";
}

function parseRetryAfter(res, data) {
  const fromBody = data?.retry_after ?? data?.retryAfter;
  if (fromBody != null && !Number.isNaN(Number(fromBody))) return Number(fromBody);
  const hdr = res.headers?.get?.("Retry-After");
  if (hdr != null && !Number.isNaN(Number(hdr))) return Number(hdr);
  return null;
}

function messageFromBody(data, status) {
  if (data?.details && typeof data.details === "object") {
    const parts = Object.values(data.details).flat().filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (typeof data?.error === "string" && data.error.trim()) return data.error;
  if (typeof data?.message === "string" && data.message.trim()) return data.message;
  return `Request failed (${status})`;
}

/** Normalize fetch failures / HTTP errors into ApiError. */
export function toApiError(input, res = null, data = null) {
  if (input instanceof ApiError) return input;

  if (input?.name === "AbortError") {
    return new ApiError({ message: "Request cancelled", status: 0, code: "aborted" });
  }

  if (!res) {
    return new ApiError({
      message: "Can't reach the Monetra API. Confirm the backend is running on port 5000.",
      status: 0,
      code: "network_error",
    });
  }

  const status = res.status;
  const code = data?.code || codeFromStatus(status);
  const retryAfter = parseRetryAfter(res, data);
  let message = messageFromBody(data, status);

  if (code === "session_expired") {
    message = "Your session ended. Sign in again.";
  } else if (code === "unauthorized") {
    message = "Unauthorized — check your API key configuration.";
  } else if (code === "invalid_credentials") {
    message = "Email or password is incorrect.";
  } else if (code === "account_exists") {
    message = "An account with this email already exists";
  } else if (code === "rate_limit_exceeded") {
    message = retryAfter
      ? `Too many requests. Try again in ${retryAfter}s.`
      : "Too many requests. Please wait a moment and try again.";
  } else if (code === "rate_policy_missing") {
    message = "This API route is not available.";
  } else if (code === "upstream_timeout") {
    message = "The AI provider took too long. Please retry.";
  } else if (code === "upstream_rate_limit") {
    message = "AI provider rate limit hit. Please wait and retry.";
  } else if (code === "upstream_error") {
    message = data?.error || "The AI provider is unavailable. Please try again shortly.";
  } else if (code === "pdf_unavailable") {
    message = data?.error || "PDF is not available right now.";
  } else if (code === "network_error") {
    message = "Can't reach the Monetra API. Confirm the backend is running on port 5000.";
  }

  return new ApiError({ message, status, code, details: data?.details ?? null, retryAfter });
}

/** Toast tone for a given error. */
export function toastTypeForError(err) {
  const e = err instanceof ApiError ? err : toApiError(err);
  if (e.code === "aborted") return null;
  if (e.code === "rate_limit_exceeded") return "warning";
  if (e.code === "upstream_rate_limit" || e.code === "upstream_timeout") return "warning";
  if (e.code === "not_found") return "info";
  return "error";
}

export function formatApiErrorMessage(err, fallback = "Something went wrong") {
  if (!err) return fallback;
  if (err instanceof ApiError) return err.message || fallback;
  return err.message || fallback;
}
