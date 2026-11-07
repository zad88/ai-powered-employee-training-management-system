
import pandas as pd

training = pd.read_csv(
    "backend/data/raw/employee_hr/training_and_development_data.csv"
)

summary = training.groupby(
    ["Training Program Name", "Training Outcome"]
).size().unstack(fill_value=0)

print(summary)
