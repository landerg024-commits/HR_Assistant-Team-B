"""Generic local RAG regression patterns: not production QA answer keys."""
from types import SimpleNamespace
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, HybridRetriever,
    SmartPortalAssistant, UNDETERMINED_ANSWER,
)


def evidence(id, name, body, *, company=17, role="shared", section="Rules"):
    return KnowledgeDocument(
        id, body, name, "policy", company, role,
        {"file_key": name, "filename": name + ".docx", "section": section},
    )


def test_second_direct_policy_consequence_survives_single_file_domination():
    question = "What happens if an employee fails to submit the daily checklist at shift end?"
    main = evidence("main", "daily logs", "An employee who fails to submit the daily checklist at shift end is marked absent in the daily log.")
    second = evidence("second", "staff rewards", "An employee who fails to submit the daily checklist at shift end will be disqualified from the monthly performance award.")
    seeds = [RetrievedDocument(main, .039) for _ in range(3)]
    reps = [RetrievedDocument(second, .019)]
    output, reason = HybridRetriever._preserve_direct_cross_file_evidence(question, seeds, reps)
    assert reason == "direct-secondary-policy-preserved"
    assert output[-1].document.document_id == "second"
    assert output[0].document.document_id == "main"


def test_no_unrelated_second_policy_and_no_cross_company_record():
    question = "What happens if an employee fails to submit the daily checklist at shift end?"
    main = evidence("main", "daily logs", "An employee who fails to submit the daily checklist at shift end is marked absent in the daily log.")
    irrelevant = evidence("irrelevant", "unrelated", "A worker may apply for a travel allowance after an approval.")
    alien = evidence("alien", "another company", "An employee who fails to submit the daily checklist at shift end will be suspended.", company=99)
    private = evidence("private", "staff review", "An employee who fails to submit the daily checklist at shift end will be suspended.", role="admin")
    seeds = [RetrievedDocument(main, .05), RetrievedDocument(main, .04)]
    reps = [RetrievedDocument(x, .03) for x in (irrelevant, alien, private)]
    output, reason = HybridRetriever._preserve_direct_cross_file_evidence(question, seeds, reps)
    assert reason == "no-supported-second-source"
    assert {x.document.document_id for x in output} == {"main"}


def test_do_not_force_unrelated_policy_diversity_on_definition_questions():
    base = evidence("a", "alpha", "The organization values personal development.")
    other = evidence("b", "beta", "Employees participate in development events.")
    answer, reason = HybridRetriever._preserve_direct_cross_file_evidence(
        "What is the purpose of the organization's development program?",
        [RetrievedDocument(base, .09), RetrievedDocument(base, .08)],
        [RetrievedDocument(other, .05)],
    )
    assert reason == "not-a-direct-rule-question"
    assert answer[0].document.document_id == "a"


class DummyTrace:
    def __init__(self):
        self.logs = []
    def line(self, section, message):
        self.logs.append((section, message))


def test_binary_contradiction_one_local_repair_uses_authorized_evidence():
    class Model:
        def __init__(self):
            self.calls = []
        def generate(self, prompt, *, quality, timeout_seconds):
            self.calls.append((prompt, quality, timeout_seconds))
            return "YES. This is expressly permitted by the documented exception."

    assistant = SmartPortalAssistant.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(binary_repair_enabled=True,
                                         binary_repair_timeout_seconds=18,
                                         evidence_excerpt_chars=900)
    assistant.ollama = Model()
    doc = evidence("p", "staff exceptions", "The rule permits continued participation when the request was submitted on time, subject to other criteria.")
    answer = assistant._repair_local_binary_answer(
        question="Can an employee still participate after submitting the request on time?",
        retrieved=[RetrievedDocument(doc, .04)], trace=DummyTrace(),
    )
    assert answer.startswith("**YES.")
    assert len(assistant.ollama.calls) == 1
    prompt, quality, timeout = assistant.ollama.calls[0]
    assert "permits continued participation" in prompt
    assert quality is False and timeout == 18


def test_binary_repair_disabled_abstains_without_external_calls():
    assistant = SmartPortalAssistant.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(binary_repair_enabled=False)
    class FailClient:
        def generate(self, *args, **kwargs):
            raise AssertionError("Model should not be called")
    assistant.ollama = FailClient()
    doc = evidence("p", "staff exceptions", "A permitted exception is documented.")
    result = assistant._repair_local_binary_answer(
        question="Is the exception allowed?",
        retrieved=[RetrievedDocument(doc, .04)], trace=DummyTrace(),
    )
    assert result == UNDETERMINED_ANSWER
