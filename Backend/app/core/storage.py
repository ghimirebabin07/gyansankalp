from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class Storage:
    """Thin wrapper around an S3-compatible bucket. The bucket is always private."""

    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
                # Without these a dead endpoint holds a request thread open for
                # the 60 second default, and a few of those exhaust the pool.
                connect_timeout=settings.s3_connect_timeout_seconds,
                read_timeout=settings.s3_read_timeout_seconds,
            ),
        )

    def ensure_bucket(self) -> None:
        """Development helper. In production, create the bucket in the provider dashboard."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def ping(self) -> None:
        """Cheapest possible round trip, used by the readiness probe."""
        self.client.head_bucket(Bucket=self.bucket)

    def put_fileobj(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download_to_path(self, key: str, path: str) -> None:
        self.client.download_file(self.bucket, key, path)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(
                    Bucket=self.bucket, Delete={"Objects": objects}
                )


@lru_cache
def get_storage() -> Storage:
    return Storage()
