
import pandas as pd

training = pd.read_csv(
    "backend/data/raw/employee_hr/training_and_development_data.csv"
)

records_per_employee = training.groupby("Employee ID").size()

print("Total employees:", records_per_employee.count())

print("\nEmployees with one training record:",
      (records_per_employee == 1).sum())

print("Employees with multiple training records:",
      (records_per_employee > 1).sum())

print("\nTraining records per employee:")
print(records_per_employee.value_counts().sort_index())

