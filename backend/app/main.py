import backend.app.db.models

from fastapi import FastAPI
from backend.app.api.employee_imports import router as employee_imports_router
from backend.app.api.skill_assessments import router as skill_assessments_router
from backend.app.api.health import router as health_router
from backend.app.api.employees import router as employees_router
from backend.app.api.skills import router as skills_router
from backend.app.api.job_skills import router as job_skills_router
from backend.app.api.courses import router as courses_router
from backend.app.api.course_skills import router as course_skills_router
from backend.app.api.course_sessions import router as course_sessions_router
from backend.app.api.training_plans import router as training_plans_router
from backend.app.api.plan_courses import router as plan_courses_router
from backend.app.api.enrollments import router as enrollments_router

from backend.app.api.session_attendance import router as session_attendance_router
from backend.app.api.session_feedback import router as session_feedback_router
from backend.app.api.enrollment_assessments import (
    router as enrollment_assessments_router
)


app = FastAPI(
    title="AI-Powered Employee Training Management System",
    description="Backend API for employee training management",
    version="0.1.0",
)


@app.get("/")
def home():
    return {"message": "AI Training Manager API is running!"}


app.include_router(health_router)
app.include_router(employees_router)
app.include_router(skills_router)
app.include_router(job_skills_router)
app.include_router(courses_router)
app.include_router(course_skills_router)
app.include_router(skill_assessments_router)
app.include_router(course_sessions_router)
app.include_router(training_plans_router)
app.include_router(plan_courses_router)
app.include_router(enrollments_router)
app.include_router(session_attendance_router)
app.include_router(session_feedback_router)
app.include_router(enrollment_assessments_router) 
app.include_router(employee_imports_router)

