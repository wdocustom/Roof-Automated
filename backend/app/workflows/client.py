"""Temporal client singleton — used to start and signal workflows."""

from temporalio.client import Client, TLSConfig

from app.core.config import settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    """Get or create the Temporal client (cached singleton)."""
    global _client
    if _client is not None:
        return _client

    tls_config = None
    if settings.temporal_tls_cert_path and settings.temporal_tls_key_path:
        with open(settings.temporal_tls_cert_path, "rb") as f:
            cert = f.read()
        with open(settings.temporal_tls_key_path, "rb") as f:
            key = f.read()
        tls_config = TLSConfig(client_cert=cert, client_private_key=key)

    _client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        tls=tls_config or False,
    )
    return _client
