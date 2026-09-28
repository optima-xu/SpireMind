from pathlib import Path


class SingleWriter:
    """Kernel-released advisory lock. Lock-file existence alone never means ownership."""

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            import sys

            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("Another SpireMind process owns this bridge") from None
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()
