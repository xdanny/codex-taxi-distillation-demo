from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import textwrap
import webbrowser
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .domain import read_json
from .paths import active_experiment_id, state_root

DEMO_ARMS = ("qwen-bare", "qwen-skill", "terra")
ARM_LABELS = {
    "qwen-bare": "Qwen · base skills",
    "qwen-skill": "Qwen · distilled skill",
    "terra": "Terra · teacher",
}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class DemoRun:
    arm: str
    directory: Path
    record: dict[str, Any]
    request: dict[str, Any]
    verification: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_demo_runs(root: Path, experiment_id: str | None = None) -> list[DemoRun]:
    selected = experiment_id or active_experiment_id(root)
    experiment = state_root(root) / "experiments" / selected
    if not experiment.is_dir():
        raise FileNotFoundError(f"experiment does not exist: {selected}")
    found: list[DemoRun] = []
    for arm in DEMO_ARMS:
        candidates: list[DemoRun] = []
        for record_path in sorted((experiment / "runs").glob("*/run.json")):
            record = read_json(record_path)
            if record.get("arm") != arm or record.get("accepted") is not True:
                continue
            directory = record_path.parent
            request_path = directory / "attempt-1.request.json"
            verification_path = directory / "attempt-1.verification.json"
            events_path = directory / "attempt-1.events.jsonl"
            if not all(path.is_file() for path in (request_path, verification_path, events_path)):
                continue
            candidates.append(
                DemoRun(
                    arm=arm,
                    directory=directory,
                    record=record,
                    request=read_json(request_path),
                    verification=read_json(verification_path),
                )
            )
        if not candidates:
            raise FileNotFoundError(f"no accepted {arm} run with complete evidence in {selected}")
        found.append(candidates[-1])
    return found


def select_demo_run_history(root: Path, experiment_id: str | None = None) -> list[DemoRun]:
    selected = experiment_id or active_experiment_id(root)
    experiment = state_root(root) / "experiments" / selected
    if not experiment.is_dir():
        raise FileNotFoundError(f"experiment does not exist: {selected}")
    history: list[DemoRun] = []
    for arm in DEMO_ARMS:
        candidates: list[DemoRun] = []
        for record_path in sorted((experiment / "runs").glob("*/run.json")):
            record = read_json(record_path)
            if record.get("arm") != arm or record.get("accepted") is not True:
                continue
            directory = record_path.parent
            request_path = directory / "attempt-1.request.json"
            verification_path = directory / "attempt-1.verification.json"
            events_path = directory / "attempt-1.events.jsonl"
            if not all(path.is_file() for path in (request_path, verification_path, events_path)):
                continue
            candidates.append(
                DemoRun(
                    arm=arm,
                    directory=directory,
                    record=record,
                    request=read_json(request_path),
                    verification=read_json(verification_path),
                )
            )
        take_count = 2 if arm in {"qwen-bare", "qwen-skill"} else 1
        if not candidates:
            raise FileNotFoundError(
                f"no accepted {arm} run with complete evidence in {selected}"
            )
        history.extend(reversed(candidates[-take_count:]))
    return history


def _clean(value: str) -> str:
    return ANSI_ESCAPE.sub("", value).replace("\t", "    ").replace("\r", "")


def _screen_lines(text: str, *, limit: int = 18) -> list[str]:
    lines: list[str] = []
    for original in _clean(text).splitlines():
        if not original.strip():
            continue
        lines.extend(textwrap.wrap(original, width=88, subsequent_indent="  ") or [""])
    if len(lines) <= limit:
        return lines
    head = max(1, limit // 2)
    tail = max(1, limit - head - 1)
    return [
        *lines[:head],
        "… screen excerpt shortened; raw event stream is linked …",
        *lines[-tail:],
    ]


def _command_events(events_path: Path) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        item = event.get("item", {})
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
        ):
            completed.append(item)
    return completed


def _pick_command(
    events: list[dict[str, Any]],
    patterns: tuple[str, ...],
    *,
    prefer_last: bool,
) -> dict[str, Any] | None:
    command_matches = [
        item
        for item in events
        if any(pattern in str(item.get("command", "")).lower() for pattern in patterns)
    ]
    if command_matches:
        return command_matches[-1] if prefer_last else command_matches[0]
    output_matches = [
        item
        for item in events
        if any(pattern in str(item.get("aggregated_output", "")).lower() for pattern in patterns)
    ]
    if not output_matches:
        return None
    return output_matches[-1] if prefer_last else output_matches[0]


