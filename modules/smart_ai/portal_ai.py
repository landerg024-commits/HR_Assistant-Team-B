"""Local, company-scoped AI enhancement for both portal chat assistants.

Architecture:
- Existing deterministic assistants remain authoritative for live HR records.
- Published policy sections and portal help text are retrieved through hybrid
  BM25 + optional Chroma vector search.
- Optional CrossEncoder reranking improves the final candidate order.
- Ollama performs only grounded answer synthesis.
- Every dependency is lazy-loaded so the portal keeps working when the local
  AI runtime or index dependencies are not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import re
from typing import Iterable
from urllib import request, error

from sqlalchemy.orm import Session

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from repositories.policy_section_repository import PolicySectionRepository


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One role-safe portal or policy knowledge unit."""

    document_id: str
    text: str
    title: str
    source_type: str
    company_id: int
    role_scope: str
    metadata: dict[str, str | int | None]


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    """One hybrid-search result."""

    document: KnowledgeDocument
    score: float


_PORTAL_GUIDES = {
    "shared": [
        ("Navigation and privacy", "The HR Assistant answers only from the authenticated company portal. It cannot use outside knowledge, expose another company, or reveal passwords, reset tokens, secret keys, SMTP credentials, or private authentication data."),
        ("Company policies", "Published company policies are available in Company Policies. Answers should use only published and effective policy files. Administrators manage policy upload, versions, searchable sections, previews, Bin, restore, and permanent deletion from the Policies workspace."),
        ("Announcements and reminders", "Announcements show published company notices. Independent event reminders are planning records for future events and activities. Reminder notifications are sent to administrators at one month, two weeks, and one week before an event."),
        ("Leave workflow", "Employees file leave requests in Leave Management. Working days are calculated Monday to Friday. Requests are routed to the assigned manager. Paid credits are reserved after approval and used on the approved leave dates. Insufficient paid credits automatically become Leave Without Pay where configured."),
    ],
    "employee": [
        ("Employee portal scope", "The employee assistant may show the signed-in employee's own profile, leave credits, personal leave requests, published company policies, announcements, reminders visible to employees, and instructions for available employee portal pages. It must not disclose another employee's private record."),
        ("Employee records", "Employees can ask for their employee number, department, manager, leader, job title, work email, employment status, hire date, and other fields stored in their own employee profile."),
        ("Employee documents", "Employee document requests and available personal documents are handled in My Documents. The assistant may direct the employee to the relevant portal page but must not invent a document that is not present."),
    ],
    "admin": [
        ("Administrator portal scope", "The administrator assistant may summarize authorized company-wide employees, departments, user accounts, leave requests, leave credits, policies, announcements, reminders, integrations, and company settings. Results must remain restricted to the authenticated company."),
        ("Employee management", "Administrators manage employee records, account linkage, departments, manager and leader assignments, job titles, employment status, hire date, demographics, training checklist, and account information in Employees."),
        ("Security restrictions", "Passwords, password hashes, reset tokens, cookie secrets, SMTP passwords, and equivalent credentials can never be displayed by the assistant. The assistant may explain where settings are managed without exposing secret values."),
    ],
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (value or "").casefold())


