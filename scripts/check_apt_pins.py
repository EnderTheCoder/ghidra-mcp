"""Check that the runtime stage's pinned apt packages are still installable.

Reads the runtime stage of the Dockerfile (base image digest and every
``package=version`` passed to ``apt-get install``) and asks apt inside that exact
base image to simulate the installation. Ubuntu only indexes the newest version
of a package per pocket, so a pin stops resolving once an update is published;
this script then exits non-zero. It changes nothing: no image is built and no
package is installed.
"""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([a-z0-9][a-z0-9.+-]*)=([0-9][A-Za-z0-9.+~:-]*)$")


def runtime_pins(dockerfile: str) -> tuple[str, dict[str, str]]:
    stage = re.search(
        r"^FROM (ubuntu:[0-9.]+@sha256:[0-9a-f]{64}) AS runtime$\n(.*?)(?=^FROM |\Z)",
        dockerfile,
        re.M | re.S,
    )
    if stage is None:
        raise SystemExit("Dockerfile has no digest-pinned ubuntu runtime stage")
    pins: dict[str, str] = {}
    for install in re.findall(r"apt-get install ([^\n]*?) \\\n", stage.group(2)):
        for token in install.split():
            match = PIN.match(token)
            if match:
                pins[match.group(1)] = match.group(2)
    if not pins:
        raise SystemExit("runtime stage pins no apt packages")
    return stage.group(1), pins


def main() -> None:
    base, pins = runtime_pins((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    requested = [f"{name}={version}" for name, version in pins.items()]
    print(f"base image: {base}")
    print("pins: " + " ".join(requested), flush=True)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=missing",
            base,
            "sh",
            "-ec",
            'apt-get update -qq && apt-get install -y --dry-run --no-install-recommends "$@"',
            "apt-pin-check",
            *requested,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    print(result.stdout[-4000:], end="")
    print(result.stderr[-4000:], end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(
            f"apt cannot install the pinned runtime packages (exit {result.returncode})"
        )
    missing = [
        f"{name}={version}"
        for name, version in pins.items()
        if not re.search(
            rf"^Inst {re.escape(name)} (?:\[[^\]]*\] )?\({re.escape(version)} ", result.stdout, re.M
        )
    ]
    if missing:
        raise SystemExit("apt would not install these exact versions: " + " ".join(missing))
    print(f"all {len(pins)} runtime pins are installable")


if __name__ == "__main__":
    main()
