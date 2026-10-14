import * as contracts from './contracts';
import type {Bundle, EvaluationJob, EvaluationTruth, Evidence, Incident, IncidentInput, Investigation, ReplayInput, Report, Scenario, Timeline} from './types';

export class ApiError extends Error {
  constructor(public code: string, message: string, public request_id: string, public retryable = false, public status = 0) { super(message); this.name = 'ApiError'; }
}
export function asError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('CLIENT_ERROR', 'The request could not be completed.', 'unavailable', true);
}
const HIDDEN = new Set(['ground_truth', 'expected_root_cause', 'expected_category', 'injected_fault', 'injection_record', 'injection_ts', 'chaos_run_id', 'truth_database_url', 'scenario_id']);
/** Defense in depth: non-evaluation displays discard protected fields, including nested payloads. */
export function observable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(observable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key]) => !HIDDEN.has(key.toLowerCase())).map(([key, child]) => [key, observable(child)]));
  return value;
}
export async function request<T>(path: string, options: RequestInit = {}, evaluation = false, validate?: (value: unknown) => boolean): Promise<T> {
  const requestId = crypto.randomUUID();
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, {once: true});
  if (options.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 60000);
  let response: Response;
  try { response = await fetch('/api' + path, {...options, signal: controller.signal, headers: {'Content-Type': 'application/json', 'X-Request-ID': requestId, ...options.headers}}); }
  catch (error) { if (options.signal?.aborted) throw error; throw new ApiError('NETWORK_ERROR', 'Cannot reach the API. Check the local lab and retry.', requestId, true); }
  finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); }
  const rid = response.headers.get('X-Request-ID') ?? requestId;
  let value: unknown;
  try { value = await response.json(); } catch { throw new ApiError('INVALID_RESPONSE', 'The API returned an unreadable response.', rid, true, response.status); }
  if (!response.ok) {
    const detail = (value as {error?: {code?: string; message?: string; request_id?: string; retryable?: boolean}})?.error;
    throw new ApiError(detail?.code ?? 'HTTP_ERROR', detail?.message ?? 'Request failed.', detail?.request_id ?? rid, detail?.retryable ?? false, response.status);
  }
  if (value === null || typeof value !== 'object' || (validate && !validate(value))) throw new ApiError('INVALID_RESPONSE', 'The API returned an unexpected response.', rid, false, response.status);
  return (evaluation ? value : observable(value)) as T;
}
const incident = (id: string) => '/incidents/' + encodeURIComponent(id);
const post = (body: unknown): RequestInit => ({method: 'POST', body: JSON.stringify(body)});
export const api = {
  incidents: (signal?: AbortSignal) => request<Incident[]>('/incidents', {signal}, false, contracts.incidentListContract),
  incident: (id: string, signal?: AbortSignal) => request<Incident>(incident(id), {signal}, false, contracts.incidentContract),
  create: (input: IncidentInput) => request<Incident>('/incidents', post(input), false, contracts.incidentContract),
  evidence: (id: string, signal?: AbortSignal) => request<Bundle>(incident(id) + '/evidence', {signal}, false, contracts.bundleContract),
  evidenceItem: (id: string, eid: string, signal?: AbortSignal) => request<Evidence>(incident(id) + '/evidence/' + encodeURIComponent(eid), {signal}, false, contracts.evidenceContract),
  timeline: (id: string, signal?: AbortSignal) => request<Timeline>(incident(id) + '/timeline', {signal}, false, contracts.timelineContract),
  latest: (id: string, signal?: AbortSignal) => request<Investigation>(incident(id) + '/investigation', {signal}, false, contracts.investigationContract),
  investigate: (id: string) => request<Investigation>(incident(id) + '/investigate', post({}), false, contracts.investigationContract),
  investigation: (id: string, signal?: AbortSignal) => request<Investigation>('/investigations/' + encodeURIComponent(id), {signal}, false, contracts.investigationContract),
  report: (id: string, signal?: AbortSignal) => request<Report>(incident(id) + '/report', {signal}, false, contracts.reportContract),
  scenarios: (signal?: AbortSignal) => request<Scenario[]>('/scenarios', {signal}, false, contracts.scenarioContract),
  replay: (body: ReplayInput) => request<EvaluationJob>('/evaluations/replay', post(body), true, contracts.evaluationContract),
  evaluation: (id: string, signal?: AbortSignal) => request<EvaluationJob>('/evaluations/' + encodeURIComponent(id), {signal}, true, contracts.evaluationContract),
  truth: (id: string, signal?: AbortSignal) => request<EvaluationTruth>('/evaluations/' + encodeURIComponent(id) + '/ground-truth', {signal}, true, contracts.truthContract),
};
