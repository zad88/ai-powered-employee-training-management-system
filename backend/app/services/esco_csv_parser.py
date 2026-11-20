"""Streaming readers for the local ESCO CSV reference datasets."""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


ESCO_DATA_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "esco"
)

DATASET_FILES = {
    "skills": "skills_en.csv",
    "occupations": "occupations_en.csv",
    "hierarchy": "skillsHierarchy_en.csv",
    "occupation_skill_relations": "occupationSkillRelations_en.csv",
}

# Audited row totals for the ESCO source bundle documented in
# notes/dataset_audit.md. Update only after reviewing a replacement bundle.
ESCO_EXPECTED_SOURCE_ROWS = {
    "skills": 13_960,
    "occupations": 3_043,
    "hierarchy": 640,
    "occupation_skill_relations": 126_051,
}

DATASET_COLUMNS = {
    "skills": (
        "conceptUri",
        "skillType",
        "reuseLevel",
        "preferredLabel",
        "altLabels",
        "status",
        "modifiedDate",
        "description",
    ),
    "occupations": (
        "conceptUri",
        "iscoGroup",
        "preferredLabel",
        "altLabels",
        "status",
        "modifiedDate",
        "regulatedProfessionNote",
        "scopeNote",
        "definition",
        "inScheme",
        "description",
        "code",
        "naceCode",
    ),
    "hierarchy": (
        "Level 0 URI",
        "Level 0 preferred term",
        "Level 1 URI",
        "Level 1 preferred term",
        "Level 2 URI",
        "Level 2 preferred term",
        "Level 3 URI",
        "Level 3 preferred term",
        "Description",
        "Scope note",
        "Level 0 code",
        "Level 1 code",
        "Level 2 code",
        "Level 3 code",
    ),
    "occupation_skill_relations": (
        "occupationUri",
        "occupationLabel",
        "relationType",
        "skillType",
        "skillUri",
        "skillLabel",
    ),
}

REQUIRED_ROW_VALUES = {
    "skills": ("conceptUri", "preferredLabel"),
    "occupations": ("conceptUri", "preferredLabel"),
    "hierarchy": ("Level 0 URI", "Level 0 preferred term"),
    "occupation_skill_relations": (
        "occupationUri",
        "relationType",
        "skillUri",
    ),
}


@dataclass(frozen=True)
class ESCOCSVRecord:
    row_number: int
    physical_line_end: int
    values: dict[str, str]
    padded_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ESCOCSVRowIssue:
    row_number: int
    physical_line_end: int
    code: str
    message: str
    actual_width: int


class ESCOCSVError(ValueError):
    def __init__(
        self,
        dataset: str,
        code: str,
        message: str,
        *,
        row_number: int | None = None,
        physical_line: int | None = None,
    ):
        super().__init__(message)
        self.dataset = dataset
        self.code = code
        self.row_number = row_number
        self.physical_line = physical_line


class ESCOCSVReader:
    """Iterate CSV records without retaining the file's rows in memory."""

    def __init__(self, path: Path, dataset: str):
        if dataset not in DATASET_FILES:
            raise ValueError(f"Unknown ESCO dataset: {dataset}")

        self.path = path
        self.dataset = dataset
        self.headers: tuple[str, ...] = ()
        self.delimiter: str | None = None
        self.encoding: str | None = None
        self.source_rows = 0
        self.padded_rows = 0
        self.padded_cells = 0

    def __iter__(self) -> Iterator[ESCOCSVRecord | ESCOCSVRowIssue]:
        try:
            with self.path.open("rb") as raw_file:
                has_bom = raw_file.read(3) == b"\xef\xbb\xbf"

            self.encoding = "UTF-8 with BOM" if has_bom else "UTF-8"
            with self.path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as source:
                sample = source.read(16_384)
                source.seek(0)
                self.delimiter = self._detect_delimiter(sample)

                reader = csv.reader(
                    source,
                    delimiter=self.delimiter,
                    quotechar='"',
                    doublequote=True,
                    strict=True,
                )
                header = next(reader, None)
                if not header:
                    raise ESCOCSVError(
                        self.dataset,
                        "missing_header",
                        "The CSV does not contain a header row.",
                    )

                headers = tuple(value.strip() for value in header)
                if any(not value for value in headers):
                    raise ESCOCSVError(
                        self.dataset,
                        "empty_header",
                        "The CSV contains an empty column name.",
                    )
                if len(headers) != len(set(headers)):
                    raise ESCOCSVError(
                        self.dataset,
                        "duplicate_header",
                        "The CSV contains duplicate column names.",
                    )

                required = set(DATASET_COLUMNS[self.dataset])
                missing = sorted(required - set(headers))
                if missing:
                    raise ESCOCSVError(
                        self.dataset,
                        "missing_columns",
                        "Required columns are missing: " + ", ".join(missing),
                    )

                self.headers = headers
                required_values = set(REQUIRED_ROW_VALUES[self.dataset])
                logical_row = 1

                while True:
                    try:
                        row = next(reader)
                    except StopIteration:
                        break
                    except csv.Error as exc:
                        raise ESCOCSVError(
                            self.dataset,
                            "malformed_csv",
                            f"Malformed CSV near physical line "
                            f"{reader.line_num}: {exc}",
                            row_number=logical_row + 1,
                            physical_line=reader.line_num,
                        ) from exc

                    logical_row += 1
                    self.source_rows += 1
                    if not row or all(value == "" for value in row):
                        yield ESCOCSVRowIssue(
                            logical_row,
                            reader.line_num,
                            "blank_record",
                            "The CSV contains a blank data record.",
                            len(row),
                        )
                        continue

                    if len(row) > len(headers):
                        yield ESCOCSVRowIssue(
                            logical_row,
                            reader.line_num,
                            "extra_columns",
                            f"Record has {len(row) - len(headers)} "
                            "more values than the header.",
                            len(row),
                        )
                        continue

                    padded_columns: tuple[str, ...] = ()
                    if len(row) < len(headers):
                        missing_trailing = headers[len(row):]
                        if required_values.intersection(missing_trailing):
                            yield ESCOCSVRowIssue(
                                logical_row,
                                reader.line_num,
                                "missing_required_trailing_columns",
                                "Record omits a required trailing field.",
                                len(row),
                            )
                            continue

                        padded_columns = missing_trailing
                        row.extend([""] * len(missing_trailing))
                        self.padded_rows += 1
                        self.padded_cells += len(missing_trailing)

                    yield ESCOCSVRecord(
                        logical_row,
                        reader.line_num,
                        dict(zip(headers, row)),
                        padded_columns,
                    )
        except ESCOCSVError:
            raise
        except UnicodeDecodeError as exc:
            raise ESCOCSVError(
                self.dataset,
                "invalid_encoding",
                f"The CSV is not valid UTF-8: {exc}",
            ) from exc
        except OSError as exc:
            raise ESCOCSVError(
                self.dataset,
                "file_error",
                f"Unable to read the CSV file: {exc}",
            ) from exc
        except csv.Error as exc:
            raise ESCOCSVError(
                self.dataset,
                "malformed_csv",
                f"Malformed CSV header: {exc}",
            ) from exc

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        try:
            return csv.Sniffer().sniff(
                sample,
                delimiters=",;\t|",
            ).delimiter
        except csv.Error:
            return ","
