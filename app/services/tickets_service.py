from datetime import datetime
from app.db import execute, query_one

def create_ticket(data, encrypt_func):
    now = datetime.utcnow().isoformat(timespec="seconds")

    execute("""
        INSERT INTO tickets(
            protocol, requester_name, requester_phone_enc,
            sector, description, company_id, company_other_enc,
            status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ABERTO', ?)
    """, (
        data["protocol"],
        data["requester_name"],
        encrypt_func(data.get("phone")),
        data["sector"],
        data["description"],
        data.get("company_id"),
        data.get("company_other"),
        now
    ))