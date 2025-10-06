#!/bin/bash
# Fetch full text for the latest get_papers run
#
# Usage:
#   ./fetch_fulltext_for_latest.sh
#
# Or with options:
#   export NCBI_API_KEY="your_key"
#   ./fetch_fulltext_for_latest.sh --limit 1000 --concurrency 2

# Get the latest papers path from latest.json
LATEST_JSON="data/ingest/runs/latest.json"

if [ ! -f "$LATEST_JSON" ]; then
    echo "Error: $LATEST_JSON not found"
    echo "Run get_papers pipeline first:"
    echo "  python -m agents.ingest.get_papers.pipeline --mode bootstrap"
    exit 1
fi

# Extract papers_path from latest.json
PAPERS_PATH=$(python -c "import json; print(json.load(open('$LATEST_JSON'))['papers_path'])")
RUN_ID=$(python -c "import json; print(json.load(open('$LATEST_JSON'))['run_id'])")

echo "=========================================="
echo "Fetching full text for run: $RUN_ID"
echo "Papers: $PAPERS_PATH"
echo "=========================================="
echo ""

# Run the fulltext fetcher
python -m agents.ingest.get_papers.fulltext_fetcher \
    --jsonl "$PAPERS_PATH" \
    "$@"

echo ""
echo "=========================================="
echo "Full-text fetch complete!"
echo "Manifest saved to: data/ingest/runs/$RUN_ID/fulltext_manifest.json"
echo "Store location: data/fulltext_store/"
echo "=========================================="

