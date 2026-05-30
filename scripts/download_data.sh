#!/bin/bash
# Fetch the two raster COG files required by the self-hostable benchmark API.
#
# Targets:
#   api/data/cogs/co2_spain.tif          — CO2 geological storage suitability, Spain
#                                          Source: MITECO (Ministerio para la
#                                          Transición Ecológica), processed by
#                                          the authors into a categorical COG.
#   api/data/cogs/gully_europe.tif       — Gully erosion probability, Europe
#                                          Source: JRC LUCAS 2022 + a random
#                                          forest model trained by the authors.
#
# The BigEarthNet Portugal LULC stats ship in-repo at
#   api/data/bigearthnet_portugal_stats.json
# and do NOT need to be downloaded.
#
# Usage:
#   # Option A — automated download (when the public hosting URLs are set):
#   CO2_SPAIN_URL=https://...      \
#   GULLY_EUROPE_URL=https://...   \
#     ./scripts/download_data.sh
#
#   # Option B — manual placement:
#   #   Obtain the two files (see "Where to get the data" below) and copy
#   #   them into api/data/cogs/ before re-running the script. The script
#   #   is idempotent and will skip files that already exist.
#
# Where to get the data
#   The COG files are large (several hundred MB each) and are not yet hosted
#   in a public archive. Until they are mirrored to Zenodo / Hugging Face,
#   request them from the paper authors (see CITATION.cff) or rebuild them
#   from the cited source datasets using the pipeline described in §3.4
#   ("MLOps Pipeline") of the paper.
#
# File specifications (for sanity checks after manual placement)
#   co2_spain.tif    — categorical COG, uint8, EPSG:3035, 100 m, NoData 255,
#                      values: 0 = Not Eligible, 1 = Eligible with Conditions,
#                      2 = Eligible (3 classes)
#   gully_europe.tif — continuous probability [0, 100], float32, EPSG:3035 (ETRS89-LAEA),
#                      100 m, NoData 256
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COG_DIR="$REPO_DIR/api/data/cogs"
mkdir -p "$COG_DIR"

# Default to the published Zenodo dataset record (v2, concept DOI 10.5281/zenodo.20450995).
# Override via env vars if mirroring elsewhere.
CO2_URL="${CO2_SPAIN_URL:-https://zenodo.org/records/20454498/files/co2_spain.tif}"
GULLY_URL="${GULLY_EUROPE_URL:-https://zenodo.org/records/20454498/files/gully_europe.tif}"

cat <<EOF
==============================================
GeoNatureAgent data downloader
==============================================
Target directory:
  $COG_DIR

Files required:
  1. co2_spain.tif
  2. gully_europe.tif

EOF

missing=0
need_url=0

check_file() {
  local name="$1" url_var="$2" url_val="$3"
  local path="$COG_DIR/$name"

  if [[ -s "$path" ]]; then
    echo "  [ok]      $name already present — skipping"
    return 0
  fi

  missing=1
  if [[ -z "$url_val" ]]; then
    echo "  [missing] $name (no \$$url_var set; nothing to download)"
    need_url=1
    return 0
  fi

  echo "  [fetch]   $name  ←  $url_val"
  if ! curl -fL --retry 3 -o "$path" "$url_val"; then
    echo "  [error]   curl failed for $name"
    rm -f "$path"
    exit 2
  fi
  echo "  [ok]      $name downloaded"
}

check_file "co2_spain.tif"    "CO2_SPAIN_URL"    "$CO2_URL"
check_file "gully_europe.tif" "GULLY_EUROPE_URL" "$GULLY_URL"

echo ""

if [[ $need_url -eq 1 ]]; then
  cat <<EOF
==============================================
Manual step required
==============================================
One or more files are missing and no download URL was provided.

  Either:
    a) Set CO2_SPAIN_URL and/or GULLY_EUROPE_URL and re-run this script, OR
    b) Place the file(s) directly under $COG_DIR
       and re-run the script to verify.

The benchmark API will start without these files, but every analyze_area /
compare_areas / find_top_n call targeting co2_spain_legislation or
rf_gully_probability will fail until the COGs are present.

Source datasets and processing notes are documented in the paper (§3.1
"Benchmark Design", §3.4 "MLOps Pipeline") and in this script's header.
EOF
  exit 1
fi

if [[ $missing -eq 0 ]]; then
  echo "All required files are present."
else
  echo "Download complete. Verify with:"
  echo "  ls -lh $COG_DIR/"
fi
