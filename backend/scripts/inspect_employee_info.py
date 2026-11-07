
import pandas as pd

employees = pd.read_csv(
    "backend/data/raw/employee_hr/employee_data.csv"
)

print("Total employees:", len(employees))

print("\nDepartments:")
print(employees["DepartmentType"].value_counts())

print("\nEmployee status:")
print(employees["EmployeeStatus"].value_counts())

print("\nJob titles:")
print(employees["Title"].value_counts())

print("\nSample employees:")
print(
    employees[["EmpID", "Title", "DepartmentType", "EmployeeStatus"]]
    .head(10)
    .to_string(index=False)
)