def _normalized_command(value: str) -> str:
    compact = " ".join(_clean(value).split())
    compact = re.sub(r"/private/[^ ]+/workspace", "<candidate-workspace>", compact)
    compact = re.sub(r"/(?:Users|home)/[^/\s]+/[^ ]+", "<demo-repo>", compact)
    return compact[:520] + ("…" if len(compact) > 520 else "")


def _scene(title: str, subtitle: str, body: list[str]) -> str:
    yellow = "\x1b[38;2;246;196;69m"
    cyan = "\x1b[38;2;75;143;216m"
    green = "\x1b[38;2;53;183;121m"
    white = "\x1b[38;2;245;241;232m"
    dim = "\x1b[38;2;151;164;176m"
    reset = "\x1b[0m"
    rule = "─" * 88
    rendered = [
        "\x1b[2J\x1b[H",
        f"{yellow}NYC TAXI · PRESERVED RUN REPLAY{reset}",
        f"{white}{title}{reset}",
        f"{dim}{subtitle}{reset}",
        f"{cyan}{rule}{reset}",
        "",
    ]
    for line in body:
        prefix = f"{green}✓{reset} " if line.startswith("PASS ") else "  "
        visible = line[5:] if line.startswith("PASS ") else line
        rendered.append(prefix + visible)
    rendered.extend(
        [
            "",
            f"{cyan}{rule}{reset}",
            f"{dim}Edited timing. Screen text is derived from linked run evidence.{reset}",
        ]
    )
    return "\r\n".join(rendered) + "\r\n"


def build_cast(demo: DemoRun, output: Path) -> dict[str, Any]:
    record = demo.record
    events_path = demo.directory / "attempt-1.events.jsonl"
    commands = _command_events(events_path)
    skills = [str(value) for value in record.get("selected_skills", [])]
    usage = record.get("usage", {})
    findings = demo.verification.get("findings", [])
    row_finding = next(
        (
            item
            for item in findings
            if isinstance(item, dict) and item.get("name") == "every input row is accounted for"
        ),
        {},
    )
    rows = row_finding.get("evidence", {}) if isinstance(row_finding, dict) else {}

    scenes: list[tuple[str, str, list[str], float]] = [
        (
            ARM_LABELS[demo.arm],
            f"Run {record['run_id']}",
            [
                f"Model: {record.get('model')} · provider route: {record.get('provider')}",
                f"Mounted skills: {', '.join(skills)}",
                f"Sandbox: {demo.request.get('sandbox')} · attempt: 1",
                "",
                "Prompt supplied to the model:",
                *_screen_lines(str(demo.request.get("prompt", "")), limit=9),
            ],
            11.0,
        )
    ]
    command_specs = (
        (
            "The model inspects the staged Taxi inputs",
            ("read_parquet", "taxi_trips.parquet"),
            False,
        ),
        ("The model builds and tests the dbt product", ("dbt build",), True),
        (
            "The model publishes and queries the serving data",
            ("analyst-questions", "exports"),
            True,
        ),
    )
    for title, patterns, prefer_last in command_specs:
        item = _pick_command(commands, patterns, prefer_last=prefer_last)
        if item is None:
            continue
        body = [
            "$ " + _normalized_command(str(item.get("command", ""))),
            "",
            *_screen_lines(str(item.get("aggregated_output", "")), limit=15),
            f"exit code: {item.get('exit_code')}",
        ]
        scenes.append((title, "Raw command and output excerpt", body, 13.0))

    passed = [
        str(item.get("name"))
        for item in findings
        if isinstance(item, dict) and item.get("pass") is True
    ]
    scenes.append(
        (
            "The unchanged verifier accepts the finished product",
            "Verifier executed after the model exited",
            [
                *(f"PASS {name}" for name in passed[:9]),
                "",
                f"Rows: {rows.get('raw', '?')} raw = {rows.get('accepted', '?')} accepted + "
                f"{rows.get('quarantined', '?')} quarantined",
                f"Reported input + output tokens: "
                f"{int(usage.get('input_tokens', 0)) + int(usage.get('output_tokens', 0)):,}",
                f"Cached input tokens: {int(usage.get('cached_input_tokens', 0)):,}",
                f"Elapsed model time: {float(record.get('elapsedSeconds', 0)):.1f}s",
                f"Final status: {'ACCEPTED' if record.get('accepted') is True else 'NOT ACCEPTED'}",
            ],
            14.0,
        )
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    cast_lines = [
        json.dumps(
            {
                "version": 2,
                "width": 96,
                "height": 30,
                "timestamp": 0,
                "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
                "title": f"{ARM_LABELS[demo.arm]} · {record['run_id']}",
            }
        )
    ]
    now = 0.0
    chapters: list[dict[str, Any]] = []
    for title, _subtitle, _body, hold in scenes:
        chapters.append({"time": round(now, 2), "label": title})
        payload = _scene(title, _subtitle, _body)
        cast_lines.append(json.dumps([round(now, 2), "o", payload]))
        now += hold
    cast_lines.append(json.dumps([round(now, 2), "o", "\r"]))
    output.write_text("\n".join(cast_lines) + "\n", encoding="utf-8")
    return {"duration": round(now, 2), "chapters": chapters, "sceneCount": len(scenes)}


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _render_video(cast: Path, video: Path, poster: Path) -> None:
    agg = shutil.which("agg")
    ffmpeg = shutil.which("ffmpeg")
    if agg is None or ffmpeg is None:
        raise RuntimeError("recording needs `agg` and `ffmpeg` on PATH")
    gif = video.with_suffix(".render-cache.gif")
    _run(
        [
            agg,
            "--font-family",
            "Menlo",
            "--font-size",
            "20",
            "--line-height",
            "1.32",
            "--cols",
            "96",
            "--rows",
            "30",
            "--fps-cap",
            "30",
            "--idle-time-limit",
            "3600",
            "--no-loop",
            "--last-frame-duration",
            "14",
            "--quiet",
            str(cast),
            str(gif),
        ]
    )
    _run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(gif),
            "-vf",
            "scale=-2:1080:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x101820,"
            "fps=30,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(video),
        ]
    )
    _run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "2",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(poster),
        ]
    )
    gif.unlink()


