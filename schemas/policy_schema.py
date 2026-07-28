"""Validation schemas for HR policy administration and questions."""

from datetime import date

from pydantic import BaseModel, Field


class PolicyCreateRequest(BaseModel):
    """Validated values used to create one policy version."""

    company_id: int
    created_by_user_id: int
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    summary: str | None = Field(default=None, max_length=1000)
    content: str = Field(min_length=20)
    version: str = Field(default="1.0", min_length=1, max_length=30)
    effective_date: date | None = None
    publish_immediately: bool = False


class PolicyStatusUpdate(BaseModel):
    """Validated policy publication-status change."""

    company_id: int
    policy_id: int
    status: str


class PolicyQuestionRequest(BaseModel):
    """Validated employee question submitted to Policy Q&A."""

    company_id: int
    question: str = Field(min_length=3, max_length=1000)




class PolicyUploadRequest(BaseModel):
    """Metadata for an automatically published uploaded policy version."""

    company_id: int
    created_by_user_id: int
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    version: str = Field(default="1.0", min_length=1, max_length=30)

    # Compatibility fields accepted from older scripts; uploaded policies are
    # always published and their summary is generated from the preview text.
    summary: str | None = Field(default=None, max_length=1000)
    effective_date: date | None = None
    publish_immediately: bool = True


class PolicyBinActionRequest(BaseModel):
    """Validated reversible move-to-Bin or restore request."""

    company_id: int
    policy_id: int
    user_id: int
    confirmation_public_id: str | None = Field(default=None, max_length=30)



class PolicyMetadataUpdate(BaseModel):
    """Editable metadata and content for an active policy version."""

    company_id: int
    policy_id: int
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    version: str = Field(min_length=1, max_length=30)

    # Optional keeps compatibility with existing service callers. The
    # administrator interface supplies content so the searchable database
    # text and sections can be regenerated.
    content: str | None = Field(
        default=None,
        min_length=20,
    )


class PolicyPermanentDeleteRequest(BaseModel):
    """Protected permanent deletion request for one Bin version."""

    company_id: int
    policy_id: int
    confirmation_public_id: str = Field(
        min_length=1,
        max_length=30,
    )
    permanent_delete_acknowledged: bool
