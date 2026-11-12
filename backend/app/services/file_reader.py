"""Utilities for reading uploaded CSV and Excel files."""

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


def _clean_value(value: Any) -> Any:
    """Convert pandas and NumPy values into Python-friendly values."""
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if hasattr(value, "item"):
        return value.item()

    return value


def read_tabular_file(file_content: bytes, filename: str) -> dict:
    """
    Read a CSV or XLSX file and return standardized tabular data.

    Returns:
        {
            "filename": str,
            "file_type": str,
            "columns": list[str],
            "total_rows": int,
            "rows": list[dict]
        }
    """
    if not file_content:
        raise ValueError("The uploaded file is empty.")

    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported file format. Please upload a CSV or XLSX file."
        )

    try:
        file_buffer = BytesIO(file_content)

        if extension == ".csv":
            try:
                dataframe = pd.read_csv(
                    file_buffer,
                    sep=None,
                    engine="python",
                    encoding="utf-8-sig",
                )
            except UnicodeDecodeError:
                file_buffer.seek(0)
                dataframe = pd.read_csv(
                    file_buffer,
                    sep=None,
                    engine="python",
                    encoding="cp1252",
                )

        else:
            dataframe = pd.read_excel(
                file_buffer,
                engine="openpyxl",
            )

    except Exception as exc:
        raise ValueError(
            f"Could not read the uploaded file: {exc}"
        ) from exc

    if len(dataframe.columns) == 0:
        raise ValueError("The uploaded file does not contain any columns.")

    columns = [str(column).strip() for column in dataframe.columns]

    if any(not column for column in columns):
        raise ValueError("The file contains an empty column name.")

    if len(columns) != len(set(columns)):
        raise ValueError(
            "The file contains duplicate column names. "
            "Please rename the duplicate columns and upload again."
        )

    dataframe.columns = columns

    if dataframe.empty:
        raise ValueError("The uploaded file contains no data rows.")

    rows = [
        {
            column: _clean_value(value)
            for column, value in row.items()
        }
        for row in dataframe.to_dict(orient="records")
    ]

    return {
        "filename": Path(filename).name,
        "file_type": extension.lstrip("."),
        "columns": columns,
        "total_rows": len(rows),
        "rows": rows,
    }
