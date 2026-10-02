import json

from spiremind.providers.openai import OpenAIProvider
from spiremind.providers.protocols import BudgetExceeded, RequestBudget

from .experience import LessonProposal


async def consolidate_model(store, config, output=None, *, prior=None):
    budget = RequestBudget(8, 40000)
    if prior:
        budget.requests = prior["budget"]["requests"]
        budget.tokens = prior["budget"]["tokens"]
    provider = OpenAIProvider(config.model, budget=budget)
    accepted = prior.get("accepted", 0) if prior else 0
    rejected = prior.get("rejected", 0) if prior else 0
    jobs = prior.get("completed_jobs", 0) if prior else 0
    if prior:
        provider.request_records.extend(prior.get("requests", []))

    def checkpoint():
        if output:
            value = dict(
                budget=budget.report(),
                completed_jobs=jobs,
                accepted=accepted,
                rejected=rejected,
                requests=provider.request_records,
            )
            temporary = output.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
            temporary.replace(output)

    provider.request_sink = checkpoint
    try:
        lineages = [
            row[0]
            for row in store.db.execute(
                "SELECT DISTINCT lineage FROM episodes WHERE partition_name='train' "
                "AND verified=1 ORDER BY lineage"
            )
        ]
        for lineage in lineages:
            keys = [
                r[0]
                for r in store.db.execute(
                    "SELECT id FROM episodes WHERE lineage=? AND verified=1 AND partition_name='train' "
                    "ORDER BY rowid DESC LIMIT 2",
                    (lineage,),
                )
            ]
            try:
                lessons = await provider.reflect([store.compact(key) for key in keys])
                jobs += 1
                for value in lessons:
                    try:
                        store.propose(LessonProposal.model_validate(value))
                        accepted += 1
                    except ValueError:
                        rejected += 1
            except BudgetExceeded:
                break
            except (ValueError, RuntimeError):
                rejected += 1
            checkpoint()
        return dict(
            budget=budget.report(),
            completed_jobs=jobs,
            accepted=accepted,
            rejected=rejected,
            requests=provider.request_records,
            memory=store.inspect(),
        )
    finally:
        await provider.close()
        checkpoint()
