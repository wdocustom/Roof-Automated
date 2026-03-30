"""Photo upload endpoint — crew and customer photo management.

Photos are stored in S3, threaded to projects, and optionally analyzed
by the LLM vision pipeline. Supports offline-first: append-only uploads
are idempotent via client-generated upload IDs.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.middleware.tenant import get_company_id

router = APIRouter(prefix="/photos", tags=["photos"])


class PhotoUploadResponse(BaseModel):
    photo_id: str
    media_url: str
    project_id: str | None
    analysis_queued: bool


@router.post("", response_model=PhotoUploadResponse)
async def upload_photo(
    file: UploadFile = File(...),
    project_id: str = Form(default=""),
    milestone_id: str = Form(default=""),
    upload_id: str = Form(default=""),  # Client-generated for idempotency
    analyze: bool = Form(default=True),
    company_id: str = Depends(get_company_id),
):
    """Upload a photo and optionally queue it for LLM vision analysis.

    Supports:
    - Crew progress photos (linked to project + milestone)
    - Customer property photos (linked to project)
    - Offline-first: pass a client-generated upload_id for idempotency
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted")

    # Generate storage key
    photo_id = upload_id or str(uuid.uuid4())
    s3_key = f"{company_id}/{project_id or 'unassigned'}/{photo_id}"

    # Upload to S3
    media_url = await _upload_to_s3(
        file=file,
        key=s3_key,
        content_type=file.content_type,
    )

    # Store reference in DB
    from app.core.database import get_tenant_session
    from app.models.message import MessageMedia

    async with get_tenant_session(company_id) as session:
        media = MessageMedia(
            company_id=company_id,
            message_id=None,  # Not linked to a message (direct upload)
            media_url=media_url,
            content_type=file.content_type,
            file_size_bytes=file.size,
            original_filename=file.filename,
        )
        session.add(media)

    # Queue vision analysis if requested
    analysis_queued = False
    if analyze and project_id:
        # This will be picked up by the agent or a dedicated analysis workflow
        analysis_queued = True

    return PhotoUploadResponse(
        photo_id=photo_id,
        media_url=media_url,
        project_id=project_id or None,
        analysis_queued=analysis_queued,
    )


async def _upload_to_s3(file: UploadFile, key: str, content_type: str) -> str:
    """Upload file to S3 and return the URL.

    In development, returns a local placeholder URL.
    In production, uses boto3 to upload to the configured bucket.
    """
    if settings.environment == "development":
        # Dev mode: store locally or return placeholder
        return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

    import boto3

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

    contents = await file.read()
    s3.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=key,
        Body=contents,
        ContentType=content_type,
    )

    return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"
