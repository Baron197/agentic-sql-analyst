"""Whole runs through the LangGraph graph with a scripted model (keyless, no database).

The six paths from the Phase 4 Definition of Done: success, repair, unsafe refusal,
unanswerable refusal, budget stop, and grounding rejection; plus their edge cases.
"""

import json

from backend.tests.agent.conftest import (
    ANALYST,
    BY_CHANNEL_SQL,
    MANAGER,
    ORDERS_SQL,
    VALIDATOR,
    ScriptedLLM,
    StubExecutor,
    make_agent,
)
from sql_analyst.agent.schemas import AnswerDraft, ChartSpec, CriticVerdict, SQLDraft
from sql_analyst.llm.base import LLMError, Usage
from sql_analyst.safety.errors import QueryFailed

PATH = [
    "guard_input",
    "retrieve_context",
    "generate_sql",
    "validate_sql",
    "execute",
    "check_result",
    "write_answer",
    "render_numbers",
]


def _sql(sql=ORDERS_SQL, **kw):
    return SQLDraft(decision="answer", sql=sql, **kw)


def _answer(template="There were {{r0.orders}} orders.", **kw):
    kw.setdefault("chart", ChartSpec(type="kpi", y="orders"))
    return AnswerDraft(template=template, **kw)


def _nodes(result):
    return [e.node for e in result.trace]


# ------------------------------------------------------------------ success
def test_success_path_fills_numbers_from_the_result(run_store):
    llm = ScriptedLLM(
        {SQLDraft: [_sql(assumptions=["All orders, any status."])], AnswerDraft: [_answer()]}
    )
    executor = StubExecutor((["orders"], [[12345]]))
    r = make_agent(llm, executor, run_store=run_store).ask("How many orders are there?", ANALYST)

    assert r.status == "answered"
    assert r.answer == "There were 12,345 orders."
    assert r.model_text == "There were   orders."  # what the model typed: no digits
    assert r.assumptions == ["All orders, any status."]
    assert r.chart.type == "kpi" and r.row_count == 1 and r.repairs == 0
    assert _nodes(r) == PATH  # finalize records the run itself
    assert r.usage.llm_calls == 2 and r.usage.keyless and r.usage.cost_usd == 0
    assert r.sql == VALIDATOR.validate(ORDERS_SQL).sql and executor.calls[0][1] == ANALYST

    sql_prompt = llm.messages("SQLDraft")[0]
    assert "<context>" in sql_prompt and "## Relevant views" in sql_prompt
    assert "Question: How many orders are there?" in sql_prompt
    assert "access to all regions" in sql_prompt and "2026-10-01" in sql_prompt
    stored = [json.loads(line) for line in next(run_store.directory.glob("*.jsonl")).open()]
    assert stored[0]["run_id"] == r.run_id and stored[0]["status"] == "answered"


def test_indonesian_question_is_answered_with_indonesian_formatting():
    llm = ScriptedLLM(
        {
            SQLDraft: [_sql(BY_CHANNEL_SQL)],
            AnswerDraft: [
                _answer(
                    "Channel teratas {{r0.channel_name}} dengan {{r0.orders}} pesanan.",
                    chart=ChartSpec(type="bar", x="channel_name", y="orders"),
                )
            ],
        }
    )
    executor = StubExecutor((["channel_name", "orders"], [["Website", 4321], ["Mobile app", 99]]))
    r = make_agent(llm, executor).ask("Berapa jumlah pesanan per channel?", ANALYST)
    assert r.lang == "id" and r.answer == "Channel teratas Website dengan 4.321 pesanan."
    assert "Bahasa Indonesia" in llm.messages("AnswerDraft")[0]
    assert r.chart.type == "bar"


def test_manager_scope_reaches_the_executor_and_the_prompt():
    llm = ScriptedLLM({SQLDraft: [_sql()], AnswerDraft: [_answer()]})
    executor = StubExecutor((["orders"], [[7]]))
    make_agent(llm, executor).ask("How many orders are there?", MANAGER)
    assert executor.calls[0][1] == MANAGER
    assert "some regions only" in llm.messages("SQLDraft")[0]


# ------------------------------------------------------------------- repair
def test_rejected_sql_is_repaired_with_the_validator_error():
    llm = ScriptedLLM(
        {SQLDraft: [_sql("SELECT email FROM core.customers"), _sql()], AnswerDraft: [_answer()]}
    )
    r = make_agent(llm, StubExecutor((["orders"], [[5]]))).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.repairs == 1
    assert [a.stage for a in r.sql_attempts] == ["validate", "check"]
    assert r.sql_attempts[0].error_code == "forbidden_table" and not r.sql_attempts[0].ok
    retry = llm.messages("SQLDraft")[1]
    assert "Previous attempts failed" in retry and "core.customers" in retry
    assert _nodes(r).count("generate_sql") == 2


