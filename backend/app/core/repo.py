"""Tenant-scoped repository. Guarantees no query can ever cross company boundaries."""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from .db import ASCENDING, DESCENDING

from .db import NO_ID, audit_fields, get_db, new_id


class TenantRepository:
    def __init__(self, collection: str, company_id: str):
        if not company_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Konteks perusahaan tidak ditemukan.")
        self.collection = collection
        self.company_id = company_id
        self.coll = get_db()[collection]

    def _scope(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q: Dict[str, Any] = {"company_id": self.company_id}
        if extra:
            q.update({k: v for k, v in extra.items() if k != "company_id"})
        return q

    async def list(
        self,
        q: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> Dict[str, Any]:
        query = self._scope(filters)
        query.setdefault("status", {"$ne": "deleted"})
        if q:
            fields = search_fields or ["name", "code"]
            query["$or"] = [{f: {"$regex": q, "$options": "i"}} for f in fields]

        page = max(1, int(page or 1))
        limit = min(200, max(1, int(limit or 20)))
        total = await self.coll.count_documents(query)
        direction = DESCENDING if sort_dir == "desc" else ASCENDING
        cursor = (
            self.coll.find(query, NO_ID)
            .sort([(sort_by, direction), ("id", ASCENDING)])
            .skip((page - 1) * limit)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
        }

    async def all(self, filters: Optional[Dict[str, Any]] = None, limit: int = 1000) -> List[Dict]:
        query = self._scope(filters)
        query.setdefault("status", {"$ne": "deleted"})
        return await self.coll.find(query, NO_ID).sort("name", ASCENDING).to_list(limit)

    async def get(self, record_id: str, required: bool = True) -> Optional[Dict[str, Any]]:
        doc = await self.coll.find_one(self._scope({"id": record_id}), NO_ID)
        if not doc and required:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Data tidak ditemukan pada perusahaan aktif Anda.",
            )
        return doc

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.coll.count_documents(self._scope(filters))

    async def ensure_unique(
        self, field: str, value: Any, exclude_id: Optional[str] = None, label: str = "Kode"
    ) -> None:
        if value in (None, ""):
            return
        query = self._scope({field: value, "status": {"$ne": "deleted"}})
        if exclude_id:
            query["id"] = {"$ne": exclude_id}
        if await self.coll.count_documents(query) > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{label} '{value}' sudah digunakan pada perusahaan ini. Gunakan nilai lain.",
            )

    async def create(self, data: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
        doc = {k: v for k, v in data.items() if k not in ("_id", "company_id", "id")}
        doc["id"] = new_id()
        doc["company_id"] = self.company_id  # tenant guard: always forced
        doc.setdefault("status", "active")
        doc.update(audit_fields(user_id, creating=True))
        await self.coll.insert_one(dict(doc))
        return {k: v for k, v in doc.items() if k != "_id"}

    async def update(
        self, record_id: str, data: Dict[str, Any], user_id: Optional[str]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        before = await self.get(record_id)
        patch = {
            k: v
            for k, v in data.items()
            if k not in ("_id", "id", "company_id", "created_at", "created_by")
        }
        patch.update(audit_fields(user_id, creating=False))
        await self.coll.update_one(self._scope({"id": record_id}), {"$set": patch})
        after = await self.get(record_id)
        return before, after

    async def set_status(
        self, record_id: str, new_status: str, user_id: Optional[str]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return await self.update(record_id, {"status": new_status}, user_id)

    async def hard_delete(self, record_id: str) -> Dict[str, Any]:
        before = await self.get(record_id)
        await self.coll.delete_one(self._scope({"id": record_id}))
        return before


async def is_referenced(company_id: str, refs: List[Tuple[str, str, str]]) -> Optional[str]:
    """refs = [(collection, field, human_label)] -> returns label of first collection using it."""
    db = get_db()
    for collection, field, label in refs:
        count = await db[collection].count_documents(
            {"company_id": company_id, field: {"$exists": True}, "status": {"$ne": "deleted"}}
        )
        if count:
            return label
    return None


async def reference_count(company_id: str, collection: str, field: str, value: str) -> int:
    db = get_db()
    return await db[collection].count_documents(
        {"company_id": company_id, field: value, "status": {"$ne": "deleted"}}
    )
