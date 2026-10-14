import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {App} from './App';
import {api} from './api';
import {EvaluationPage} from './EvaluationPage';
import {bundle, evaluation, incident, investigation, report} from './test-fixtures';
vi.mock('./stream', () => ({streamInvestigation: vi.fn().mockResolvedValue(undefined)}));
beforeEach(() => {vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);location.hash = '/incidents';});
afterEach(() => {cleanup();vi.restoreAllMocks();});
test('incidents list renders live records, status and the read-only banner', async () => {
  vi.spyOn(api, 'incidents').mockResolvedValue([incident]);render(<App/>);expect(screen.getByRole('note')).toHaveTextContent('Read-only investigation — no remediation is executed.');expect(await screen.findByRole('link', {name: 'Checkout failures'})).toHaveAttribute('href', `#/incidents/${incident.id}`);expect(screen.getByText('open')).toBeVisible();
});
test('empty and error list states are explicit and include request_id', async () => {
  const fetcher = vi.spyOn(api, 'incidents').mockResolvedValue([]);render(<App/>);expect(await screen.findByText('No incidents yet')).toBeVisible();cleanup();
  const {ApiError} = await import('./api');fetcher.mockRejectedValue(new ApiError('EVIDENCE_QUERY_TIMEOUT', 'Database unavailable', 'incident-request', true, 503));render(<App/>);expect(await screen.findByRole('alert')).toHaveTextContent('incident-request');
});
test('incident pages never render ground-truth fields, including extras attached to report artifacts', async () => {
  location.hash = '/incidents/' + incident.id;
  vi.spyOn(api, 'incident').mockResolvedValue({...incident, expected_root_cause: 'ORACLE_ONLY'} as typeof incident);
  vi.spyOn(api, 'evidence').mockResolvedValue(bundle);vi.spyOn(api, 'timeline').mockResolvedValue({items: [], truncated: false});vi.spyOn(api, 'latest').mockResolvedValue(investigation);vi.spyOn(api, 'report').mockResolvedValue({...report, ground_truth: {expected_root_cause: 'ORACLE_ONLY'}} as typeof report);const truth = vi.spyOn(api, 'truth');
  render(<App/>);await screen.findByRole('tab', {name: 'Report'});for (const name of ['Timeline', 'Evidence', 'Hypotheses', 'Report', 'Agent Trace']) {fireEvent.click(screen.getByRole('tab', {name}));await waitFor(() => expect(screen.queryByText(/ORACLE_ONLY/)).toBeNull());expect(screen.getByRole('note')).toHaveTextContent('Read-only investigation');}
  expect(truth).not.toHaveBeenCalled();expect(screen.queryByRole('heading', {name: 'Ground truth'})).toBeNull();
});
test('evaluation reveals oracle only after a terminal scored run and fetches it from the scorer-backed endpoint', async () => {
  vi.spyOn(api, 'scenarios').mockResolvedValue([{id: 'SCN-001', name: 'Service Kill', description: 'Checkout lab'}]);vi.spyOn(api, 'replay').mockResolvedValue(evaluation);vi.spyOn(api, 'evaluation').mockResolvedValue(evaluation);const truth = vi.spyOn(api, 'truth').mockResolvedValue({evaluation_id: evaluation.id, scenario_id: 'SCN-001', expected_root_cause: 'ORACLE_ONLY', required_evidence: ['die_137'], seed: 42, source: 'golden'});
  render(<EvaluationPage params={new URLSearchParams()}/>);await screen.findByRole('button', {name: /Run replay/});expect(truth).not.toHaveBeenCalled();expect(screen.queryByRole('heading', {name: 'Ground truth'})).toBeNull();fireEvent.click(screen.getByRole('button', {name: /Run replay/}));expect(await screen.findByText('ORACLE_ONLY')).toBeVisible();expect(screen.getByRole('heading', {name: 'Evaluation passed'})).toBeVisible();expect(truth).toHaveBeenCalledWith(evaluation.id, expect.any(AbortSignal));
});
test('queued evaluation with an injected truth field cannot reveal ground truth', async () => {
  vi.spyOn(api, 'scenarios').mockResolvedValue([{id: 'SCN-001', name: 'Service Kill', description: 'Checkout lab'}]);vi.spyOn(api, 'evaluation').mockResolvedValue({...evaluation, status: 'queued', scorecard: null, expected_root_cause: 'ORACLE_ONLY'} as typeof evaluation);const truth = vi.spyOn(api, 'truth');render(<EvaluationPage params={new URLSearchParams('evaluation=' + evaluation.id)}/>);
  expect(await screen.findByText('Evaluation in progress')).toBeVisible();expect(screen.queryByText(/ORACLE_ONLY/)).toBeNull();expect(truth).not.toHaveBeenCalled();
});
