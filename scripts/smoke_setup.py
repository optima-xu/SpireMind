"""Exercise Windows Quick Start in a fresh copy, without a game or model connection."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit("The PowerShell setup smoke test requires Windows.")
    root = Path(__file__).resolve().parents[1]
    staging = root / "runs"
    staging.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setup smoke-", dir=staging) as directory:
        project = Path(directory).resolve()
        assert project.is_relative_to(staging.resolve())
        for name in (
            "src",
            "scripts",
            "README.md",
            "README.zh-CN.md",
            "LICENSE",
            "pyproject.toml",
            "uv.lock",
            ".env.example",
            "config.example.toml",
            "config.deepseek.example.toml",
            "spiremind.cmd",
        ):
            source, target = root / name, project / name
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copyfile(source, target)
        setup = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project / "scripts/setup.ps1"),
            "-Offline",
        ]
        subprocess.run([*setup, "-Provider", "deepseek"], cwd=project, check=True)
        config_path, env_path = project / "config.local.toml", project / ".env"
        assert config_path.read_bytes() == (root / "config.deepseek.example.toml").read_bytes()
        assert env_path.read_bytes() == (root / ".env.example").read_bytes()
        custom_config = config_path.read_text(encoding="utf-8") + "\n# keep-user-config\n"
        config_path.write_text(custom_config, encoding="utf-8")
        env_path.write_text("SPIREMIND_SETUP_CHECK=literal-value\n", encoding="utf-8")
        config_before, env_before = config_path.read_bytes(), env_path.read_bytes()
        subprocess.run([*setup, "-Provider", "openai"], cwd=project, check=True)
        assert config_path.read_bytes() == config_before
        assert env_path.read_bytes() == env_before
        # Run the same launcher as the README; quoted paths must also work with spaces.
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "spiremind.cmd start --environment mock --policy rules"],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report = json.loads(result.stdout)
        assert report["complete"] and report["verified_actions"] == 10
        assert report["model_calls"] == 0
        assert not (project / "references").exists() and not (project / "build").exists()
        print("Windows setup: fresh install, preserved config and 10-action launcher walkthrough passed.")


if __name__ == "__main__":
    main()
