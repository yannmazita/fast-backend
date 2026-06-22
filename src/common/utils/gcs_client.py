# src/common/utils/gcs_client
from asyncio import to_thread
from datetime import timedelta
from urllib.parse import urlparse

from google.api_core.retry import Retry
import structlog
from google.auth import default as google_auth_default
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud.storage import Bucket, Client
from pydantic import HttpUrl

from src.common.utils.settings import settings
from src.core.exceptions import BadRequestError

logger = structlog.get_logger(__name__)


class GCSClient:
    """A client for interacting with Google Cloud Storage (GCS).

    This class provides methods for generating signed URLs and managing
    objects in a GCS bucket. It can be configured to use impersonated
    credentials for enhanced security.

    Attributes:
        client: The authenticated `google.cloud.storage.Client` instance.
        bucket_name: The name of the GCS bucket to interact with.
        bucket: The `google.cloud.storage.Bucket` object.
    """

    def __init__(self):
        """Initializes the GCSClient.

        Sets up the GCS client, using impersonated service account
        credentials if `gcs_signer_service_account_email` is set in the
        application settings.
        """
        # Use impersonated credentials if a signer email is provided
        credentials = None
        if settings.gcs_signer_service_account_email:
            logger.info(
                f"Using impersonated credentials for GCS signing via SA: {settings.gcs_signer_service_account_email}"
            )
            # Get the default credentials from the environment (ie the Cloud Run SA token)
            source_credentials, _ = google_auth_default()
            # Create impersonated credentials targeting the signer SA
            credentials = ImpersonatedCredentials(
                source_credentials=source_credentials,
                target_principal=settings.gcs_signer_service_account_email,
                target_scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
            )
        else:
            logger.warning(
                "gcs_signer_service_account_email not set. Using default credentials. URL signing may fail."
            )

        # Initialize the client with the impersonated credentials if they exist,
        # otherwise it will use the default behavior.
        self.client: Client = Client(credentials=credentials)
        self.bucket_name: str = settings.uploads_gcs_bucket_name
        self.bucket: Bucket = self.client.bucket(self.bucket_name)
        logger.info(f"GCS client initialized for bucket '{self.bucket_name}'.")

    def generate_upload_presigned_url(self, blob_name: str, content_type: str) -> str:
        """Generates a V4 presigned URL for uploading a file via PUT.

        Args:
            blob_name: The full path for the object in the GCS bucket.
            content_type: The MIME type of the file to be uploaded.

        Returns:
            The V4 presigned URL.
        """
        blob = self.bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=settings.upload_url_expiration_minutes),
            method="PUT",
            content_type=content_type,
        )
        logger.debug(f"Generated V4 presigned PUT URL for blob: {blob_name}")
        return url

    def delete_blob(self, blob_name: str):
        """Deletes a blob from the GCS bucket.

        Args:
            blob_name: The full path of the object to delete.
        """
        blob = self.bucket.blob(blob_name)
        blob.delete()
        logger.info(f"Successfully deleted blob '{blob_name}' from GCS.")

    def validate_and_extract_blob_name(self, image_url: HttpUrl) -> str:
        """
        Validates that an image URL points to this GCS bucket and extracts
        the corresponding blob name.

        Args:
            image_url: The public GCS asset URL to validate.

        Returns:
            The GCS blob path extracted from the URL.

        Raises:
            BadRequestError: If the URL does not belong to the configured
                GCS asset bucket.
        """
        expected = urlparse(settings.gcs_asset_url)
        actual = urlparse(str(image_url))

        blob_name = actual.path.removeprefix(f"{expected.path}/")

        if not blob_name:
            raise BadRequestError("Invalid image URL.")

        if (
            actual.scheme != expected.scheme
            or actual.netloc != expected.netloc
            or not actual.path.startswith(f"{expected.path}/")
        ):
            raise BadRequestError(
                "Invalid image_url. Must be from the official upload bucket."
            )

        return actual.path.removeprefix(f"{expected.path}/")

    async def validate_uploaded_image(
        self,
        image_url: HttpUrl,
    ) -> str:
        """
        Validate an uploaded image URL and return its GCS blob name.

        Ensures the URL belongs to the configured GCS asset bucket,
        the object exists, and the uploaded file satisfies image constraints.

        Args:
            image_url: Public URL of the uploaded image.

        Returns:
            The GCS blob name.

        Raises:
            BadRequestError:
                If the URL is invalid, the object does not exist,
                or the uploaded file does not meet validation rules.
        """
        blob_name = self.validate_and_extract_blob_name(image_url)

        blob = self.bucket.blob(blob_name)

        exists = await to_thread(lambda: blob.exists(retry=Retry(deadline=5)))

        if not exists:
            raise BadRequestError("Image file not found.")

        await to_thread(lambda: blob.reload(retry=Retry(deadline=5)))

        if not blob.content_type or not blob.content_type.startswith("image/"):
            raise BadRequestError("Uploaded file is not an image.")

        if blob.size and blob.size > settings.max_image_size:
            raise BadRequestError("Image exceeds maximum size.")

        return blob_name