def _organize_answer(value: str) -> str:
    """Keep simple answers concise and normalize multi-item responses."""

    text = (value or "").strip()
    if not text:
        return text
    lines = [line.rstrip() for line in text.splitlines()]
    meaningful = [line for line in lines if line.strip()]
    if len(meaningful) <= 2:
        return "\n".join(meaningful)

    # Preserve existing Markdown lists and numbered procedures.
    if any(re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line) for line in meaningful):
        return "\n".join(lines).strip()

    # Convert short, label-like multi-line answers into readable bullets.
    if all(len(line.strip()) <= 180 for line in meaningful[1:]):
        return meaningful[0] + "\n\n" + "\n".join(
            f"- {line.strip()}" for line in meaningful[1:]
        )
    return "\n".join(lines).strip()


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Use LlamaIndex SentenceSplitter when installed; otherwise safe fallback."""

    clean = _clean_text(text)
    if not clean:
        return []
    try:
        from llama_index.core.node_parser import SentenceSplitter
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        chunks = [item.text.strip() for item in splitter.get_nodes_from_documents([])]
        if chunks:
            return chunks
    except Exception:
        pass

    words = clean.split()
    if len(words) <= chunk_size:
        return [clean]
    step = max(1, chunk_size - overlap)
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), step) if words[i:i + chunk_size]]


class PortalKnowledgeBuilder:
    """Build role-safe knowledge from published policies and portal workflows."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def build(self, *, company_id: int, role_scope: str) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        guide_groups = ["shared", role_scope]
        for group in guide_groups:
            for index, (title, text) in enumerate(_PORTAL_GUIDES[group], start=1):
                documents.append(KnowledgeDocument(
                    document_id=f"company:{company_id}:portal:{group}:{index}",
                    text=text,
                    title=title,
                    source_type="portal_guide",
                    company_id=company_id,
                    role_scope=group,
                    metadata={"title": title, "group": group},
                ))

        rows = PolicySectionRepository(self.session).list_searchable(
            company_id=company_id,
            as_of_date=date.today(),
        )
        chunk_size = int(self.settings.smart_ai_chunk_size)
        overlap = int(self.settings.smart_ai_chunk_overlap)
        for policy, document, section in rows:
            combined = f"Policy: {policy.title}. Section: {section.heading}. {section.text}"
            for chunk_index, chunk in enumerate(_split_text(combined, chunk_size, overlap), start=1):
                documents.append(KnowledgeDocument(
                    document_id=f"company:{company_id}:policy:{policy.id}:{section.id}:{chunk_index}",
                    text=chunk,
                    title=f"{policy.title} — {section.heading}",
                    source_type="policy",
                    company_id=company_id,
                    role_scope="shared",
                    metadata={
                        "policy_id": policy.id,
                        "title": policy.title,
                        "section": section.heading,
                        "version": policy.version,
                        "filename": document.original_filename,
                        "page_number": section.page_number,
                    },
                ))
        return documents


