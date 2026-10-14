import {ApiError, observable} from './api';
import type {InvestigationEvent} from './types';
export interface Frame {id: number; event: string; data: string}
export function parseFrame(frame: string): Frame {
  let id = 0, event = 'message'; const data: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('id:')) id = Number(line.slice(3).trim());
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  return {id, event, data: data.join('\n')};
}
export interface StreamCallbacks {event: (event: InvestigationEvent) => void; state: (state: string) => void; error: (error: ApiError) => void; done: () => void}
/** Reconnect with the last delivered seq, suppress duplicate frames, and stop on done/abort. */
export async function streamInvestigation(id: string, callbacks: StreamCallbacks, signal: AbortSignal, after = 0): Promise<void> {
  let cursor = after, retry = 0;
  while (!signal.aborted) {
    const requestId = crypto.randomUUID();
    let rid: string = requestId;
    try {
      callbacks.state(retry ? 'Reconnecting' : 'Connecting');
      const response = await fetch(`/api/investigations/${encodeURIComponent(id)}/events?after=${cursor}`, {signal, headers: {'Accept': 'text/event-stream', 'Last-Event-ID': String(cursor), 'X-Request-ID': requestId}});
      rid = response.headers.get('X-Request-ID') ?? requestId;
      if (!response.ok) {
        const body = await response.json();
        throw new ApiError(body.error?.code ?? 'STREAM_ERROR', body.error?.message ?? 'Agent stream unavailable.', body.error?.request_id ?? rid, body.error?.retryable ?? false, response.status);
      }
      if (!response.body) throw new ApiError('STREAM_ERROR', 'Streaming is unavailable.', rid, true);
      callbacks.state('Live');
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      try {
        while (!signal.aborted) {
          const chunk = await reader.read(); if (chunk.done) break;
          buffer += decoder.decode(chunk.value, {stream: true}); buffer = buffer.replace(/\r\n/g, '\n');
          let boundary: number;
          while ((boundary = buffer.indexOf('\n\n')) >= 0) {
            const frame = parseFrame(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2);
            if (frame.event === 'done') { callbacks.state('Complete'); callbacks.done(); return; }
            if (!frame.data || !Number.isSafeInteger(frame.id) || frame.id <= cursor) continue;
            const value = observable(JSON.parse(frame.data)) as InvestigationEvent;
            if (value.seq !== frame.id || typeof value.kind !== 'string') throw new ApiError('INVALID_RESPONSE', 'Invalid agent event.', rid);
            callbacks.event(value); cursor = frame.id; retry = 0;
          }
        }
      } finally { await reader.cancel().catch(() => undefined); }
      throw new ApiError('STREAM_INTERRUPTED', 'Connection interrupted; resuming from the last event.', rid, true);
    } catch (error) {
      if (signal.aborted) return;
      const failure = error instanceof ApiError ? error : new ApiError('STREAM_ERROR', 'Agent stream interrupted.', rid, true);
      callbacks.error(failure);
      if (signal.aborted) return;
      if (!failure.retryable) { callbacks.state('Unavailable'); return; }
      callbacks.state('Reconnecting'); retry++;
      await new Promise<void>(resolve => { const finish = () => {clearTimeout(timer); signal.removeEventListener('abort', finish); resolve();}; const timer = setTimeout(finish, Math.min(5000, 500 * 2 ** Math.min(retry - 1, 4))); signal.addEventListener('abort', finish, {once: true}); });
    }
  }
}
