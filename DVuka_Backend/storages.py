import os

from storages.backends.s3boto3 import S3Boto3Storage

class MediaStorage(S3Boto3Storage):
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME", "e-vuka")
    default_acl = "public-read"
    querystring_auth = False
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL", "http://localhost:9000")
    use_ssl = False
    verify = False

class StaticStorage(S3Boto3Storage):
    bucket_name = os.getenv("AWS_STATIC_BUCKET_NAME", "e-vuka-static")
    default_acl = "public-read"
    querystring_auth = False
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL", "http://localhost:9000")
    use_ssl = False
    verify = False
