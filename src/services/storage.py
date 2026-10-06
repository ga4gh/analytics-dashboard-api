import logging
import os
import boto3

logger = logging.getLogger(__name__)

_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days


def upload_to_s3(content: bytes, filename: str) -> str:
    """
    Upload export file bytes to S3 and return a pre-signed download URL.

    Reads bucket and region from environment:
      EXPORT_S3_BUCKET  — required
      AWS_REGION        — optional, falls back to us-east-1

    Raises RuntimeError if EXPORT_S3_BUCKET is not set.
    Raises botocore.exceptions.BotoCoreError on AWS failures.
    """

    bucket = os.environ.get("EXPORT_S3_BUCKET")
    if not bucket:
        raise RuntimeError("EXPORT_S3_BUCKET environment variable is not set")

    region = os.environ.get("AWS_REGION", "us-east-1")
    s3 = boto3.client("s3", region_name=region)

    s3_key = f"exports/{filename}"
    s3.put_object(Bucket=bucket, Key=s3_key, Body=content)
    logger.info("S3 upload complete bucket=%s key=%s", bucket, s3_key)

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=_EXPIRY_SECONDS,
    )
    return url
