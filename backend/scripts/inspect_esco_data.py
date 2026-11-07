
import pandas as pd
from pathlib import Path

DATA_FOLDER = Path("backend/data/raw/esco")

files = [
    "occupations_en.csv",
    "skills_en.csv",
    "occupationSkillRelations_en.csv",
    "skillsHierarchy_en.csv"
]

for file in files:

    file_path = DATA_FOLDER / file

    print("\n" + "=" * 60)
    print(f"ESCO DATASET: {file}")
    print("=" * 60)

    # Automatically detect the CSV separator
    df = pd.read_csv(
        file_path,
        sep=None,
        engine="python",
        encoding="utf-8-sig"
    )

    print("Rows:", df.shape[0])
    print("Columns:", df.shape[1])

    print("\nColumn names:")
    print(df.columns.tolist())

    print("\nFirst 3 rows:")
    print(df.head(3))

    print("\nMissing values:")
    print(df.isnull().sum())
