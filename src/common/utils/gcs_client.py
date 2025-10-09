# src/common/utils/gcs_client
from datetime import timedelta

import structlog
from google.auth import default as google_auth_default
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud.storage import Client, Bucket
from google.cloud.exceptions import GoogleCloudError

from src.common.utils.settings import settings
from src.core.exceptions import AppException

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
        # V4 signed URLs are the recommended version.
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),  # URL is valid for 15 minutes
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
