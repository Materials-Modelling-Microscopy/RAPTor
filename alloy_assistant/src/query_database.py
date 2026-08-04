"""Command-line interface for reviewed Alloy Assistant queries."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .database import DEFAULT_DATABASE_PATH, connect
from .queries import (
    find_binaries_above_miscibility_temperature,
    find_room_temperature_stable_binaries,
    get_binary_system_summary,
    get_database_summary,
    get_experimental_observations_for_system,
    get_miscibility_predictions_for_system,
    get_pmr_for_system,
    get_predicted_phases_for_system,
    get_system_overview,
    get_tdb_coverage,
    list_documents,
    rank_equimolar_miscibility_predictions,
    rank_binary_pairs_by_hmix,
    search_document_chunks,
    search_document_chunks_semantic,
)


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    return value


def _print_human(value: Any) -> None:
    records = _serializable(value)
    if isinstance(records, dict):
        for key, item in records.items():
            print(f"{key}: {item}")
        return
    if not records:
        print("No results")
        return

    if "hmix_eV_atom" in records[0]:
        print(
            f"{'System':<12} {'Hmix (eV/atom)':>15} "
            f"{'T_misc (K)':>12} {'T_melt (K)':>12} "
            f"{'T_misc/T_melt':>14}"
        )
        for record in records:
            print(
                f"{record['canonical_name']:<12} "
                f"{record['hmix_eV_atom']:>15.6f} "
                f"{record['miscibility_temperature_K']:>12.1f} "
                f"{record['melting_temperature_K']:>12.1f} "
                f"{record['miscibility_ratio']:>14.6f}"
            )
        return

    for index, record in enumerate(records, start=1):
        if index > 1:
            print()
        print(f"Result {index}")
        for key, item in record.items():
            print(f"  {key}: {item}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask reviewed SQL questions of the Alloy Assistant database.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the DuckDB database.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Return machine-readable JSON suitable for an agent tool.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("summary", help="Show curated database counts.")

    system_parser = subparsers.add_parser(
        "system",
        help="Show one binary system.",
    )
    system_parser.add_argument("system_name", help="For example Cr-Hf.")

    overview_parser = subparsers.add_parser(
        "overview",
        help="Show available evidence for any alloy system.",
    )
    overview_parser.add_argument("system_name")

    miscibility_parser = subparsers.add_parser(
        "miscibility",
        help="Show composition-level T_misc predictions for a system.",
    )
    miscibility_parser.add_argument("system_name")
    miscibility_parser.add_argument(
        "--equimolar-only",
        action="store_true",
    )

    rank_tmisc_parser = subparsers.add_parser(
        "rank-tmisc",
        help="Rank validated equimolar compositions by T_misc.",
    )
    rank_tmisc_parser.add_argument("--limit", type=int, default=10)
    rank_tmisc_parser.add_argument(
        "--lowest",
        action="store_true",
        help="Show the lowest values instead of the highest.",
    )
    rank_tmisc_parser.add_argument(
        "--components",
        type=int,
        help="Restrict to an exact number of alloying elements.",
    )

    pmr_parser = subparsers.add_parser(
        "pmr",
        help="Show PMR values for a system.",
    )
    pmr_parser.add_argument("system_name")
    pmr_parser.add_argument("--temperature", type=float)

    phases_parser = subparsers.add_parser(
        "phases",
        help="Show predicted phase fractions for a system.",
    )
    phases_parser.add_argument("system_name")
    phases_parser.add_argument("--temperature", type=float)

    experiments_parser = subparsers.add_parser(
        "experiments",
        help="Show experimental phase reports for a system.",
    )
    experiments_parser.add_argument("system_name")

    tdb_parser = subparsers.add_parser(
        "tdb",
        help="Show thermodynamic-database coverage for a system.",
    )
    tdb_parser.add_argument("system_name")

    subparsers.add_parser(
        "documents",
        help="List ingested documents and chunk counts.",
    )

    search_parser = subparsers.add_parser(
        "search-text",
        help="Run transparent lexical search over PDF chunks.",
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument(
        "--source-class",
        help="Optionally restrict results to one evidence class.",
    )

    semantic_parser = subparsers.add_parser(
        "search-semantic",
        help="Search PDF chunks by local vector similarity.",
    )
    semantic_parser.add_argument("query")
    semantic_parser.add_argument("--limit", type=int, default=5)
    semantic_parser.add_argument(
        "--source-class",
        help="Optionally restrict results to one evidence class.",
    )

    hybrid_parser = subparsers.add_parser(
        "search-hybrid",
        help="Fuse lexical and semantic retrieval into an evidence packet.",
    )
    hybrid_parser.add_argument("query")
    hybrid_parser.add_argument("--limit", type=int, default=6)
    hybrid_parser.add_argument("--candidate-pool", type=int, default=30)
    hybrid_parser.add_argument("--source-class")
    hybrid_parser.add_argument(
        "--system-name",
        help="Boost chunks explicitly annotated with this alloy system.",
    )
    hybrid_parser.add_argument("--max-per-document", type=int, default=3)
    hybrid_parser.add_argument("--max-total-words", type=int, default=1800)

    rank_parser = subparsers.add_parser(
        "rank-hmix",
        help="Rank binary pairs by Hmix.",
    )
    rank_parser.add_argument("--limit", type=int, default=10)
    rank_parser.add_argument(
        "--lowest",
        action="store_true",
        help="Show the lowest values instead of the highest.",
    )

    room_parser = subparsers.add_parser(
        "room-temperature",
        help="Find binaries stable at or below a room-temperature threshold.",
    )
    room_parser.add_argument("--temperature", type=float, default=300.0)

    high_parser = subparsers.add_parser(
        "high-tmisc",
        help="Find binaries at or above a T_misc threshold.",
    )
    high_parser.add_argument("minimum_temperature", type=float)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect(database_path, read_only=True) as connection:
        if args.command == "summary":
            result = get_database_summary(connection)
        elif args.command == "system":
            result = get_binary_system_summary(connection, args.system_name)
        elif args.command == "overview":
            result = get_system_overview(connection, args.system_name)
        elif args.command == "miscibility":
            result = get_miscibility_predictions_for_system(
                connection,
                args.system_name,
                equimolar_only=args.equimolar_only,
            )
        elif args.command == "rank-tmisc":
            result = rank_equimolar_miscibility_predictions(
                connection,
                limit=args.limit,
                descending=not args.lowest,
                n_components=args.components,
            )
        elif args.command == "pmr":
            result = get_pmr_for_system(
                connection,
                args.system_name,
                temperature_K=args.temperature,
            )
        elif args.command == "phases":
            result = get_predicted_phases_for_system(
                connection,
                args.system_name,
                temperature_K=args.temperature,
            )
        elif args.command == "experiments":
            result = get_experimental_observations_for_system(
                connection,
                args.system_name,
            )
        elif args.command == "tdb":
            result = get_tdb_coverage(
                connection,
                args.system_name,
            )
        elif args.command == "documents":
            result = list_documents(connection)
        elif args.command == "search-text":
            result = search_document_chunks(
                connection,
                args.query,
                limit=args.limit,
                source_class=args.source_class,
                system_name=args.system_name,
            )
        elif args.command == "search-semantic":
            from .embeddings import (
                MODEL_NAME,
                MODEL_REVISION,
                encode_query,
            )

            result = search_document_chunks_semantic(
                connection,
                encode_query(args.query),
                model_name=MODEL_NAME,
                model_revision=MODEL_REVISION,
                limit=args.limit,
                source_class=args.source_class,
            )
        elif args.command == "search-hybrid":
            from .hybrid_retrieval import hybrid_search

            result = hybrid_search(
                connection,
                args.query,
                limit=args.limit,
                candidate_pool=args.candidate_pool,
                source_class=args.source_class,
                max_per_document=args.max_per_document,
                max_total_words=args.max_total_words,
            )
        elif args.command == "rank-hmix":
            result = rank_binary_pairs_by_hmix(
                connection,
                limit=args.limit,
                descending=not args.lowest,
            )
        elif args.command == "room-temperature":
            result = find_room_temperature_stable_binaries(
                connection,
                room_temperature_K=args.temperature,
            )
        elif args.command == "high-tmisc":
            result = find_binaries_above_miscibility_temperature(
                connection,
                args.minimum_temperature,
            )
        else:
            raise AssertionError(f"Unhandled command: {args.command}")

    if args.json:
        print(json.dumps(_serializable(result), indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
