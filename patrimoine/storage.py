"""Supabase Storage (S3-compatible API) for user uploads in production."""

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class SupabasePublicS3Storage(S3Boto3Storage):
    """
    Write files via Supabase's S3 endpoint. Expose public HTTP URLs using the
    Storage REST path (bucket must allow public read).
    """

    file_overwrite = False

    def url(self, name):
        name = name.replace("\\", "/").lstrip("/")
        base = settings.SUPABASE_URL.rstrip("/")
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        return f"{base}/storage/v1/object/public/{bucket}/{name}"
