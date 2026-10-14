import {afterEach, expect, test, vi} from 'vitest';
import {parseFrame, streamInvestigation} from './stream';
import type {InvestigationEvent} from './types';
afterEach(() => {vi.unstubAllGlobals();vi.useRealTimers();});
const event = (seq: number): InvestigationEvent => ({id: String(seq), seq, ts: '2026-10-14T10:00:00Z', kind: 'node_completed', node: 'Triage', payload_json: {}});
const frame = (seq: number) => `id: ${seq}\nevent: node_completed\ndata: ${JSON.stringify(event(seq))}\n\n`;
function response(chunks: string[]) {return new Response(new ReadableStream({start(controller) {for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));controller.close();}}), {headers: {'Content-Type': 'text/event-stream', 'X-Request-ID': 'stream-request'}});}
test('SSE parser accepts multi-line data and ignores heartbeat comments', () => {
  expect(parseFrame(': heartbeat')).toEqual({id: 0, event: 'message', data: ''});expect(parseFrame('id: 7\nevent: done\ndata: one\ndata: two')).toEqual({id: 7, event: 'done', data: 'one\ntwo'});
});
test('interrupted stream reconnects with the last event ID, deduplicates and stops on done', async () => {
  vi.useFakeTimers();const first = frame(1), second = frame(2);const fetcher = vi.fn().mockResolvedValueOnce(response([first.slice(0, 17), first.slice(17)])).mockResolvedValueOnce(response([frame(1) + second + 'event: done\ndata: {"status":"completed"}\n\n']));vi.stubGlobal('fetch', fetcher);
  const callbacks = {event: vi.fn(), state: vi.fn(), error: vi.fn(), done: vi.fn()};const work = streamInvestigation('job', callbacks, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(600);await work;expect(callbacks.event.mock.calls.map(([e]) => e.seq)).toEqual([1, 2]);expect(fetcher.mock.calls[1][0]).toContain('?after=1');expect(fetcher.mock.calls[1][1].headers['Last-Event-ID']).toBe('1');expect(callbacks.done).toHaveBeenCalledOnce();expect(fetcher).toHaveBeenCalledTimes(2);
});
test('non-retryable SSE errors keep the server request ID and stop reconnecting', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({error: {code: 'NOT_FOUND', request_id: 'missing-stream', retryable: false, message: 'Not found'}}, {status: 404}));vi.stubGlobal('fetch', fetcher);const callbacks = {event: vi.fn(), state: vi.fn(), error: vi.fn(), done: vi.fn()};await streamInvestigation('job', callbacks, new AbortController().signal);expect(callbacks.error.mock.calls[0][0].request_id).toBe('missing-stream');expect(callbacks.state).toHaveBeenLastCalledWith('Unavailable');expect(fetcher).toHaveBeenCalledOnce();
});
test('unmount aborts stream work without reconnecting', async () => {
  const c = new AbortController();const fetcher = vi.fn().mockImplementation(() => {c.abort();return Promise.reject(new DOMException('Aborted', 'AbortError'));});vi.stubGlobal('fetch', fetcher);await streamInvestigation('job', {event: vi.fn(), state: vi.fn(), error: vi.fn(), done: vi.fn()}, c.signal);expect(fetcher).toHaveBeenCalledOnce();
});
