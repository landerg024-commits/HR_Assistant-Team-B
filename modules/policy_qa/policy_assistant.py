"""Employee-facing HR Policy Q&A facade.

The assistant uses only published, currently effective policies belonging
to the authenticated user's company. It does not use external knowledge.
"""

from sqlalchemy.orm import Session

from services.policy_service import (
    PolicyAnswer,
    PolicyService,
)


class PolicyAssistant:
    """Small facade used by Streamlit pages."""

    def __init__(self, session: Session) -> None:
        self.policy_service = PolicyService(session)

    def answer(
        self,
        *,
        company_id: int,
        question: str,
    ) -> PolicyAnswer:
        """Return an approved-policy answer and source references."""

        return self.policy_service.answer_question(
            company_id=company_id,
            question=question,
        )
