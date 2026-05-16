# Self-hostable GeoNatureAgent API.
#
# Build:  docker build -t geonatureagent-api -f api/Dockerfile .
# Run:    docker run --rm -p 8080:8080 \
#           -e ANTHROPIC_API_KEY=sk-... \
#           -v "$PWD/api/data/cogs:/app/api/data/cogs:ro" \
#           geonatureagent-api
#
# The image is designed to run locally — there is no centrally-hosted public
# endpoint. See REPRODUCIBILITY.md for how to fetch the COG/JSON data
# files before launching.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOCAL_DEV_MODE=true \
    AGENT_PROMPT_VERSION=v3

# GDAL is required by rasterio / rio-tiler for COG reads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY api/ /app/api/

# Internal imports in this codebase use the flat form ``from agent.X`` and
# ``from cache_manager import ...`` — both are satisfied by running uvicorn
# from inside /app/api with ``main:app``. /app/api becomes sys.path[0].
WORKDIR /app/api
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
