from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import SharedRuntimeBuildResult, StudioContext
from .util import assert_within, file_sha256, now_iso, write_json, write_text


ENV_SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1
PREFERRED_SUMMARY_PACKAGES = ["flet", "flet-desktop", "playwright", "pypdf", "PyMuPDF", "pywin32"]


def prepare_shared_runtime(context: StudioContext, requirements_path: Path) -> SharedRuntimeBuildResult:
    runtime_root = context.repo_root / "runtime"
    envs_root = runtime_root / "envs"
    envs_root.mkdir(parents=True, exist_ok=True)
    lock_path = requirements_path.parent / "requirements.lock"
    temp_root = context.output_dir / "shared_runtime_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)

    requirements = read_installable_requirements(requirements_path)
    probe = probe_known_good_versions(context, requirements)
    initial_lock_text = initial_lock_from_probe(requirements, probe)
    base_python = select_base_python(context, probe)
    python_version = python_version_text(base_python, context.repo_root, temp_root)
    env_id = env_id_for_lock(python_version, initial_lock_text, probe.package_versions)
    env_path = envs_root / env_id
    assert_within(env_path, envs_root, "shared runtime env")
    env_python = app_env_python(env_path)

    notes = [
        "Shared runtime registration keeps app runtime dependencies separate from build tools.",
        f"requirements_path: {requirements_path}",
        f"known_good_python: {probe.python_path or 'none'}",
        f"known_good_source: {probe.source}",
        f"base_python: {base_python}",
        f"base_python_version: {python_version}",
        f"env_id: {env_id}",
    ]
    if probe.package_versions:
        notes.append("known_good_versions: " + json.dumps(probe.package_versions, ensure_ascii=False, sort_keys=True))

    if env_path.is_dir() and env_python.is_file():
        existing_lock = env_path / "requirements.lock"
        if existing_lock.is_file():
            shutil.copy2(existing_lock, lock_path)
        else:
            write_text(lock_path, initial_lock_text)
        result = SharedRuntimeBuildResult(
            ok=True,
            skipped=True,
            env_id=env_id,
            env_path=env_path,
            python_path=env_python,
            lock_path=lock_path,
            report=build_report(context, env_id, env_path, lock_path, notes + ["Existing shared runtime env was reused."], ""),
            reused=True,
            requirements_lock_sha256=file_sha256(lock_path) if lock_path.is_file() else "",
            package_versions=read_lock_versions(lock_path),
        )
        write_shared_runtime_reports(context, result)
        return result

    staging = envs_root / f".staging_{env_id}"
    assert_within(staging, envs_root, "shared runtime staging env")
    if staging.exists():
        shutil.rmtree(staging)

    create = run_command([str(base_python), "-m", "venv", str(staging)], context.repo_root, temp_root)
    notes.append(command_summary("venv create", [str(base_python), "-m", "venv", str(staging)], create))
    if create.returncode != 0:
        result = failure_result(context, env_id, env_path, lock_path, notes, "shared runtime venv creation failed")
        write_shared_runtime_reports(context, result)
        return result

    staging_python = app_env_python(staging)
    if not staging_python.is_file():
        result = failure_result(context, env_id, env_path, lock_path, notes, "shared runtime python missing after venv creation")
        write_shared_runtime_reports(context, result)
        return result

    initial_lock_path = temp_root / "shared_runtime.initial.lock"
    write_text(initial_lock_path, initial_lock_text)
    install = run_command(
        [str(staging_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(initial_lock_path)],
        context.repo_root,
        temp_root,
    )
    notes.append(command_summary("pip install app runtime dependencies", [str(staging_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(initial_lock_path)], install))
    if install.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        result = failure_result(context, env_id, env_path, lock_path, notes, "shared runtime dependency install failed")
        write_shared_runtime_reports(context, result)
        return result

    freeze = run_command([str(staging_python), "-m", "pip", "freeze"], context.repo_root, temp_root)
    notes.append(command_summary("pip freeze app runtime dependencies", [str(staging_python), "-m", "pip", "freeze"], freeze))
    if freeze.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        result = failure_result(context, env_id, env_path, lock_path, notes, "shared runtime lock freeze failed")
        write_shared_runtime_reports(context, result)
        return result

    resolved_lock_text = freeze.stdout.strip() + ("\n" if freeze.stdout.strip() else "")
    write_text(staging / "requirements.lock", resolved_lock_text)
    write_text(lock_path, resolved_lock_text)
    manifest = env_manifest(context, env_id, python_version, lock_path, read_lock_versions(lock_path), probe)
    write_json(staging / "toolhub_env_manifest.json", manifest)

    if env_path.exists():
        shutil.rmtree(staging, ignore_errors=True)
        reused = True
    else:
        shutil.move(str(staging), str(env_path))
        reused = False
    env_python = app_env_python(env_path)
    result = SharedRuntimeBuildResult(
        ok=True,
        skipped=reused,
        env_id=env_id,
        env_path=env_path,
        python_path=env_python,
        lock_path=lock_path,
        report=build_report(
            context,
            env_id,
            env_path,
            lock_path,
            notes + (["Shared runtime env already existed after staging; reused existing env."] if reused else ["Shared runtime env was created."]),
            "",
        ),
        created=not reused,
        reused=reused,
        requirements_lock_sha256=file_sha256(lock_path),
        package_versions=read_lock_versions(lock_path),
    )
    write_shared_runtime_reports(context, result)
    return result


class KnownGoodProbe:
    def __init__(self, python_path: Path | None, source: str, package_versions: dict[str, str]) -> None:
        self.python_path = python_path
        self.source = source
        self.package_versions = package_versions


def probe_known_good_versions(context: StudioContext, requirements: list[str]) -> KnownGoodProbe:
    packages = [package_name_from_spec(line) for line in requirements]
    packages = [name for name in packages if name]
    if "flet" in {name.lower() for name in packages} and "flet-desktop" not in {name.lower() for name in packages}:
        packages.append("flet-desktop")
    candidates = candidate_pythons(context)
    best = KnownGoodProbe(None, "none", {})
    best_score = -1
    for source, python in candidates:
        versions = installed_package_versions(python, packages, context.repo_root, context.output_dir / "shared_runtime_probe")
        score = sum(1 for name in packages if versions.get(name))
        if score > best_score:
            best = KnownGoodProbe(python, source, versions)
            best_score = score
    return best


def candidate_pythons(context: StudioContext) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    for name in [".venv", "venv", "env"]:
        path = context.source_root / name / "Scripts" / "python.exe"
        if path.is_file():
            candidates.append((f"source_root/{name}", path))
    for command in ["python", "py"]:
        found = shutil.which(command)
        if found:
            candidates.append((f"path/{command}", Path(found)))
    candidates.append(("app_studio_python", Path(sys.executable)))

    seen: set[str] = set()
    unique: list[tuple[str, Path]] = []
    for source, path in candidates:
        key = str(path.resolve()).lower() if path.exists() else str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((source, path))
    return unique


def initial_lock_from_probe(requirements: list[str], probe: KnownGoodProbe) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    lower_versions = {key.lower(): value for key, value in probe.package_versions.items()}
    for requirement in requirements:
        name = package_name_from_spec(requirement)
        if not name:
            continue
        key = normalize_package_name(name)
        version = lower_versions.get(key)
        if version and version_satisfies(version, requirement):
            line = f"{name}=={version}"
        else:
            line = requirement
        lines.append(line)
        seen.add(key)

    flet_version = lower_versions.get("flet")
    if flet_version and "flet-desktop" not in seen:
        desktop_version = lower_versions.get("flet-desktop") or flet_version
        lines.append(f"flet-desktop=={desktop_version}")
    return "\n".join(lines) + ("\n" if lines else "")


def select_base_python(context: StudioContext, probe: KnownGoodProbe) -> Path:
    runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
    if runtime_python.is_file():
        return runtime_python
    if probe.python_path and probe.python_path.is_file():
        return probe.python_path
    return Path(sys.executable)


def env_id_for_lock(python_version: str, lock_text: str, package_versions: dict[str, str]) -> str:
    version_match = re.search(r"Python\s+(\d+)\.(\d+)", python_version)
    py_tag = f"py{version_match.group(1)}{version_match.group(2)}" if version_match else "pyunknown"
    platform = "win_amd64" if os.name == "nt" else sys.platform.replace("-", "_")
    summary = summary_tag(package_versions or read_lock_versions_from_text(lock_text))
    digest = hashlib.sha256((python_version + "\n" + lock_text).encode("utf-8")).hexdigest()[:8]
    return "-".join(part for part in [py_tag, platform, summary, digest] if part)


def summary_tag(package_versions: dict[str, str]) -> str:
    parts: list[str] = []
    lower = {key.lower(): value for key, value in package_versions.items()}
    for name in PREFERRED_SUMMARY_PACKAGES:
        version = lower.get(name.lower())
        if not version:
            continue
        compact = re.sub(r"[^0-9A-Za-z]+", "", version)
        parts.append(f"{normalize_package_name(name).replace('-', '')}{compact}")
    return "-".join(parts[:3]) or "runtime"


def env_manifest(
    context: StudioContext,
    env_id: str,
    python_version: str,
    lock_path: Path,
    package_versions: dict[str, str],
    probe: KnownGoodProbe,
) -> dict[str, Any]:
    return {
        "schema_version": ENV_SCHEMA_VERSION,
        "env_id": env_id,
        "python_version": python_version,
        "platform": "win_amd64" if os.name == "nt" else sys.platform,
        "requirements_lock_sha256": file_sha256(lock_path),
        "created_at": now_iso(),
        "created_for_app_id": context.app_id,
        "known_good_python": str(probe.python_path) if probe.python_path else "",
        "known_good_source": probe.source,
        "packages": package_versions,
        "shared_assets": [],
    }


def update_registry(context: StudioContext, env_id: str, env_path: Path, lock_path: Path) -> None:
    registry_path = context.repo_root / "runtime" / "envs" / "toolhub_env_registry.json"
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            registry = {}
    else:
        registry = {}
    registry.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
    envs = registry.setdefault("envs", {})
    entry = envs.setdefault(env_id, {})
    apps = set(entry.get("apps") or [])
    apps.add(context.app_id)
    entry.update(
        {
            "path": str(env_path.relative_to(context.repo_root)) if env_path.is_relative_to(context.repo_root) else str(env_path),
            "requirements_lock_sha256": file_sha256(lock_path) if lock_path.is_file() else "",
            "apps": sorted(apps),
            "last_used_at": now_iso(),
        }
    )
    write_json(registry_path, registry)


def read_installable_requirements(path: Path) -> list[str]:
    if not path.is_file():
        return []
    result: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = strip_requirement_comment(line.strip().lstrip("\ufeff"))
        if stripped and not stripped.startswith("#"):
            result.append(stripped)
    return result


def strip_requirement_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
            continue
        if char == "#" and quote is None and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line.strip()


def package_name_from_spec(spec: str) -> str:
    return re.split(r"\s*(?:===|==|~=|!=|<=|>=|<|>|;|\[)", spec.strip(), maxsplit=1)[0].strip()


def normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def version_satisfies(version: str, spec: str) -> bool:
    constraints = spec[len(package_name_from_spec(spec)):].strip()
    if not constraints:
        return True
    for raw_part in constraints.split(","):
        part = raw_part.strip()
        if not part or part.startswith(";"):
            continue
        match = re.match(r"(===|==|<=|>=|<|>|~=)\s*(.+)", part)
        if not match:
            return False
        operator, expected = match.groups()
        comparison = compare_versions(version, expected)
        if operator in {"==", "==="} and comparison != 0:
            return False
        if operator == ">=" and comparison < 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "~=" and comparison < 0:
            return False
    return True


def compare_versions(left: str, right: str) -> int:
    left_parts = version_parts(left)
    right_parts = version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts == right_parts:
        return 0
    return 1 if left_parts > right_parts else -1


def version_parts(value: str) -> list[int]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return parts or [0]


def installed_package_versions(python: Path, packages: list[str], cwd: Path, temp_dir: Path) -> dict[str, str]:
    if not python.is_file():
        return {}
    script = "\n".join(
        [
            "import importlib.metadata as metadata",
            "import json",
            "import sys",
            "result = {}",
            "for name in sys.argv[1:]:",
            "    try:",
            "        result[name] = metadata.version(name)",
            "    except metadata.PackageNotFoundError:",
            "        result[name] = ''",
            "print(json.dumps(result, sort_keys=True))",
        ]
    )
    probe = run_probe_command([str(python), "-c", script, *packages], cwd, temp_dir)
    if probe.returncode != 0:
        return {}
    try:
        data = json.loads(probe.stdout.strip() or "{}")
    except Exception:
        return {}
    return {str(key): str(value) for key, value in data.items() if value}


def read_lock_versions(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return read_lock_versions_from_text(path.read_text(encoding="utf-8", errors="replace"))


def read_lock_versions_from_text(text: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "==" not in stripped or stripped.startswith("#"):
            continue
        name, version = stripped.split("==", 1)
        versions[name.strip()] = version.strip()
    return versions


def app_env_python(env_path: Path) -> Path:
    return env_path / "Scripts" / "python.exe" if os.name == "nt" else env_path / "bin" / "python"


def python_version_text(python_path: Path, cwd: Path, temp_dir: Path) -> str:
    completed = run_command([str(python_path), "--version"], cwd, temp_dir)
    text = (completed.stdout or completed.stderr).strip()
    return text if completed.returncode == 0 and text else "unknown"


def run_command(command: list[str], cwd: Path, temp_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def run_probe_command(command: list[str], cwd: Path, temp_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def command_summary(label: str, command: list[str], completed: subprocess.CompletedProcess[str]) -> str:
    stdout = (completed.stdout or "").strip()[-3000:]
    stderr = (completed.stderr or "").strip()[-3000:]
    return f"{label}: exit_code={completed.returncode}\ncommand: {' '.join(command)}\nstdout:\n{stdout}\nstderr:\n{stderr}"


def failure_result(
    context: StudioContext,
    env_id: str,
    env_path: Path,
    lock_path: Path,
    notes: list[str],
    error: str,
) -> SharedRuntimeBuildResult:
    return SharedRuntimeBuildResult(
        ok=False,
        skipped=False,
        env_id=env_id,
        env_path=env_path,
        python_path=None,
        lock_path=lock_path,
        report=build_report(context, env_id, env_path, lock_path, notes, error),
        error=error,
    )


def build_report(
    context: StudioContext,
    env_id: str,
    env_path: Path,
    lock_path: Path,
    notes: list[str],
    error: str,
) -> str:
    status = "FAIL" if error else "PASS"
    lines = [
        "# Shared Runtime Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- status: `{status}`",
        f"- env_id: `{env_id}`",
        f"- env_path: `{env_path}`",
        f"- lock_path: `{lock_path}`",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in notes)
    if error:
        lines.extend(["", "## Error", "", error])
    return "\n".join(lines) + "\n"


def write_shared_runtime_reports(context: StudioContext, result: SharedRuntimeBuildResult) -> None:
    write_text(context.output_dir / "shared_runtime_report.md", result.report)
    write_json(
        context.output_dir / "shared_runtime_result.json",
        {
            "ok": result.ok,
            "skipped": result.skipped,
            "created": result.created,
            "reused": result.reused,
            "env_id": result.env_id,
            "env_path": str(result.env_path),
            "python_path": str(result.python_path) if result.python_path else "",
            "lock_path": str(result.lock_path),
            "requirements_lock_sha256": result.requirements_lock_sha256,
            "package_versions": result.package_versions,
            "error": result.error,
        },
    )
    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_text(log_dir / f"{context.app_id}_shared_runtime_report.md", result.report)
    write_json(
        log_dir / f"{context.app_id}_shared_runtime_result.json",
        {
            "ok": result.ok,
            "created": result.created,
            "reused": result.reused,
            "env_id": result.env_id,
            "env_path": str(result.env_path),
            "python_path": str(result.python_path) if result.python_path else "",
            "requirements_lock_sha256": result.requirements_lock_sha256,
            "package_versions": result.package_versions,
            "error": result.error,
        },
    )
