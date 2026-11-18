import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios';

/** A tiny in-test axios adapter: answers every request with a canned response. */
let status = 200;
let data: unknown = {};
let last: InternalAxiosRequestConfig | undefined;

const adapter: AxiosAdapter = async (config) => {
  last = config;
  const response = {
    data,
    status,
    statusText: String(status),
    headers: {},
    config,
  };
  if (status >= 400) {
    throw new AxiosError(`HTTP ${status}`, String(status), config, undefined, response);
  }
  return response;
};

const MockAdapter = {
  adapter,
  respond(nextStatus: number, nextData: unknown) {
    status = nextStatus;
    data = nextData;
  },
  lastHeaders(): Record<string, unknown> | undefined {
    if (!last) return undefined;
    return AxiosHeaders.from(last.headers as AxiosHeaders).toJSON() as Record<string, unknown>;
  },
  reset() {
    status = 200;
    data = {};
    last = undefined;
  },
};

export default MockAdapter;
