"""Shared helpers for admin bulk-import endpoints.

Enforces the limits the import handlers were missing: a bounded read (so a
giant or zip-bomb-shaped .xlsx can't OOM the process), a real magic-byte
check (xlsx is a zip), and a hard row cap.
"""
import io

from fastapi import UploadFile
from openpyxl import load_workbook

from app.core.config import settings
from app.core.exceptions import BadRequestException

# No import may exceed this many data rows. Matches EXPORT_ROW_CAP so a
# round-trip export→edit→import stays within bounds.
MAX_IMPORT_ROWS = 5000

# xlsx (OOXML) files are zip containers.
_XLSX_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


async def load_xlsx_bounded(file: UploadFile, *, data_only: bool = False):
    """Read and open an uploaded .xlsx with size + type guards. Returns the
    active worksheet."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise BadRequestException(code="INVALID_FILE_TYPE", message="Only .xlsx files are accepted")

    max_bytes = settings.max_file_size_bytes
    contents = await file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise BadRequestException(
            code="FILE_TOO_LARGE",
            message=f"File size exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
        )
    if not contents.startswith(_XLSX_MAGIC):
        raise BadRequestException(
            code="INVALID_FILE",
            message="The uploaded file is not a valid .xlsx workbook",
        )

    try:
        wb = load_workbook(filename=io.BytesIO(contents), read_only=True, data_only=data_only)
    except Exception:
        raise BadRequestException(
            code="INVALID_FILE",
            message="Could not parse the uploaded file as a valid Excel workbook",
        )

    ws = wb.active
    if ws is None:
        raise BadRequestException(code="EMPTY_FILE", message="The workbook has no active sheet")
    return ws


def read_rows_capped(ws, cap: int = MAX_IMPORT_ROWS) -> list:
    """Materialise rows but refuse a sheet with more than `cap` data rows,
    checked as we stream so a million-row sheet is rejected before it's all in
    memory."""
    rows: list = []
    for row in ws.iter_rows(values_only=True):
        rows.append(row)
        if len(rows) > cap + 1:  # +1 header
            raise BadRequestException(
                code="TOO_MANY_ROWS",
                message=f"Import is limited to {cap} rows per file",
            )
    if len(rows) < 2:
        raise BadRequestException(
            code="EMPTY_FILE",
            message="The file must contain a header row and at least one data row",
        )
    return rows
