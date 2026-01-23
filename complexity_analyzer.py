#!/usr/bin/env python3
"""
Complexity Score Analyzer
==========================

Analyzes features and helps optimize complexity scores for cost-efficient model routing.
"""

import sys
from pathlib import Path
from collections import defaultdict

from api.database import create_database, Feature
from parallel_orchestrator import MODEL_ROUTING


def analyze_project(project_dir: Path):
    """Analyze complexity scores for a project."""
    print("=" * 70)
    print("  COMPLEXITY SCORE ANALYSIS")
    print("=" * 70)
    print(f"\nProject: {project_dir}")
    print()

    engine, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Get all features
        features = session.query(Feature).all()
        if not features:
            print("No features found in database.")
            return

        # Group by complexity score
        by_complexity = defaultdict(list)
        for f in features:
            score = getattr(f, 'complexity_score', 2)
            by_complexity[score].append(f)

        # Print summary
        print("COMPLEXITY DISTRIBUTION:")
        print("-" * 70)
        for score in sorted(by_complexity.keys()):
            count = len(by_complexity[score])
            percentage = (count / len(features)) * 100
            model = MODEL_ROUTING.get(score, "unknown")
            print(f"  Score {score} ({model}): {count} features ({percentage:.1f}%)")
        print()

        # Cost analysis
        print("COST IMPACT ANALYSIS:")
        print("-" * 70)
        simple_count = len(by_complexity.get(1, []))
        total_features = len(features)
        potential_savings = (simple_count / total_features) * 100 if total_features > 0 else 0

        print(f"  Total features: {total_features}")
        print(f"  Simple features (Haiku): {simple_count}")
        print(f"  Potential cost savings: ~{potential_savings:.1f}% of features use cheaper Haiku")
        print()

        # Show examples by category
        print("COMPLEXITY BY CATEGORY:")
        print("-" * 70)
        by_category = defaultdict(lambda: defaultdict(int))
        for f in features:
            score = getattr(f, 'complexity_score', 2)
            by_category[f.category][score] += 1

        for category in sorted(by_category.keys()):
            scores = by_category[category]
            total = sum(scores.values())
            score_str = ", ".join(f"{score}:{count}" for score, count in sorted(scores.items()))
            print(f"  {category}: {total} features (scores: {score_str})")

        print()

        # Show sample simple features
        if by_complexity.get(1):
            print("SAMPLE SIMPLE FEATURES (using Haiku):")
            print("-" * 70)
            for f in by_complexity[1][:5]:
                print(f"  #{f.id}: [{f.category}] {f.name}")
            if len(by_complexity[1]) > 5:
                print(f"  ... and {len(by_complexity[1]) - 5} more")
            print()

        # Show sample complex features
        if by_complexity.get(3):
            print("SAMPLE COMPLEX FEATURES (using Sonnet):")
            print("-" * 70)
            for f in by_complexity[3][:5]:
                print(f"  #{f.id}: [{f.category}] {f.name}")
            if len(by_complexity[3]) > 5:
                print(f"  ... and {len(by_complexity[3]) - 5} more")
            print()

    finally:
        session.close()

    print("=" * 70)
    print()
    print("To update complexity scores manually:")
    print(f"  cd {project_dir}")
    print(f"  sqlite3 features.db")
    print(f"  UPDATE features SET complexity_score = 1 WHERE category = 'UI';")
    print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python complexity_analyzer.py <project-dir>")
        print()
        print("Example:")
        print("  python complexity_analyzer.py ~/projects/autocoder-projects/qr")
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    if not project_dir.exists():
        print(f"Error: Project directory does not exist: {project_dir}")
        sys.exit(1)

    db_path = project_dir / "features.db"
    if not db_path.exists():
        print(f"Error: No features.db found at: {db_path}")
        sys.exit(1)

    analyze_project(project_dir)


if __name__ == "__main__":
    main()
