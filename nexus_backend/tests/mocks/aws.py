"""
AWS S3/Spaces Storage Mock
==========================

Mock implementation of AWS S3 (DigitalOcean Spaces) for testing file uploads.

Usage:
-----
@pytest.fixture
def mock_s3(monkeypatch):
    mock = AWSS3Mock()
    monkeypatch.setattr('boto3.client', lambda *args, **kwargs: mock)
    return mock
"""

import hashlib
import io
from datetime import datetime
from typing import BinaryIO, Dict, List, Optional


class AWSS3Mock:
    """Mock AWS S3/DigitalOcean Spaces client"""

    def __init__(self):
        self.buckets: Dict[str, Dict[str, bytes]] = {}
        self.uploaded_files: List[Dict] = []

    def create_bucket(self, Bucket: str, **kwargs):
        """Create a bucket"""
        if Bucket not in self.buckets:
            self.buckets[Bucket] = {}
        return {"Location": f"/{Bucket}"}

    def put_object(self, Bucket: str, Key: str, Body: BinaryIO, **kwargs) -> Dict:
        """Upload object to bucket"""
        if Bucket not in self.buckets:
            self.create_bucket(Bucket=Bucket)

        # Read content
        if isinstance(Body, bytes):
            content = Body
        elif hasattr(Body, "read"):
            content = Body.read()
        else:
            content = str(Body).encode("utf-8")

        # Store file
        self.buckets[Bucket][Key] = content

        # Calculate ETag
        etag = hashlib.md5(content).hexdigest()

        # Record upload
        self.uploaded_files.append(
            {
                "bucket": Bucket,
                "key": Key,
                "size": len(content),
                "etag": etag,
                "uploaded_at": datetime.now().isoformat(),
                "content_type": kwargs.get("ContentType", "application/octet-stream"),
                "acl": kwargs.get("ACL", "private"),
            }
        )

        return {"ETag": etag, "VersionId": "null"}

    def get_object(self, Bucket: str, Key: str) -> Dict:
        """Get object from bucket"""
        if Bucket not in self.buckets:
            raise Exception(f"Bucket {Bucket} does not exist")

        if Key not in self.buckets[Bucket]:
            raise Exception(f"Key {Key} does not exist in bucket {Bucket}")

        content = self.buckets[Bucket][Key]

        return {
            "Body": io.BytesIO(content),
            "ContentLength": len(content),
            "ETag": hashlib.md5(content).hexdigest(),
            "LastModified": datetime.now(),
            "ContentType": "application/octet-stream",
        }

    def delete_object(self, Bucket: str, Key: str) -> Dict:
        """Delete object from bucket"""
        if Bucket in self.buckets and Key in self.buckets[Bucket]:
            del self.buckets[Bucket][Key]

        return {"DeleteMarker": False}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", **kwargs) -> Dict:
        """List objects in bucket"""
        if Bucket not in self.buckets:
            return {"Contents": [], "KeyCount": 0}

        contents = []
        for key, content in self.buckets[Bucket].items():
            if key.startswith(Prefix):
                contents.append(
                    {
                        "Key": key,
                        "Size": len(content),
                        "ETag": hashlib.md5(content).hexdigest(),
                        "LastModified": datetime.now(),
                    }
                )

        return {
            "Contents": contents,
            "KeyCount": len(contents),
            "Name": Bucket,
            "Prefix": Prefix,
        }

    def head_object(self, Bucket: str, Key: str) -> Dict:
        """Get object metadata"""
        if Bucket not in self.buckets or Key not in self.buckets[Bucket]:
            raise Exception("Not Found")

        content = self.buckets[Bucket][Key]

        return {
            "ContentLength": len(content),
            "ETag": hashlib.md5(content).hexdigest(),
            "LastModified": datetime.now(),
            "ContentType": "application/octet-stream",
        }

    def generate_presigned_url(
        self, ClientMethod: str, Params: Dict, ExpiresIn: int = 3600
    ) -> str:
        """Generate presigned URL"""
        bucket = Params.get("Bucket", "")
        key = Params.get("Key", "")
        return f"https://s3.amazonaws.com/{bucket}/{key}?expires={ExpiresIn}"

    def upload_fileobj(self, Fileobj: BinaryIO, Bucket: str, Key: str, **kwargs):
        """Upload file object"""
        return self.put_object(Bucket=Bucket, Key=Key, Body=Fileobj, **kwargs)

    def download_fileobj(self, Bucket: str, Key: str, Fileobj: BinaryIO):
        """Download file object"""
        obj = self.get_object(Bucket=Bucket, Key=Key)
        Fileobj.write(obj["Body"].read())

    def copy_object(self, Bucket: str, Key: str, CopySource: Dict) -> Dict:
        """Copy object"""
        source_bucket = CopySource["Bucket"]
        source_key = CopySource["Key"]

        if (
            source_bucket not in self.buckets
            or source_key not in self.buckets[source_bucket]
        ):
            raise Exception("Source not found")

        content = self.buckets[source_bucket][source_key]
        return self.put_object(Bucket=Bucket, Key=Key, Body=content)

    def get_uploaded_files(self, bucket: Optional[str] = None) -> List[Dict]:
        """Get all uploaded files"""
        if bucket:
            return [f for f in self.uploaded_files if f["bucket"] == bucket]
        return self.uploaded_files

    def file_exists(self, bucket: str, key: str) -> bool:
        """Check if file exists"""
        return bucket in self.buckets and key in self.buckets[bucket]

    def get_file_content(self, bucket: str, key: str) -> Optional[bytes]:
        """Get file content"""
        if self.file_exists(bucket, key):
            return self.buckets[bucket][key]
        return None

    def reset(self):
        """Reset all mock data"""
        self.buckets = {}
        self.uploaded_files = []
