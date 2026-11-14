"""Run the ML model on one shared stack.

    python -m pipeline.ml run --site albufera --stack 066_D_069
    python -m pipeline.ml synthetic          # fake stack for testing
    python -m pipeline.ml run --site synthetic --stack 066_D_069 --truth-var truth

Reads data/stack/<site>_<stack>.nc and the label files that exist for the site
(see pipeline.ml.labels.default_sources); writes data/ml/<site>_<stack>/.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np

from pipeline.config import REPO_ROOT

from . import __version__, config, data, export, features, labels, split, synthetic, train


def _cmd_synthetic(args: argparse.Namespace) -> None:
    ds = synthetic.make_stack(size=args.size, seed=args.seed)
    path = synthetic.write_stack(ds, data.stack_path("synthetic", "066_D_069", Path(args.stack_dir)))
    print(f"wrote FAKE stack {path} ({ds.sizes['time']} dates, {ds.sizes['y']}x{ds.sizes['x']} px)")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _cmd_run(args: argparse.Namespace) -> None:
    path = data.stack_path(args.site, args.stack, Path(args.stack_dir))
    if not path.exists():
        sys.exit(f"no stack at {path}. Get it with: gh release download data-v1 --pattern \"*.nc\" "
                 f"--dir data/stack   (or build it: python -m pipeline.run)")
    st = data.load(path, crid=args.crid, filter_px=args.filter_px)
    tag = "  [FAKE DATA]" if st.synthetic else ""
    print(f"stack {path.name}: {len(st.dates)} dates {st.dates[0]} to {st.dates[-1]}, "
          f"{st.grid.width}x{st.grid.height} px{tag}")
    for d in st.dropped:
        print(f"  left out {d['date']}: {d['reason']}")

    # Labels and sea.
    if args.truth_var:
        if args.truth_var not in st.extra:
            available = ", ".join(sorted(st.extra)) if st.extra else "(none)"
            sys.exit(f"--truth-var '{args.truth_var}' not found in stack; available variables: {available}")
        y_map = st.extra[args.truth_var].astype(np.int16)
        sea = y_map == synthetic.SEA
        y_map[sea] = config.UNLABELED
        sources = {"truth_var": args.truth_var}
    else:
        found = labels.default_sources(st.site)
        given = {"worldcover": args.worldcover, "jrc_occurrence": args.jrc,
                 "effis": args.effis, "polygons": args.polygons, "sea": args.sea, "corine": args.corine}
        sources = {k: (Path(v) if v else found[k]) for k, v in given.items()}
        y_map, sea = labels.build_labels(st.grid, **sources)
        sources = {k: (_rel(v) if v else None) for k, v in sources.items()}
    counts = labels.label_counts(y_map)
    print("label sources:", {k: v for k, v in sources.items() if v})
    print("label pixels:", counts, f"| sea pixels left out: {int(sea.sum())}")
    if sum(counts.values()) == 0:
        sys.exit("no labelled pixels: pass --worldcover / --jrc / --effis / --polygons")
    missing = [n for n, c in counts.items() if c == 0]
    if missing:
        print(f"  WARNING: no training pixels for {missing}; the model cannot predict these")

    # Features. The water threshold uses every pixel, sea included: without the
    # sea there is no clear water mode and Otsu lands among vegetation (PR #7).
    dark_db, dark_rule = features.water_threshold(st.hh_db)
    X, usable, dark_db = features.pixel_features(st.hh_db, st.hv_db, st.times, dark_threshold_db=dark_db)
    usable &= ~sea.ravel()
    print(f"features: {X.shape[1]} per pixel, {usable.mean():.1%} of pixels classified, "
          f"water threshold {dark_db:.1f} dB ({dark_rule}), speckle filter {args.filter_px or 'off'}")
    forbid = train.burned_rule(X, None if args.burned_min_hv_drop <= 0 else args.burned_min_hv_drop)

    # Spatial split, train, score.
    labels_usable = np.where(usable.reshape(st.shape), y_map, config.UNLABELED)
    train_mask, test_mask = split.split_blocks(st.shape, block_px=args.block_px, seed=args.seed,
                                               labels=labels_usable)
    y = y_map.ravel()
    labelled = (y != config.UNLABELED) & usable
    tr = train.sample_per_class(y, labelled & train_mask.ravel(), args.max_per_class, args.seed)
    te = np.flatnonzero(labelled & test_mask.ravel())
    print(f"train pixels {tr.size}, test pixels {te.size} (1 test block = {args.block_px} px square)")
    if tr.size == 0 or te.size == 0:
        sys.exit("not enough labelled pixels in train or test blocks")
    model = train.fit(X[tr], y[tr], seed=args.seed)
    metrics = train.evaluate(model, X[te], y[te], forbid={c: m[te] for c, m in forbid.items()})
    print(f"test: accuracy {metrics['overall_accuracy']:.3f}, macro F1 {metrics['macro_f1']:.3f}, "
          f"kappa {metrics['kappa']:.3f}")

    class_map, confidence = train.predict_map(model, X, usable, st.shape, forbid=forbid)

    # Outputs.
    out_dir = Path(args.out_dir) / f"{st.site}_{args.stack}"
    paths = export.write_outputs(class_map, confidence, st.grid, out_dir)
    importance = train.feature_importance(model)
    run_info = {
        "site": st.site, "stack": args.stack, "synthetic": st.synthetic,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_version": __version__,
        "stack_file": _rel(path),
        "dates": st.dates, "dates_left_out": st.dropped, "crid_rule": args.crid,
        "label_sources": sources,
        "water_threshold_hh_db": dark_db, "water_threshold_rule": dark_rule,
        "speckle_filter_px": args.filter_px,
        "burned_min_hv_drop_db": args.burned_min_hv_drop if args.burned_min_hv_drop > 0 else None,
        "split": {"block_px": args.block_px, "gap_px": config.GAP_PX,
                  "test_fraction": config.TEST_FRACTION, "seed": args.seed, "balanced_by_class": True,
                  "test_share_per_class": {
                      n: round(float((labels_usable[test_mask] == i).sum() / max(1, (labels_usable == i).sum())), 3)
                      for i, n in enumerate(config.CLASSES)}},
        "train_pixels": int(tr.size),
        "label_pixels": counts,
        "sea_pixels": int(sea.sum()),
        "class_area_ha": train.class_areas_ha(class_map),
        "valid_fraction": float(usable.mean()),
        **metrics,
    }
    export.write_json(run_info, out_dir / "metrics.json")
    export.write_json(importance, out_dir / "feature_importance.json")
    print("top features:", ", ".join(f"{d['feature']} {d['gain_share']:.0%}" for d in importance[:5]))

    if st.synthetic:
        print("fake stack: manifest left untouched")
    else:
        base = {
            "model": "ml", "site": st.site, "stack": args.stack, "date": f"{st.dates[0]}/{st.dates[-1]}",
            "source": st.provenance, "valid_fraction": run_info["valid_fraction"],
            "score": {"macro_f1": metrics["macro_f1"], "overall_accuracy": metrics["overall_accuracy"]},
        }
        export.upsert_manifest(Path(args.manifest), [
            {**base, "layer": "class", "file": _rel(paths["class"]), "classes": config.CLASSES},
            {**base, "layer": "confidence", "file": _rel(paths["confidence"]),
             "units": "percent, highest class probability"},
        ], key_fields=export.ML_MANIFEST_KEY)
        print(f"manifest updated: {_rel(Path(args.manifest))}")
    print(f"outputs in {_rel(out_dir)}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline.ml", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("synthetic", help="write a FAKE stack for testing")
    s.add_argument("--stack-dir", default=str(config.STACK_DIR))
    s.add_argument("--size", type=int, default=300)
    s.add_argument("--seed", type=int, default=config.SEED)
    s.set_defaults(func=_cmd_synthetic)

    r = sub.add_parser("run", help="features -> train -> score -> export for one stack")
    r.add_argument("--site", required=True, help="albufera or espada (or synthetic)")
    r.add_argument("--stack", required=True, help="track_direction_frame, e.g. 066_D_069")
    r.add_argument("--crid", default="all",
                   help="which processing release to keep: all (default), majority, or e.g. P05023")
    r.add_argument("--worldcover", help="override the default WorldCover file")
    r.add_argument("--jrc", help="override the default JRC occurrence file")
    r.add_argument("--effis", help="override the default EFFIS burnt area file")
    r.add_argument("--polygons", help="hand-drawn GeoJSON/GeoPackage with a `class` column "
                                      "(default data/labels/<site>_drawn.geojson)")
    r.add_argument("--sea", help="override the default sea mask file (1 = sea)")
    r.add_argument("--corine", help="override the default CORINE 2018 polygons (python -m pipeline.ml.corine)")
    r.add_argument("--filter-px", type=int, default=data.FILTER_PX,
                   help=f"speckle filter window in pixels, 0 = off (default {data.FILTER_PX})")
    r.add_argument("--burned-min-hv-drop", type=float, default=1.5,
                   help="only call a pixel burned if HV dropped this many dB and stayed down; 0 = off")
    r.add_argument("--truth-var", help="use a label variable inside the stack (fake stacks only)")
    r.add_argument("--stack-dir", default=str(config.STACK_DIR))
    r.add_argument("--out-dir", default=str(config.ML_OUT_DIR))
    r.add_argument("--manifest", default=str(config.MANIFEST))
    r.add_argument("--block-px", type=int, default=config.BLOCK_PX)
    r.add_argument("--max-per-class", type=int, default=config.MAX_TRAIN_PER_CLASS)
    r.add_argument("--seed", type=int, default=config.SEED)
    r.set_defaults(func=_cmd_run)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
