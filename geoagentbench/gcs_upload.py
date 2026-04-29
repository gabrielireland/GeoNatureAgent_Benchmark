"""GCS auto-upload for benchmark output directories.

Uploads all files from a local directory to a GCS prefix.
All operations are non-fatal — failures log warnings but never block the run.
"""

import warnings
from pathlib import Path
from typing import Optional


def upload_directory(
    local_dir: str,
    bucket_name: str,
    prefix: str,
    experiment_id: str,
    run_id: str = "",
) -> Optional[str]:
    """Upload all files in *local_dir* to GCS.

    When *run_id* is provided, uploads to ``gs://<bucket>/<prefix>/<experiment_id>/<run_id>/``
    for per-run isolation. When empty, uses flat ``gs://<bucket>/<prefix>/<experiment_id>/``.

    Returns the GCS URI on success, or None on failure.
    """
    if not bucket_name:
        return None

    try:
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        local_path = Path(local_dir)

        parts = [p for p in (prefix, experiment_id, run_id) if p]
        gcs_prefix = "/".join(parts).strip("/")

        uploaded = 0
        for file in sorted(local_path.rglob("*")):
            if not file.is_file():
                continue
            blob_name = f"{gcs_prefix}/{file.relative_to(local_path)}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(file))
            uploaded += 1

        gcs_uri = f"gs://{bucket_name}/{gcs_prefix}/"
        print(f"  GCS upload: {uploaded} files -> {gcs_uri}")
        return gcs_uri
    except Exception as exc:
        warnings.warn(f"GCS upload failed (non-fatal): {exc}", stacklevel=2)
        return None
