from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from backend.app.db.employee import Employee
from backend.app.db.job_skill import JobSkill
from backend.app.db.skill import Skill
from backend.app.db.skill_assessment import SkillAssessment


IMPORTANCE_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def analyze_company_tna(db: Session, company_id: int) -> dict:
    """
    Analyse approved job requirements and valid employee assessments.

    This function is read-only. It does not create or update database records.
    """

    today = date.today()

    employees = (
        db.query(Employee)
        .filter(
            Employee.company_id == company_id,
            Employee.is_active.is_(True),
        )
        .all()
    )

    requirements = (
        db.query(JobSkill, Skill)
        .join(Skill, Skill.skill_id == JobSkill.skill_id)
        .filter(JobSkill.company_id == company_id)
        .all()
    )

    assessments = (
        db.query(SkillAssessment, Employee)
        .join(Employee, Employee.id == SkillAssessment.employee_id)
        .filter(
            SkillAssessment.company_id == company_id,
            Employee.company_id == company_id,
            Employee.is_active.is_(True),
            SkillAssessment.evidence_status == "Approved",
            (
                SkillAssessment.expiry_date.is_(None)
                | (SkillAssessment.expiry_date >= today)
            ),
        )
        .order_by(
            SkillAssessment.assessment_date.desc(),
            SkillAssessment.assessment_id.desc(),
        )
        .all()
    )

    # Keep the most recent valid, approved assessment per employee and skill.
    current_assessments = {}

    for assessment, employee in assessments:
        key = (employee.id, assessment.skill_id)

        if key not in current_assessments:
            current_assessments[key] = assessment

    employee_requirements = defaultdict(list)
    position_requirements = defaultdict(list)
    position_status_counts = defaultdict(
        lambda: {"approved": 0, "pending": 0, "rejected": 0}
    )

    for requirement, skill in requirements:
        position = requirement.job_title.strip()
        requirement_data = {
            "requirement_id": requirement.id,
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "category": skill.category,
            "required_proficiency": requirement.required_proficiency,
            "importance": requirement.importance,
            "approval_status": requirement.approval_status,
        }

        position_requirements[position].append(requirement_data)

        status = requirement.approval_status.lower()
        if status in position_status_counts[position]:
            position_status_counts[position][status] += 1

        if requirement.approval_status == "Approved":
            employee_requirements[position].append(requirement_data)

    # Position-level analysis includes positions with employees and
    # positions that have configured requirements but no active employees.
    position_names = {
        employee.job_title.strip() for employee in employees
    }
    position_names.update(position_requirements.keys())

    position_analysis = []

    for position in sorted(position_names, key=str.lower):
        position_employees = [
            employee for employee in employees
            if employee.job_title.strip().lower() == position.lower()
        ]

        approved_items = [
            item for item in position_requirements[position]
            if item["approval_status"] == "Approved"
        ]

        pending_items = [
            item for item in position_requirements[position]
            if item["approval_status"] == "Pending"
        ]

        rejected_items = [
            item for item in position_requirements[position]
            if item["approval_status"] == "Rejected"
        ]

        position_analysis.append({
            "job_title": position,
            "employee_count": len(position_employees),
            "approved_requirements": approved_items,
            "pending_requirements": pending_items,
            "rejected_requirements": rejected_items,
            "approved_requirement_count": len(approved_items),
            "pending_requirement_count": len(pending_items),
            "rejected_requirement_count": len(rejected_items),
            "note": (
                "Configured requirements only. Unconfigured skills "
                "cannot be identified by this rule-based analysis."
            ),
        })

    employee_analysis = []
    department_stats = defaultdict(
        lambda: {
            "employee_count": 0,
            "confirmed_skill_gaps": 0,
            "assessments_needed": 0,
            "gap_skills": defaultdict(int),
        }
    )

    for employee in employees:
        department = employee.department or "Unspecified"
        department_stats[department]["employee_count"] += 1

        job_requirements = employee_requirements[
            employee.job_title.strip()
        ]

        employee_gaps = []
        employee_skill_results = []

        for requirement in job_requirements:
            skill_id = requirement["skill_id"]
            assessment = current_assessments.get(
                (employee.id, skill_id)
            )

            if assessment is None:
                result = {
                    **requirement,
                    "current_proficiency": None,
                    "gap": None,
                    "status": "Assessment Needed",
                    "priority_score": None,
                }
                department_stats[department]["assessments_needed"] += 1

            else:
                current_level = assessment.proficiency_level
                gap = max(
                    requirement["required_proficiency"] - current_level,
                    0,
                )

                if gap > 0:
                    status = "Skill Gap"
                    weight = IMPORTANCE_WEIGHTS.get(
                        requirement["importance"].lower(), 1
                    )
                    priority_score = gap * weight

                    employee_gaps.append({
                        "skill_id": skill_id,
                        "skill_name": requirement["skill_name"],
                        "gap": gap,
                        "importance": requirement["importance"],
                        "priority_score": priority_score,
                    })

                    department_stats[department]["confirmed_skill_gaps"] += 1
                    department_stats[department]["gap_skills"][
                        requirement["skill_name"]
                    ] += 1
                else:
                    status = "Meets Requirement"
                    priority_score = 0

                result = {
                    **requirement,
                    "current_proficiency": current_level,
                    "gap": gap,
                    "assessment_date": assessment.assessment_date,
                    "status": status,
                    "priority_score": priority_score,
                }

            employee_skill_results.append(result)

        employee_gaps.sort(
            key=lambda item: item["priority_score"],
            reverse=True,
        )

        employee_analysis.append({
            "employee_id": employee.id,
            "employee_code": employee.employee_id,
            "employee_name": employee.full_name,
            "job_title": employee.job_title,
            "department": department,
            "skills": employee_skill_results,
            "confirmed_skill_gaps": employee_gaps,
            "confirmed_gap_count": len(employee_gaps),
            "assessment_needed_count": sum(
                1 for item in employee_skill_results
                if item["status"] == "Assessment Needed"
            ),
        })

    department_analysis = []

    for department, stats in sorted(department_stats.items()):
        common_gaps = sorted(
            [
                {"skill_name": skill_name, "employee_count": count}
                for skill_name, count in stats["gap_skills"].items()
            ],
            key=lambda item: item["employee_count"],
            reverse=True,
        )

        department_analysis.append({
            "department": department,
            "employee_count": stats["employee_count"],
            "confirmed_skill_gaps": stats["confirmed_skill_gaps"],
            "assessments_needed": stats["assessments_needed"],
            "common_skill_gaps": common_gaps,
        })

    total_confirmed_gaps = sum(
        item["confirmed_gap_count"] for item in employee_analysis
    )
    total_assessments_needed = sum(
        item["assessment_needed_count"] for item in employee_analysis
    )

    return {
        "company_id": company_id,
        "analysis_date": today,
        "summary": {
            "active_employees": len(employees),
            "positions_analysed": len(position_analysis),
            "confirmed_skill_gaps": total_confirmed_gaps,
            "assessments_needed": total_assessments_needed,
        },
        "position_analysis": position_analysis,
        "employee_analysis": employee_analysis,
        "department_analysis": department_analysis,
    }

