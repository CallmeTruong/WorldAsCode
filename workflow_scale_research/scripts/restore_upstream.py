"""Restore the exact pinned img2threejs checkout from the committed Git bundle."""

import json
import subprocess
from pathlib import Path


def main():
    project = Path(__file__).resolve().parents[1]
    lock = json.loads((project / "upstream.lock.json").read_text(encoding="utf-8"))
    target = project.parent / lock["path"]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", str(project / "vendor/img2threejs.bundle"), str(target)],
            check=True,
        )
        subprocess.run(["git", "checkout", "--detach", lock["commit"]], cwd=target, check=True)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=target, text=True).strip()
    if actual != lock["commit"]:
        raise SystemExit("Existing checkout differs from upstream.lock.json; preserve local work and reconcile it before continuing.")
    print("Pinned upstream ready:", actual)


if __name__ == "__main__":
    main()
