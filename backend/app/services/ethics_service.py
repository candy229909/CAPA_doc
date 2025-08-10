# app/services/ethics_service.py
class EthicsService:
    BLACKLIST = ["非法", "色情", "仇恨"]

    @classmethod
    def check(cls, text: str):
        t = text or ""
        bad = [w for w in cls.BLACKLIST if w in t]
        return {"flagged": bool(bad), "reasons": bad}
