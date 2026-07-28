@router.post("/admin/add-tech")
def add_tech(payload: dict, current_user=Depends(admin_only), db: Session = Depends(get_db)):

    invite = Invitation(
        email=payload["email"],
        full_name=payload["full_name"],
        alias=payload["alias"],
        company_id=current_user.company_id
    )

    db.add(invite)
    db.commit()

    return {"status": "invited"}
