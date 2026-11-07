import pandas as pd

# Load HR employee data
df = pd.read_csv(
    "backend/data/raw/employee_hr/employee_data.csv"
)

# Show job titles and their associated job function descriptions
result = (
    df.groupby("Title")["JobFunctionDescription"]
    .unique()
)

print("=" * 70)
print("JOB TITLES AND JOB FUNCTION DESCRIPTIONS")
print("=" * 70)

for title, descriptions in result.items():

    print(f"\nJob Title: {title}")

    for description in descriptions:
        print("Job Function:", description)