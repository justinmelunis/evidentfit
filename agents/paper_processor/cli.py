from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from .collect import build_section_bundle, write_bundle, _load_meta_map
from .extract import build_card, write_card
from evidentfit_shared.banking.aggregate import BankingConfig, pool_and_grade, load_cards_for
from evidentfit_shared.banking.adjust import apply_suitability, load_rules


def _iter_paper_ids(canonical_path: Path, paper_ids_file: Optional[Path], single_id: Optional[str], limit: Optional[int]):
    if single_id:
        yield str(single_id)
        return
    if paper_ids_file and paper_ids_file.exists():
        count = 0
        for line in paper_ids_file.read_text(encoding="utf-8").splitlines():
            pid = line.strip()
            if not pid:
                continue
            yield pid
            count += 1
            if limit and count >= limit:
                break
        return
    # else read canonical jsonl
    count = 0
    for rec in Path(canonical_path).read_text(encoding="utf-8").splitlines():
        if not rec.strip():
            continue
        try:
            obj = json.loads(rec)
        except Exception:
            continue
        pid = obj.get("paper_id") or obj.get("pmid") or obj.get("id")
        if not pid:
            continue
        yield str(pid)
        count += 1
        if limit and count >= limit:
            break


_G_META_MAP = None

def _pool_init(canonical):
    # Load meta_map once per worker process
    global _G_META_MAP
    _G_META_MAP = _load_meta_map(Path(canonical))


def _collect_worker(task):
    pid, canonical, chunks, outdir, skip_existing, verbose = task
    out_path = Path(outdir) / f"{pid}.json"
    if skip_existing and out_path.exists():
        return ("SKIP", pid, str(out_path))
    try:
        bundle = build_section_bundle(
            paper_id=pid,
            canonical_path=Path(canonical),
            chunks_path=Path(chunks) if chunks else None,
            meta_map=_G_META_MAP,
        )
        path = write_bundle(bundle, Path(outdir))
        return ("OK", pid, str(path))
    except Exception as e:
        return ("ERR", pid, repr(e))


def cmd_collect(args: argparse.Namespace) -> None:
    # Build the worklist
    ids = list(_iter_paper_ids(Path(args.canonical), Path(args.paper_ids_file) if args.paper_ids_file else None, args.paper_id, args.limit))
    if not ids:
        print("No paper_ids found.")
        return
    # Prepare tasks
    tasks = [(pid, args.canonical, args.chunks, args.outdir, args.skip_existing, args.verbose) for pid in ids]
    # Progress bar (optional)
    try:
        from tqdm import tqdm  # type: ignore
        use_tqdm = True
    except Exception:
        use_tqdm = False

    if args.workers and args.workers > 1:
        from multiprocessing import Pool
        print(f"Starting collect: {len(tasks)} papers, workers={args.workers}")
        with Pool(processes=args.workers, initializer=_pool_init, initargs=(args.canonical,)) as pool:
            # chunksize=1 for fastest first progress tick
            it = pool.imap_unordered(_collect_worker, tasks, chunksize=1)
            iterator = tqdm(it, total=len(tasks), ncols=100, disable=not use_tqdm) if use_tqdm else it
            ok = err = skip = 0
            for status, pid, info in iterator:
                if status == "OK":
                    ok += 1
                    if args.verbose:
                        print("OK", pid, info)
                elif status == "SKIP":
                    skip += 1
                    if args.verbose:
                        print("SKIP", pid)
                else:
                    err += 1
                    print("ERR", pid, info)
            if use_tqdm:
                iterator.close()
            print(f"Done. ok={ok} skip={skip} err={err}")
    else:
        print(f"Starting collect (single worker): {len(tasks)} papers")
        ok = err = skip = 0
        it = tqdm(tasks, ncols=100, disable=not use_tqdm) if use_tqdm else tasks
        # Load meta_map once in main process
        global _G_META_MAP
        _G_META_MAP = _load_meta_map(Path(args.canonical))
        for t in it:
            status, pid, info = _collect_worker(t)
            if status == "OK":
                ok += 1
                if args.verbose:
                    print("OK", pid, info)
            elif status == "SKIP":
                skip += 1
                if args.verbose:
                    print("SKIP", pid)
            else:
                err += 1
                print("ERR", pid, info)
        print(f"Done. ok={ok} skip={skip} err={err}")


