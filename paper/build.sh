#!/bin/bash
# Build paper.docx and timeline.png from source files.
# Usage: cd agentic/paper && bash build.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Step 1: Generate reference template ==="
python3 generate_template.py

echo "=== Step 2: Generate timeline diagram ==="
python3 generate_timeline.py

echo "=== Step 3: Download IEEE CSL (if needed) ==="
if [ ! -f ieee.csl ]; then
    curl -sL "https://raw.githubusercontent.com/citation-style-language/styles/master/ieee.csl" -o ieee.csl
    echo "Downloaded ieee.csl"
else
    echo "ieee.csl already exists"
fi

echo "=== Step 4: Build paper.docx with pandoc ==="
pandoc paper.md \
    --from markdown \
    --to docx \
    --reference-doc=reference-template.docx \
    --citeproc \
    --bibliography=references.bib \
    --csl=ieee.csl \
    --toc \
    --number-sections \
    -o paper.docx

echo ""
echo "=========================================="
echo "BUILD COMPLETE"
echo "  paper.docx                 — Paper draft"
echo "  geoagentbench-timeline.png — Timeline"
echo "=========================================="
