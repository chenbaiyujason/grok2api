"""Cloudflare R2 文件上传下载工具"""

from typing import BinaryIO
from pathlib import Path
import aiofiles
from aioboto3 import Session  # type: ignore
from botocore.config import Config  # type: ignore

from .env import env

# R2 需要 SigV4 签名
S3_CONFIG = Config(signature_version="s3v4")


class R2Client:
    """Cloudflare R2 异步客户端"""

    def __init__(
        self,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str | None = None,
    ):
        """
        初始化 R2 客户端

        Args:
            endpoint_url: R2 端点 URL
            access_key_id: 访问密钥 ID
            secret_access_key: 机密访问密钥
            bucket_name: 存储桶名称（可选）
        """
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket_name = bucket_name
        self.session = Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    async def upload_file(
        self,
        file_path: str | Path,
        object_key: str,
        bucket_name: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """
        上传文件到 R2

        Args:
            file_path: 本地文件路径
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
            content_type: 内容类型（可选）

        Returns:
            上传后的对象键
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            # 设置缓存控制头：缓存 1 年（图片和视频资源通常不会改变）
            extra_args["CacheControl"] = "public, max-age=31536000, immutable"

            async with aiofiles.open(file_path, "rb") as f:
                file_data = await f.read()
                await s3_client.put_object(
                    Bucket=bucket,
                    Key=object_key,
                    Body=file_data,
                    **extra_args,
                )

        return object_key

    async def upload_fileobj(
        self,
        file_obj: bytes | BinaryIO,
        object_key: str,
        bucket_name: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """
        上传文件对象到 R2

        Args:
            file_obj: 文件对象或字节数据
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
            content_type: 内容类型（可选）

        Returns:
            上传后的对象键
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            # 设置缓存控制头：缓存 1 年（图片和视频资源通常不会改变）
            extra_args["CacheControl"] = "public, max-age=31536000, immutable"

            await s3_client.put_object(Bucket=bucket, Key=object_key, Body=file_obj, **extra_args)

        return object_key

    async def download_file(
        self,
        object_key: str,
        file_path: str | Path,
        bucket_name: str | None = None,
    ) -> Path:
        """
        从 R2 下载文件

        Args:
            object_key: R2 对象键（文件名）
            file_path: 本地保存路径
            bucket_name: 存储桶名称（如果未指定则使用默认值）

        Returns:
            下载后的文件路径
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            response = await s3_client.get_object(Bucket=bucket, Key=object_key)
            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in response["Body"]:
                    await f.write(chunk)

        return file_path

    async def download_fileobj(self, object_key: str, bucket_name: str | None = None) -> bytes:
        """
        从 R2 下载文件为字节数据

        Args:
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）

        Returns:
            文件字节数据
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            response = await s3_client.get_object(Bucket=bucket, Key=object_key)
            data = await response["Body"].read()
            return data

    async def delete_file(self, object_key: str, bucket_name: str | None = None) -> None:
        """
        从 R2 删除文件

        Args:
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            await s3_client.delete_object(Bucket=bucket, Key=object_key)

    async def list_files(
        self,
        prefix: str = "",
        bucket_name: str | None = None,
        max_keys: int = 1000,
    ) -> list[str]:
        """
        列出 R2 中的文件

        Args:
            prefix: 对象键前缀（可选）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
            max_keys: 最大返回数量

        Returns:
            对象键列表
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            response = await s3_client.list_objects_v2(
                Bucket=bucket, Prefix=prefix, MaxKeys=max_keys
            )
            contents = response.get("Contents", [])
            return [obj["Key"] for obj in contents]

    async def get_file_url(
        self,
        object_key: str,
        bucket_name: str | None = None,
        expires_in: int = 3600,
    ) -> str:
        """
        获取文件的预签名 URL

        Args:
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
            expires_in: URL 过期时间（秒）

        Returns:
            预签名 URL
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            url = await s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
            return url

    async def get_upload_url(
        self,
        object_key: str,
        bucket_name: str | None = None,
        expires_in: int = 3600,
        content_type: str | None = None,
    ) -> str:
        """
        获取上传文件的预签名 URL

        Args:
            object_key: R2 对象键（文件名）
            bucket_name: 存储桶名称（如果未指定则使用默认值）
            expires_in: URL 过期时间（秒）
            content_type: 内容类型（可选）

        Returns:
            上传用的预签名 URL
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("未指定存储桶名称")

        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=S3_CONFIG,
        ) as s3_client:
            params = {"Bucket": bucket, "Key": object_key}
            if content_type:
                params["ContentType"] = content_type

            # 设置缓存控制头：缓存 1 年（图片和视频资源通常不会改变）
            params["CacheControl"] = "public, max-age=31536000, immutable"

            url = await s3_client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return url


