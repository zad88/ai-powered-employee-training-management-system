import pandas as pd

# Load training courses
courses = pd.read_csv(
    "backend/data/raw/training_development/training_courses.csv"
)

print("=" * 70)
print("COURSE DETAILS")
print("=" * 70)

print("Total courses:", len(courses))

for _, course in courses.iterrows():

    print("\nCourse ID:", course["course_id"])
    print("Title:", course["course_title"])
    print("Category:", course["course_category"])
    print("Delivery Mode:", course["delivery_mode"])
    print("Duration:", course["duration_hours"], "hours")
    print("Target Job Level:", course["target_job_level"])
    print("Active:", course["is_active"])