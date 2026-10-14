import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {api, ApiError} from './api';
import {EvidenceViewer, HypothesisList, ReportSections, TraceEvents} from './components';
import {bundle, evidence, hypothesis, incident, outside, report} from './test-fixtures';
import {CreateIncident, validateWindow} from './IncidentsPage';
afterEach(() => {cleanup();vi.restoreAllMocks();});
test('ranked hypotheses preserve FOR and AGAINST and open citations beyond the cap', () => {
  const open = vi.fn();render(<HypothesisList items={[hypothesis]} bundleIds={new Set([evidence.evidence_id])} open={open}/>);
  expect(screen.getByText('91%')).toBeVisible();expect(screen.getByText('FOR')).toBeVisible();expect(screen.getByText('AGAINST')).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: `Open evidence ${outside.evidence_id} outside bundle`}));expect(open).toHaveBeenCalledWith(outside.evidence_id);
  fireEvent.click(screen.getByText('Falsification & evidence gaps'));expect(screen.getByText(hypothesis.falsification_condition)).toBeVisible();
});
test('evidence viewer resolves outside IDs through the incident evidence-by-ID API', async () => {
  const lookup = vi.spyOn(api, 'evidenceItem').mockResolvedValue(outside);
  render(<EvidenceViewer incidentId={incident.id} evidenceId={outside.evidence_id} bundle={bundle} close={vi.fn()}/>);
  expect(await screen.findByText('Replica lag rising')).toBeVisible();expect(screen.getByText('outside bundle')).toBeVisible();expect(screen.getByText(/replica_lag_seconds/)).toBeVisible();
  expect(lookup).toHaveBeenCalledWith(incident.id, outside.evidence_id, expect.any(AbortSignal));
});
test('evidence displays redaction metadata and treats telemetry as text', () => {
  const malicious = {...evidence, summary: '<script>alert(1)</script>', payload: {body: '<img src=x onerror=alert(1)>', ground_truth: {expected_root_cause: 'ORACLE_ONLY'}}};
  render(<EvidenceViewer incidentId={incident.id} evidenceId={evidence.evidence_id} bundle={{...bundle, items: [malicious]}} close={vi.fn()}/>);
  expect(screen.getByText('attributes.token')).toBeVisible();expect(screen.getByText(/secret_key/)).toBeVisible();expect(screen.getByText(malicious.summary)).toBeVisible();expect(document.querySelector('script')).toBeNull();expect(screen.queryByText(/ORACLE_ONLY/)).toBeNull();
});
test('failed citation lookup displays the API request ID and a retry', async () => {
  vi.spyOn(api, 'evidenceItem').mockRejectedValue(new ApiError('NOT_FOUND', 'Scoped evidence missing', 'request-123', false, 404));
  render(<EvidenceViewer incidentId={incident.id} evidenceId={outside.evidence_id} bundle={bundle} close={vi.fn()}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('request-123');expect(screen.getByRole('button', {name: 'Retry'})).toBeVisible();
});
test('report has distinct facts, hypotheses and approval-required recommendations', () => {
  render(<ReportSections report={report} bundleIds={new Set([evidence.evidence_id])} open={vi.fn()} incidentId={incident.id}/>);
  const facts = screen.getByRole('region', {name: 'Facts'}), hypotheses = screen.getByRole('region', {name: 'Hypotheses'}), recommendations = screen.getByRole('region', {name: 'Recommendations'});
  expect(within(facts).getByText('Runtime exit observed.')).toBeVisible();expect(within(hypotheses).getByText(hypothesis.statement)).toBeVisible();expect(within(recommendations).getByText('Requires human approval')).toBeVisible();expect(within(recommendations).getByText(/Not executed/)).toBeVisible();
});
test('Markdown export uses the stored report, not HTML', () => {
  const create = vi.fn().mockReturnValue('blob:report');Object.defineProperty(URL, 'createObjectURL', {configurable: true, value: create});Object.defineProperty(URL, 'revokeObjectURL', {configurable: true, value: vi.fn()});const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  render(<ReportSections report={report} bundleIds={new Set()} open={vi.fn()} incidentId={incident.id}/>);fireEvent.click(screen.getByRole('button', {name: /Export Markdown/}));expect(create).toHaveBeenCalledWith(expect.any(Blob));expect(click).toHaveBeenCalledOnce();
});
test('incident window validation rejects reversed or oversized windows and accepts exactly six hours', () => {
  expect(validateWindow('2026-10-14T10:00', '2026-10-14T09:00')).toMatch(/after/);expect(validateWindow('2026-10-14T10:00', '2026-10-14T16:00:01')).toMatch(/6 hours/);expect(validateWindow('2026-10-14T10:00', '2026-10-14T16:00')).toBeUndefined();
});
test('create form validates before sending and submits explicit service/time scope', async () => {
  const create = vi.spyOn(api, 'create').mockResolvedValue(incident), done = vi.fn();render(<CreateIncident created={done} cancel={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Incident title'), {target: {value: 'Checkout errors'}});fireEvent.change(screen.getByLabelText('Symptoms'), {target: {value: '5xx errors'}});fireEvent.change(screen.getByLabelText('Window start'), {target: {value: '2026-10-14T10:00:00'}});fireEvent.change(screen.getByLabelText('Window end'), {target: {value: '2026-10-14T09:00:00'}});
  fireEvent.click(screen.getByRole('button', {name: 'Create incident'}));expect(screen.getByRole('alert')).toHaveTextContent('End time must be after');expect(create).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Window end'), {target: {value: '2026-10-14T10:05:00'}});fireEvent.click(screen.getByRole('button', {name: 'Create incident'}));await screen.findByRole('button', {name: 'Create incident'});expect(create).toHaveBeenCalledWith(expect.objectContaining({related_services: ['gateway'], service: 'checkout-api', symptom: '5xx errors'}));
});

test('native input events submit the visible dates, not a stale controlled default', async () => {
  const create = vi.spyOn(api, 'create').mockResolvedValue(incident);render(<CreateIncident created={vi.fn()} cancel={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Incident title'), {target: {value: 'Native date check'}});fireEvent.change(screen.getByLabelText('Symptoms'), {target: {value: 'Request errors'}});
  fireEvent.input(screen.getByLabelText('Window start'), {target: {value: '2026-10-14T10:00'}});fireEvent.input(screen.getByLabelText('Window end'), {target: {value: '2026-10-14T10:05'}});
  fireEvent.click(screen.getByRole('button', {name: 'Create incident'}));
  expect(create).toHaveBeenCalledWith(expect.objectContaining({start_time: new Date('2026-10-14T10:00').toISOString(), end_time: new Date('2026-10-14T10:05').toISOString()}));
});

test('trace events expose tool identity, duration and an accessible expansion label', () => {
  render(<TraceEvents events={[{id: 'event', seq: 7, ts: '2026-10-14T10:00:00Z', kind: 'tool_completed', node: 'Retriever', payload_json: {tool: 'logs_query', latency_ms: 3.25, ground_truth: {expected_root_cause: 'ORACLE_ONLY'}}}]}/>);
  expect(screen.getByText('logs_query · 3.25 ms')).toBeVisible();
  const summary = screen.getByText('tool completed').closest('summary');expect(summary).toHaveAttribute('aria-label', 'Event 7: Retriever tool completed logs_query');
  fireEvent.click(summary!);expect(screen.queryByText(/ORACLE_ONLY/)).toBeNull();
});