def test_database_error_is_repaired():
    llm = ScriptedLLM({SQLDraft: [_sql(), _sql()], AnswerDraft: [_answer()]})
    executor = StubExecutor(
        QueryFailed("The database rejected the query: boom"), (["orders"], [[5]])
    )
    r = make_agent(llm, executor).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.repairs == 1
    assert r.sql_attempts[0].stage == "execute" and "boom" in llm.messages("SQLDraft")[1]


def test_repairs_are_capped_then_the_run_ends_with_an_error():
    bad = _sql("SELECT * FROM pg_authid")
    llm = ScriptedLLM({SQLDraft: [bad, bad, bad, bad]})
    r = make_agent(llm).ask("How many orders?", ANALYST)
    assert r.status == "error" and r.repairs == 3 and len(r.sql_attempts) == 4
    assert r.answer and "couldn't build" in r.answer
    assert r.error.startswith("forbidden_table")


def test_no_repair_ablation_stops_at_the_first_failure():
    llm = ScriptedLLM({SQLDraft: [_sql("SELECT * FROM pg_authid")]})
    r = make_agent(llm, repair=False).ask("How many orders?", ANALYST)
    assert r.status == "error" and r.repairs == 0 and r.usage.llm_calls == 1
    assert r.variant == "agent-no-repair"


def test_empty_result_is_retried_once_then_accepted_with_a_caveat():
    llm = ScriptedLLM({SQLDraft: [_sql(), _sql()], AnswerDraft: [_answer("No orders matched.")]})
    executor = StubExecutor((["orders"], []), (["orders"], []))
    r = make_agent(llm, executor).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.repairs == 1
    assert r.sql_attempts[0].error_code == "result_check"
    assert "No rows matched the question." in r.caveats


def test_critic_can_send_the_run_back_once():
    llm = ScriptedLLM(
        {
            SQLDraft: [_sql(), _sql()],
            CriticVerdict: [CriticVerdict(ok=False, problem="Exclude cancelled orders.")],
            AnswerDraft: [_answer()],
        }
    )
    executor = StubExecutor((["orders"], [[10]]), (["orders"], [[8]]))
    r = make_agent(llm, executor, critic=True).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.repairs == 1 and r.answer == "There were 8 orders."
    assert "Exclude cancelled orders." in llm.messages("SQLDraft")[1]
    assert r.variant == "agent-critic"


# ----------------------------------------------------------------- refusals
def test_unsafe_question_is_refused_by_the_guard_before_any_model_call():
    llm, executor = ScriptedLLM(), StubExecutor()
    r = make_agent(llm, executor).ask("Delete all cancelled orders from the database.", ANALYST)
    assert r.status == "refused" and r.refusal.kind == "unsafe" and r.refusal.source == "guard"
    assert llm.calls == [] and executor.calls == []
    assert _nodes(r) == ["guard_input", "refuse"]
    assert "only reads business data" in r.answer and r.sql is None


def test_unsafe_question_can_be_refused_by_the_model():
    llm = ScriptedLLM({SQLDraft: [SQLDraft(decision="refuse_unsafe", reason="asks for core data")]})
    r = make_agent(llm).ask("Join the orders to the raw customer table please.", ANALYST)
    assert r.status == "refused" and r.refusal.kind == "unsafe" and r.refusal.source == "model"


def test_unanswerable_question_is_refused_in_its_language():
    llm = ScriptedLLM(
        {SQLDraft: [SQLDraft(decision="refuse_unanswerable", reason="Data starts in 2024.")]}
    )
    r = make_agent(llm).ask("Berapa pendapatan bersih tahun 2019?", ANALYST)
    assert r.status == "refused" and r.refusal.kind == "unanswerable"
    assert r.answer.startswith("Maaf") and r.refusal.reason == "Data starts in 2024."


# --------------------------------------------------------------- budget stop
def test_llm_call_limit_stops_before_the_answer_call_and_returns_the_table():
    llm = ScriptedLLM({SQLDraft: [_sql()]})
    r = make_agent(llm, StubExecutor((["orders"], [[3]])), limits={"max_llm_calls": 1}).ask(
        "How many orders?", ANALYST
    )
    assert r.status == "partial" and "LLM call limit" in r.stop_reason
    assert r.usage.llm_calls == 1 and r.rows == [[3]]
    assert "budget_stop" in _nodes(r) and "write_answer" not in _nodes(r)
    assert r.answer == "Here is the result of the query (1 rows)."
    assert any("stopped early" in c for c in r.caveats)


def test_time_limit_stops_the_run_cleanly():
    llm = ScriptedLLM()
    r = make_agent(llm, limits={"max_seconds": 0.0}).ask("How many orders?", ANALYST)
    assert r.status == "partial" and "time limit" in r.stop_reason
    assert llm.calls == [] and r.rows == []
    assert r.answer.startswith("I stopped before finishing")


