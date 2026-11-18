/**
 * Bridge between the login session and the API client: the axios interceptors read
 * the current access token and report 401 / 403 through these hooks, without the API
 * layer depending on React.
 */
type TokenGetter = () => string | undefined;

let getToken: TokenGetter = () => undefined;
let onUnauthorized: () => void = () => {};

export function setSessionHandlers(handlers: {
  getToken: TokenGetter;
  onUnauthorized: () => void;
}): void {
  getToken = handlers.getToken;
  onUnauthorized = handlers.onUnauthorized;
}

export function currentAccessToken(): string | undefined {
  return getToken();
}

export function reportUnauthorized(): void {
  onUnauthorized();
}

/** Window event raised when the API answers 403 (shown as a permission banner). */
export const FORBIDDEN_EVENT = 'cadence:forbidden';

export function reportForbidden(message?: string): void {
  window.dispatchEvent(new CustomEvent(FORBIDDEN_EVENT, { detail: message }));
}
