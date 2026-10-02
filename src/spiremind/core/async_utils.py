import inspect


async def resolve(value):
    """Allow synchronous offline adapters alongside asynchronous production ports."""
    return await value if inspect.isawaitable(value) else value
