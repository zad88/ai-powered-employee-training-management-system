
# Dataset Audit Summary
## AI-Powered Employee Training Management System

## 1. Purpose

This document summarizes the datasets inspected during development, their usefulness, limitations, and decisions made before database design.

## 2. Dataset Overview

| Dataset | Records | Decision |
|---|---:|---|
| HR Employee Data | 3,000 | Keep |
| HR Training History | 3,000 | Keep |
| Employee Engagement Survey | 3,000 | Keep for reporting |
| Recruitment Data | 3,000 | Exclude from core system |
| ESCO Occupations | 3,043 | Keep |
| ESCO Skills | 13,960 | Keep |
| ESCO Occupation-Skill Relations | 126,051 | Keep |
| ESCO Skills Hierarchy | 640 | Keep |
| Training Catalogue | 43 | Keep |
| Training Learners | 1,500 | Keep separately for testing |
| Training Enrolments | 15,333 | Keep separately for testing |

## 3. HR Employee Data

**File:** employee_data.csv

Contains 3,000 employees and 26 columns.

Useful information:
- Employee ID
- Job title
- Department
- Employment status
- General employee information

Limitations:
- No actual employee skill assessments.
- Performance scores do not represent technical skill proficiency.
- JobFunctionDescription contains inconsistent information and must not be used for occupation mapping.
- Job titles can be used for initial ESCO mapping, but mappings require review.

## 4. HR Training History

**File:** training_and_development_data.csv

Contains 3,000 training records.

Training outcomes:
- Incomplete: 775
- Completed: 770
- Passed: 739
- Failed: 716

Five training programs:
- Communication Skills
- Customer Service
- Leadership Development
- Project Management
- Technical Skills

Findings:
- All 3,000 employee IDs matched the HR employee dataset.
- Every employee has exactly one training record in this sample.
- Our database must support multiple training records per employee.
- These five programs cannot automatically be matched to the separate 43-course catalogue.
- Course completion does not prove skill mastery.

## 5. Employee Engagement Survey

**File:** employee_engagement_survey_data.csv

Contains 3,000 records.

Average scores:
- Engagement: 2.94
- Satisfaction: 3.02
- Work-Life Balance: 2.99

Decision:
Use these scores for optional management reporting.

Important:
Do not use engagement or satisfaction scores to calculate employee skill gaps.

Employee IDs must be checked against the main HR dataset before joining.

## 6. Recruitment Data

**File:** recruitment_data.csv

Contains 3,000 applicant records.

Decision:
Exclude from the core project because recruitment is outside our employee training workflow.

Keep the original file in the raw folder.

## 7. ESCO Dataset

Important files:

- occupations_en.csv
- skills_en.csv
- occupationSkillRelations_en.csv
- skillsHierarchy_en.csv

Purpose:
- Identify occupations.
- Identify skills associated with occupations.
- Establish standardized occupation-to-skill relationships.

Limitations:
ESCO describes occupational requirements, not an individual employee's current proficiency.

Occupation mappings must be reviewed rather than relying entirely on text similarity.

## 8. Training Catalogue

**File:** training_courses.csv

Contains 43 courses across:
- Compliance
- Health & Safety
- Technical
- Digital Skills
- Leadership
- Professional Skills

Available information:
- Course ID
- Course title
- Category
- Delivery mode
- Duration
- Target job level
- Active status

Limitations:
- No explicit course-to-skill mapping.
- No detailed course descriptions.

Decisions:
- Do not invent course-skill relationships.
- Candidate mappings require review and approval.
- Only active courses from the relevant company's catalogue can be recommended.
- Validate every recommended course ID.

## 9. Separate Training & Development Dataset

Files:
- learners.csv
- training_courses.csv
- training_enrollments.csv

Contains:
- 1,500 learners
- 43 courses
- 15,333 enrolments

The dataset README identifies it as synthetic data generated for analytics practice.

Important:
- Its learner IDs do not match the HR employee IDs.
- It represents a separate population.
- Do not join it with the HR employee dataset.

Use it separately to test:
- Training progress
- Course completion
- Assessment outcomes
- Training reports

## 10. Information Required From Real Companies

The final system must allow companies to upload their own information.

Useful information includes:

1. Employee IDs, job titles, departments and employment status.
2. Employee skill assessments or other evidence of proficiency.
3. Existing course catalogues and course descriptions.
4. Verified course-to-skill mappings, where available.
5. Training enrolments, progress and completion records.

Companies may upload different CSV formats.

Our system will use column mapping and validation to convert their data into a standard internal structure.

## 11. Reliability Rules

Our system must:

- Never guess employee skill levels.
- Distinguish confirmed skill gaps from unknown skills.
- Never treat performance ratings as skill proficiency.
- Never join unrelated datasets.
- Recommend only real, active company courses.
- Validate course IDs before recommendations are accepted.
- Keep each company's data separate.
- Require manager approval before assigning training.
- Use actual database records for reporting calculations.

## 12. Final Dataset Decision

**Selected approach: Option B**

Keep useful datasets and handle their limitations properly.

The current datasets are sufficient for developing and testing several parts of the prototype, but they do not provide verified employee skill proficiency or explicit course-to-skill mappings.

These limitations will be addressed through company-provided information, employee assessments and reviewed mappings.

## 13. Next Development Phase

Before database implementation:

1. Complete remaining dataset relationship checks.
2. Define the standard company upload format.
3. Define validation rules.
4. Finalize database requirements.
5. Begin database design.
