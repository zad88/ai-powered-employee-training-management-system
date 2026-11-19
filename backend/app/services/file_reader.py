"""Safe parsers for supported employee import formats."""

import csv
import json
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
MAX_IMPORT_ROWS = 10_000
MAX_EXCEL_UNCOMPRESSED_SIZE = 100 * 1024 * 1024
OLE_WORKBOOK_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class WorksheetSelectionRequired(ValueError):
    def __init__(self, sheet_names: list[str]):
        super().__init__("Select a worksheet before importing this workbook.")
        self.sheet_names = sheet_names


def _clean_value(value: Any) -> Any:
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if hasattr(value, "item"):
        return value.item()

    return value


def _validated_columns(raw_columns: list[Any]) -> list[str]:
    columns = [
        "" if column is None or pd.isna(column) else str(column).strip()
        for column in raw_columns
    ]

    if any(not column for column in columns):
        raise ValueError("The file contains an empty column or key name.")
    if len(columns) != len(set(columns)):
        raise ValueError("The file contains duplicate column or key names.")
    return columns


def _build_result(
    filename: str,
    extension: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    sheet_names: list[str] | None = None,
    worksheet: str | None = None,
) -> dict[str, Any]:
    if not columns:
        raise ValueError("The file does not contain any columns.")
    if not rows:
        raise ValueError("The file does not contain any data rows.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(
            f"The file exceeds the {MAX_IMPORT_ROWS:,}-row import limit."
        )

    return {
        "filename": Path(filename).name,
        "file_type": extension.lstrip("."),
        "columns": columns,
        "total_rows": len(rows),
        "rows": rows,
        "available_sheets": sheet_names or [],
        "worksheet": worksheet,
    }


def parse_csv_file(file_content: bytes, filename: str) -> dict[str, Any]:
    if not file_content:
        raise ValueError("The uploaded file is empty.")
    if b"\x00" in file_content:
        raise ValueError("The CSV file contains binary data.")
    if file_content.startswith((b"PK\x03\x04", OLE_WORKBOOK_SIGNATURE)):
        raise ValueError("The file content does not match the .csv extension.")

    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = file_content.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ValueError("The CSV file encoding is not supported.") from exc

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    if dialect.delimiter == "\t":
        raise ValueError("Tab-separated files are not supported; upload CSV.")

    reader = csv.reader(StringIO(text, newline=""), dialect, strict=True)
    try:
        raw_columns = next(reader, None)
        if raw_columns is None:
            raise ValueError("The CSV file does not contain a header row.")
        columns = _validated_columns(raw_columns)

        rows = []
        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) > len(columns):
                raise ValueError(
                    f"CSV row {reader.line_num} has more values than headers."
                )
            row.extend([None] * (len(columns) - len(row)))
            rows.append(dict(zip(columns, row)))
            if len(rows) > MAX_IMPORT_ROWS:
                raise ValueError(
                    f"The file exceeds the {MAX_IMPORT_ROWS:,}-row import limit."
                )
    except csv.Error as exc:
        raise ValueError("The CSV file is malformed.") from exc

    return _build_result(filename, ".csv", columns, rows)


def _check_xlsx_archive(file_content: bytes) -> None:
    if not file_content.startswith(b"PK\x03\x04"):
        raise ValueError("The file content does not match the .xlsx extension.")

    try:
        with zipfile.ZipFile(BytesIO(file_content)) as archive:
            members = archive.infolist()
            member_names = {member.filename for member in members}
            total_uncompressed_size = sum(member.file_size for member in members)
            if (
                "[Content_Types].xml" not in member_names
                or "xl/workbook.xml" not in member_names
            ):
                raise ValueError("The XLSX file is not a valid workbook.")
            if total_uncompressed_size > MAX_EXCEL_UNCOMPRESSED_SIZE:
                raise ValueError("The XLSX workbook expands beyond the safe limit.")
            for member in members:
                if (
                    member.file_size > 0
                    and (
                        member.compress_size == 0
                        or member.file_size / member.compress_size > 1000
                    )
                ):
                    raise ValueError("The XLSX workbook has unsafe compression.")
    except zipfile.BadZipFile as exc:
        raise ValueError("The XLSX file is malformed.") from exc


