"""Install the freshly built wheel in isolation and verify packaged behavior data."""

import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = sorted((root / "dist").glob("spiremind-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("No built SpireMind wheel found in dist/")
    with tempfile.TemporaryDirectory(prefix="spiremind-wheel-") as directory:
        environment = Path(directory)
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheels[-1])],
            check=True,
        )
        code = (
            "import json; from importlib.resources import files; "
            "from spiremind.core.enums import ActionKind; "
            "assert ActionKind.OPEN_CARD_REWARD.value == 'open_card_reward'; "
            "assert files('spiremind').joinpath('knowledge/strategies/ironclad/packages.yaml').is_file(); "
            "assert files('spiremind').joinpath('knowledge/skills/tactics.yaml').is_file(); "
            "p=files('spiremind').joinpath('knowledge/enemies/v0.111.0.json'); "
            "assert p.is_file(); k=json.loads(p.read_text(encoding='utf-8')); "
            "assert k['enemy_count'] == 115; "
            "assert next(x for x in k['enemies'] if x['id']=='the_insatiable')['strategy']; "
            "b=next(x for x in k['enemies'] if x['id']=='bygone_effigy'); "
            "assert any('Slow increases' in tip for tip in b['strategy'])"
        )
        subprocess.run([str(python), "-c", code], check=True)
        result = subprocess.run(
            [
                str(python),
                "-m",
                "spiremind",
                "start",
                "--environment",
                "mock",
                "--policy",
                "rules",
                "--no-limits",
            ],
            cwd=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        import json

        walkthrough = json.loads(result.stdout)
        assert walkthrough["complete"] and walkthrough["verified_actions"] == 10
        benchmark_path = environment / "benchmark.json"
        subprocess.run(
            [str(python), "-m", "spiremind", "benchmark", "--rounds", "1", "--output", str(benchmark_path)],
            cwd=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(benchmark_path.read_text())["cases"] == 16
        print("Isolated wheel: packaged knowledge, 10 verified actions and offline benchmark passed.")


if __name__ == "__main__":
    main()
