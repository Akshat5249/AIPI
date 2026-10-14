import {useCallback, useEffect, useState, type FormEvent} from 'react';
import {api, asError, type ApiError} from './api';
import {date, Empty, ErrorState, Loading, Status} from './components';
import {SERVICES, type Incident} from './types';
function localInput(date: Date) {return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);}
export function validateWindow(start: string, end: string): string | undefined {
  const a = new Date(start).getTime(), b = new Date(end).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 'Enter valid start and end times.';
  if (b <= a) return 'End time must be after start time.';
  if (b - a > 6 * 3600000) return 'The incident window must not exceed 6 hours.';
}
export function CreateIncident({created, cancel}: {created: (id: string) => void; cancel: () => void}) {
  const [title, setTitle] = useState(''), [service, setService] = useState('checkout-api'), [related, setRelated] = useState<string[]>(['gateway']);
  const [start] = useState(localInput(new Date(Date.now() - 900000))), [end] = useState(localInput(new Date()));
  const [symptom, setSymptom] = useState(''), [validation, setValidation] = useState<string>(), [error, setError] = useState<ApiError>(), [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const values = new FormData(e.currentTarget), submittedStart = String(values.get("start_time") ?? ""), submittedEnd = String(values.get("end_time") ?? ""); const invalid = validateWindow(submittedStart, submittedEnd) ?? (!title.trim() || !symptom.trim() ? 'Enter an incident title and symptoms.' : undefined); setValidation(invalid); if (invalid) return;
    setBusy(true); setError(undefined);
    try {const item = await api.create({title: title.trim(), service, related_services: related.filter(s => s !== service), start_time: new Date(submittedStart).toISOString(), end_time: new Date(submittedEnd).toISOString(), symptom: symptom.trim()}); created(item.id);}
    catch (e) {setError(asError(e));} finally {setBusy(false);}
  }
  return <section className="create-panel" aria-label="New incident"><div className="section-heading"><div><span className="eyebrow">Define the investigation scope</span><h2>New incident</h2></div><button className="icon-button" onClick={cancel} aria-label="Close create form">×</button></div><form onSubmit={submit}>
    <label>Incident title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Checkout errors after service restart"/></label>
    <div className="form-grid"><label>Primary service<select value={service} onChange={e => {setService(e.target.value); setRelated(r => r.filter(s => s !== e.target.value));}}>{SERVICES.map(s => <option key={s}>{s}</option>)}</select></label><div><span className="field-label">Related services</span><div className="service-checkboxes">{SERVICES.filter(s => s !== service).map(s => <label key={s}><input type="checkbox" checked={related.includes(s)} onChange={e => setRelated(r => e.target.checked ? [...r, s] : r.filter(x => x !== s))}/>{s}</label>)}</div></div></div>
    <div className="form-grid"><label>Window start<input required type="datetime-local" name="start_time" step="1" defaultValue={start}/></label><label>Window end<input required type="datetime-local" name="end_time" step="1" defaultValue={end}/></label></div><p className="form-help">Times in {Intl.DateTimeFormat().resolvedOptions().timeZone}. Maximum window: 6 hours. Evidence stays within these services and times.</p>
    <label>Symptoms<textarea required maxLength={2000} rows={3} value={symptom} onChange={e => setSymptom(e.target.value)} placeholder="Describe the observable impact: errors, latency, stale reads…"/></label>
    {validation && <p role="alert" className="validation">{validation}</p>}{error && <ErrorState error={error}/>}<div className="form-actions"><button type="button" className="secondary" onClick={cancel}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Creating…' : 'Create incident'}</button></div>
  </form></section>;
}
export function IncidentsPage() {
  const [items, setItems] = useState<Incident[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<ApiError>(), [creating, setCreating] = useState(false), [service, setService] = useState('all'), [search, setSearch] = useState('');
  const load = useCallback(() => {const c = new AbortController();setLoading(true);setError(undefined);api.incidents(c.signal).then(setItems).catch(e => {if (!c.signal.aborted) setError(asError(e));}).finally(() => {if (!c.signal.aborted) setLoading(false);});return () => c.abort();}, []);
  useEffect(load, [load]);
  const shown = items.filter(i => (service === 'all' || i.service === service) && `${i.title} ${i.id} ${i.symptom}`.toLowerCase().includes(search.toLowerCase()));
  return <><header className="page-heading"><div><span className="eyebrow">Workspace / investigation</span><h1>Incidents<span className="heading-dot">.</span></h1><p>Trace symptoms to their source. Keep every conclusion accountable.</p></div><button className="primary" onClick={() => setCreating(true)}>+ New incident</button></header>
    <div className="stats"><div><span>Tracked incidents</span><strong>{loading ? '—' : items.length}</strong><small>Latest 100 records</small></div><div><span>Services in scope</span><strong>{loading ? '—' : new Set(items.flatMap(i => [i.service, ...i.related_services])).size}</strong><small>Across tracked incidents</small></div><div><span>Open incidents</span><strong>{loading ? '—' : items.filter(i => i.status === 'open').length}</strong><small>Read-only investigations</small></div></div>
    {creating && <CreateIncident created={id => {location.hash = '/incidents/' + id;}} cancel={() => setCreating(false)}/>}
    <section className="panel"><div className="panel-toolbar"><h2>Investigation queue <span className="count">{shown.length}</span></h2><div className="filters"><input aria-label="Search incidents" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search incidents…"/><select aria-label="Filter incidents by service" value={service} onChange={e => setService(e.target.value)}><option value="all">All services</option>{[...new Set(items.map(i => i.service))].sort().map(s => <option key={s}>{s}</option>)}</select><button className="icon-button" aria-label="Refresh incidents" onClick={load}>↻</button></div></div>
      {error ? <ErrorState error={error} retry={load}/> : loading ? <Loading label="Loading incidents…"/> : shown.length ? <div className="table-scroll"><table><thead><tr><th>Incident</th><th>Service</th><th>Window</th><th>Status</th><th aria-label="Open"/></tr></thead><tbody>{shown.map(i => <tr key={i.id}><td><a className="incident-link" href={`#/incidents/${i.id}`}>{i.title}</a><small className="mono muted">{i.id.slice(0, 8)}</small></td><td><span className="service-tag">{i.service}</span></td><td><time>{date(i.start_time)}</time><small className="muted">{Math.round((Date.parse(i.end_time) - Date.parse(i.start_time)) / 60000)} min window</small></td><td><Status status={i.status}/></td><td><a aria-label={`Open ${i.title}`} className="arrow-link" href={`#/incidents/${i.id}`}>↗</a></td></tr>)}</tbody></table></div> : <Empty title={items.length ? 'No matching incidents' : 'No incidents yet'}>Create an incident with a service and time window to get started.</Empty>}
    </section></>;
}
