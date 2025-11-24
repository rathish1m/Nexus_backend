from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    location = "static"
    default_acl = "public-read"


class PrivateMediaStorage(S3Boto3Storage):
    location = "private"
    default_acl = "private"
    file_overwrite = True
    custom_domain = False

    @property
    def querystring_auth(self):
        return True
