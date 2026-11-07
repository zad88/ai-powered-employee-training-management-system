
import pandas as pd
from pathlib import Path

# Locate the folder containing our original HR datasets
DATA_FOLDER = Path("backend/data/raw/employee_hr")

# List of CSV files we want to inspect
files = [
    "employee_data.csv",
    "employee_engagement_survey_data.csv",
    "recruitment_data.csv",
    "training_and_development_data.csv"
]

# Inspect each dataset
for file in files:
    file_path = DATA_FOLDER / file

    print("\n" + "=" * 60)
    print(f"DATASET: {file}")
    print("=" * 60)

    # Load the CSV file
    df = pd.read_csv(file_path)

    # Display basic information
    print("Number of rows:", df.shape[0])
    print("Number of columns:", df.shape[1])

    print("\nColumn names:")
    print(df.columns.tolist())

    print("\nFirst 5 rows:")
    print(df.head())

    print("\nMissing values per column:")
    print(df.isnull().sum())