def _select_worksheet(
    sheet_names: list[str],
    sheet_name: str | None,
    *,
    require_selection: bool,
) -> str:
    if not sheet_names:
        raise ValueError("The Excel workbook does not contain worksheets.")
    if sheet_name is None:
        if require_selection and len(sheet_names) > 1:
            raise WorksheetSelectionRequired(sheet_names)
        return sheet_names[0]
    if sheet_name not in sheet_names:
        raise ValueError(
            "The selected worksheet does not exist in this workbook."
        )
    return sheet_name


def _raw_excel_headers(
    workbook: pd.ExcelFile,
    engine: str,
    sheet_name: str,
) -> list[Any]:
    if engine == "openpyxl":
        worksheet = workbook.book[sheet_name]
        first_row = next(
            worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
            (),
        )
        return list(first_row)
    return workbook.book.sheet_by_name(sheet_name).row_values(0)


def parse_excel_file(
    file_content: bytes,
    filename: str,
    *,
    sheet_name: str | None = None,
    require_sheet_selection: bool = False,
) -> dict[str, Any]:
    if not file_content:
        raise ValueError("The uploaded file is empty.")

    extension = Path(filename).suffix.lower()
    if extension == ".xlsx":
        _check_xlsx_archive(file_content)
        engine = "openpyxl"
    elif extension == ".xls":
        if not file_content.startswith(OLE_WORKBOOK_SIGNATURE):
            raise ValueError(
                "The file content does not match the .xls extension."
            )
        engine = "xlrd"
    else:
        raise ValueError("Only .xls and .xlsx workbooks are supported.")

    try:
        workbook = pd.ExcelFile(BytesIO(file_content), engine=engine)
        available_sheets = list(workbook.sheet_names)
        selected_sheet = _select_worksheet(
            available_sheets,
            sheet_name,
            require_selection=require_sheet_selection,
        )
        columns = _validated_columns(
            _raw_excel_headers(workbook, engine, selected_sheet)
        )
        dataframe = workbook.parse(sheet_name=selected_sheet)
    except WorksheetSelectionRequired:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The Excel workbook is malformed or unreadable.") from exc

    dataframe.columns = columns
    if len(dataframe.index) > MAX_IMPORT_ROWS:
        raise ValueError(
            f"The file exceeds the {MAX_IMPORT_ROWS:,}-row import limit."
        )

    rows = [
        {
            column: _clean_value(value)
            for column, value in row.items()
        }
        for row in dataframe.to_dict(orient="records")
    ]
    return _build_result(
        filename,
        extension,
        columns,
        rows,
        sheet_names=available_sheets,
        worksheet=selected_sheet,
    )


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"The JSON object contains duplicate key '{key}'.")
        result[key] = value
    return result


def parse_json_file(file_content: bytes, filename: str) -> dict[str, Any]:
    if not file_content:
        raise ValueError("The uploaded file is empty.")

    try:
        payload = json.loads(
            file_content.decode("utf-8-sig"),
            object_pairs_hook=_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The JSON file is malformed or not UTF-8 encoded.") from exc

    if not isinstance(payload, list) or not payload:
        raise ValueError(
            "JSON imports must be a non-empty array of employee objects."
        )
    if len(payload) > MAX_IMPORT_ROWS:
        raise ValueError(
            f"The file exceeds the {MAX_IMPORT_ROWS:,}-row import limit."
        )
    if any(not isinstance(item, dict) for item in payload):
        raise ValueError(
            "Every item in the JSON array must be an employee object."
        )

    columns = []
    for item in payload:
        for key, value in item.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("JSON object keys must be non-empty strings.")
            if isinstance(value, (dict, list)):
                raise ValueError(
                    "JSON employee objects must contain flat scalar values."
                )
            if key not in columns:
                columns.append(key)

    columns = _validated_columns(columns)
    rows = [
        {column: _clean_value(item.get(column)) for column in columns}
        for item in payload
    ]
    return _build_result(filename, ".json", columns, rows)


def read_tabular_file(
    file_content: bytes,
    filename: str,
    *,
    sheet_name: str | None = None,
    require_sheet_selection: bool = False,
) -> dict[str, Any]:
    """Parse a supported file into columns and flat records."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported file format. Upload CSV, XLSX, XLS, or JSON."
        )

    if extension == ".csv":
        return parse_csv_file(file_content, filename)
    if extension in {".xlsx", ".xls"}:
        return parse_excel_file(
            file_content,
            filename,
            sheet_name=sheet_name,
            require_sheet_selection=require_sheet_selection,
        )
    return parse_json_file(file_content, filename)
