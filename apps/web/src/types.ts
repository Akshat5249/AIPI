/** Handwritten public contracts matching the Pydantic API. Oracle data is separate. */
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed';
export const SERVICES = ['gateway', 'checkout-api', 'orders-api', 'pg-lag-probe', 'event-watcher', 'traffic', 'postgres-primary', 'postgres-replica', 'api'] as const;
export interface IncidentInput { title: string; service: string; related_services: string[]; start_time: string; end_time: string; symptom: string }
export interface Incident extends IncidentInput { id: string; status: 'open'; created_at: string }
export type EvidenceType = 'log' | 'metric' | 'trace' | 'event' | 'runbook';
export interface Evidence { evidence_id: string; type: EvidenceType; service: string; timestamp: string; source_ref: string; summary: string; payload: Record<string, unknown>; redactions: {field: string; rule: string}[] }
export interface Bundle { items: Evidence[]; truncated: boolean; dropped_counts: Record<string, number>; raw_counts: Record<string, number>; available_counts: Record<string, number>; retrieval_version: string }
export interface TimelineItem { ts: string; label: string; evidence_ids: string[] }
export interface Timeline { items: TimelineItem[]; truncated: boolean }
export interface Hypothesis { id: string; statement: string; category: string; rank: number; confidence: number; for: string[]; against: string[]; missing: string[]; falsification_condition: string; expected_evidence: string[] }
export interface Claim { claim_id: string; kind: 'fact' | 'hypothesis' | 'recommendation'; text: string; evidence_ids: string[] }
export interface Recommendation { id: string; statement: string; evidence_ids: string[]; requires_approval: true; executed: false; approval_status: 'pending' }
export interface Report { root_cause: { statement: string; hypothesis_id: string; confidence: number }; claims: Claim[]; ranked_hypotheses: Hypothesis[]; timeline: TimelineItem[]; recommendations: Recommendation[]; unresolved_questions: string[]; markdown: string }
export interface Investigation { id: string; incident_id: string; status: JobStatus; created_at: string; started_at: string | null; completed_at: string | null; provider: string; model: string; prompt_version: string; tool_version: string; code_commit: string; input_tokens: number; output_tokens: number; estimated_cost: number; latency_ms: number | null; error: string | null }
export interface InvestigationEvent { id: string; seq: number; ts: string; kind: string; node: string; payload_json: Record<string, unknown> }
export interface Scenario { id: string; name: string; description: string }
export interface Scores { top1: number; top3_recall: number; evidence_precision: number; evidence_coverage: number; unsupported_claim_rate: number; contradiction_handling: number; latency_ms: number; useful_evidence_per_tool_call: number; useful_evidence_per_token: number | null; critical_unsupported_claims: number; tool_calls: number; tokens: number }
export interface Experiment { provider: string; model: string; prompt_version: string; tool_version: string; code_commit: string; seed: number; fixture_digest: string | null; retrieval_params: Record<string, unknown> }
export interface Scorecard { scenario_id: string; passed: boolean; scores: Scores; experiment: Experiment; failures: string[]; mode: string; created_at: string }
export interface EvaluationJob { id: string; scenario_id: string; status: JobStatus; scorecard: Scorecard | null; error: string | null; created_at: string }
export interface ReplayInput { scenario_id: string; mode: 'golden' | 'recorded'; incident_id?: string; chaos_run_id?: string }
/** Returned only by the terminal evaluation disclosure endpoint; never an agent input. */
export interface EvaluationTruth { evaluation_id: string; scenario_id: string; expected_root_cause: string; required_evidence: string[]; seed: number; source: 'golden' | 'recorded' }
