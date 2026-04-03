from __future__ import annotations

from typing import Any

from aioboto3 import Session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from config.settings import Settings
from storage.chart_storage import (
    ChartStorage,
    ChartStorageError,
    StoredChartBinary,
    StoredChartObject,
)


class S3ChartStorage(ChartStorage):
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        use_ssl: bool,
        force_path_style: bool,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._region = region
        self._bucket = bucket
        self._session = Session()
        self._client_config = Config(
            s3={"addressing_style": "path" if force_path_style else "virtual"},
        )
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._use_ssl = use_ssl

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ChartStorage:
        return cls(
            endpoint_url=settings.chart_storage_endpoint_url,
            region=settings.chart_storage_region,
            bucket=settings.chart_storage_bucket,
            access_key_id=settings.chart_storage_access_key_id.get_secret_value(),
            secret_access_key=settings.chart_storage_secret_access_key.get_secret_value(),
            use_ssl=settings.chart_storage_use_ssl,
            force_path_style=settings.chart_storage_force_path_style,
        )

    async def ensure_ready(self) -> None:
        try:
            async with self._client() as client:
                await client.head_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError) as error:
            raise ChartStorageError(
                f"Chart storage bucket '{self._bucket}' is not reachable."
            ) from error

    async def put_chart(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> StoredChartObject:
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=self._bucket,
                    Key=object_key,
                    Body=content,
                    ContentType=content_type,
                )
        except (BotoCoreError, ClientError) as error:
            raise ChartStorageError("Failed to upload chart binary.") from error

        return StoredChartObject(
            bucket=self._bucket,
            key=object_key,
            size_bytes=len(content),
            content_type=content_type,
        )

    async def get_chart(self, *, bucket: str, object_key: str) -> StoredChartBinary:
        try:
            async with self._client() as client:
                response = await client.get_object(Bucket=bucket, Key=object_key)
                body = response["Body"]
                payload = await body.read()
                content_type = str(response.get("ContentType") or "application/octet-stream")
        except (BotoCoreError, ClientError) as error:
            raise ChartStorageError("Failed to retrieve chart binary.") from error

        return StoredChartBinary(
            content=payload,
            content_type=content_type,
        )

    async def delete_chart(self, *, bucket: str, object_key: str) -> None:
        try:
            async with self._client() as client:
                await client.delete_object(Bucket=bucket, Key=object_key)
        except (BotoCoreError, ClientError):
            # Cleanup is best-effort to avoid masking the primary error.
            return None

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            use_ssl=self._use_ssl,
            config=self._client_config,
        )
