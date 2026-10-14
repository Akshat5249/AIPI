import {useCallback, useEffect, useMemo, useState} from 'react';
import {api, asError, type ApiError} from './api';
import {date, Empty, ErrorState, EvidenceChips, EvidenceViewer, HypothesisList, Loading, ReportSections, Status, TraceEvents} from './components';
import {streamInvestigation} from './stream';
import type {Bundle, Incident, Investigation, InvestigationEvent, Report, Timeline} from './types';
const TABS = ['Timeline', 'Evidence', 'Hypotheses', 'Report', 'Agent Trace'] as const;
export function IncidentDetail({id}: {id: string}) {
  const [incident, setIncident] = useState<Incident>(), [bundle, setBundle] = useState<Bundle>(), [timeline, setTimeline] = useState<Timeline>(), [job, setJob] = useState<Investigation>(), [report, setReport] = useState<Report>();
  const [error, setError] = useState<ApiError>(), [reportError, setReportError] = useState<ApiError>(), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [tab, setTab] = useState<typeof TABS[number]>('Timeline');
  const [type, setType] = useState('all'), [service, setService] = useState('all'), [selected, setSelected] = useState<string>();
  const [events, setEvents] = useState<InvestigationEvent[]>([]), [streamState, setStreamState] = useState('Not started'), [streamError, setStreamError] = useState<ApiError>();
  const closeEvidence = useCallback(() => setSelected(undefined), []);
  const load = useCallback(() => {
    const c = new AbortController(); setLoading(true); setError(undefined);
    Promise.all([api.incident(id, c.signal), api.evidence(id, c.signal), api.timeline(id, c.signal), api.latest(id, c.signal).catch(e => {if (e instanceof Error && 'status' in e && e.status === 404) return undefined; throw e;})]).then(([i, b, t, j]) => {setIncident(i);setBundle(b);setTimeline(t);setJob(j);}).catch(e => {if (!c.signal.aborted) setError(asError(e));}).finally(() => {if (!c.signal.aborted) setLoading(false);});
    return () => c.abort();
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!job || job.status === 'completed' || job.status === 'failed') return;
    const c = new AbortController(); const timer = setInterval(() => {api.investigation(job.id, c.signal).then(setJob).catch(e => {if (!c.signal.aborted) setError(asError(e));});}, 1000);
    return () => {clearInterval(timer);c.abort();};
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (!job || job.status !== 'completed') return;
    const c = new AbortController(); setReportError(undefined); api.report(id, c.signal).then(setReport).catch(e => {if (!c.signal.aborted) setReportError(asError(e));}); return () => c.abort();
  }, [id, job?.id, job?.status]);
  useEffect(() => {
    if (!job?.id) return;
    setEvents([]); setStreamError(undefined); const c = new AbortController();
    void streamInvestigation(job.id, {event: e => {setStreamError(undefined);setEvents(old => old.some(item => item.seq === e.seq) ? old : [...old, e]);}, state: setStreamState, error: setStreamError, done: () => {setStreamError(undefined);api.investigation(job.id).then(setJob).catch(e => setError(asError(e)));}}, c.signal);
    return () => c.abort();
  }, [job?.id]);
  const bundleIds = useMemo(() => new Set(bundle?.items.map(e => e.evidence_id)), [bundle]);
  async function investigate() {
    setBusy(true);setError(undefined);setReport(undefined);setReportError(undefined);
    try {setJob(await api.investigate(id));setTab('Agent Trace');} catch (e) {setError(asError(e));} finally {setBusy(false);}
  }
  if (loading) return <Loading label="Loading incident and scoped evidence…"/>;
  if (!incident || !bundle || !timeline) return error ? <ErrorState error={error} retry={load}/> : <Empty title="Incident unavailable"/>;
  const filtered = bundle.items.filter(e => (type === 'all' || e.type === type) && (service === 'all' || e.service === service));
  const investigating = busy || job?.status === 'queued' || job?.status === 'running';
  return <><a className="back-link" href="#/incidents">← All incidents</a><header className="page-heading incident-heading"><div><span className="eyebrow">Incident / {id.slice(0, 8)}</span><h1>{incident.title}</h1><div className="heading-meta"><span className="service-tag">{incident.service}</span><Status status={job?.status ?? incident.status}/><span>{date(incident.start_time)} — {date(incident.end_time)}</span></div></div><button className="primary" disabled={investigating} onClick={investigate}>{investigating ? 'Investigating…' : job ? 'Investigate again' : 'Start investigation'}</button></header>
    <div className="scope-strip"><div><span className="eyebrow">Reported symptoms</span><p>{incident.symptom}</p></div><div><span className="eyebrow">Service scope</span><p>{[incident.service, ...incident.related_services].join(' · ')}</p></div><div><span className="eyebrow">Evidence snapshot</span><p>{bundle.items.length} items {bundle.truncated && <span className="outside">capped bundle</span>}</p></div></div>
    {error && <ErrorState error={error} retry={load}/>}{job?.status === 'failed' && <div className="error-state" role="alert"><strong>Investigation failed</strong><p>{job.error ?? 'The investigation could not complete.'}</p><p>Start another investigation to retry.</p></div>}
    <div className="detail-tabs" role="tablist" aria-label="Incident detail">{TABS.map(t => <button key={t} role="tab" aria-selected={tab === t} aria-controls="detail-panel" id={`tab-${t.replace(' ', '-')}`} onClick={() => setTab(t)}>{t}{t === 'Agent Trace' && (job?.status === 'running' || job?.status === 'queued') && <i className="live-dot"/>}</button>)}</div>
    <section id="detail-panel" role="tabpanel" aria-labelledby={`tab-${tab.replace(' ', '-')}`} className="detail-panel">
      {tab === 'Timeline' && <><div className="section-heading"><div><h2>What happened, in order</h2><p className="muted">Chronological observations from the frozen incident window.</p></div><span className="count">{timeline.items.length} observations</span></div>{timeline.items.length ? <ol className="timeline">{timeline.items.map((t, i) => <li key={i}><time>{date(t.ts)}</time><div><p>{t.label}</p><EvidenceChips ids={t.evidence_ids} bundleIds={bundleIds} open={setSelected}/></div></li>)}</ol> : <Empty title="No observations in this window">Check the declared services and incident window.</Empty>}</>}
      {tab === 'Evidence' && <><div className="section-heading"><div><h2>Observable evidence</h2><p className="muted">{bundle.retrieval_version} · immutable snapshot</p></div><div className="filters"><select aria-label="Filter evidence by type" value={type} onChange={e => setType(e.target.value)}><option value="all">All types</option>{['event', 'metric', 'log', 'trace', 'runbook'].map(t => <option key={t}>{t}</option>)}</select><select aria-label="Filter evidence by service" value={service} onChange={e => setService(e.target.value)}><option value="all">All services</option>{[...new Set(bundle.items.map(e => e.service))].sort().map(s => <option key={s}>{s}</option>)}</select></div></div><div className="retrieval-note"><span>{bundle.items.length} returned</span><span>{Object.entries(bundle.dropped_counts).map(([type, count]) => `${type}: ${count}`).join(' · ')} dropped</span><span>Rules use full scoped data.</span></div>{filtered.length ? <div className="evidence-list">{filtered.map(e => <button key={e.evidence_id} className="evidence-row" onClick={() => setSelected(e.evidence_id)}><span className={`type type-${e.type}`}>{e.type}</span><span><strong>{e.summary}</strong><small>{e.service} <span className="mono">{e.evidence_id}</span></small></span><time>{date(e.timestamp)}</time><span aria-hidden="true">↗</span></button>)}</div> : <Empty title="No evidence matches these filters">Try another type or service.</Empty>}</>}
      {(tab === 'Hypotheses' || tab === 'Report') && (reportError ? <ErrorState error={reportError} retry={() => {setJob(undefined);load();}}/> : report ? tab === 'Hypotheses' ? <><div className="section-heading"><div><h2>Competing explanations</h2><p className="muted">Confidence comes from evidence and deterministic checks.</p></div><span className="count">{report.ranked_hypotheses.length} hypotheses</span></div><HypothesisList items={report.ranked_hypotheses} bundleIds={bundleIds} open={setSelected}/></> : <ReportSections report={report} bundleIds={bundleIds} open={setSelected} incidentId={id}/> : investigating || job?.status === 'completed' ? <Loading label="Preparing investigation artifacts…"/> : <Empty title="An investigation is needed">Start an investigation to generate hypotheses and an evidence-linked report.</Empty>)}
      {tab === 'Agent Trace' && <><div className="section-heading"><div><h2>Investigation execution</h2><p className="muted">Ordered node and read-only tool events. Reconnect resumes from the last event ID.</p></div><span className="status"><i/>{streamState}</span></div>{job && <><div className="trace-stats"><div><span>Latency</span><strong>{job.latency_ms == null ? 'Pending' : `${(job.latency_ms / 1000).toFixed(2)} s`}</strong></div><div><span>Tokens in / out</span><strong>{job.input_tokens} / {job.output_tokens}</strong></div><div><span>Estimated cost</span><strong>${job.estimated_cost.toFixed(4)}</strong></div><div><span>Provider / model</span><strong>{job.provider}</strong><small>{job.model}</small></div></div><p className="version-line">Prompt {job.prompt_version} · Tools {job.tool_version} · Commit <code>{job.code_commit}</code></p></>}{streamError && <ErrorState error={streamError}/>}{events.length ? <TraceEvents events={events}/> : <Empty title={job ? 'Waiting for events' : 'No investigation started'}>Node and tool activity will appear here.</Empty>}</>}
    </section>{job?.status === 'completed' && <div className="evaluation-link"><div><strong>Put this investigation to the test.</strong><p>Replay a golden scenario or score this completed live incident.</p></div><a className="secondary" href={`#/evaluations?incident=${id}`}>Open evaluation ↗</a></div>}
    {selected && <EvidenceViewer key={selected} incidentId={id} evidenceId={selected} bundle={bundle} close={closeEvidence}/>}
  </>;
}
