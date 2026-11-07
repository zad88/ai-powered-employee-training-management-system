
import pandas as pd
from pathlib import Path

# Locate the training dataset folder
DATA_FOLDER = Path("backend/data/raw/training_development")

# Files we want to inspect
files = [
    "learners.csv",
    "training_courses.csv",
    "training_enrollments.csv"
]

# Inspect each file
for file in files:

    file_path = DATA_FOLDER / file

    print("\n" + "=" * 60)
    print(f"DATASET: {file}")
    print("=" * 60)

    # Load CSV
    df = pd.read_csv(file_path)

    # Dataset size
    print("Rows:", df.shape[0])
    print("Columns:", df.shape[1])

    # Column names
    print("\nColumn names:")
    print(df.columns.tolist())

    # First five records
    print("\nFirst 5 rows:")
    print(df.head())

    # Missing values
    print("\nMissing values:")
    print(df.isnull().sum())
