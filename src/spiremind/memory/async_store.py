"""All runtime SQLite connections belong to one dedicated worker thread."""

import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor

from spiremind.knowledge.cards import CardDB
from spiremind.strategies.run import DeckAnalyzer

from .experience import ExperienceStore
from .manager import MemoryManager
from .storage_sqlite import MemoryStore


class AsyncCards:
    def __init__(self, worker):
        self.worker = worker

    async def lookup(self, ids, version):
        if not ids:
            return []
        return await self.worker.call(lambda: self.worker.cards.lookup(ids, version))

    async def count(self, version):
        return await self.worker.call(lambda: self.worker.cards.count(version))

    async def metadata(self, version):
        return await self.worker.call(lambda: self.worker.cards.metadata(version))

    async def sync(self, version, facts):
        def sync():
            if self.worker.cards.needs_sync(version, facts=facts):
                self.worker.cards.put_many(facts)

        return await self.worker.call(sync)


class AsyncMemory:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spiremind-sqlite")
        self.closed = False

    @classmethod
    async def create(cls, memory_path, cards_path, library, *, learning=True):
        worker = cls()

        def initialize():
            worker.thread_id = threading.get_ident()
            worker.store = MemoryStore(memory_path)
            worker.cards = CardDB(cards_path)
            worker.manager = MemoryManager(worker.store, cards=worker.cards)
            worker.analyzer = DeckAnalyzer(library, worker.cards)
            worker.experience = ExperienceStore(worker.store.db)
            if learning:
                worker.manager.experience = worker.experience

        try:
            await worker.call(initialize)
        except BaseException:
            await worker.close()
            raise
        worker.card_gateway = AsyncCards(worker)
        return worker

    async def call(self, function):
        if self.closed:
            raise RuntimeError("storage_worker_closed")

        def run():
            result = function()
            return asyncio.run(result) if inspect.isawaitable(result) else result

        # Shielding keeps a cancelled caller from cancelling a queued transaction.
        return await asyncio.shield(asyncio.get_running_loop().run_in_executor(self.executor, run))

    async def prepare(self, state, agent):
        def prepare():
            self.manager.apply_analysis(state, self.analyzer.analyze(state))
            return self.manager.context(state, agent)

        return await self.call(prepare)

    async def ensure_run(self, state):
        return await self.call(lambda: self.manager.ensure_run(state))

    async def begin_run(self, state):
        return await self.call(lambda: self.manager.begin_run(state))

    async def update(self, *args, **kwargs):
        return await self.call(lambda: self.manager.update_sync(*args, **kwargs))

    async def finish_run(self, outcome):
        return await self.call(lambda: self.manager.finish_run(outcome))

    async def invalidate_plan(self):
        return await self.call(self.manager.invalidate_plan)

    async def stats(self):
        return await self.call(
            lambda: dict(
                thread_id=self.thread_id,
                transactions=self.store.transactions,
                card_queries=self.cards.lookup_queries,
                card_cache=self.cards.cache.stats(),
                deck_cache=self.analyzer.cache.stats(),
                retrieval_cache=self.experience.cache.stats(),
            )
        )

    async def close(self):
        if self.closed:
            return

        def close():
            if hasattr(self, "cards"):
                self.cards.close()
            if hasattr(self, "store"):
                self.store.close()

        await self.call(close)
        self.closed = True
        self.executor.shutdown(wait=True)
