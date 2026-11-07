
import pandas as pd

training = pd.read_csv(
    "backend/data/raw/employee_hr/training_and_development_data.csv"
)

print("Total training records:", len(training))

print("\nTraining outcomes:")
print(training["Training Outcome"].value_counts())

print("\nTraining types:")
print(training["Training Type"].value_counts())

print("\nUnique training programs:")
print(training["Training Program Name"].nunique())

print("\nSample records:")
print(training[
    ["Employee ID", "Training Program Name", "Training Outcome"]
].head(10).to_string(index=False))

