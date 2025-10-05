import argparse
import csv
import json
import math
import sys
import threading
import time
import os
import signal
from collections import deque, Counter as _Counter
from typing import Deque, Dict, List, Optional, Tuple, Union, Any, TYPE_CHECKING

from .config import ScoringConfig
from . import __version__
from .parsers import parse_line
from .score import InfoModel
from .templates import set_custom_replacers
import re
from .tail import tail
from .sinks import JsonlSink, AlertSink
from .quantiles import P2Quantile
from .service import build_app

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rich.console import Console as _Console
    from rich.text import Text as _Text
else:  # runtime optional import
    try:  # noqa: SIM105
        from rich.console import Console as _Console  # type: ignore
        from rich.text import Text as _Text  # type: ignore
    except Exception:  # noqa: BLE001
        _Console = None  # type: ignore
        _Text = None  # type: ignore

ConsoleType = Optional["_Console"]
TextType = Optional["_Text"]


def _print_guardrail_summary(model: InfoModel, force: bool = False) -> None:
    """Emit guardrail counters summary to stderr.

    If force=True, always emit a summary line (even if all counters zero). This
    ensures consistent test expectations for abrupt termination (SIGTERM/Ctrl-C).
    """
    try:
        emit = force or any(
            [
                getattr(model, "lines_truncated", 0),
                getattr(model, "lines_token_truncated", 0),
                getattr(model, "lines_dropped", 0),
            ]
        )
        if emit:
            print(
                f"[elaborlog] summary: truncated_lines={getattr(model, 'lines_truncated', 0)} "
                f"token_truncated_lines={getattr(model, 'lines_token_truncated', 0)} dropped_lines={getattr(model, 'lines_dropped', 0)} "
                f"vocab_tokens={len(getattr(model, 'token_counts', []))} vocab_templates={len(getattr(model, 'template_counts', []))}",
                file=sys.stderr,
                flush=True,
            )
    except Exception:  # noqa: BLE001 - never let summary crash the program
        pass


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
    # Configure custom masks before creating model (affects to_template)
    masks = getattr(args, "mask", None) or []
    if masks:
        compiled = []
        for spec in masks:
            if "=" not in spec:
                print(f"[elaborlog] ignoring malformed --mask '{spec}' (expected pattern=replacement)", file=sys.stderr)
                continue
            pattern_s, repl = spec.split("=", 1)
            try:
                compiled.append((re.compile(pattern_s), repl))
            except re.error as exc:  # noqa: BLE001
                print(f"[elaborlog] invalid regex in --mask '{pattern_s}': {exc}", file=sys.stderr)
        order = getattr(args, "mask_order", "before")
        set_custom_replacers(compiled, order=order)
    cfg = ScoringConfig()
    cfg.include_bigrams = bool(getattr(args, "with_bigrams", False))
    cfg.split_camel = bool(getattr(args, "split_camel", False))
    cfg.split_dot = bool(getattr(args, "split_dot", False))
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
        import uvicorn
    except Exception:  # noqa: BLE001
        print("'serve' requires uvicorn. Install with `pip install elaborlog[server]`.", file=sys.stderr)
        return 2

    model = build_model(args)
    app = build_app(model)

    # Periodic snapshot thread
    stop_flag = False

    def _snapshot_loop() -> None:
        while not stop_flag:
            time.sleep(max(5, args.interval))
            try:
                maybe_save_model(model, getattr(args, "state_out", None))
            except Exception as snap_exc:  # noqa: BLE001
                print(f"[elaborlog] snapshot failed: {snap_exc}", file=sys.stderr)

    import time
    import threading

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


def _maybe_console(args: argparse.Namespace) -> ConsoleType:
    if getattr(args, "no_color", False):
        return None
    if _Console is None:
        return None
    # force_terminal ensures ANSI codes even when output is being captured (for tests)
    return _Console(color_system="truecolor", stderr=False, force_terminal=True)


def _color_scale(novelty: float) -> str:
    # Map novelty [0,1] roughly to a color gradient (green -> yellow -> red)
    # We'll interpolate manually via thresholds for simplicity.
    if novelty < 0.6:
        return "green"
    if novelty < 0.75:
        return "yellow"
    if novelty < 0.9:
        return "orange1"
    return "red"


