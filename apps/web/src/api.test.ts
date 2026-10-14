import {afterEach, expect, test, vi} from 'vitest';
import {api, ApiError, observable, request} from './api';
import {bundle, evidence, incident} from './test-fixtures';
afterEach(() => {vi.unstubAllGlobals();vi.restoreAllMocks();});
test('client uses same-origin paths, sends a request ID and preserves explicit creation scope', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(incident));vi.stubGlobal('fetch', fetcher);expect(await api.create(incident)).toEqual(incident);
  const [path, opts] = fetcher.mock.calls[0];expect(path).toBe('/api/incidents');expect(opts.method).toBe('POST');expect(JSON.parse(opts.body).related_services).toEqual(['gateway']);expect(opts.headers['X-Request-ID']).toBeTruthy();
});
test('client exposes the API error contract and server request_id', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({error: {code: 'SCOPE_POLICY_DENIED', message: 'Requested scope exceeds incident', retryable: false, request_id: 'server-request'}}, {status: 403})));
  await expect(api.evidence('id')).rejects.toMatchObject({code: 'SCOPE_POLICY_DENIED', request_id: 'server-request', status: 403, retryable: false});
});
test('malformed responses and network failure have actionable errors with request IDs', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('broken', {headers: {'X-Request-ID': 'broken-response'}})));await expect(request('/incidents')).rejects.toMatchObject({code: 'INVALID_RESPONSE', request_id: 'broken-response'});
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));await expect(api.incidents()).rejects.toBeInstanceOf(ApiError);
});
test('evidence-by-ID is incident scoped and outside IDs are never looked up globally', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(evidence));vi.stubGlobal('fetch', fetcher);await api.evidenceItem(incident.id, evidence.evidence_id);expect(fetcher.mock.calls[0][0]).toBe(`/api/incidents/${incident.id}/evidence/${evidence.evidence_id}`);
});
test('protected fields are dropped recursively from non-evaluation API results', async () => {
  const contaminated = {...bundle, expected_root_cause: 'ORACLE_ONLY', items: [{...evidence, payload: {value: 4, ground_truth: {expected_root_cause: 'ORACLE_ONLY'}, nested: {injected_fault: 'ORACLE_ONLY'}}}]};
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(contaminated)));const result = await api.evidence(incident.id);expect(JSON.stringify(result)).not.toContain('ORACLE_ONLY');expect(result.items[0].payload.value).toBe(4);expect(observable({expected_category: 'hidden', event_name: 'die'})).toEqual({event_name: 'die'});
});
test('only the dedicated evaluation truth endpoint preserves the oracle disclosure', async () => {
  const body = {evaluation_id: 'e', scenario_id: 'SCN-001', expected_root_cause: 'ORACLE_ONLY', required_evidence: [], seed: 42, source: 'golden'};const fetcher = vi.fn().mockResolvedValue(Response.json(body));vi.stubGlobal('fetch', fetcher);
  expect((await api.truth('e')).expected_root_cause).toBe('ORACLE_ONLY');expect(fetcher.mock.calls[0][0]).toBe('/api/evaluations/e/ground-truth');
});

test('successful JSON with an invalid result shape fails safely with its request ID', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({items: 'invalid'}, {headers: {'X-Request-ID': 'shape-request'}})));
  await expect(api.evidence(incident.id)).rejects.toMatchObject({code: 'INVALID_RESPONSE', request_id: 'shape-request'});
});
