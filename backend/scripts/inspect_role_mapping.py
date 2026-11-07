import pandas as pd
import re
from difflib import SequenceMatcher

# Load datasets
hr = pd.read_csv(
    "backend/data/raw/employee_hr/employee_data.csv"
)

esco = pd.read_csv(
    "backend/data/raw/esco/occupations_en.csv"
)

# Get unique HR job titles
hr_titles = sorted(
    hr["Title"].dropna().astype(str).str.strip().unique()
)

# Get ESCO occupation names
esco_occupations = esco[
    ["conceptUri", "preferredLabel"]
].dropna().drop_duplicates()


def normalize(text):
    """Make text easier to compare."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


print("=" * 70)
print("POSSIBLE HR TO ESCO OCCUPATION MATCHES")
print("=" * 70)

for title in hr_titles:

    normalized_title = normalize(title)

    candidates = []

    for _, occupation in esco_occupations.iterrows():

        esco_name = occupation["preferredLabel"]
        normalized_esco = normalize(esco_name)

        score = SequenceMatcher(
            None,
            normalized_title,
            normalized_esco
        ).ratio()

        candidates.append(
            (score, esco_name, occupation["conceptUri"])
        )

    # Show the five closest matches
    candidates.sort(reverse=True)

    print(f"\nHR JOB TITLE: {title}")

    for score, name, uri in candidates[:5]:

        print(f"  Match: {name}")
        print(f"  Similarity: {score:.2f}")
        print(f"  URI: {uri}")
        