def _copy_evidence(demo: DemoRun, destination: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    for source_name, public_name in (
        ("run.json", "run.json"),
        ("attempt-1.request.json", "request.json"),
        ("attempt-1.verification.json", "verification.json"),
        ("attempt-1.events.jsonl", "events.jsonl"),
        ("input-receipt.json", "input-receipt.json"),
    ):
        source = demo.directory / source_name
        target = destination / public_name
        shutil.copy2(source, target)
        copied[public_name] = _sha256(target)
    return copied


def record_demo_videos(
    root: Path,
    *,
    experiment_id: str | None = None,
    site_directory: Path | None = None,
) -> Path:
    selected = experiment_id or active_experiment_id(root)
    site = site_directory or root / "demo-site"
    assets = site / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    primary_ids = {
        demo.arm: str(demo.record["run_id"]) for demo in select_demo_runs(root, selected)
    }
    for demo in select_demo_run_history(root, selected):
        run_id = str(demo.record["run_id"])
        primary = primary_ids[demo.arm] == run_id
        directory_name = demo.arm if primary else f"{demo.arm}-earlier"
        directory = assets / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        cast = directory / "replay.cast"
        video = directory / "replay.mp4"
        poster = directory / "poster.png"
        timing = build_cast(demo, cast)
        _render_video(cast, video, poster)
        evidence = _copy_evidence(demo, directory)
        usage = demo.record.get("usage", {})
        entries.append(
            {
                "arm": demo.arm,
                "id": run_id,
                "label": ARM_LABELS[demo.arm],
                "takeLabel": "Fresh take" if primary else "Earlier take",
                "primary": primary,
                "runId": run_id,
                "model": demo.record.get("model"),
                "provider": demo.record.get("provider"),
                "accepted": demo.record.get("accepted") is True,
                "skills": demo.record.get("selected_skills", []),
                "elapsedSeconds": demo.record.get("elapsedSeconds", 0),
                "inputTokens": usage.get("input_tokens", 0),
                "cachedInputTokens": usage.get("cached_input_tokens", 0),
                "outputTokens": usage.get("output_tokens", 0),
                "video": f"assets/{directory_name}/replay.mp4",
                "poster": f"assets/{directory_name}/poster.png",
                "cast": f"assets/{directory_name}/replay.cast",
                "evidence": {
                    name: f"assets/{directory_name}/{name}" for name in evidence
                },
                "sha256": {
                    "video": _sha256(video),
                    "poster": _sha256(poster),
                    "cast": _sha256(cast),
                    **{f"evidence/{name}": digest for name, digest in evidence.items()},
                },
                **timing,
            }
        )
    manifest = {
        "schemaVersion": 1,
        "experimentId": selected,
        "status": "edited evidence replays from completed runs",
        "claimBoundary": (
            "These videos preserve run evidence with edited timing. They do not show fresh "
            "live execution and do not establish causal improvement from the distilled skill."
        ),
        "recordings": entries,
    }
    manifest_path = assets / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def serve_demo_site(root: Path, *, port: int = 8765, open_browser: bool = True) -> None:
    site = root / "demo-site"
    if not (site / "index.html").is_file() or not (site / "assets" / "manifest.json").is_file():
        raise FileNotFoundError("demo site is missing; run `taxi-demo record-demos` first")
    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Taxi demo player: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
