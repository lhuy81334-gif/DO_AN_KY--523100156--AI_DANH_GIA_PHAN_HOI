from fastapi import APIRouter, Depends
from pymongo.database import Database
from app.db.database import get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
def health_check(db: Database = Depends(get_db)):
    db_status = "connected"
    try:
        db.client.admin.command("ping")
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    return {"status": "ok", "service": "Seller Feedback Intelligence Backend", "database": db_status, "version": "1.0.0"}