def cmd_rank(args: argparse.Namespace) -> int:
    model = build_model(args)
    rows: List[Tuple[Optional[str], Optional[str], float, float, float, float, str, str]] = []
    json_rows: Optional[List[Dict[str, Any]]] = [] if getattr(args, "json", None) else None
    console = _maybe_console(args)
    with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            ts, level, msg = parse_line(line)
            model.observe(msg)
            sc = model.score(msg, level=level)
            if json_rows is not None:
                raw_token_details = model.token_surprisals(sc.toks)
                token_details = raw_token_details if getattr(args, "all_token_contributors", False) else raw_token_details[:10]
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
            if console is not None:
                color = _color_scale(row[2])
                text = _Text()
                text.append(f"{row[0] or '-'} ", style="dim")
                text.append(f"[{row[1] or '-'}] ", style="cyan")
                text.append(f"novelty={row[2]:.3f} ", style=color)
                text.append(f"score={row[3]:.3f}  ", style="magenta")
                text.append(row[7], style="white")
                console.print(text)
            else:
                print(f"{row[0] or '-'} [{row[1] or '-'}] novelty={row[2]:.3f} score={row[3]:.3f}  {row[7]}")
    maybe_save_model(model, getattr(args, "state_out", None))
    _print_guardrail_summary(model, force=True)
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
    multi_qs: Optional[List[float]] = getattr(args, "quantiles", None)
    if multi_qs:
        # Sanitize and sort unique
        qs_clean = sorted({min(max(0.5, float(q)), 0.9995) for q in multi_qs})
    else:
        qs_clean = []
    use_p2 = getattr(args, "window", None) is None
    scores: Deque[float] = deque([], maxlen=window)
    p2: Optional[P2Quantile] = None
    p2_multi: List[P2Quantile] = []
    if use_p2:
        if qs_clean:
            p2_multi = [P2Quantile(q=q) for q in qs_clean]
        else:
            p2 = P2Quantile(q=quantile)
    line_idx = 0
    manual_threshold = args.threshold
    # Build sinks (currently only JSONL sink optional)
    sink: Optional[AlertSink] = None
    if getattr(args, "jsonl", None):
        try:
            sink = JsonlSink(args.jsonl, all_token_contributors=getattr(args, "all_token_contributors", False))
        except Exception as exc:  # noqa: BLE001
            print(f"[elaborlog] could not open JSONL file {args.jsonl}: {exc}", file=sys.stderr)
            sink = None

    console = _maybe_console(args)

    # Periodic snapshot thread (optional) - mutation confined to model.save() which
    # only reads counters & maps; InfoModel methods themselves handle internal state.
    stop_event: Optional[threading.Event] = None
    snapshot_thread: Optional[threading.Thread] = None
    interval = getattr(args, "snapshot_interval", None)
    state_out = getattr(args, "state_out", None)
    if interval and state_out:
        try:
            interval = float(interval)
            if interval > 0:
                stop_event = threading.Event()
                def _snap_loop() -> None:
                    while not stop_event.is_set():
                        time.sleep(interval)
                        if stop_event.is_set():
                            break
                        try:
                            maybe_save_model(model, state_out)
                        except Exception as snap_exc:  # noqa: BLE001
                            print(f"[elaborlog] periodic snapshot failed: {snap_exc}", file=sys.stderr)
                snapshot_thread = threading.Thread(target=_snap_loop, daemon=True)
                snapshot_thread.start()
        except ValueError:
            print("[elaborlog] invalid --snapshot-interval; ignoring", file=sys.stderr)

    alerts_emitted = 0
    # Initialize last_stats_time such that we can emit a stats line quickly on startup
    # (helps tests that run briefly) and still respect a positive interval.
    last_stats_time = time.time()
    stats_interval = getattr(args, "stats_interval", None)
    # Install SIGTERM handler so external terminate() triggers cleanup & summary (Linux CI)
    _old_sigterm = None
    def _sigterm_handler(signum, frame):  # pragma: no cover - exercised indirectly
        raise KeyboardInterrupt
    try:
        _old_sigterm = signal.signal(signal.SIGTERM, _sigterm_handler)
    except Exception:  # pragma: no cover - signal may not be available
        _old_sigterm = None

    try:
        follow_flag = not getattr(args, "no_follow", False)
        start_at_end = manual_threshold is None  # if manual threshold set, process existing file contents too
        for line in tail(args.file, follow=follow_flag, start_at_end=start_at_end):
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
                    # Update single or multi P2 estimators first
                    if p2_multi:
                        for est in p2_multi:
                            est.update(sc.novelty)
                        if line_idx > burn_in and line_idx >= 10:
                            # Use the maximum required threshold among all quantiles (strictest alerting)
                            thresholds = [est.value() for est in p2_multi]
                            # Choose threshold associated with highest q (last estimator) for labeling
                            threshold_value = thresholds[-1]
                            should_alert = sc.novelty >= threshold_value
                    elif p2 is not None:
                        p2.update(sc.novelty)
                        if line_idx > burn_in and line_idx >= 10:
                            threshold_value = p2.value()
                            should_alert = sc.novelty >= threshold_value
                else:
                    # Rolling window mode. Support multi-quantiles similarly to P2 multi.
                    if line_idx > burn_in and len(scores) >= min(window, 30):
                        if qs_clean:
                            thresholds = [compute_quantile(scores, qv) for qv in qs_clean]
                            threshold_value = thresholds[-1]  # highest quantile threshold
                            should_alert = sc.novelty >= threshold_value
                        else:
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
                    nn_text += f"\n   -> neighbor (sim={sim:.2f}): {prev_line.strip()}"

                header = f"{ts or '-'} [{level or '-'}] novelty={sc.novelty:.3f}"
                if manual_threshold is None and threshold_value is not None:
                    if use_p2:
                        if p2_multi:
                            # Report all quantile estimates compactly
                            est_parts = []
                            for est in p2_multi:
                                est_parts.append(f"q{est.q:.3f}={est.value():.3f}")
                            header += " (" + ",".join(est_parts) + f"; using>={threshold_value:.3f})"
                        else:
                            header += f" (q{quantile:.3f}@p2>={threshold_value:.3f})"
                    else:
                        header += f" (q{quantile:.3f}@w{len(scores)}>={threshold_value:.3f})"
                header += f" score={sc.score:.3f}"
                if manual_threshold is not None and threshold_value is not None:
                    header += f" (>={threshold_value:.3f})"
                header += f"  {msg.strip()}"

                tpl_prob = model.template_probability(sc.tpl)
                # Use ASCII '~' instead of Unicode '≈' for wider console compatibility
                detail = f"   template={sc.tpl} p~{tpl_prob:.5f}"
                if console is not None:
                    header_text = _Text()
                    header_text.append(f"{ts or '-'} ", style="dim")
                    header_text.append(f"[{level or '-'}] ", style="cyan")
                    header_text.append(f"novelty={sc.novelty:.3f} ", style=_color_scale(sc.novelty))
                    if manual_threshold is None and threshold_value is not None:
                        if use_p2:
                            if p2_multi:
                                est_parts = []
                                for est in p2_multi:
                                    est_parts.append(f"q{est.q:.3f}={est.value():.3f}")
                                header_text.append("(" + ",".join(est_parts) + f"; using>={threshold_value:.3f}) ", style="dim")
                            else:
                                header_text.append(f"(q{quantile:.3f}@p2>={threshold_value:.3f}) ", style="dim")
                        else:
                            if qs_clean:
                                header_text.append(f"(q{qs_clean[-1]:.3f}@w{len(scores)}>={threshold_value:.3f}) ", style="dim")
                            else:
                                header_text.append(f"(q{quantile:.3f}@w{len(scores)}>={threshold_value:.3f}) ", style="dim")
                    header_text.append(f"score={sc.score:.3f} ", style="magenta")
                    header_text.append(msg.strip(), style="white")
                    console.print(header_text)
                    if nn_text:
                        console.print(_Text(nn_text, style="dim"))
                        console.print(_Text(detail, style="dim"))
                else:
                    print(f"{header}{nn_text}\n{detail}")
                if sink is not None:
                    raw_token_details = model.token_surprisals(sc.toks)
                    token_details = raw_token_details if getattr(args, "all_token_contributors", False) else raw_token_details[:10]
                    quantile_estimates: Optional[Dict[str, float]] = None
                    if getattr(args, "emit_intermediate", False) and (p2_multi or qs_clean):
                        if p2_multi:
                            quantile_estimates = {f"{est.q:.3f}": est.value() for est in p2_multi}
                        elif qs_clean:
                            quantile_estimates = {f"{qv:.3f}": compute_quantile(scores, qv) for qv in qs_clean}
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
                        "quantile": (
                            (p2_multi[-1].q if p2_multi else (qs_clean[-1] if (qs_clean and not use_p2) else quantile))
                            if manual_threshold is None
                            else None
                        ),
                        "quantile_estimates": quantile_estimates,
                        "neighbors": [
                            {"similarity": sim, "line": prev.strip()} for sim, prev in nns[: cfg.nn_topk]
                        ],
                    }
                    try:
                        sink.emit(alert_obj)
                    except Exception as wexc:  # noqa: BLE001
                        print(f"[elaborlog] failed to write alert via sink: {wexc}", file=sys.stderr)
                alerts_emitted += 1

            # Periodic stats: observed alert rate vs target quantile
            if stats_interval and stats_interval > 0:
                now = time.time()
                if now - last_stats_time >= stats_interval:
                    # Always emit stats line even if zero lines processed (lines=0 alerts=0)
                    rate = (alerts_emitted / line_idx) if line_idx > 0 else 0.0
                    target_q = (
                        (p2_multi[-1].q if p2_multi else (qs_clean[-1] if (qs_clean and not use_p2) else quantile))
                        if manual_threshold is None else 0.0
                    )
                    print(
                        f"[elaborlog] stats: lines={line_idx} alerts={alerts_emitted} observed_rate={rate:.4f} target_quantile={target_q:.4f}",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_stats_time = now

            recent.append((sc.toks, line))
    except KeyboardInterrupt:
        print("[elaborlog] stopping tail (Ctrl-C)", file=sys.stderr)
    finally:
        # Restore prior handler
        if _old_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, _old_sigterm)
            except Exception:  # pragma: no cover
                pass
        if stop_event is not None:
            stop_event.set()
        if snapshot_thread is not None:
            snapshot_thread.join(timeout=0.1)
        if sink is not None:
            try:
                sink.close()
            except Exception:
                pass
        # Final stats emission (even if interval not elapsed) when enabled
        if getattr(args, "stats_interval", None):
            # Emit final stats line even if zero lines processed
            target_q_final = (
                (p2_multi[-1].q if p2_multi else (qs_clean[-1] if (qs_clean and not use_p2) else quantile))
                if manual_threshold is None else 0.0
            )
            rate_final = (alerts_emitted / line_idx) if line_idx > 0 else 0.0
            print(
                f"[elaborlog] stats: lines={line_idx} alerts={alerts_emitted} observed_rate={rate_final:.4f} target_quantile={target_q_final:.4f}",
                file=sys.stderr,
                flush=True,
            )
        maybe_save_model(model, getattr(args, "state_out", None))
    _print_guardrail_summary(model, force=True)
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
        full_token_details = model.token_surprisals(sc.toks)
        token_details = (
            full_token_details
            if getattr(args, "all_token_contributors", False)
            else full_token_details[: args.top_tokens]
        )
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
                print(f"   {tok:<20} bits={bits:.2f} freq={freq} p~{prob:.5f}")
        else:
            print("No tokens to report (line was empty after masking).")
        tpl_prob = model.template_probability(sc.tpl)
        print(f"Template: {sc.tpl} (p~{tpl_prob:.5f})")
    maybe_save_model(model, getattr(args, "state_out", None))
    _print_guardrail_summary(model, force=True)
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    from .templates import to_template

    counter: _Counter[str] = _Counter()
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


