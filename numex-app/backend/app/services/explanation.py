"""LLM explanation service with RAG."""

from openai import AsyncOpenAI

from app.config import settings
from rag.retriever import RAGRetriever


class ExplanationService:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=settings.vllm_url,
            api_key=settings.vllm_api_key,
        )
        self.retriever = RAGRetriever()

    async def explain_payment(
        self,
        loan_name: str,
        month: int,
        payment: float,
        balance_before: float,
        interest_rate: float,
        min_payment: float,
        user_question: str | None = None,
    ) -> str:
        query = user_question or f"почему платить {payment} по кредиту {loan_name} в месяц {month}"
        context_chunks = self.retriever.search(query, top_k=5)
        context = "\n\n".join(context_chunks)

        prompt = f"""Ты помощник по объяснению плана погашения долгов. Используй контекст из базы знаний RPML.

Контекст из базы знаний:
{context}

Данные по платежу:
- Кредит: {loan_name}
- Месяц: {month}
- Рекомендованный платёж: {payment}
- Баланс до платежа: {balance_before}
- Процентная ставка: {interest_rate}
- Минимальный платёж: {min_payment}

Вопрос пользователя: {query}

Дай краткое понятное объяснение на русском языке (2-4 предложения)."""

        try:
            response = await self.client.chat.completions.create(
                model="default",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=512,
            )
            return response.choices[0].message.content or "Не удалось сгенерировать объяснение."
        except Exception as e:
            return f"Сервис объяснений временно недоступен: {e}"

    async def explain_stream(
        self,
        question: str,
        plan_context: str | None = None,
    ):
        """Stream explanation response."""
        context_chunks = self.retriever.search(question, top_k=5)
        context = "\n\n".join(context_chunks)

        prompt = f"""Ты помощник по объяснению плана погашения долгов. Используй контекст из базы знаний RPML.

Контекст:
{context}
"""
        if plan_context:
            prompt += f"\nКонтекст плана пользователя:\n{plan_context}\n\n"

        prompt += f"Вопрос пользователя: {question}\n\nОтветь кратко и понятно на русском."

        try:
            stream = await self.client.chat.completions.create(
                model="default",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Ошибка: {e}"