# 预配置的客户端实例（从环境变量读取凭据）
def _get_default_client() -> R2Client:
    """获取默认 R2 客户端实例"""
    if not all([env.r2_endpoint_url, env.r2_access_key_id, env.r2_secret_access_key]):
        raise ValueError(
            "R2 配置不完整，请在 .env 文件中设置 R2_ENDPOINT_URL, "
            "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
        )

    return R2Client(
        endpoint_url=env.r2_endpoint_url,  # type: ignore
        access_key_id=env.r2_access_key_id,  # type: ignore
        secret_access_key=env.r2_secret_access_key,  # type: ignore
        bucket_name=env.r2_bucket_name,
    )


_default_client: R2Client | None = None


def _ensure_client() -> R2Client:
    """确保客户端已初始化"""
    global _default_client
    if _default_client is None:
        _default_client = _get_default_client()
    return _default_client


# 便捷函数
async def upload_file(
    file_path: str | Path,
    object_key: str,
    content_type: str | None = None,
) -> str:
    """上传文件到默认 R2 存储桶"""
    client = _ensure_client()
    return await client.upload_file(file_path, object_key, content_type=content_type)


async def upload_fileobj(
    file_obj: bytes | BinaryIO,
    object_key: str,
    content_type: str | None = None,
) -> str:
    """上传文件对象到默认 R2 存储桶"""
    client = _ensure_client()
    return await client.upload_fileobj(file_obj, object_key, content_type=content_type)


async def download_file(object_key: str, file_path: str | Path) -> Path:
    """从默认 R2 存储桶下载文件"""
    client = _ensure_client()
    return await client.download_file(object_key, file_path)


async def download_fileobj(object_key: str) -> bytes:
    """从默认 R2 存储桶下载文件为字节数据"""
    client = _ensure_client()
    return await client.download_fileobj(object_key)


async def delete_file(object_key: str) -> None:
    """从默认 R2 存储桶删除文件"""
    client = _ensure_client()
    await client.delete_file(object_key)


async def list_files(prefix: str = "", max_keys: int = 1000) -> list[str]:
    """列出默认 R2 存储桶中的文件"""
    client = _ensure_client()
    return await client.list_files(prefix, max_keys=max_keys)


async def get_file_url(object_key: str, expires_in: int = 3600) -> str:
    """获取默认 R2 存储桶中文件的预签名 URL"""
    client = _ensure_client()
    return await client.get_file_url(object_key, expires_in=expires_in)


async def get_upload_url(
    object_key: str,
    expires_in: int = 3600,
    content_type: str | None = None,
) -> str:
    """获取默认 R2 存储桶的上传预签名 URL"""
    client = _ensure_client()
    return await client.get_upload_url(object_key, expires_in=expires_in, content_type=content_type)


def get_public_url(object_key: str) -> str:
    """
    获取文件的公开访问 URL（需要配置 R2_PUBLIC_URL 环境变量）

    Args:
        object_key: R2 对象键（文件名）

    Returns:
        公开访问 URL
    """
    if not env.r2_public_url:
        raise ValueError("未配置 R2_PUBLIC_URL，请在 .env 文件中设置")

    # 移除末尾的斜杠
    public_url = env.r2_public_url.rstrip("/")
    # 移除开头的斜杠
    object_key = object_key.lstrip("/")

    return f"{public_url}/{object_key}"
