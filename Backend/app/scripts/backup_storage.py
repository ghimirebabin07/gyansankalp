"""Copy the private object-storage bucket somewhere else.

pg_dump covers the database. The PDFs and the rendered page images live in
object storage, and losing that bucket means the admin has to re-upload every
course from scratch - so it needs a copy too.

    python -m app.scripts.backup_storage --dest-bucket gyansankalp-backups
    python -m app.scripts.backup_storage --dest-bucket gyansankalp-backups --dry-run

Re-running only copies what is missing or a different size, so it is safe on a
schedule. For Cloudflare R2 / Backblaze B2, set DEST_S3_* environment variables
to point at the second account; they default to the source credentials.
"""

import argparse
import os
import sys

import boto3

from app.core.config import settings


def _client(endpoint, access_key, secret_key):
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=settings.s3_region,
    )


def _list_objects(client, bucket):
    """Yield (key, size) for every object, paging through the response."""
    token = None
    while True:
        params = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            params["ContinuationToken"] = token
        page = client.list_objects_v2(**params)
        for item in page.get("Contents", []):
            yield item["Key"], item["Size"]
        if not page.get("IsTruncated"):
            return
        token = page["NextContinuationToken"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest-bucket", required=True)
    parser.add_argument("--src-bucket", default=settings.s3_bucket)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src = _client(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key)
    dest = _client(
        os.getenv("DEST_S3_ENDPOINT_URL", settings.s3_endpoint_url),
        os.getenv("DEST_S3_ACCESS_KEY", settings.s3_access_key),
        os.getenv("DEST_S3_SECRET_KEY", settings.s3_secret_key),
    )

    dest_sizes = dict(_list_objects(dest, args.dest_bucket))
    copied = skipped = missing = 0

    for key, size in _list_objects(src, args.src_bucket):
        if key in dest_sizes:
            if dest_sizes[key] == size:
                skipped += 1
                continue
            action = "replace"
        else:
            action = "copy"
            missing += 1
        if args.dry_run:
            print(f"{action} {key} ({size} bytes)")
            continue
        dest.copy_object(
            Bucket=args.dest_bucket,
            Key=key,
            CopySource={"Bucket": args.src_bucket, "Key": key},
        )
        copied += 1

    print(f"copied={copied} already-present={skipped} missing_before={missing}")
    if args.dry_run:
        return 0

    # Prove the copy rather than trusting the loop count.
    after = dict(_list_objects(dest, args.dest_bucket))
    mismatches = [
        key for key, size in _list_objects(src, args.src_bucket)
        if after.get(key) != size
    ]
    if mismatches:
        print(f"{len(mismatches)} object(s) did not land, first few: {mismatches[:5]}", file=sys.stderr)
        return 1
    print(f"verified: {len(after)} objects in {args.dest_bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