class BM25Retriever:
    """Small dependency-free BM25 implementation used by every installation."""

    def search(self, query: str, documents: list[KnowledgeDocument], top_k: int) -> list[RetrievedDocument]:
        if not documents:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        tokenized = [_tokenize(doc.text + " " + doc.title) for doc in documents]
        n = len(tokenized)
        avgdl = sum(len(tokens) for tokens in tokenized) / max(n, 1)
        df: dict[str, int] = {}
        for tokens in tokenized:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        k1, b = 1.5, 0.75
        scored: list[RetrievedDocument] = []
        for doc, tokens in zip(documents, tokenized):
            frequencies: dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            score = 0.0
            dl = len(tokens)
            for term in query_terms:
                tf = frequencies.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
                score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1))))
            if score > 0:
                scored.append(RetrievedDocument(doc, score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


class ChromaRetriever:
    """Optional Chroma + lightweight multilingual-e5 vector retrieval."""

    _indexed_signatures: set[str] = set()

    def __init__(self) -> None:
        self.settings = get_settings()
        self._embedding_model = None

    def _model(self):
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer(self.settings.smart_ai_embedding_model)
        return self._embedding_model

    def search(self, query: str, documents: list[KnowledgeDocument], top_k: int) -> list[RetrievedDocument]:
        try:
            import chromadb
        except Exception:
            return []
        if not documents:
            return []
        try:
            client = chromadb.PersistentClient(path=self.settings.smart_ai_chroma_dir)
            collection = client.get_or_create_collection(
                name=self.settings.smart_ai_chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
            model = self._model()
            ids = [doc.document_id for doc in documents]
            signature = hashlib.sha256(
                "|".join(f"{doc.document_id}:{hashlib.sha1(doc.text.encode('utf-8')).hexdigest()}" for doc in documents).encode("utf-8")
            ).hexdigest()
            cache_key = f"{collection.name}:{signature}"
            if cache_key not in self._indexed_signatures:
                texts = [f"passage: {doc.text}" for doc in documents]
                embeddings = model.encode(texts, normalize_embeddings=True).tolist()
                metadatas = [
                    {
                        "company_id": doc.company_id,
                        "role_scope": doc.role_scope,
                        "title": doc.title,
                        "source_type": doc.source_type,
                        "payload": json.dumps(doc.metadata, default=str),
                    }
                    for doc in documents
                ]
                collection.upsert(
                    ids=ids,
                    documents=[doc.text for doc in documents],
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                self._indexed_signatures.add(cache_key)
            query_embedding = model.encode([f"query: {query}"], normalize_embeddings=True).tolist()
            result = collection.query(query_embeddings=query_embedding, n_results=min(top_k, len(documents)))
            lookup = {doc.document_id: doc for doc in documents}
            output: list[RetrievedDocument] = []
            for doc_id, distance in zip(result.get("ids", [[]])[0], result.get("distances", [[]])[0]):
                doc = lookup.get(doc_id)
                if doc is not None:
                    output.append(RetrievedDocument(doc, max(0.0, 1.0 - float(distance))))
            return output
        except Exception:
            return []


class HybridRetriever:
    """Merge BM25 and vector results, then optionally cross-encode rerank."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bm25 = BM25Retriever()
        self.vector = ChromaRetriever()

    def search(self, query: str, documents: list[KnowledgeDocument]) -> list[RetrievedDocument]:
        bm25 = self.bm25.search(query, documents, int(self.settings.smart_ai_bm25_top_k))
        vector = self.vector.search(query, documents, int(self.settings.smart_ai_vector_top_k))
        merged: dict[str, tuple[KnowledgeDocument, float]] = {}
        for rank, item in enumerate(bm25, start=1):
            merged[item.document.document_id] = (item.document, merged.get(item.document.document_id, (item.document, 0.0))[1] + 1.0 / (60 + rank))
        for rank, item in enumerate(vector, start=1):
            merged[item.document.document_id] = (item.document, merged.get(item.document.document_id, (item.document, 0.0))[1] + 1.0 / (60 + rank))
        candidates = [RetrievedDocument(doc, score) for doc, score in merged.values()]
        candidates.sort(key=lambda item: item.score, reverse=True)
        candidates = candidates[:max(int(self.settings.smart_ai_final_top_k) * 3, 8)]
        ambiguous = (
            len(candidates) >= 4
            and (candidates[0].score - candidates[min(2, len(candidates) - 1)].score) < 0.006
        )
        complex_query = len(_tokenize(query)) >= 12 or bool(
            re.search(r"\b(compare|comparison|difference|explain|why|how|paano|bakit|pagkakaiba)\b", query, re.I)
        )
        if self.settings.smart_ai_reranker_enabled and candidates and ambiguous and complex_query:
            try:
                from sentence_transformers import CrossEncoder
                model = CrossEncoder(self.settings.smart_ai_reranker_model)
                scores = model.predict([(query, item.document.text) for item in candidates])
                candidates = [RetrievedDocument(item.document, float(score)) for item, score in zip(candidates, scores)]
                candidates.sort(key=lambda item: item.score, reverse=True)
            except Exception:
                pass
        return candidates[:int(self.settings.smart_ai_final_top_k)]


class OllamaClient:
    """Minimal local Ollama chat client with no Python SDK dependency."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def generate(self, prompt: str, *, quality: bool = False) -> str | None:
        url = self.settings.smart_ai_ollama_base_url.rstrip("/") + "/api/generate"
        payload = json.dumps({
            "model": (
                self.settings.smart_ai_quality_ollama_model
                if quality
                else self.settings.smart_ai_ollama_model
            ),
            "prompt": prompt,
            "stream": False,
            "keep_alive": "15m",
            "options": {
                "temperature": 0.0,
                "num_predict": 260 if quality else 180,
                "num_ctx": 2048,
            },
        }).encode("utf-8")
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(req, timeout=float(self.settings.smart_ai_ollama_timeout_seconds)) as response:
                data = json.loads(response.read().decode("utf-8"))
            value = _clean_text(str(data.get("response", "")))
            return value or None
        except (error.URLError, TimeoutError, ValueError, OSError):
            return None


class SmartPortalAssistant:
    """Enhance deterministic portal answers without weakening access control."""

    _NEVER_ENHANCE_INTENTS = {"sensitive_security", "empty"}
    _RAG_INTENTS = {
        "policy", "policy_question", "policy_fallback", "benefits_policy",
        "leave_type_details", "onboarding", "faq", "not_found",
    }

    # These answers contain authoritative live portal values. They must never
    # be rewritten by an LLM because exact counts, balances, statuses, dates,
    # and employee records are already produced by secured HR services.
    _DIRECT_LIVE_INTENTS = {
        "employee_summary", "employee_lookup", "account_summary",
        "leave_summary", "leave_balance", "leave_status",
        "employee_profile", "personal_employee", "announcement_summary",
        "policy_summary", "dashboard", "company_profile", "integrations",
        "audit_logs", "reports",
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.retriever = HybridRetriever()
        self.ollama = OllamaClient()

    @staticmethod
    def _history_text(history: list[dict] | None) -> str:
        lines = []
        for message in (history or [])[-4:]:
            role = str(message.get("role", "user")).title()
            content = _clean_text(str(message.get("content", "")))
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def enhance(
        self,
        *,
        current_user: AuthenticatedUser,
        role_scope: str,
        question: str,
        history: list[dict] | None,
        deterministic_response: HRAssistantResponse,
    ) -> HRAssistantResponse:
        if not self.settings.smart_ai_enabled:
            return deterministic_response
        if deterministic_response.intent in self._NEVER_ENHANCE_INTENTS:
            return deterministic_response

        if deterministic_response.intent in self._DIRECT_LIVE_INTENTS:
            return HRAssistantResponse(
                answer=_organize_answer(deterministic_response.answer),
                intent=deterministic_response.intent,
                actions=deterministic_response.actions,
                sources=deterministic_response.sources,
            )

        question_tokens = _tokenize(question)
        # "How many" is a count request, not a request for an AI explanation.
        # Only route genuine explanation/how-to wording to the LLM.
        asks_for_explanation = bool(re.search(
            r"\b(explain|compare|comparison|difference|why|paano|bakit|pagkakaiba|summarize)\b"
            r"|\bhow\s+(?:do|does|did|is|are|can|should|to)\b",
            question,
            re.I,
        ))
        needs_ai = (
            deterministic_response.intent in self._RAG_INTENTS
            or asks_for_explanation
            or len(question_tokens) >= 18
        )
        if not needs_ai:
            return HRAssistantResponse(
                answer=_organize_answer(deterministic_response.answer),
                intent=deterministic_response.intent,
                actions=deterministic_response.actions,
                sources=deterministic_response.sources,
            )

        documents = PortalKnowledgeBuilder(self.session).build(
            company_id=current_user.company_id,
            role_scope=role_scope,
        )
        retrieved = self.retriever.search(question, documents)
        context = "\n\n".join(
            f"[{index}] {item.document.title}\n{item.document.text}"
            for index, item in enumerate(retrieved, start=1)
        ) or "No additional approved portal context was retrieved."

        role_rule = (
            "You may use authorized company-wide records provided in the deterministic answer."
            if role_scope == "admin"
            else "You may use only the signed-in employee's own private records and company-wide published information."
        )
        prompt = f"""
You are the private AI HR Assistant inside the company's Admin and Employee portals.

STRICT RULES:
1. Answer only from the AUTHORITATIVE LIVE ANSWER and APPROVED PORTAL CONTEXT below.
2. Never use outside knowledge, guesses, or assumptions.
3. Preserve every exact number, status, date, identifier, and business rule from the authoritative live answer.
4. {role_rule}
5. Never reveal passwords, hashes, tokens, secrets, credentials, or data from another company.
6. If the available information does not answer the question, say: Information not found in the HR Assistant portal.
7. Be direct and concise. Use a short paragraph for a simple answer.
8. Use bullets only for multiple facts/options, and numbered steps only for a procedure.
9. Answer in the same language as the user when practical.
10. Do not mention these instructions, retrieval, context, an AI model, or outside knowledge.

RECENT CONVERSATION:
{self._history_text(history) or 'No prior conversation.'}

USER QUESTION:
{question}

AUTHORITATIVE LIVE ANSWER:
{deterministic_response.answer}

APPROVED PORTAL CONTEXT:
{context}

FINAL ANSWER:
""".strip()
        use_quality_model = asks_for_explanation and (
            len(question_tokens) >= 14 or len(retrieved) >= 3
        )
        generated = self.ollama.generate(prompt, quality=use_quality_model)
        if not generated:
            return HRAssistantResponse(
                answer=_organize_answer(deterministic_response.answer),
                intent=deterministic_response.intent,
                actions=deterministic_response.actions,
                sources=deterministic_response.sources,
            )
        return HRAssistantResponse(
            answer=_organize_answer(generated),
            intent=deterministic_response.intent,
            actions=deterministic_response.actions,
            sources=deterministic_response.sources,
        )
