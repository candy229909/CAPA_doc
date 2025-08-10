# app/services/nlu_service.py
class NLUService:
    @staticmethod
    def analyze(text: str) -> dict:
        t = (text or "").lower()
        is_law = any(k in t for k in ["勞基法", "勞動基準法", "加班", "資遣", "工時", "請假", "職災", "年資", "薪資"])
        return {"intent": "law_question" if is_law else "general", "entities": []}

