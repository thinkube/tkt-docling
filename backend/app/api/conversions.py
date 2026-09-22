# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""PDF conversions: upload, follow, download, delete.

Every route takes a Thinkube Identity token or one of this application's API
tokens, so scripts call the same API as the web page.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.api_tokens import get_current_user_dual_auth
from app.core.config import settings
from app.db.session import get_db
from app.models.conversion import TERMINAL, Conversion, ConversionStatus
from app.services import storage, workflows
from converter.formats import FORMATS, PIPELINES

router = APIRouter()

PHASES = {
    "Pending": ConversionStatus.QUEUED,
    "Running": ConversionStatus.RUNNING,
    "Succeeded": ConversionStatus.SUCCEEDED,
    "Failed": ConversionStatus.FAILED,
    "Error": ConversionStatus.FAILED,
}


class FormatInfo(BaseModel):
    name: str
    filename: str
    description: str


class PipelineInfo(BaseModel):
    name: str
    description: str
    available: bool
    unavailable_reason: Optional[str] = None


class Options(BaseModel):
    formats: List[FormatInfo]
    pipelines: List[PipelineInfo]
    max_upload_mb: int


class ConversionOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    pipeline: str
    formats: List[str]
    status: ConversionStatus
    error: Optional[str] = None
    pages: Optional[int] = None
    seconds: Optional[float] = None
    workflow_name: Optional[str] = None
    logs_url: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    @classmethod
    def of(cls, c: Conversion) -> "ConversionOut":
        return cls(
            id=c.id, filename=c.filename, size_bytes=c.size_bytes, pipeline=c.pipeline,
            formats=c.formats, status=c.status, error=c.error, pages=c.pages, seconds=c.seconds,
            workflow_name=c.workflow_name,
            logs_url=workflows.logs_url(c.workflow_name) if c.workflow_name else None,
            created_at=c.created_at, finished_at=c.finished_at,
        )


def granite_refusal() -> Optional[str]:
    if not settings.THINKUBE_API_TOKEN:
        return (
            "THINKUBE_API_TOKEN is not set. Create an API token in thinkube-control, "
            "add it as THINKUBE_API_TOKEN on the Secrets page, and redeploy this app."
        )
    return None


@router.get("/options", response_model=Options)
async def options(current_user: dict = Depends(get_current_user_dual_auth)):
    """The pipelines and output formats a conversion can ask for."""
    pipelines = []
    for name, description in PIPELINES.items():
        reason = granite_refusal() if name == "granite-docling" else None
        pipelines.append(PipelineInfo(name=name, description=description, available=reason is None,
                                      unavailable_reason=reason))
    return Options(
        formats=[FormatInfo(name=f.name, filename=f.filename, description=f.description) for f in FORMATS.values()],
        pipelines=pipelines,
        max_upload_mb=settings.MAX_UPLOAD_MB,
    )


@router.post("", response_model=ConversionOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ConversionOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_conversion(
    file: UploadFile = File(...),
    pipeline: str = Form(...),
    formats: str = Form(..., description="Comma-separated format names"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """Upload a PDF and start its conversion."""
    if pipeline not in PIPELINES:
        raise HTTPException(422, f"Unknown pipeline '{pipeline}'. Known: {', '.join(PIPELINES)}")
    if pipeline == "granite-docling" and granite_refusal():
        raise HTTPException(409, granite_refusal())

    names = [n.strip() for n in formats.split(",") if n.strip()]
    unknown = [n for n in names if n not in FORMATS]
    if not names or unknown:
        raise HTTPException(422, f"formats must name one or more of {', '.join(FORMATS)}; unknown: {unknown}")

    if not file.filename:
        raise HTTPException(422, "The upload has no file name")
    data = await file.read()
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, f"'{file.filename}' is not a PDF")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"'{file.filename}' is larger than {settings.MAX_UPLOAD_MB} MB")

    conversion = Conversion(
        user_id=current_user["sub"],
        filename=file.filename,
        size_bytes=len(data),
        pipeline=pipeline,
        formats=names,
    )
    db.add(conversion)
    db.flush()

    storage.put_source(conversion.id, data)
    conversion.workflow_name = workflows.submit(conversion.id, pipeline, names)
    db.commit()
    db.refresh(conversion)
    return ConversionOut.of(conversion)


def _refresh(conversion: Conversion, db: Session) -> Conversion:
    """Bring a running conversion up to date with its workflow."""
    if conversion.status in TERMINAL or not conversion.workflow_name:
        return conversion
    state = workflows.state(conversion.workflow_name)
    if state is None:
        # Finished runs are removed after a day; what the run left in storage
        # says how it ended.
        state = workflows.WorkflowState(
            phase="Succeeded" if storage.read_result(conversion.id) is not None else "Failed",
            message=f"Workflow {conversion.workflow_name} was removed before its result was read",
        )
    if state.phase not in PHASES:
        raise HTTPException(502, f"Workflow {conversion.workflow_name} reports an unknown phase '{state.phase}'")
    new_status = PHASES[state.phase]
    if new_status == ConversionStatus.SUCCEEDED:
        result = storage.read_result(conversion.id)
        if result is None:
            new_status = ConversionStatus.FAILED
            conversion.error = "The workflow succeeded but wrote no result.json"
        else:
            conversion.pages = result["pages"]
            conversion.seconds = result["seconds"]
            if result.get("errors"):
                conversion.error = "; ".join(result["errors"])
    elif new_status == ConversionStatus.FAILED:
        conversion.error = state.message or f"Workflow {state.phase}"
    if new_status != conversion.status:
        conversion.status = new_status
        if new_status in TERMINAL:
            conversion.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(conversion)
    return conversion


def _owned(conversion_id: str, db: Session, user: dict) -> Conversion:
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id, Conversion.user_id == user["sub"]
    ).first()
    if not conversion:
        raise HTTPException(404, "Conversion not found")
    return conversion


@router.get("", response_model=List[ConversionOut])
@router.get("/", response_model=List[ConversionOut], include_in_schema=False)
async def list_conversions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """The caller's conversions, newest first."""
    rows = (
        db.query(Conversion)
        .filter(Conversion.user_id == current_user["sub"])
        .order_by(Conversion.created_at.desc())
        .all()
    )
    return [ConversionOut.of(_refresh(c, db)) for c in rows]


@router.get("/{conversion_id}", response_model=ConversionOut)
async def get_conversion(
    conversion_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    return ConversionOut.of(_refresh(_owned(conversion_id, db, current_user), db))


@router.get("/{conversion_id}/outputs/{format_name}")
async def download_output(
    conversion_id: str,
    format_name: str,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """One output of a finished conversion."""
    conversion = _refresh(_owned(conversion_id, db, current_user), db)
    if format_name not in conversion.formats:
        raise HTTPException(404, f"This conversion did not produce '{format_name}'")
    if conversion.status != ConversionStatus.SUCCEEDED:
        raise HTTPException(409, f"The conversion is {conversion.status.value}")
    fmt = FORMATS[format_name]
    chunks = storage.open_output(conversion.id, fmt.filename)
    if chunks is None:
        raise HTTPException(404, f"{fmt.filename} is not in storage")
    stem = conversion.filename.rsplit(".", 1)[0]
    extension = fmt.filename.split(".", 1)[1]
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        chunks,
        media_type=fmt.media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{stem}.{extension}"'},
    )


@router.delete("/{conversion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversion(
    conversion_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """Delete the conversion, its PDF and its outputs."""
    conversion = _owned(conversion_id, db, current_user)
    storage.delete_conversion(conversion.id)
    db.delete(conversion)
    db.commit()
