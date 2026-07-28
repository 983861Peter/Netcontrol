from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Company, User
from utils.security import hash_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register-company")
def register_company(payload: dict, db: Session = Depends(get_db)):

    if db.query(Company).filter_by(company_email=payload["company_email"]).first():
        raise HTTPException(400, "Company already exists")

    company = Company(
        name=payload["company_name"],
        company_email=payload["company_email"],
        location=payload["company_location"]
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    admin = User(
        full_name=payload["full_name"],
        email=payload["email"],
        alias=payload["alias"],
        password_hash=hash_password(payload["password"]),
        role="admin",
        company_id=company.id
    )

    db.add(admin)
    db.commit()

    return {"status": "success", "role": "admin"}
