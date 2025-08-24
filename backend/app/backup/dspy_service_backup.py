# -*- coding: utf-8 -*-
"""
DSPy 服務 - 僅負責 DSPy 程式碼的定義、編譯和執行
不做檢索，不引用 RAGService，避免循環依賴。
"""

from typing import List, Dict, Any, Optional
from loguru import logger
import dspy

from app.config import settings
from app.models.chat_request import ProblemType, LegalAdvice


class LocalLLM(dspy.LM):
    """本地/模擬 LLM 適配器（可替換為實際 LLM 介面）"""

    def __init__(self, model_name: str = "gemma-3n-e4b"):
        super().__init__(model_name)
        self.model_name = model_name
        self.max_tokens = settings.DSPY_MAX_TOKENS
        self.temperature = settings.DSPY_TEMPERATURE

    def basic_request(self, prompt: str, **kwargs) -> Dict[str, Any]:
        try:
            # 這裡可串接真實 LLM；暫以模擬回應
            response = self._mock_response(prompt)
            return {"choices": [{"text": response}], "usage": {"total_tokens": len(response.split())}}
        except Exception as e:
            logger.error(f"LLM 請求失敗: {e}")
            return {"choices": [{"text": "抱歉，系統暫時無法回應。"}]}  # 優雅失敗

    def _mock_response(self, prompt: str) -> str:
        if "問題分析" in prompt:
            return "這可能屬於工資爭議，需確認工資給付、加班費等事實。"
        if "法律條文" in prompt:
            return "參考《勞動基準法》第22條、第24條。"
        if "解決方案" in prompt:
            return "協商→勞資爭議調解→勞檢申訴→（視情況）訴訟。"
        return "請補充事實細節（時間、對話紀錄、給付證據），才能更精準分析。"


class LegalAnalysisSignature(dspy.Signature):
    question = dspy.InputField(desc="使用者的法律問題")
    context = dspy.InputField(desc="背景資訊（含RAG檢索結果等）")
    problem_type = dspy.OutputField(desc="問題類型分類")
    analysis = dspy.OutputField(desc="詳細的法律分析")
    legal_basis = dspy.OutputField(desc="相關法律依據（條文/實務）")


class SolutionGenerationSignature(dspy.Signature):
    problem_analysis = dspy.InputField(desc="問題分析結果")
    legal_context = dspy.InputField(desc="法律背景資訊")
    solutions = dspy.OutputField(desc="具體解決方案列表")
    risks = dspy.OutputField(desc="各方案風險評估")
    steps = dspy.OutputField(desc="執行步驟建議")


class RiskAssessmentSignature(dspy.Signature):
    solutions = dspy.InputField(desc="提出的解決方案")
    case_context = dspy.InputField(desc="案件背景")
    risk_analysis = dspy.OutputField(desc="風險分析結果")
    recommendations = dspy.OutputField(desc="風險控制建議")


class LegalAdviceModule(dspy.Module):
    """不負責檢索；僅在已備妥 context 下做推理"""

    def __init__(self):
        super().__init__()
        self.analyze_problem = dspy.ChainOfThought(LegalAnalysisSignature)
        self.generate_solutions = dspy.ChainOfThought(SolutionGenerationSignature)
        self.assess_risks = dspy.ChainOfThought(RiskAssessmentSignature)

    def forward(self, question: str, context: str = "") -> dspy.Prediction:
        try:
            analysis_result = self.analyze_problem(question=question, context=context)
            solution_result = self.generate_solutions(
                problem_analysis=analysis_result.analysis, legal_context=analysis_result.legal_basis
            )
            risk_result = self.assess_risks(
                solutions=solution_result.solutions, case_context=context
            )
            return dspy.Prediction(
                problem_type=analysis_result.problem_type,
                analysis=analysis_result.analysis,
                legal_basis=analysis_result.legal_basis,
                solutions=solution_result.solutions,
                risks=solution_result.risks,
                steps=solution_result.steps,
                risk_analysis=risk_result.risk_analysis,
                recommendations=risk_result.recommendations
            )
        except Exception as e:
            logger.error(f"DSPy 模組執行失敗: {e}")
            return dspy.Prediction(
                problem_type="unknown",
                analysis="分析過程中發生錯誤",
                legal_basis="無法獲取法律依據",
                solutions="請諮詢專業律師",
                risks="未知風險",
                steps="建議尋求專業協助",
                risk_analysis="風險評估失敗",
                recommendations="請謹慎處理"
            )


class ConversationModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.respond = dspy.ChainOfThought("question, context -> response")

    def forward(self, question: str, context: str = "") -> dspy.Prediction:
        return self.respond(question=question, context=context)


class DSPyService:
    """對外提供：generate_legal_advice / generate_conversation_response"""

    def __init__(self):
        self.llm = None
        self.legal_advice_module = None
        self.conversation_module = None
        self.compiled_modules = {}
        self._setup()

    def _setup(self):
        try:
            self.llm = LocalLLM(settings.LLM_MODEL_NAME)
            dspy.configure(lm=self.llm)
            self.legal_advice_module = LegalAdviceModule()
            self.conversation_module = ConversationModule()
        except Exception as e:
            logger.error(f"DSPy 服務初始化失敗: {e}")
            raise

    def generate_legal_advice(self, question: str, context: str = "", retrieved_docs: Optional[List[str]] = None) -> LegalAdvice:
        try:
            full_context = context
            if retrieved_docs:
                full_context += "\n相關法律文件:\n" + "\n".join(retrieved_docs)
            prediction = self.legal_advice_module(question=question, context=full_context)
            return self._parse_legal_advice(prediction)
        except Exception as e:
            logger.error(f"生成法律建議失敗: {e}")
            return self._fallback_advice()

    def generate_conversation_response(self, question: str, context: str = "") -> str:
        try:
            pred = self.conversation_module(question=question, context=context)
            return getattr(pred, "response", str(pred))
        except Exception as e:
            logger.error(f"生成對話回應失敗: {e}")
            return "抱歉，我暫時無法回應您的問題。請稍後再試或聯繫專業律師。"

    def _parse_legal_advice(self, prediction) -> LegalAdvice:
        mapping = {
            "工資爭議": ProblemType.WAGE_DISPUTE,
            "wage_dispute": ProblemType.WAGE_DISPUTE,
            "解僱爭議": ProblemType.DISMISSAL_DISPUTE,
            "dismissal_dispute": ProblemType.DISMISSAL_DISPUTE,
            "工時問題": ProblemType.WORKING_HOURS,
            "working_hours": ProblemType.WORKING_HOURS,
            "職業安全": ProblemType.WORKPLACE_SAFETY,
            "workplace_safety": ProblemType.WORKPLACE_SAFETY,
            "歧視": ProblemType.DISCRIMINATION,
            "discrimination": ProblemType.DISCRIMINATION,
        }
        pt_str = str(getattr(prediction, "problem_type", "other")).lower()
        problem_type = mapping.get(pt_str, ProblemType.OTHER)

        def _split(txt: str) -> List[str]:
            if not txt:
                return []
            import re
            items = re.split(r"[;；。\n]", str(txt))
            return [i.strip() for i in items if i.strip()][:5]

        def _legal_refs(txt: str) -> List[Dict[str, str]]:
            import re
            refs = []
            patterns = [r"《?([^《》]+法)》?第?(\d+)條", r"(勞基法|民法|刑法)第?(\d+)條"]
            for p in patterns:
                for m in re.findall(p, str(txt)):
                    if len(m) == 2:
                        refs.append({"法條": f"{m[0]}第{m[1]}條", "內容": "具體內容請參閱法條原文"})
            if not refs:
                refs.append({"法條": "相關法律條文", "內容": "請參考勞動相關法規"})
            return refs[:3]

        risks_text = getattr(prediction, "risks", "")
        risks = {"整體風險": "中等"}
        if "高" in str(risks_text):
            risks["整體風險"] = "高"
        elif "低" in str(risks_text):
            risks["整體風險"] = "低"

        return LegalAdvice(
            problem_type=problem_type,
            analysis=str(getattr(prediction, "analysis", "")),
            solutions=_split(getattr(prediction, "solutions", "")),
            risks=risks,
            legal_references=_legal_refs(getattr(prediction, "legal_basis", "")),
            execution_steps=_split(getattr(prediction, "steps", "")),
            confidence_score=0.8
        )

    def _fallback_advice(self) -> LegalAdvice:
        return LegalAdvice(
            problem_type=ProblemType.OTHER,
            analysis="系統暫時無法完整分析您的問題，建議諮詢專業律師。",
            solutions=["聯繫專業律師", "向勞工局諮詢", "蒐集相關證據"],
            risks={"諮詢風險": "低"},
            legal_references=[{"法條": "建議參考", "內容": "勞動基準法及相關勞工法規"}],
            execution_steps=["蒐集資料", "諮詢專家", "評估選項"],
            confidence_score=0.3
        )


# 全域實例
dspy_service = DSPyService()