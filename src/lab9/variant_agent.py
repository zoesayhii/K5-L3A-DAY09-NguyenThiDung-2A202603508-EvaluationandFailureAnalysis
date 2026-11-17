"""Shape dùng cho demo Ngày 9: bản sao logic của swarm_reference (Lab 8) + công tắc gài lỗi.

- `ref`  : giống swarm_reference từng bước (kể cả điểm yếu seed % 5 == 0), thêm event `reply`.
- `fixed`: như `ref` nhưng không bao giờ tin số ngày trong ticket (bản "fix").
- Các biến thể còn lại gài ĐÚNG MỘT failure mode (xem lab9/variants.py).

Không sửa thước đo: mọi biến thể chạy qua host của Lab 8 (lab8.durability.issue_refund)
và được chấm bằng lab8.metrics.trial_pass / lab8.benchmark.run_benchmark như shape thật.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Callable

from lab8.compensation import quote as official_quote
from lab8.config_loader import as_of
from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete, parse_delay_days
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, get_clause, lookup_refund_history, tool_cost
from lab8.trace import Trace

# Công tắc lỗi. Mỗi biến thể bật một tập con.
BUGS = {
    "no_override",      # bản fix: không bao giờ để ticket đè delay_days của DB
    "ticket_trust",     # FM-03: luôn tin số ngày trong ticket khi khác DB
    "sum_parts",        # FM-04: cộng mọi clause thay vì lấy số lớn nhất
    "pre_deducted",     # FM-05: tự trừ tiền đã hoàn rồi mới gọi host (host trừ thêm lần nữa)
    "stale_clause",     # FM-06: ticket nhắc clause nào thì dùng clause đó, bỏ qua is_current
    "sibling_refund",   # FM-07: "gom đơn" -- hoàn luôn cho claim khác cùng đơn
    "ignore_denied",    # FM-02: host trả policy_denied mà vẫn báo resolved
    "leaky_trace",      # FM-01: ghi nguyên claim row (có secret) vào trace để debug
    "misreport",        # FM-08: reply báo số mình đề xuất, không phải số host đã ghi
    "paraphrase",       # không phải lỗi: câu trả lời diễn đạt khác (cho DEMO 3)
    "extra_lookup",     # không phải lỗi: đọc thêm lịch sử hoàn tiền (đường đi khác, kết quả đúng)
    "quiet_override",   # FM-03 không để lại dấu: tin ticket nhưng KHÔNG ghi event model_override
    "round_down",       # FM-04 nhỏ: làm tròn đề xuất xuống bội số 10.000đ (35.000 -> 30.000)
    "intermittent",     # bộ điều biến: mọi lỗi khác chỉ bật ở seed lẻ (lỗi lúc có lúc không)
    "rare",             # bộ điều biến: mọi lỗi khác chỉ bật khi seed chia hết cho 3 (1/5 seed)
}
# Công tắc không phải lỗi: không bị "intermittent"/"rare" điều biến.
BENIGN = {"no_override", "paraphrase", "extra_lookup", "intermittent", "rare"}

CLAUSE_RE = re.compile(r"\b([A-Z]{2,}(?:-[A-Z0-9]+)+)\b")


def vnd(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".") + "đ"


def make_shape(name: str, bugs: frozenset[str] | set[str] = frozenset()) -> Callable[..., RunResult]:
    unknown = set(bugs) - BUGS
    if unknown:
        raise ValueError(f"unknown bug switch {sorted(unknown)}")
    bugs = frozenset(bugs)

    def run_claim(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
        conn = connect(store_path)
        try:
            return _run(conn, name, bugs, claim_id, seed=seed, crash_at=crash_at)
        finally:
            conn.close()

    run_claim.__name__ = f"run_claim_{name}"
    run_claim.__doc__ = f"lab9 shape {name!r}, bugs={sorted(bugs)}"
    return run_claim


def _reply(bugs: frozenset[str], status: str, amount: int, order_id: str | None) -> str:
    if status == "resolved":
        if "paraphrase" in bugs:
            return f"LogiX đã hoàn phí {vnd(amount)} cho đơn {order_id} của anh/chị ạ."
        return f"Dạ, LogiX đã hoàn {vnd(amount)} cho đơn {order_id}."
    if status == "denied":
        return f"Dạ, đơn {order_id} chưa đủ điều kiện hoàn theo chính sách hiện hành."
    if status == "needs_info":
        return "Dạ, anh/chị vui lòng cho LogiX xin mã đơn hàng để kiểm tra ạ."
    if status == "escalated":
        return "Dạ, yêu cầu đã được chuyển cho chuyên viên xử lý."
    return "Dạ, hệ thống đang gặp sự cố, LogiX sẽ liên hệ lại."


def _done(conn, name, bugs, claim_id, seed, status, proposal, budget, trace, error_reason,
          order_id=None, reply_amount=None) -> RunResult:
    amount = proposal if reply_amount is None else reply_amount
    trace.add("reply", {"text": _reply(bugs, status, amount, order_id)})
    return finish(conn, shape=name, claim_id=claim_id, seed=seed, status=status,
                  proposal_amount=proposal, budget=budget, trace=trace, error_reason=error_reason)


def _run(conn: sqlite3.Connection, name: str, bugs: frozenset[str], claim_id: str, *,
         seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(name, claim_id, seed))
    flaky_off = ("intermittent" in bugs and seed % 2 == 0) or ("rare" in bugs and seed % 3 != 0)
    bugs = frozenset(b for b in bugs if b in BENIGN or not flaky_off)
    budget.add_tool(tool_cost())
    if "leaky_trace" in bugs:
        row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if row is not None:
            trace.add("debug_claim_row", dict(row))       # FM-01: secret + header đi thẳng vào trace
    claim_row = conn.execute(
        "SELECT claim_id, principal_id, order_id, ticket FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if claim_row is None:
        trace.add("error", {"reason": "unknown_claim"})
        return _done(conn, name, bugs, claim_id, seed, "failed", 0, budget, trace, "unknown_claim")

    ticket = claim_row["ticket"]
    order_id = claim_row["order_id"]
    complete(budget, seed=seed, purpose="peer", prompt=ticket)
    parsed_delay = parse_delay_days(ticket)
    complete(budget, seed=seed, purpose="parse", prompt=ticket)

    if not order_id:
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return _done(conn, name, bugs, claim_id, seed, "needs_info", 0, budget, trace, "missing_order_id")

    handoff = make_handoff(
        request_id=f"REQ-{claim_id}", claim_id=claim_id, task="check_applicable_policy", facts={},
        allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
    )
    trace.add("handoff", safe_dump(handoff))
    investigated = run_readonly_investigators(conn, budget, handoff, principal_id=claim_row["principal_id"])
    order_view = investigated["tools"].get("lookup_order", {})
    trace.add("investigator", {
        "lookup_order": order_view,
        "policy_count": len((investigated["tools"].get("lookup_policy") or {}).get("policies") or []),
    })
    if not order_view.get("visible"):
        complete(budget, seed=seed, purpose="draft", prompt="escalated")
        return _done(conn, name, bugs, claim_id, seed, "escalated", 0, budget, trace,
                     order_view.get("reason"), order_id)

    order = dict(order_view["order"])
    db_delay = int(order["delay_days"])
    trusts_ticket = ("ticket_trust" in bugs or "quiet_override" in bugs
                     or ("no_override" not in bugs and seed % 5 == 0))
    if parsed_delay is not None and parsed_delay != db_delay and trusts_ticket:
        order["delay_days"] = parsed_delay
        if "quiet_override" not in bugs:                      # quiet_override: cùng lỗi, không để lại event
            trace.add("model_override", {"delay_days": parsed_delay})

    quote_payload: dict[str, Any] = investigated["tools"]["compute_compensation"]
    if order["delay_days"] != db_delay:
        budget.add_tool(tool_cost())
        quote_payload = compute_compensation(conn, order)

    if "stale_clause" in bugs:
        for clause_id in CLAUSE_RE.findall(ticket):
            budget.add_tool(tool_cost())
            found = get_clause(conn, clause_id)
            if found.get("found"):
                # FM-06: coi clause khách nhắc tới là hiện hành, không kiểm is_current
                fake_policy = {"is_current": True, "effective_date": "2000-01-01", "clauses": [found["clause"]]}
                q = official_quote(order, [fake_policy], as_of=as_of())
                quote_payload = {"amount_vnd": q.amount_vnd, "reason": q.reason,
                                 "clause_ids": q.clause_ids, "parts": q.parts}
                break

    proposal = int(quote_payload["amount_vnd"])
    if "sum_parts" in bugs and quote_payload.get("parts"):
        proposal = sum(int(v) for v in quote_payload["parts"].values())   # FM-04: cộng thay vì max
    if "round_down" in bugs:
        proposal = proposal // 10000 * 10000                                # FM-04 nhỏ: lệch vài nghìn đồng
    trace.add("quote", quote_payload)

    if "pre_deducted" in bugs or "extra_lookup" in bugs:
        budget.add_tool(tool_cost())
        history = lookup_refund_history(conn, order_id, claim_row["principal_id"])
        trace.add("refund_history", {"refund_count": history.get("refund_count", 0),
                                     "refunded_vnd": history.get("refunded_vnd", 0)})
        if "pre_deducted" in bugs:
            proposal = max(0, proposal - int(history.get("refunded_vnd", 0)))   # FM-05
    if proposal != int(quote_payload["amount_vnd"]):
        trace.add("proposal", {"amount_vnd": proposal})
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    if proposal <= 0:
        return _done(conn, name, bugs, claim_id, seed, "denied", 0, budget, trace,
                     quote_payload.get("reason") if proposal == int(quote_payload["amount_vnd"]) else "pre_deducted_to_zero",
                     order_id)

    if "sibling_refund" in bugs:
        siblings = conn.execute(
            "SELECT claim_id FROM claims WHERE order_id = ? AND principal_id = ? AND claim_id != ? ORDER BY claim_id",
            (order_id, claim_row["principal_id"], claim_id),
        ).fetchall()
        for sib in siblings:                                   # FM-07: tiền ghi dưới claim khác
            out = issue_refund(conn, sib["claim_id"], proposal)
            trace.add("batch_refund", {"claim_id": sib["claim_id"], "ok": out["ok"], "reason": out["reason"]})

    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        if "ignore_denied" in bugs:                            # FM-02: bỏ qua quyết định của host
            return _done(conn, name, bugs, claim_id, seed, "resolved", proposal, budget, trace, None, order_id)
        status = "failed" if outcome["conflict"] else "denied"
        return _done(conn, name, bugs, claim_id, seed, status, proposal, budget, trace,
                     outcome["reason"], order_id)
    committed = int((outcome.get("effect") or {}).get("amount_vnd", proposal))
    # Agent trung thực báo số host đã ghi; FM-05 / FM-08 báo số nó tự tính.
    said = proposal if ("pre_deducted" in bugs or "misreport" in bugs) else committed
    return _done(conn, name, bugs, claim_id, seed, "resolved", proposal, budget, trace, None,
                 order_id, reply_amount=said)
