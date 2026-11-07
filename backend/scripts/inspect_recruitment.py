
import pandas as pd

data = pd.read_csv(
    "backend/data/raw/employee_hr/recruitment_data.csv"
)

print("Total applicants:", len(data))

print("\nJob titles:")
print(data["Job Title"].value_counts().head(15))

print("\nApplicant status:")
print(data["Status"].value_counts())

print("\nEducation levels:")
print(data["Education Level"].value_counts())

print("\nSample records:")
print(data[["Applicant ID", "Job Title", "Education Level", "Status"]]
      .head(10).to_string(index=False))
