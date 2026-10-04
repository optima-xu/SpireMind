"""Atomic replacement with a short, bounded Windows sharing-violation retry."""

import time


def replace_file(temporary, target):
    for attempt in range(5):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * 2**attempt)
