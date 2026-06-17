"""CLI entry: ``python -m resume_agent --resume <path> --jd <path> [--out <path>]``."""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from resume_agent import llm
from resume_agent import resume as resume_mod
from resume_agent import tailor


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"file not found: {path}")


def main(argv: list[str] | None = None) -> int:
    defaults = llm.LLMConfig()
    p = argparse.ArgumentParser(
        prog="resume_agent",
        description="Tailor a Markdown resume to a job description using a local LLM (Ollama by default).",
    )
    p.add_argument("--resume", required=True, type=Path, help="path to the base resume (Markdown)")
    p.add_argument("--jd", required=True, type=Path, help="path to the job description (plain text)")
    p.add_argument("--out", type=Path, help="write tailored resume here (default: stdout)")
    p.add_argument("--model", default=None, help=f"local LLM model (default: {defaults.model})")
    p.add_argument("--host", default=None, help=f"Ollama base URL (default: {defaults.base_url})")
    p.add_argument("--temperature", type=float, default=None, help=f"sampling temperature (default: {defaults.temperature})")
    p.add_argument("--no-diff", action="store_true", help="skip the diff preview")
    p.add_argument("--yes", action="store_true", help="overwrite --out without prompting")
    args = p.parse_args(argv)

    cfg = llm.LLMConfig()
    if args.model:
        cfg.model = args.model
    if args.host:
        cfg.base_url = args.host
    if args.temperature is not None:
        cfg.temperature = args.temperature

    original = _read(args.resume)
    jd_text = _read(args.jd)
    parsed = resume_mod.parse(original)

    print(f"using local model: {cfg.model} @ {cfg.base_url}", file=sys.stderr)

    def _progress(title: str) -> None:
        print(f"  tailoring: {title} ...", file=sys.stderr, flush=True)

    try:
        report = tailor.tailor_resume(parsed, jd_text, cfg=cfg, on_section=_progress)
    except llm.LLMError as e:
        sys.exit(str(e))

    tailored = parsed.render()

    if not args.no_diff:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            tailored.splitlines(keepends=True),
            fromfile=str(args.resume),
            tofile="tailored",
        )
        sys.stderr.writelines(diff)
        sys.stderr.write("\n")

    print(f"[changed]  {', '.join(report.changed) or '(none)'}", file=sys.stderr)
    print(f"[skipped]  {', '.join(report.skipped) or '(none)'}", file=sys.stderr)
    if report.rejected:
        print("[rejected]", file=sys.stderr)
        for title, reason in report.rejected:
            print(f"  - {title}: {reason}", file=sys.stderr)

    if args.out:
        if args.out.exists() and not args.yes:
            try:
                ans = input(f"overwrite {args.out}? [y/N] ").strip().lower()
            except EOFError:
                ans = ""
            if ans not in {"y", "yes"}:
                print("aborted.", file=sys.stderr)
                return 1
        args.out.write_text(tailored, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(tailored)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