def test_token_limit_stops_the_run():
    llm = ScriptedLLM({SQLDraft: [_sql()]})
    r = make_agent(llm, StubExecutor((["orders"], [[3]])), limits={"max_tokens": 50}).ask(
        "How many orders?", ANALYST
    )
    assert r.status == "partial" and "token limit" in r.stop_reason


# ------------------------------------------------------- grounding rejection
def test_typed_number_is_rejected_and_the_answer_rewritten():
    llm = ScriptedLLM(
        {
            SQLDraft: [_sql()],
            AnswerDraft: [_answer("There were about 12,000 orders."), _answer()],
        }
    )
    r = make_agent(llm, StubExecutor((["orders"], [[12345]]))).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.answer == "There were 12,345 orders."
    assert (
        "12,000" in llm.messages("AnswerDraft")[1] and "rejected" in llm.messages("AnswerDraft")[1]
    )
    assert _nodes(r).count("write_answer") == 2 and not r.answer_fallback


def test_numbers_from_the_question_may_be_typed():
    llm = ScriptedLLM(
        {SQLDraft: [_sql()], AnswerDraft: [_answer("In 2025 there were {{r0.orders}} orders.")]}
    )
    r = make_agent(llm, StubExecutor((["orders"], [[9]]))).ask("How many orders in 2025?", ANALYST)
    assert r.answer == "In 2025 there were 9 orders." and not r.answer_fallback


def test_second_grounding_failure_falls_back_to_the_table_only():
    bad = _answer("Roughly 12 thousand orders.", caveats=["Up 3% on last year."])
    llm = ScriptedLLM({SQLDraft: [_sql()], AnswerDraft: [bad, bad]})
    r = make_agent(llm, StubExecutor((["orders"], [[12345]]))).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.answer_fallback
    assert r.answer == "Here is the result of the query (1 rows)."
    assert r.model_text == "" and not any("3%" in c for c in r.caveats)


def test_bad_slot_is_rejected_like_a_typed_number():
    llm = ScriptedLLM({SQLDraft: [_sql()], AnswerDraft: [_answer("{{r0.revenue}}"), _answer()]})
    r = make_agent(llm, StubExecutor((["orders"], [[4]]))).ask("How many orders?", ANALYST)
    assert r.answer == "There were 4 orders."
    assert "Unknown column 'revenue'" in llm.messages("AnswerDraft")[1]


def test_assumptions_with_invented_figures_are_dropped():
    draft = _sql(
        assumptions=["Orders up to 2026-09-30 are counted.", "Revenue grew 14% last year."]
    )
    sql_with_date = ORDERS_SQL + " WHERE o.ordered_at < '2026-09-30'"
    draft = draft.model_copy(update={"sql": sql_with_date})
    llm = ScriptedLLM({SQLDraft: [draft], AnswerDraft: [_answer()]})
    r = make_agent(llm, StubExecutor((["orders"], [[4]]))).ask("How many orders?", ANALYST)
    assert r.assumptions == ["Orders up to 2026-09-30 are counted."]


# ------------------------------------------------------------- model failures
def test_model_failure_while_writing_sql_ends_with_an_error_and_records_usage():
    usage = Usage(provider="fake", model="fake", input_tokens=10, output_tokens=0)
    llm = ScriptedLLM({SQLDraft: [LLMError("incomplete response", usage)]})
    r = make_agent(llm).ask("How many orders?", ANALYST)
    assert r.status == "error" and r.error.startswith("llm_error")
    assert r.usage.input_tokens == 10


def test_model_failure_while_writing_the_answer_falls_back_to_the_table():
    llm = ScriptedLLM({SQLDraft: [_sql()], AnswerDraft: [LLMError("refused")]})
    r = make_agent(llm, StubExecutor((["orders"], [[4]]))).ask("How many orders?", ANALYST)
    assert r.status == "answered" and r.answer_fallback and r.rows == [[4]]


def test_no_retrieval_ablation_puts_the_whole_dictionary_in_the_static_prompt():
    llm = ScriptedLLM({SQLDraft: [_sql()], AnswerDraft: [_answer()]})
    r = make_agent(llm, StubExecutor((["orders"], [[1]])), retrieval=False).ask(
        "How many orders?", ANALYST
    )
    _schema, system, message = llm.calls[0]
    assert "## analytics.fact_web_sessions" in system and "<context>" not in message
    assert r.context.full_schema and r.variant == "agent-no-retrieval"


def test_static_sql_prompt_is_identical_across_questions():
    """Prompt caching needs a byte-identical prefix: nothing question-specific in it."""
    llm = ScriptedLLM({SQLDraft: [_sql(), _sql()], AnswerDraft: [_answer(), _answer()]})
    agent = make_agent(llm, StubExecutor((["orders"], [[1]]), (["orders"], [[2]])))
    agent.ask("How many orders?", ANALYST)
    agent.ask("Berapa jumlah pesanan?", MANAGER)
    systems = [system for schema, system, _ in llm.calls if schema == "SQLDraft"]
    assert systems[0] == systems[1]
