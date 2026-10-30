import { describe, expect, it } from "vitest";

import { SSEParser, readSSE } from "./sse";

function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? encoder.encode(c) : c);
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const out = [];
  for await (const m of readSSE(body)) out.push(m);
  return out;
}

describe("SSEParser", () => {
  it("parses complete events", () => {
    const p = new SSEParser();
    expect(p.feed('event: step\ndata: {"node":"a"}\n\nevent: sql\ndata: {"sql":"x"}\n\n')).toEqual([
      { event: "step", data: '{"node":"a"}' },
      { event: "sql", data: '{"sql":"x"}' },
    ]);
  });

  it("waits for the blank line when an event is split across chunks", () => {
    const p = new SSEParser();
    expect(p.feed("event: st")).toEqual([]);
    expect(p.feed('ep\ndata: {"no')).toEqual([]);
    expect(p.feed('de":"a"}\n')).toEqual([]);
    expect(p.feed("\n")).toEqual([{ event: "step", data: '{"node":"a"}' }]);
  });

  it("handles CRLF, comments, multi-line data, and the default event name", () => {
    const p = new SSEParser();
    expect(p.feed(": keep-alive\r\n\r\ndata: line1\r\ndata: line2\r\n\r\n")).toEqual([
      { event: "message", data: "line1\nline2" },
    ]);
  });
});

describe("readSSE", () => {
  it("yields events from a byte stream, including a UTF-8 character split across chunks", async () => {
    const bytes = new TextEncoder().encode(
      'event: answer\ndata: {"text":"Rp 1,2 miliar · ok"}\n\n',
    );
    const split = bytes.indexOf(0xc2) + 1; // the middle of "·" (0xC2 0xB7)
    const events = await collect(streamOf(bytes.slice(0, split), bytes.slice(split)));
    expect(events).toEqual([{ event: "answer", data: '{"text":"Rp 1,2 miliar · ok"}' }]);
  });

  it("flushes a last event that has no trailing blank line", async () => {
    expect(await collect(streamOf("event: done\ndata: {}"))).toEqual([
      { event: "done", data: "{}" },
    ]);
  });
});
