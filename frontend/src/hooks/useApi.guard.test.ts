import React from 'react';
import { Text } from 'ink';
import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../types';
import { isSendBlocked, resolveFinalContent, settleActiveMessages, useApi } from './useApi';

// Bug A: sendMessage must refuse a new turn while a response is streaming.
describe('isSendBlocked (Bug A: duplicate-send guard)', () => {
  it('blocks a send when already streaming', () => {
    expect(isSendBlocked(true)).toBe(true);
  });

  it('allows a send when idle', () => {
    expect(isSendBlocked(false)).toBe(false);
  });
});

describe('resolveFinalContent', () => {
  it('prefers authoritative final text over previously streamed tokens', () => {
    expect(resolveFinalContent('draft token output', 'COMPOSE_TRIGGER final answer'))
      .toBe('COMPOSE_TRIGGER final answer');
  });

  it('falls back to accumulated tokens when final text is absent', () => {
    expect(resolveFinalContent('complete token output')).toBe('complete token output');
  });
});

describe('settleActiveMessages', () => {
  it('terminates active assistant, thinking, and tool messages after a failed stream', () => {
    const settled = settleActiveMessages([
      { id: 'a', role: 'assistant', content: 'partial', timestamp: 1, done: false },
      { id: 't', role: 'thinking', content: 'reasoning', timestamp: 2, done: false, live: true },
      { id: 'x', role: 'tool', content: 'partial output', timestamp: 3, toolStatus: 'running' },
      { id: 'u', role: 'user', content: 'question', timestamp: 4 },
    ], 'error');

    expect(settled[0]).toMatchObject({ done: true });
    expect(settled[1]).toMatchObject({ done: true, live: false });
    expect(settled[2]).toMatchObject({ toolStatus: 'error' });
    expect(settled[3]).toMatchObject({ role: 'user' });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function HookHarness({ onState }: { onState: (messages: ChatMessage[], isStreaming: boolean) => void }) {
  const api = useApi();
  React.useEffect(() => {
    onState(api.messages, api.isStreaming);
  }, [api.messages, api.isStreaming, onState]);
  React.useEffect(() => {
    void api.sendMessage('question');
  }, []);
  return React.createElement(Text, null, 'hook');
}

describe('useApi SSE message ordering', () => {
  it('keeps final answer dynamic until done so late process events stay above it', async () => {
    vi.useFakeTimers();
    const encoder = new TextEncoder();
    const firstChunk = [
      'data: {"type":"reasoning","text":"reasoning"}\n\n',
      'data: {"type":"token","text":"draft answer"}\n\n',
      'data: {"type":"final","text":"final answer"}\n\n',
    ].join('');
    const lateProcessChunk = [
      'data: {"type":"tool_call","name":"websearch","args":{"query":"school"},"message_id":"tool-1"}\n\n',
      'data: {"type":"tool_result","result":"found","status":"success","duration":0.01,"message_id":"tool-1"}\n\n',
    ].join('');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(firstChunk));
        setTimeout(() => controller.enqueue(encoder.encode(lateProcessChunk)), 200);
        setTimeout(() => {
          controller.enqueue(encoder.encode('data: {"type":"done","status":"succeeded"}\n\n'));
          controller.close();
        }, 400);
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    })));

    let latestMessages: ChatMessage[] = [];
    let latestStreaming = false;
    render(React.createElement(HookHarness, {
      onState: (messages, isStreaming) => {
        latestMessages = messages;
        latestStreaming = isStreaming;
      },
    }));

    await vi.advanceTimersByTimeAsync(100);
    const answerBeforeDone = latestMessages.find(message => message.role === 'assistant');
    expect(answerBeforeDone).toMatchObject({ content: 'final answer', done: false });
    expect(latestStreaming).toBe(true);

    await vi.advanceTimersByTimeAsync(200);
    expect(latestMessages.map(message => message.role)).toEqual([
      'user',
      'thinking',
      'tool',
      'assistant',
    ]);
    expect(latestMessages.at(-1)).toMatchObject({ content: 'final answer', done: false });

    await vi.advanceTimersByTimeAsync(200);
    await vi.waitFor(() => expect(latestStreaming).toBe(false));

    expect(latestMessages.filter(message => message.role === 'system')).toEqual([]);
    expect(latestMessages.map(message => message.role)).toEqual([
      'user',
      'thinking',
      'tool',
      'assistant',
    ]);
    expect(latestMessages.at(-1)).toMatchObject({
      role: 'assistant',
      content: 'final answer',
      done: true,
    });
  });
});
