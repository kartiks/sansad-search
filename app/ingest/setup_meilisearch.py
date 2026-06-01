"""
One-time / deploy-time script: configure the Meilisearch parliamentary_records index
and push all synonyms from data/synonyms.json.

Usage:
    MEILISEARCH_URL=https://... MEILISEARCH_MASTER_KEY=... python -m ingest.setup_meilisearch
"""

import json
import os
import sys
from pathlib import Path

import httpx
import meilisearch_python_sdk as meilisearch

INDEX_NAME = "parliamentary_records"

SEARCHABLE_ATTRIBUTES = [
    "speaker_name",
    "minister_name",
    "ministry",
    "questioner_names",
    "subject",
    "full_text_en",
]

FILTERABLE_ATTRIBUTES = [
    "source",
    "proceeding_type",
    "date",
    "speaker_name",
    "session_name",
    "minister_name",
    "record_type",
]

SORTABLE_ATTRIBUTES = ["date", "sequence_within_sitting"]

RANKING_RULES = ["words", "typos", "proximity", "attribute", "sort", "exactness"]

TYPO_TOLERANCE = {
    "enabled": True,
    "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
    "disableOnAttributes": ["date", "source", "proceeding_type", "source_url"],
}

PAGINATION = {"maxTotalHits": 10000}

# Meilisearch experimental features required by this application.
# containsFilter enables the CONTAINS filter operator used for speaker_name and
# session_name substring matching in the search service.
EXPERIMENTAL_FEATURES = {"containsFilter": True}


def _load_synonyms(synonyms_path: Path) -> list[dict]:
    """
    Convert synonyms.json groups into the flat list of bidirectional synonym
    pairs that the Meilisearch synonyms API expects.

    Each group is an array of equivalent terms. We emit every ordered pair
    (a → [all others]) for each term in the group, which is what the
    Meilisearch synonyms API requires for bidirectionality.
    """
    with synonyms_path.open() as f:
        data = json.load(f)

    pairs: list[dict] = []
    for category_groups in data.values():
        if not isinstance(category_groups, list):
            continue
        for group in category_groups:
            if not isinstance(group, list) or len(group) < 2:
                continue
            for i, term in enumerate(group):
                others = [t for j, t in enumerate(group) if j != i]
                pairs.append({"word": term, "synonyms": others})
    return pairs


def main() -> None:
    url = os.environ.get("MEILISEARCH_URL")
    key = os.environ.get("MEILISEARCH_MASTER_KEY")
    if not url or not key:
        print("Error: MEILISEARCH_URL and MEILISEARCH_MASTER_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = meilisearch.Client(url, key)

    # Create index if absent
    existing = [idx.uid for idx in client.get_indexes()["results"]]
    if INDEX_NAME not in existing:
        task = client.create_index(INDEX_NAME, {"primaryKey": "id"})
        client.wait_for_task(task.task_uid)
        print(f"Created index '{INDEX_NAME}'.")
    else:
        print(f"Index '{INDEX_NAME}' already exists — updating settings.")

    index = client.index(INDEX_NAME)

    # Apply all settings
    task = index.update_settings({
        "searchableAttributes": SEARCHABLE_ATTRIBUTES,
        "filterableAttributes": FILTERABLE_ATTRIBUTES,
        "sortableAttributes": SORTABLE_ATTRIBUTES,
        "rankingRules": RANKING_RULES,
        "typoTolerance": TYPO_TOLERANCE,
        "pagination": PAGINATION,
    })
    client.wait_for_task(task.task_uid)
    print("Index settings applied.")

    # Enable experimental features (instance-level, not index-level).
    # PATCH /experimental-features is not exposed by the SDK; use httpx directly.
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = httpx.patch(f"{url}/experimental-features", json=EXPERIMENTAL_FEATURES, headers=headers)
    resp.raise_for_status()
    print("Experimental features enabled:", list(EXPERIMENTAL_FEATURES.keys()))

    # Load and push synonyms (full replace)
    synonyms_path = Path(__file__).parent.parent / "data" / "synonyms.json"
    if not synonyms_path.exists():
        print(f"Error: synonyms.json not found at {synonyms_path}", file=sys.stderr)
        sys.exit(1)

    synonym_pairs = _load_synonyms(synonyms_path)
    synonyms_dict = {pair["word"]: pair["synonyms"] for pair in synonym_pairs}

    task = index.update_synonyms(synonyms_dict)
    client.wait_for_task(task.task_uid)
    print(f"Pushed {len(synonym_pairs)} synonym entries to Meilisearch.")

    print("Setup complete.")


if __name__ == "__main__":
    main()
