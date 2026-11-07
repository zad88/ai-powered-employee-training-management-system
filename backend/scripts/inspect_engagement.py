
import pandas as pd

survey = pd.read_csv(
    "backend/data/raw/employee_hr/employee_engagement_survey_data.csv"
)

print("Total survey records:", len(survey))

print("\nColumns:")
print(survey.columns.tolist())

print("\nAverage scores:")
print(survey[
    ["Engagement Score", "Satisfaction Score", "Work-Life Balance Score"]
].mean())

print("\nSample records:")
print(survey.head(10).to_string(index=False))
