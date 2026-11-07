
import pandas as pd

# Load the two datasets
employees = pd.read_csv(
    "backend/data/raw/employee_hr/employee_data.csv"
)

training = pd.read_csv(
    "backend/data/raw/employee_hr/training_and_development_data.csv"
)

# Get employee IDs from each file
employee_ids = set(employees["EmpID"])
training_ids = set(training["Employee ID"])

# Find matching IDs
matching_ids = employee_ids.intersection(training_ids)

print("HR employee IDs:", len(employee_ids))
print("Training employee IDs:", len(training_ids))
print("Matching IDs:", len(matching_ids))

print("\nDo the datasets share employee IDs?")
print("YES" if matching_ids else "NO")