def cmd_summarize(args: argparse.Namespace) -> int:
    import statistics
    # Read alerts JSONL
    path = args.file
    if not os.path.exists(path):
        print(f"[elaborlog] alerts JSONL not found: {path}", file=sys.stderr)
        return 2
    lines: List[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            lines.append(line)
    if not lines:
        print("[elaborlog] no alert lines found", file=sys.stderr)
        return 0
    alerts: List[Dict[str, Any]] = []
    for line_str in lines:
        try:
            alerts.append(json.loads(line_str))
        except Exception as exc:  # noqa: BLE001
            print(f"[elaborlog] skipped malformed JSON line: {exc}", file=sys.stderr)
    n = len(alerts)
    novelties = [a.get("novelty", 0.0) for a in alerts]
    scores = [a.get("score", 0.0) for a in alerts]
    thresholds = [a.get("threshold") for a in alerts if a.get("threshold") is not None]
    quantile = None
    for a in alerts:
        if a.get("quantile") is not None:
            quantile = a.get("quantile")
            break
    template_counter: _Counter[str] = _Counter()
    token_bits: _Counter[str] = _Counter()
    for a in alerts:
        tpl = a.get("template")
        if tpl:
            template_counter[tpl] += 1
        # token_contributors may contain bits values
        for tc in a.get("token_contributors", []):
            tok = tc.get("token")
            bits = tc.get("bits")
            if isinstance(tok, str) and isinstance(bits, (int, float)):
                token_bits[tok] += bits
    summary: Dict[str, Any] = {
        "alerts": n,
        "quantile": quantile,
        "novelty_min": min(novelties),
        "novelty_max": max(novelties),
        "novelty_mean": statistics.fmean(novelties) if novelties else 0.0,
        "novelty_p50": statistics.median(novelties),
        "score_mean": statistics.fmean(scores) if scores else 0.0,
        "threshold_mean": statistics.fmean(thresholds) if thresholds else None,
        "threshold_last": thresholds[-1] if thresholds else None,
        "top_templates": template_counter.most_common(args.top_templates),
        "top_tokens": token_bits.most_common(args.top_tokens),
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as oh:
            json.dump(summary, oh, indent=2)
        print(f"Wrote summary JSON to {args.out}")
    else:
        print(f"Alerts: {n}")
        if quantile is not None:
            print(f"Quantile (active): {quantile:.3f}")
        print(
            f"Novelty min={summary['novelty_min']:.3f} p50={summary['novelty_p50']:.3f} max={summary['novelty_max']:.3f} mean={summary['novelty_mean']:.3f}"
        )
        print(
            f"Score mean={summary['score_mean']:.3f} threshold_mean={summary['threshold_mean'] if summary['threshold_mean'] is not None else 'n/a'}"
        )
        if summary["top_templates"]:
            print("Top templates:")
            for tpl, c in summary["top_templates"]:
                print(f"  {c:5d} {tpl}")
        if summary["top_tokens"]:
            print("Top tokens by cumulative bits:")
            for tok, bits in summary["top_tokens"]:
                print(f"  {bits:7.2f} {tok}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elaborlog", description="Surface rare, high-signal log lines.")
    # Global --version (argparse will exit 0 before validating subcommands)
    parser.add_argument(
        "--version",
        action="version",
        version=f"elaborlog {__version__}",
        help="Show version and exit",
    )
    sub = parser.add_subparsers(dest="cmd")

    score_parser = sub.add_parser("score", help="(Legacy) score and rank a log file")
    score_parser.add_argument("file")
    score_parser.add_argument("--out", help="Write CSV if set")
    score_parser.add_argument("--top", type=int, default=20)
    score_parser.add_argument("--with-bigrams", action="store_true", help="Include token bigrams while scoring")
    score_parser.add_argument("--split-camel", action="store_true", help="Split mixedCase/PascalCase tokens into parts (retain original)")
    score_parser.add_argument("--split-dot", action="store_true", help="Split dotted.identifiers into parts (retain original)")
    score_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    score_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    score_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    score_parser.add_argument("--json", help="Write full JSON results (array) to this path")
    score_parser.add_argument("--all-token-contributors", action="store_true", help="Include all token contributors (no truncation) in JSON output")
    score_parser.add_argument("--state-in", help="Load model state from this JSON file before scoring")
    score_parser.add_argument("--state-out", help="Persist the updated model state to this JSON file")
    score_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    score_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    score_parser.add_argument("--mask", action="append", help="Custom regex=replacement mask (repeatable)")
    score_parser.add_argument(
        "--mask-order",
        choices=["before", "after"],
        default="before",
        help="Apply custom masks before or after built-ins (default: before)",
    )
    score_parser.set_defaults(func=cmd_score)

    rank_parser = sub.add_parser("rank", help="Rank a log file by novelty")
    rank_parser.add_argument("file")
    rank_parser.add_argument("--out", help="Write CSV if set")
    rank_parser.add_argument("--top", type=int, default=20)
    rank_parser.add_argument("--with-bigrams", action="store_true", help="Include token bigrams while scoring")
    rank_parser.add_argument("--split-camel", action="store_true", help="Split mixedCase/PascalCase tokens into parts (retain original)")
    rank_parser.add_argument("--split-dot", action="store_true", help="Split dotted.identifiers into parts (retain original)")
    rank_parser.add_argument("--w-token", type=float, help="Override weight for token surprisal component")
    rank_parser.add_argument("--w-template", type=float, help="Override weight for template surprisal component")
    rank_parser.add_argument("--w-level", type=float, help="Override weight for level bonus component")
    rank_parser.add_argument("--json", help="Write full JSON results (array) to this path")
    rank_parser.add_argument("--all-token-contributors", action="store_true", help="Include all token contributors (no truncation) in JSON output")
    rank_parser.add_argument("--state-in", help="Load model state from this JSON file before scoring")
    rank_parser.add_argument("--state-out", help="Persist the updated model state to this JSON file")
    rank_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    rank_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    rank_parser.add_argument("--no-color", action="store_true", help="Disable colorized output even if rich present")
    rank_parser.add_argument("--mask", action="append", help="Custom regex=replacement mask (repeatable)")
    rank_parser.add_argument(
        "--mask-order",
        choices=["before", "after"],
        default="before",
        help="Apply custom masks before or after built-ins (default: before)",
    )
    rank_parser.set_defaults(func=cmd_rank)

    tail_parser = sub.add_parser("tail", help="Tail a log and print only high-novelty lines with context")
    tail_parser.add_argument("file")
    tail_parser.add_argument("--no-follow", action="store_true", help="Process existing file once and exit (do not wait for new lines)")
    tail_parser.add_argument("--quantile", type=float, help="Override the rolling novelty quantile [0,1)")
    tail_parser.add_argument(
        "--quantiles",
        nargs="+",
        type=float,
        help="Multiple high-percentile novelty quantiles (e.g. 0.99 0.995); highest chosen for alerts",
    )
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
    tail_parser.add_argument("--split-camel", action="store_true", help="Split mixedCase/PascalCase tokens into parts (retain original)")
    tail_parser.add_argument("--split-dot", action="store_true", help="Split dotted.identifiers into parts (retain original)")
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
    tail_parser.add_argument("--all-token-contributors", action="store_true", help="Include full token contributor list in JSONL alerts (instead of top 10)")
    tail_parser.add_argument(
        "--emit-intermediate",
        action="store_true",
        help="Include all individual quantile estimates in JSONL alerts (quantile_estimates map)",
    )
    tail_parser.add_argument("--decay", type=float, help="Per-line decay multiplier (e.g. 0.9999)")
    tail_parser.add_argument("--decay-every", type=int, help="Apply decay multiplier every N lines")
    tail_parser.add_argument("--no-color", action="store_true", help="Disable colorized output even if rich present")
    tail_parser.add_argument("--snapshot-interval", type=float, help="Seconds between periodic snapshots while tailing (requires --state-out)")
    tail_parser.add_argument("--stats-interval", type=float, help="Seconds between alert rate stats (stderr)")
    tail_parser.add_argument("--mask", action="append", help="Custom regex=replacement mask (repeatable)")
    tail_parser.add_argument(
        "--mask-order",
        choices=["before", "after"],
        default="before",
        help="Apply custom masks before or after built-ins (default: before)",
    )
    tail_parser.set_defaults(func=cmd_tail)

    explain_parser = sub.add_parser("explain", help="Explain why a line scored high")
    explain_parser.add_argument("file", help="Use this file to prime frequencies")
    explain_parser.add_argument("--line", required=True, help="A single log line to explain (quote it)")
    explain_parser.add_argument(
        "--with-bigrams",
        action="store_true",
        help="Include bigrams when assessing token contributions",
    )
    explain_parser.add_argument("--split-camel", action="store_true", help="Split mixedCase/PascalCase tokens into parts (retain original)")
    explain_parser.add_argument("--split-dot", action="store_true", help="Split dotted.identifiers into parts (retain original)")
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
    explain_parser.add_argument("--all-token-contributors", action="store_true", help="Do not truncate token contributor list in JSON explanation")
    explain_parser.add_argument("--no-color", action="store_true", help="Disable color output (not used for JSON mode)")
    explain_parser.add_argument("--mask", action="append", help="Custom regex=replacement mask (repeatable)")
    explain_parser.add_argument(
        "--mask-order",
        choices=["before", "after"],
        default="before",
        help="Apply custom masks before or after built-ins (default: before)",
    )
    explain_parser.set_defaults(func=cmd_explain)

    cluster_parser = sub.add_parser("cluster", help="Show most common templates")
    cluster_parser.add_argument("file")
    cluster_parser.add_argument("--top", type=int, default=30)
    cluster_parser.add_argument("--no-color", action="store_true", help="Disable colorized output")
    cluster_parser.add_argument("--mask", action="append", help="Custom regex=replacement mask (repeatable)")
    cluster_parser.add_argument(
        "--mask-order",
        choices=["before", "after"],
        default="before",
        help="Apply custom masks before or after built-ins (default: before)",
    )
    cluster_parser.set_defaults(func=cmd_cluster)

    demo_parser = sub.add_parser("demo", help="Run the examples/app.log demo")
    demo_parser.set_defaults(func=cmd_demo)

    summarize_parser = sub.add_parser("summarize", help="Summarize an alerts JSONL file (from tail)")
    summarize_parser.add_argument("file", help="Path to alerts JSONL produced by tail --jsonl")
    summarize_parser.add_argument("--top-templates", type=int, default=10, help="Number of top templates to show")
    summarize_parser.add_argument("--top-tokens", type=int, default=10, help="Number of top tokens by bits to show")
    summarize_parser.add_argument("--out", help="Optional path to write JSON summary (prints pretty text otherwise)")
    summarize_parser.set_defaults(func=cmd_summarize)

    # Bench subcommand (lightweight wrapper around bench/benchmark.py)
    bench_parser = sub.add_parser("bench", help="Run a quick throughput benchmark (synthetic or file)")
    bench_parser.add_argument("--file", help="Optional log file to benchmark against")
    bench_parser.add_argument("--lines", type=int, default=10000, help="Synthetic lines if no file provided")
    bench_parser.add_argument("--warm", type=int, default=1000, help="Warm-up lines (not timed)")
    bench_parser.add_argument("--measure", type=int, default=5000, help="Lines to measure timing over")

    def _cmd_bench(a: argparse.Namespace) -> int:  # pragma: no cover - covered via integration test
        try:
            from bench.benchmark import run, synthetic_lines, iter_file
        except Exception as exc:  # noqa: BLE001
            print(f"[elaborlog] bench harness import failed: {exc}", file=sys.stderr)
            return 2
        if a.file:
            from pathlib import Path
            p = Path(a.file)
            if not p.exists():
                print(f"[elaborlog] file not found: {p}", file=sys.stderr)
                return 2
            content = list(iter_file(p))
            if len(content) < a.warm + a.measure:
                need = a.warm + a.measure - len(content)
                content.extend(content[:need])
            run(content, a.warm, a.measure)
        else:
            run(list(synthetic_lines(a.lines)), a.warm, a.measure)
        return 0

    bench_parser.set_defaults(func=_cmd_bench)

    serve_parser = sub.add_parser("serve", help="Run HTTP service (requires elaborlog[server])")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--state-in", help="Load model snapshot at startup")
    serve_parser.add_argument("--state-out", help="Persist snapshot periodically and on shutdown")
    serve_parser.add_argument("--interval", type=int, default=60, help="Snapshot interval seconds")
    serve_parser.set_defaults(func=cmd_serve)

    # Simple 'version' subcommand for shells/users preferring explicit command
    version_parser = sub.add_parser("version", help="Show version and exit")
    version_parser.set_defaults(func=lambda _: (print(f"elaborlog {__version__}"), 0)[1])

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):  # No subcommand provided
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
