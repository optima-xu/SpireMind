"""Install the freshly built wheel in isolation and verify packaged behavior data."""

import argparse
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Reuse installed dependencies; no downloads")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheels = sorted((root / "dist").glob("spiremind-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("No built SpireMind wheel found in dist/")
    staging = root / "runs" / "wheel-smoke"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spiremind-wheel-", dir=staging) as directory:
        environment = Path(directory).resolve()
        assert environment.is_relative_to(staging.resolve())
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        install_flags = ["--no-index", "--no-deps", "--disable-pip-version-check"] if args.offline else []
        subprocess.run(
            [str(python), "-m", "pip", "install", *install_flags, str(wheels[-1])],
            check=True,
        )
        if args.offline:
            import httpx

            site = environment / (
                "Lib/site-packages"
                if sys.platform == "win32"
                else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
            )
            # The wheel's own site directory precedes this dependency-only fallback.
            (site / "offline-dependencies.pth").write_text(
                str(Path(httpx.__file__).resolve().parents[1]) + "\n", encoding="utf-8"
            )
        code = (
            "import json,sys,spiremind; from pathlib import Path; from importlib.resources import files; "
            "assert Path(spiremind.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "from spiremind.core.enums import ActionKind; "
            "assert ActionKind.OPEN_CARD_REWARD.value == 'open_card_reward'; "
            "assert files('spiremind').joinpath('evaluation/cases/quality.json').is_file(); "
            "assert files('spiremind').joinpath('knowledge/strategies/ironclad/packages.yaml').is_file(); "
            "assert files('spiremind').joinpath('knowledge/skills/tactics.yaml').is_file(); "
            "p=files('spiremind').joinpath('knowledge/enemies/v0.111.0.json'); "
            "assert p.is_file(); k=json.loads(p.read_text(encoding='utf-8')); "
            "assert k['enemy_count'] == 115; "
            "assert next(x for x in k['enemies'] if x['id']=='the_insatiable')['strategy']; "
            "b=next(x for x in k['enemies'] if x['id']=='bygone_effigy'); "
            "assert any('Slow increases' in tip for tip in b['strategy'])"
        )
        subprocess.run([str(python), "-I", "-c", code], check=True)
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
        quality = subprocess.run(
            [str(python), "-m", "spiremind", "evaluate"],
            cwd=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        quality = json.loads(quality.stdout)
        assert quality["passed"] == quality["total"] == 8 and quality["model_calls"] == 0
        benchmark_path = environment / "benchmark.json"
        subprocess.run(
            [str(python), "-m", "spiremind", "benchmark", "--rounds", "1", "--output", str(benchmark_path)],
            cwd=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(benchmark_path.read_text())["cases"] == 16
        print(
            "Isolated wheel: knowledge, 10-action walkthrough, 8 quality cases and offline benchmark passed."
        )


if __name__ == "__main__":
    main()
