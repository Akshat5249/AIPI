import {useEffect, useRef, useState} from 'react';
import {api, asError, observable, type ApiError} from './api';
import type {Bundle, Evidence, Hypothesis, InvestigationEvent, Report} from './types';
export const date = (value: string) => new Date(value).toLocaleString(undefined, {month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'});
export const percent = (value: number) => `${Math.round(value * 100)}%`;
export function Status({status}: {status: string}) { return <span className={`status status-${status}`}><i/>{status}</span>; }
export function ErrorState({error, retry}: {error: ApiError; retry?: () => void}) { return <div role="alert" className="error-state"><strong>{error.code}</strong><p>{error.message}</p><small>Request ID: <code>{error.request_id}</code></small>{retry && <button className="secondary" onClick={retry}>Retry</button>}</div>; }
export function Empty({title, children}: {title: string; children?: React.ReactNode}) { return <div className="empty"><span aria-hidden="true">◎</span><h3>{title}</h3><p>{children}</p></div>; }
export function Loading({label = 'Loading…'}: {label?: string}) { return <div role="status" className="loading"><span className="spinner"/>{label}</div>; }
export type OpenEvidence = (id: string) => void;
export function EvidenceChips({ids, bundleIds, open}: {ids: string[]; bundleIds: Set<string>; open: OpenEvidence}) {
  const [expanded, setExpanded] = useState(false);
  return <div className="chips">{(expanded ? ids : ids.slice(0, 5)).map(id => <button className="evidence-chip" key={id} title={id} aria-label={`Open evidence ${id}${bundleIds.has(id) ? '' : ' outside bundle'}`} onClick={() => open(id)}><code>{id.slice(0, 11)}…</code>{!bundleIds.has(id) && <span className="outside">outside bundle</span>}<span aria-hidden="true">↗</span></button>)}{ids.length > 5 && <button className="text-button" onClick={() => setExpanded(!expanded)}>{expanded ? 'Show fewer' : `+${ids.length - 5} more`}</button>}{ids.length === 0 && <span className="muted">No observations cited</span>}</div>;
}
export function HypothesisList({items, bundleIds, open}: {items: Hypothesis[]; bundleIds: Set<string>; open: OpenEvidence}) {
  if (!items.length) return <Empty title="No hypotheses yet">Start an investigation to compare possible causes.</Empty>;
  return <div className="hypothesis-list">{items.map(h => <article className={`hypothesis ${h.rank === 1 ? 'leading' : ''}`} key={h.id}>
    <header><span className="rank">{String(h.rank).padStart(2, '0')}</span><div><span className="eyebrow">{h.rank === 1 ? 'Leading hypothesis' : 'Alternative hypothesis'}</span><h3>{h.statement}</h3></div><div className="confidence"><strong>{percent(h.confidence)}</strong><small>confidence</small><meter min="0" max="1" value={h.confidence} aria-label={`Confidence for ${h.statement}`}/></div></header>
    <div className="stance"><span className="stance-label for">FOR <b>{h.for.length}</b></span><EvidenceChips ids={h.for} bundleIds={bundleIds} open={open}/></div>
    <div className="stance"><span className="stance-label against">AGAINST <b>{h.against.length}</b></span><EvidenceChips ids={h.against} bundleIds={bundleIds} open={open}/></div>
    <details><summary>Falsification & evidence gaps</summary><p>{h.falsification_condition}</p><p><strong>Expected observations:</strong> {h.expected_evidence.join('; ')}</p><p><strong>Missing:</strong> {h.missing.join('; ') || 'No missing observations recorded.'}</p></details>
  </article>)}</div>;
}
export function EvidenceViewer({incidentId, evidenceId, bundle, close}: {incidentId: string; evidenceId: string; bundle: Bundle; close: () => void}) {
  const cached = bundle.items.find(e => e.evidence_id === evidenceId);
  const [item, setItem] = useState<Evidence | undefined>(cached), [error, setError] = useState<ApiError>(), [retry, setRetry] = useState(0);
  const closeButton = useRef<HTMLButtonElement>(null), dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null, overflow = document.body.style.overflow;
    closeButton.current?.focus(); document.body.style.overflow = 'hidden';
    const keys = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      if (e.key === 'Tab') {
        const elements = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, select, textarea, summary, [tabindex="0"]');
        if (!elements?.length) return;
        const first = elements[0], last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {e.preventDefault();last.focus();}
        if (!e.shiftKey && document.activeElement === last) {e.preventDefault();first.focus();}
      }
    };
    document.addEventListener('keydown', keys); return () => {document.removeEventListener('keydown', keys);document.body.style.overflow = overflow;if (prior?.isConnected) prior.focus();};
  }, [close]);
  useEffect(() => {
    setError(undefined); setItem(cached); if (cached) return;
    const controller = new AbortController(); api.evidenceItem(incidentId, evidenceId, controller.signal).then(setItem).catch(e => {if (!controller.signal.aborted) setError(asError(e));}); return () => controller.abort();
  }, [incidentId, evidenceId, cached, retry]);
  return <div className="viewer-backdrop" onClick={close}><aside ref={dialog} className="evidence-viewer" role="dialog" aria-modal="true" aria-labelledby="viewer-title" onClick={e => e.stopPropagation()}><header><div><span className="eyebrow">Scoped evidence</span><h2 id="viewer-title">Evidence detail</h2></div><button ref={closeButton} className="icon-button" aria-label="Close evidence" onClick={close}>×</button></header>
    <code className="full-id">{evidenceId}</code>{!cached && <span className="outside">outside bundle</span>}
    {error ? <ErrorState error={error} retry={() => setRetry(n => n + 1)}/> : !item ? <Loading label="Resolving citation…"/> : <><div className="evidence-meta"><span className={`type type-${item.type}`}>{item.type}</span><strong>{item.service}</strong><time>{date(item.timestamp)}</time></div><h3>{item.summary}</h3><p className="source-ref">Source: {item.source_ref}</p><h4>Payload</h4><pre>{JSON.stringify(observable(item.payload), null, 2)}</pre><h4>Redactions</h4>{item.redactions.length ? <ul>{item.redactions.map((r, i) => <li key={i}><code>{r.field}</code> — {r.rule}</li>)}</ul> : <p className="muted">No redactions recorded.</p>}</>}
  </aside></div>;
}
export function downloadReport(report: Report, id: string) {
  const url = URL.createObjectURL(new Blob([report.markdown], {type: 'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `incident-${id}.md`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function ReportSections({report, bundleIds, open, incidentId}: {report: Report; bundleIds: Set<string>; open: OpenEvidence; incidentId: string}) {
  return <div className="report"><div className="section-heading"><div><span className="eyebrow">Investigation report</span><h2>Evidence, reasoning & next checks</h2></div><button className="secondary" onClick={() => downloadReport(report, incidentId)}>↓ Export Markdown</button></div>
    <div className="root-cause"><span className="eyebrow">Most likely cause · {percent(report.root_cause.confidence)} confidence</span><h3>{report.root_cause.statement}</h3></div>
    <section aria-labelledby="facts-heading"><h3 id="facts-heading"><span className="section-number" aria-hidden="true">01</span> Facts</h3><p className="muted">Observed telemetry, supported by deterministic checks.</p>{report.claims.filter(c => c.kind === 'fact').map(c => <article className="claim" key={c.claim_id}><p>{c.text}</p><EvidenceChips ids={c.evidence_ids} bundleIds={bundleIds} open={open}/></article>)}</section>
    <section aria-labelledby="hypotheses-heading"><h3 id="hypotheses-heading"><span className="section-number" aria-hidden="true">02</span> Hypotheses</h3><p className="muted">Inferences, with both supporting and contradicting observations.</p><HypothesisList items={report.ranked_hypotheses} bundleIds={bundleIds} open={open}/></section>
    <section aria-labelledby="recommendations-heading"><h3 id="recommendations-heading"><span className="section-number" aria-hidden="true">03</span> Recommendations</h3>{report.recommendations.length ? report.recommendations.map(r => <article className="recommendation" key={r.id}><span className="approval">Requires human approval</span><p>{r.statement}</p><EvidenceChips ids={r.evidence_ids} bundleIds={bundleIds} open={open}/><small>Not executed · {r.approval_status}</small></article>) : <Empty title="No recommendations recorded"/>}</section>
    {report.unresolved_questions.length > 0 && <section><h3>Open questions</h3><ul>{report.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></section>}
  </div>;
}

export function TraceEvents({events}: {events: InvestigationEvent[]}) {
  return <div className="trace-events">{events.map(e => {
    const tool = typeof e.payload_json.tool === 'string' ? e.payload_json.tool : '';
    const latency = typeof e.payload_json.latency_ms === 'number' ? e.payload_json.latency_ms : undefined;
    const kind = e.kind.replaceAll('_', ' ');
    return <details key={e.seq} className={`trace-event ${e.kind.includes('failed') ? 'trace-failed' : ''}`}><summary aria-label={`Event ${e.seq}: ${e.node} ${kind}${tool ? ' ' + tool : ''}`}><span className="mono muted">{String(e.seq).padStart(3, '0')}</span><span className="event-node">{e.node}</span><span>{kind}{tool && <small className="tool-name">{tool}{latency !== undefined ? ` · ${latency.toFixed(2)} ms` : ''}</small>}</span><time>{date(e.ts)}</time></summary><pre>{JSON.stringify(observable(e.payload_json), null, 2)}</pre></details>;
  })}</div>;
}