def _setup_logging(level: str, json_mode: bool = False) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    if json_mode:
        # minimal JSON formatter
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "level": record.levelname,
                    "name": record.name,
                    "msg": record.getMessage(),
                }
                return json.dumps(payload, ensure_ascii=False)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(lvl)
    else:
        logging.basicConfig(
            level=lvl,
            format="%(levelname)s %(name)s: %(message)s",
        )


def cmd_extract(args: argparse.Namespace) -> None:
    _setup_logging(args.log_level, args.log_json)
    log = logging.getLogger("paper_processor.cli")
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    metrics_path = Path(args.metrics) if args.metrics else Path("data/cards/_logs/extract_metrics.jsonl")
    card = build_card(bundle, model_ver=args.model, prompt_ver=args.prompt_ver, llm_mode=args.llm_mode, metrics_path=metrics_path)
    path = write_card(card, Path(args.outdir))
    log.info("Wrote card %s", path)
    # Quick visibility: outcome domain/direction (if present)
    if card.get("outcomes"):
        oc = card["outcomes"][0]
        log.info("Outcome: domain=%s direction=%s es_norm=%s", oc.get("domain"), oc.get("direction"), oc.get("effect_size_norm"))
    print(path)


def cmd_bank_aggregate(args: argparse.Namespace) -> None:
    cfg = BankingConfig.load(Path(args.config))
    cards = load_cards_for(args.supplement, args.goal, Path(args.cards))
    agg = pool_and_grade(cards, cfg)
    payload = {
        "supplement": args.supplement,
        "goal": args.goal,
        **agg,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_bank_adjust(args: argparse.Namespace) -> None:
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    rules = load_rules(Path(args.rules))
    result = apply_suitability(
        supplement=args.supplement,
        intrinsic_grade=args.intrinsic,
        rules=rules,
        user_profile=profile,
        max_downgrade=args.max_downgrade,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paper_processor")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("collect")
    sp.add_argument("--paper-id", help="single paper id")
    sp.add_argument("--paper-ids-file", help="path to a file with one paper_id per line")
    sp.add_argument("--limit", type=int, default=None, help="limit number of papers (for smoke runs)")
    sp.add_argument("--canonical", default="data/index/canonical_papers.jsonl")
    sp.add_argument("--chunks", default="data/index/chunks.jsonl")
    sp.add_argument("--outdir", default="data/cards/_raw")
    sp.add_argument("--workers", type=int, default=8, help="number of parallel workers")
    sp.add_argument("--skip-existing", action="store_true", help="skip if output exists")
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser("extract")
    sp.add_argument("--bundle", required=True, help="path to _raw bundle json")
    sp.add_argument("--outdir", default="data/cards")
    sp.add_argument("--model", default="mistral-7b-instruct")
    sp.add_argument("--prompt-ver", default="v1")
    sp.add_argument("--llm-mode", choices=["off","basic","fallback"], default="fallback")
    sp.add_argument("--metrics", default="data/cards/_logs/extract_metrics.jsonl")
    sp.add_argument("--log-level", default="INFO", help="DEBUG|INFO|WARNING|ERROR")
    sp.add_argument("--log-json", action="store_true", help="emit newline-delimited JSON logs")
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("bank-aggregate")
    sp.add_argument("--supplement", required=True)
    sp.add_argument("--goal", default=None)
    sp.add_argument("--cards", default="data/cards")
    sp.add_argument("--config", default="config/banking.yml")
    sp.set_defaults(func=cmd_bank_aggregate)

    sp = sub.add_parser("bank-adjust")
    sp.add_argument("--supplement", required=True)
    sp.add_argument("--intrinsic", required=True, help="intrinsic grade A/B/C/D/F")
    sp.add_argument("--profile", required=True, help="path to user profile JSON")
    sp.add_argument("--rules", default="config/suitability_rules.json")
    sp.add_argument("--max-downgrade", type=int, default=1)
    sp.set_defaults(func=cmd_bank_adjust)
    return p


def main(argv: Optional[list] = None) -> None:
    p = build_parser()
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()




