"""Bounded producer/consumer logging with failure propagation and orderly drain."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from .trace import TraceWriter


class TraceWriteError(RuntimeError):
    pass


class AsyncTraceWriter:
    def __init__(self, root, mode, configuration=None, *, capacity=256):
        base = TraceWriter(root, mode, configuration)
        self.path, self.mode, self.attempt_id = base.path, base.mode, base.attempt_id
        self.queue = asyncio.Queue(maxsize=capacity)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spiremind-trace")
        self.handles = {}
        self.closed = False
        self.error = None
        self.max_depth = self.records = self.batches = 0
        self.consumer = asyncio.create_task(self._consume(), name="trace-consumer")

    def _write_batch(self, batch):
        for kind, filename, text, _ in batch:
            if kind == "append":
                if filename not in self.handles:
                    self.handles[filename] = (self.path / filename).open("a", encoding="utf-8")
                self.handles[filename].write(text)
            elif kind == "json":
                temporary = self.path / (filename + ".tmp")
                temporary.write_text(text, encoding="utf-8")
                temporary.replace(self.path / filename)
            elif kind == "flush":
                for handle in self.handles.values():
                    handle.flush()

    def _close_handles(self):
        for handle in self.handles.values():
            handle.close()

    async def _consume(self):
        loop = asyncio.get_running_loop()
        try:
            while True:
                first = await self.queue.get()
                batch = [first]
                while len(batch) < 32 and not self.queue.empty() and batch[-1][0] != "stop":
                    batch.append(self.queue.get_nowait())
                try:
                    await loop.run_in_executor(self.executor, self._write_batch, batch)
                    self.records += len(batch)
                    self.batches += 1
                    for _, _, _, future in batch:
                        if future and not future.done():
                            future.set_result(None)
                except Exception as error:
                    self.error = TraceWriteError(f"trace_write_failed:{type(error).__name__}")
                    for _, _, _, future in batch:
                        if future and not future.done():
                            future.set_exception(self.error)
                    raise self.error from None
                finally:
                    for _ in batch:
                        self.queue.task_done()
                if any(item[0] == "stop" for item in batch):
                    break
        finally:
            try:
                await loop.run_in_executor(self.executor, self._close_handles)
            finally:
                # A producer may finish queue.put while handle closure awaits
                # the worker. Settle those late acknowledgements before exiting;
                # draining earlier can leave flush waiting on a dead consumer.
                while not self.queue.empty():
                    _, _, _, future = self.queue.get_nowait()
                    if future and not future.done():
                        future.set_exception(self.error or TraceWriteError("trace_stopped"))
                    self.queue.task_done()

    async def _send(self, kind, filename="", text="", future=None):
        if self.error:
            raise self.error
        if self.closed:
            raise TraceWriteError("trace_closed")
        put = asyncio.create_task(self.queue.put((kind, filename, text, future)))
        try:
            done, _ = await asyncio.wait((put, self.consumer), return_when=asyncio.FIRST_COMPLETED)
            if self.consumer in done:
                await self.consumer
                raise TraceWriteError("trace_consumer_stopped")
            await put
            self.max_depth = max(self.max_depth, self.queue.qsize())
        finally:
            if not put.done():
                put.cancel()
                await asyncio.gather(put, return_exceptions=True)

    async def append(self, filename, payload):
        await self._send("append", filename, json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    async def write_json(self, filename, payload):
        await self._send("json", filename, json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    async def flush(self):
        future = asyncio.get_running_loop().create_future()
        await self._send("flush", future=future)
        await future

    async def close(self):
        if self.closed:
            return

        async def drain():
            if not self.consumer.done() and self.error is None:
                await self._send("stop")
            await self.consumer

        task = asyncio.create_task(drain())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        finally:
            self.closed = True
            self.executor.shutdown(wait=True)
