"""Reflection has evidence access, and deliberately has no game/environment port."""

import asyncio
import json

from .experience import LessonProposal


class ReflectionAgent:
    name = "reflection"

    def __init__(self, memory, provider=None):
        self.memory, self.provider = memory, provider
        self.queue = asyncio.Queue(maxsize=8)
        self.queued = set()
        self.closing = False
        self.closed = False
        self.completed = self.rejected = 0
        self.task = asyncio.create_task(self._consume(), name="reflection-agent")

    async def notify(self):
        if self.closing:
            return
        jobs = await self.memory.call(
            lambda: self.memory.store.db.execute(
                "SELECT id,payload FROM reflection_jobs WHERE status='pending' ORDER BY rowid LIMIT 16"
            ).fetchall()
        )
        for identity, payload in jobs:
            if identity not in self.queued:
                try:
                    self.queue.put_nowait((identity, json.loads(payload)))
                    self.queued.add(identity)
                except asyncio.QueueFull:
                    break  # Durable pending jobs are picked up after the consumer frees space.

    async def _consume(self):
        while True:
            item = await self.queue.get()
            try:
                if item is None:
                    return
                identity, job = item
                if self.provider:
                    evidence = await self.memory.call(
                        lambda j=job: [self.memory.experience.compact(key) for key in j["evidence_ids"][:8]]
                    )
                    proposals = await self.provider.reflect(evidence)
                    for value in proposals:
                        try:
                            proposal = LessonProposal.model_validate(value)
                            await self.memory.call(lambda p=proposal: self.memory.experience.propose(p))
                        except ValueError:
                            self.rejected += 1
                else:
                    await self.memory.call(self.memory.experience.consolidate)
                await self.memory.call(lambda i=identity: self._status(i, "complete"))
                self.completed += 1
            except asyncio.CancelledError:
                if item is not None:
                    await self.memory.call(lambda i=item: self._status(i[0], "pending"))
                raise
            except Exception as error:
                # A failed/budget-limited job remains recoverable, with an audit entry.
                if item is not None:
                    error_name = type(error).__name__
                    await self.memory.call(lambda i=item, e=error_name: self._status(i[0], "pending", e))
                self.closing = True
            finally:
                if item is not None:
                    self.queued.discard(item[0])
                self.queue.task_done()
            if not self.closing:
                await self.notify()

    def _status(self, identity, status, error=None):
        self.memory.store.db.execute(
            "UPDATE reflection_jobs SET status=?,attempts=attempts+1 WHERE id=?", (status, identity)
        )
        if error:
            self.memory.store.db.execute(
                "INSERT INTO memory_audit(instance,producer,payload) VALUES (?,'reflection',?)",
                (identity, json.dumps({"error": error})),
            )
        self.memory.store.db.commit()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        self.closing = True

        async def drain():
            if self.task.done():
                while not self.queue.empty():
                    self.queue.get_nowait()
                    self.queue.task_done()
                await asyncio.gather(self.task, return_exceptions=True)
                return
            await self.queue.join()
            await self.queue.put(None)
            await self.task

        task = asyncio.create_task(drain())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
