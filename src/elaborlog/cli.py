import argparse
import csv
import json
import math
import sys
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple, Union

from .config import ScoringConfig
from .parsers import parse_line
from .score import InfoModel
from .tail import tail
from .quantiles import P2Quantile
from .service import build_app


_TAIL_DEFAULTS = {"quantile": 0.992, "window": 1000, "burn_in": 500}
TAIL_PROFILES: Dict[str, Dict[str, Union[int, float]]] = {
    "web": {"quantile": 0.992, "window": 1200, "burn_in": 400},
    "k8s": {"quantile": 0.995, "window": 900, "burn_in": 350},
    "auth": {"quantile": 0.994, "window": 1100, "burn_in": 500},
}
MODE_PRESETS: Dict[str, float] = {
    "triage": 0.992,
    "page": 0.995,
}
MIN_WINDOW = 10


def build_model(args: argparse.Namespace) -> InfoModel:
    cfg = ScoringConfig()
    cfg.include_bigrams = bool(getattr(args, "with_bigrams", False))
    if getattr(args, "decay", None) is not None:
        try:
            cfg.decay = float(args.decay)
        except ValueError:
            print("[elaborlog] invalid --decay; using default", file=sys.stderr)
    if getattr(args, "decay_every", None) is not None:
        try:
            cfg.decay_every = int(args.decay_every)
        except ValueError:
            print("[elaborlog] invalid --decay-every; using default", file=sys.stderr)
    # Optional weight overrides
    for attr, flag in [("w_token", "w_token"), ("w_template", "w_template"), ("w_level", "w_level")]:
        if getattr(args, flag, None) is not None:
            try:
                setattr(cfg, attr, float(getattr(args, flag)))
            except ValueError:
                print(f"[elaborlog] invalid value for --{flag}; using default.", file=sys.stderr)
    state_in = getattr(args, "state_in", None)
    if state_in:
        try:
            return InfoModel.load(state_in, cfg_override=cfg)
        except FileNotFoundError:
            print(f"[elaborlog] state file '{state_in}' not found; starting fresh.", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - surface error then continue fresh
            print(f"[elaborlog] failed to load state '{state_in}': {exc}", file=sys.stderr)
    return InfoModel(cfg)


def maybe_save_model(model: InfoModel, path: Optional[str]) -> None:
    if path:
        saved_path = model.save(path)
        print(f"Wrote state snapshot to {saved_path}")


def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover - integration feature
    try:
        import uvicorn  # type: ignore
    except Exception:  # noqa: BLE001
        print("'serve' requires uvicorn. Install with `pip install elaborlog[server]`.", file=sys.stderr)
        return 2

    model = build_model(args)
    app = build_app(model)

    # Periodic snapshot thread
    stop_flag = False

    def _snapshot_loop():
        while not stop_flag:
            time.sleep(max(5, args.interval))
            try:
                maybe_save_model(model, getattr(args, "state_out", None))
            except Exception as snap_exc:  # noqa: BLE001
                print(f"[elaborlog] snapshot failed: {snap_exc}", file=sys.stderr)

    import time
    import threading

    t = None
    if getattr(args, "state_out", None):
        t = threading.Thread(target=_snapshot_loop, daemon=True)
        t.start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        # Final snapshot
        if getattr(args, "state_out", None):
            maybe_save_model(model, getattr(args, "state_out", None))
    return 0


def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def resolve_tail_settings(args: argparse.Namespace) -> Tuple[float, int, int]:
    settings: Dict[str, Union[int, float]] = dict(_TAIL_DEFAULTS)
    if getattr(args, "profile", None):
        settings.update(TAIL_PROFILES.get(args.profile, {}))
    if getattr(args, "mode", None):
        settings["quantile"] = MODE_PRESETS[args.mode]

    quantile = args.quantile if args.quantile is not None else settings["quantile"]
    window = args.window if args.window is not None else settings["window"]
    burn_in = args.burn_in if args.burn_in is not None else settings["burn_in"]

    quantile = float(min(max(0.5, quantile), 0.9995))
    window = max(MIN_WINDOW, int(window))
    burn_in = max(0, int(burn_in))
    return quantile, window, burn_in


def compute_quantile(values: Deque[float], q: float) -> float:
    data = sorted(values)
    if not data:
        return math.inf
    if len(data) == 1:
        return data[0]
    position = q * (len(data) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    fraction = position - lower
    return data[lower] + (data[upper] - data[lower]) * fraction


def cmd_rank(args: argparse.Namespace) -> int:
    model = build_model(args)
    rows = []
    json_rows = [] if getattr(args, "json", None) else None
    with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            ts, level, msg = parse_line(line)
            model.observe(msg)
            sc = model.score(msg, level=level)
            if json_rows is not None:
                token_details = model.token_surprisals(sc.toks)[:10]
                json_rows.append(
                    {
                        "timestamp": ts,
                        "level": level,
                        "novelty": sc.novelty,
                        "score": sc.score,
                        "token_info_bits": sc.token_info,
                        "template_info_bits": sc.template_info,
                        "level_bonus": sc.level_bonus,
                        "template": sc.tpl,
                        "token_contributors": [
                            {"token": t, "prob": p, "bits": bits, "freq": freq}
                            for (t, p, bits, freq) in token_details
                        ],
                        "line": msg.strip(),
                    }
                )
            rows.append(
                (
                    ts,
                    level,
                    sc.novelty,
                    sc.score,
                    sc.token_info,
                    sc.template_info,
                    sc.tpl,
                    msg.strip(),
                )
            )
    rows.sort(key=lambda row: -row[2])

    if json_rows is not None and args.json:
        with open(args.json, "w", encoding="utf-8") as jf:
            json.dump(json_rows, jf, indent=2)
        print(f"Wrote JSON {args.json} ({len(json_rows)} objects)")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as writer:
            writer_obj = csv.writer(writer)
            writer_obj.writerow(
                [
                    "timestamp",
                    "level",
                    "novelty",
                    "score",
                    "token_info",
                    "template_info",
                    "template",
                    "line",
                ]
            )
            writer_obj.writerows(rows)
        print(f"Wrote {args.out} ({len(rows)} lines)")
    else:
        top = rows[: args.top]
        for row in top:
            print(f"{row[0] or '-'} [{row[1] or '-'}] novelty={row[2]:.3f} score={row[3]:.3f}  {row[7]}")
    maybe_save_model(model, getattr(args, "state_out", None))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    """Backward-compatible alias for cmd_rank."""
    return cmd_rank(args)


def cmd_tail(args: argparse.Namespace) -> int:
    model = build_model(args)
    cfg = model.cfg
    recent: Deque[Tuple[List[str], str]] = deque([], maxlen=cfg.nn_window)
    template_last_seen: Dict[str, int] = {}
    quantile, window, burn_in = resolve_tail_settings(args)
    # If user explicitly supplied --window we honor fixed-window quantile; otherwise use streaming P².
    use_p2 = getattr(args, "window", None) is None
    scores = deque([], maxlen=window)
    p2: Optional[P2Quantile] = None
    if use_p2:
        p2 = P2Quantile(q=quantile)
    line_idx = 0
    manual_threshold = args.threshold
    jsonl_handle = None
    if getattr(args, "jsonl", None):
        try:
            jsonl_handle = open(args.jsonl, "a", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"[elaborlog] could not open JSONL file {args.jsonl}: {exc}", file=sys.stderr)
            jsonl_handle = None

    try:
        for line in tail(args.file, follow=True):
            line_idx += 1
            ts, level, msg = parse_line(line)
            model.observe(msg)
            sc = model.score(msg, level=level)
            scores.append(sc.novelty)

            threshold_value: Optional[float] = None
            should_alert = False

            if manual_threshold is not None:
                threshold_value = manual_threshold
                should_alert = sc.score >= manual_threshold
            else:
                if use_p2:
                    # Update streaming estimator regardless; start evaluating after burn-in + a few samples
                    if p2 is not None:
                        p2.update(sc.novelty)
                        if line_idx > burn_in and line_idx >= 10:
                            threshold_value = p2.value()
                            should_alert = sc.novelty >= threshold_value
                else:
                    if line_idx > burn_in and len(scores) >= min(window, 30):
                        threshold_value = compute_quantile(scores, quantile)
                        should_alert = sc.novelty >= threshold_value

            last_seen = template_last_seen.get(sc.tpl)
            template_last_seen[sc.tpl] = line_idx
            if should_alert and args.dedupe_template and last_seen is not None and line_idx - last_seen < window:
                should_alert = False

            if should_alert:
                nns: List[Tuple[float, str]] = []
                for toks_prev, line_prev in recent:
                    nns.append((jaccard(sc.toks, toks_prev), line_prev))
                nns.sort(key=lambda item: -item[0])
                nn_text = ""
                for sim, prev_line in nns[: cfg.nn_topk]:
                    nn_text += f"\n   ↳ neighbor (sim={sim:.2f}): {prev_line.strip()}"

                header = f"{ts or '-'} [{level or '-'}] novelty={sc.novelty:.3f}"
                if manual_threshold is None and threshold_value is not None:
                    mode_tag = "p2" if use_p2 else f"w{len(scores)}"
                    header += f" (q{quantile:.3f}@{mode_tag}≥{threshold_value:.3f})"
                header += f" score={sc.score:.3f}"
                if manual_threshold is not None and threshold_value is not None:
                    header += f" (≥{threshold_value:.3f})"
                header += f"  {msg.strip()}"

                tpl_prob = model.template_probability(sc.tpl)
                detail = f"   template={sc.tpl} p≈{tpl_prob:.5f}"
                print(f"{header}{nn_text}\n{detail}")
                if jsonl_handle is not None:
                    token_details = model.token_surprisals(sc.toks)[:10]
                    alert_obj = {
                        "timestamp": ts,
                        "level": level,
                        "novelty": sc.novelty,
                        "score": sc.score,
                        "token_info_bits": sc.token_info,
                        "template_info_bits": sc.template_info,
                        "level_bonus": sc.level_bonus,
                        "template": sc.tpl,
                        "template_probability": tpl_prob,
                        "tokens": sc.toks,
                        "token_contributors": [
                            {"token": t, "prob": p, "bits": bits, "freq": freq}
                            for (t, p, bits, freq) in token_details
                        ],
                        "line": msg.strip(),
                        "threshold": threshold_value,
                        "quantile": quantile if manual_threshold is None else None,
                        "neighbors": [
                            {"similarity": sim, "line": prev.strip()} for sim, prev in nns[: cfg.nn_topk]
                        ],
                    }
                    try:
                        jsonl_handle.write(json.dumps(alert_obj) + "\n")
                        jsonl_handle.flush()
                    except Exception as wexc:  # noqa: BLE001
                        print(f"[elaborlog] failed to write JSONL alert: {wexc}", file=sys.stderr)

            recent.append((sc.toks, line))
    except KeyboardInterrupt:
        print("[elaborlog] stopping tail (Ctrl-C)", file=sys.stderr)
    finally:
        if jsonl_handle is not None:
            try:
                jsonl_handle.close()
            except Exception:  # noqa: BLE001
                pass
        maybe_save_model(model, getattr(args, "state_out", None))
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    model = build_model(args)
    # Prime the model with the file to get reasonable frequencies
    with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            _, _, msg = parse_line(line)
            model.observe(msg)

    # Explain one line
    _, level, msg = parse_line(args.line)
    sc = model.score(msg, level=level)
    if getattr(args, "json", None):
        token_details = model.token_surprisals(sc.toks)[: args.top_tokens]
        obj = {
            "novelty": sc.novelty,
            "score": sc.score,
            "token_info_bits": sc.token_info,
            "template_info_bits": sc.template_info,
            "level_bonus": sc.level_bonus,
            "weights": {
                "w_token": model.cfg.w_token,
                "w_template": model.cfg.w_template,
                "w_level": model.cfg.w_level,
            },
            "template": sc.tpl,
            "template_probability": model.template_probability(sc.tpl),
            "token_contributors": [
                {"token": t, "prob": p, "bits": bits, "freq": freq}
                for (t, p, bits, freq) in token_details
            ],
            "line": msg,
        }
        with open(args.json, "w", encoding="utf-8") as jf:
            json.dump(obj, jf, indent=2)
        print(f"Wrote JSON explanation to {args.json}")
    else:
        print(
            "Line: {0}\nScore: {1:.3f} (novelty={2:.3f}, token_info={3:.3f}, template_info={4:.3f}, level_bonus={5:.2f})\nWeights: w_token={6} w_template={7} w_level={8}".format(
                msg,
                sc.score,
                sc.novelty,
                sc.token_info,
                sc.template_info,
                sc.level_bonus,
                model.cfg.w_token,
                model.cfg.w_template,
                model.cfg.w_level,
            )
        )

        token_details = model.token_surprisals(sc.toks)
        top = token_details[: args.top_tokens]
        if top:
            print("Top tokens by surprisal:")
            for tok, prob, bits, freq in top:
                print(f"   {tok:<20} bits={bits:.2f} freq={freq} p≈{prob:.5f}")
        else:
            print("No tokens to report (line was empty after masking).")
        tpl_prob = model.template_probability(sc.tpl)
        print(f"Template: {sc.tpl} (p≈{tpl_prob:.5f})")
    maybe_save_model(model, getattr(args, "state_out", None))
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    from collections import Counter

    from .templates import to_template

    counter = Counter()
    with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            _, _, msg = parse_line(line)
            counter[to_template(msg)] += 1
    for tpl, count in counter.most_common(args.top):
        print(f"{count:6d}  {tpl}")
    return 0


def cmd_demo(_: argparse.Namespace) -> int:
    print("Running demo on examples/app.log ...")
    ns = argparse.Namespace(file="examples/app.log", out="reports_demo.csv", top=20)
    return cmd_score(ns)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elaborlog", description="Surface rare, high-signal log lines.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    score_parser = sub.add_parser("score", help="(Legacy) score and rank a log file")
    score_parser.add_argument("file")
    score_parser.add_argument("--out", help="Write CSV if set")
    score_parser.add_argument("--top", type=int, default=20)
    score_parser.add_argument("--with-bigrams", action="store_true", help="Include token bigrams while scoring")
    score_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    score_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    score_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    score_parser.add_argument("--json", help="Write full JSON results (array) to this path")
    score_parser.add_argument("--state-in", help="Load model state from this JSON file before scoring")
    score_parser.add_argument("--state-out", help="Persist the updated model state to this JSON file")
    score_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    score_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    score_parser.set_defaults(func=cmd_score)

    rank_parser = sub.add_parser("rank", help="Rank a log file by novelty")
    rank_parser.add_argument("file")
    rank_parser.add_argument("--out", help="Write CSV if set")
    rank_parser.add_argument("--top", type=int, default=20)
    rank_parser.add_argument("--with-bigrams", action="store_true", help="Include token bigrams while scoring")
    rank_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    rank_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    rank_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    rank_parser.add_argument("--json", help="Write full JSON results (array) to this path")
    rank_parser.add_argument("--state-in", help="Load model state from this JSON file before scoring")
    rank_parser.add_argument("--state-out", help="Persist the updated model state to this JSON file")
    rank_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    rank_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    rank_parser.set_defaults(func=cmd_rank)

    tail_parser = sub.add_parser("tail", help="Tail a log and print only high-novelty lines with context")
    tail_parser.add_argument("file")
    tail_parser.add_argument("--quantile", type=float, help="Override the rolling novelty quantile [0,1)")
    tail_parser.add_argument("--window", type=int, help="Rolling window size (number of lines)")
    tail_parser.add_argument("--burn-in", type=int, help="Lines to observe before emitting alerts")
    tail_parser.add_argument(
        "--profile",
        choices=sorted(TAIL_PROFILES.keys()),
        help="Apply tuned defaults for a common log profile",
    )
    tail_parser.add_argument(
        "--mode",
        choices=sorted(MODE_PRESETS.keys()),
        help="Quick preset for triage (0.992) or page (0.995)",
    )
    tail_parser.add_argument(
        "--threshold",
        type=float,
        help="Bypass quantiles and alert when raw score exceeds this threshold",
    )
    tail_parser.add_argument(
        "--with-bigrams",
        action="store_true",
        help="Augment tokens with bigrams (useful for very stable templates)",
    )
    tail_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    tail_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    tail_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    tail_parser.add_argument(
        "--dedupe-template",
        action="store_true",
        help="Skip alerts when the same template fired recently",
    )
    tail_parser.add_argument("--state-in", help="Resume model state from this JSON snapshot")
    tail_parser.add_argument("--state-out", help="Write model state to this JSON snapshot on exit")
    tail_parser.add_argument("--jsonl", help="Write JSON lines for each emitted alert to this file")
    tail_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    tail_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    tail_parser.set_defaults(func=cmd_tail)

    explain_parser = sub.add_parser("explain", help="Explain why a line scored high")
    explain_parser.add_argument("file", help="Use this file to prime frequencies")
    explain_parser.add_argument("--line", required=True, help="A single log line to explain (quote it)")
    explain_parser.add_argument(
        "--with-bigrams",
        action="store_true",
        help="Include bigrams when assessing token contributions",
    )
    explain_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    explain_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    explain_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    explain_parser.add_argument(
        "--top-tokens",
        type=int,
        default=10,
        help="How many tokens to list in the explanation",
    )
    explain_parser.add_argument("--state-in", help="Load model state before priming with the file")
    explain_parser.add_argument("--state-out", help="Persist model state after priming")
    explain_parser.add_argument("--json", help="Write JSON explanation to this path")
    explain_parser.set_defaults(func=cmd_explain)

    cluster_parser = sub.add_parser("cluster", help="Show most common templates")
    cluster_parser.add_argument("file")
    cluster_parser.add_argument("--top", type=int, default=30)
    cluster_parser.set_defaults(func=cmd_cluster)

    demo_parser = sub.add_parser("demo", help="Run the examples/app.log demo")
    demo_parser.set_defaults(func=cmd_demo)

    serve_parser = sub.add_parser("serve", help="Run HTTP service (requires elaborlog[server])")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--state-in", help="Load model snapshot at startup")
    serve_parser.add_argument("--state-out", help="Persist snapshot periodically and on shutdown")
    serve_parser.add_argument("--interval", type=int, default=60, help="Snapshot interval seconds")
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
