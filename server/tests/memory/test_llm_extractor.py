"""Step 11 gate: LLMExtractor with a fake transport.

The request body holds only LLM_SAFE text and existing slot KEYS; malformed JSON -> zero candidates (+ ERROR event);
strict schema; LLM output still goes through grounding, P1 and policy.
"""

from __future__ import annotations

import json
import unittest

from server.services.memory.extractor import LLMExtractor, parse_llm_output

from ._util import SECRET, TempStoreCase, make_service, user_turn

EMAIL = "test.user@example.com"
MEETING_CANDIDATE = {  # deep dive §27.1 step 5, verbatim
    "memory_type": "preference", "subject": "user", "predicate": "pref.meeting_time", "object_entity": None,
    "value": "after 10 AM", "text": "User prefers meetings after 10 AM.", "durability": "long_term",
    "certainty": "explicit", "is_correction": False, "explicit_remember": False, "is_instruction_to_assistant": False,
    "sensitivity_category": "none", "evidence": "I prefer meetings after 10 AM", "horizon": None}


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    async def __call__(self, *, model, messages, system, api_key=None, tools=None, **_):
        self.requests.append({"model": model, "system": system, "messages": messages, "tools": tools})
        content = self.replies.pop(0) if self.replies else json.dumps({"candidates": [], "ignored": []})
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class LLMCase(TempStoreCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        TempStoreCase.setUp(self)

    def service(self, replies):
        self.transport = FakeTransport(replies)
        self.svc = make_service(self.store, self.scope, extractor=LLMExtractor("test/model", transport=self.transport))
        return self.svc


class TestRequestBoundary(LLMCase):
    async def test_request_contains_only_llm_safe_text_and_slot_keys(self):
        svc = self.service([json.dumps({"candidates": [MEETING_CANDIDATE], "ignored": []})])
        user_turn(svc, "I prefer meetings after 10 AM.")
        await svc.await_idle()
        self.assertEqual(len(self.store.rows_in_slot(self.scope, "user|pref.meeting_time", ["active"])), 1)

        user_turn(svc, f"My email is {EMAIL}, my test API key is {SECRET}, and I prefer concise emails.",
                  prev_reply=f"Sure, I'll email {EMAIL}.")
        await svc.await_idle()
        req = self.transport.requests[-1]
        body = json.dumps(req)
        self.assertNotIn(SECRET, body)
        self.assertNotIn("SYNTHETIC-12345", body)
        self.assertNotIn(EMAIL, body)  # contacts are placeholders toward the extractor (P0)
        self.assertIn("My email is [EMAIL_1], my test API key is [SECRET:API_KEY], and I prefer concise emails.", body)
        self.assertIn('note="context only, not a source">Sure, I\'ll email [EMAIL_1].</previous_assistant_reply>',
                      req["messages"][0]["content"])
        # Existing slot keys only: the key is there, the stored value/text is not.
        self.assertIn('Existing keys: ["user|pref.meeting_time"]', req["system"])
        self.assertNotIn("User prefers meetings after 10 AM", body)
        self.assertNotIn("10:00", body)
        self.assertIsNone(req["tools"])
        self.assertIn("You extract durable facts about the USER", req["system"])  # mock classifier phrase

    async def test_llm_candidates_go_through_grounding_privacy_and_policy(self):
        injected = dict(MEETING_CANDIDATE, value="before 6 AM", text="User prefers meetings before 6 AM.",
                        evidence="I prefer meetings before 6 AM")  # not in the message: ungrounded
        secret_c = dict(MEETING_CANDIDATE, predicate="profile.api_key", memory_type="profile", value="[SECRET:API_KEY]",
                        text="User's API key is [SECRET:API_KEY].", evidence="my test API key is [SECRET:API_KEY]")
        svc = self.service([json.dumps({"candidates": [injected, secret_c], "ignored": []})])
        p = user_turn(svc, f"I prefer meetings after 10 AM and my test API key is {SECRET}.")
        await svc.await_idle()
        self.assertEqual(self.store.all_rows(self.scope), [])
        ev = svc.sink.events(self.scope, p.turn.trace_id)
        self.assertEqual([(e["decision"], e["reason_codes"]) for e in ev if e["stage"] == "validate"],
                         [("IGNORE", ["UNGROUNDED"])])
        self.assertEqual([(e["decision"], e["reason_codes"]) for e in ev if e["stage"] == "policy"],
                         [("REJECT", ["SECRET_API_KEY"])])

    async def test_valid_output_is_stored(self):
        svc = self.service([json.dumps({"candidates": [MEETING_CANDIDATE],
                                        "ignored": [{"evidence": "I'm eating a turkey sandwich right now",
                                                     "reason": "TRANSIENT_STATE"}]})])
        p = user_turn(svc, "I prefer meetings after 10 AM. I'm eating a turkey sandwich right now.")
        await svc.await_idle()
        (row,) = self.store.all_rows(self.scope)
        self.assertEqual((row["canonical_text"], row["extractor_version"]), ("User prefers meetings after 10 AM.", "llm-0.1"))
        clauses = [(e["decision"], e["reason_codes"]) for e in svc.sink.events(self.scope, p.turn.trace_id)
                   if e["stage"] == "extract.clause"]
        self.assertEqual(clauses, [("CANDIDATE", []), ("NO_CANDIDATE", ["TRANSIENT_STATE"])])


class TestMalformed(LLMCase):
    async def test_malformed_json_gives_zero_candidates_and_an_event(self):
        svc = self.service(["Sure! Here are the facts: user likes meetings"])
        p = user_turn(svc, "I prefer meetings after 10 AM.")
        await svc.await_idle()
        self.assertEqual(self.store.all_rows(self.scope), [])
        (ex,) = [e for e in svc.sink.events(self.scope, p.turn.trace_id) if e["stage"] == "extract"]
        self.assertEqual((ex["decision"], ex["reason_codes"], ex["detail"]["n_candidates"]),
                         ("ERROR", ["MALFORMED_JSON"], 0))

    def test_strict_schema(self):
        extra = dict(MEETING_CANDIDATE, confidence=0.99)  # additionalProperties: false
        missing = {k: v for k, v in MEETING_CANDIDATE.items() if k != "certainty"}
        wrong_type = dict(MEETING_CANDIDATE, is_correction="yes")
        fenced = "```json\n" + json.dumps({"candidates": [MEETING_CANDIDATE] * 7}) + "\n```"
        self.assertEqual(parse_llm_output(json.dumps({"candidates": [extra, missing, wrong_type]}))[0], [])
        cands, _, err = parse_llm_output(fenced)
        self.assertIsNone(err)
        self.assertEqual(len(cands), 5)  # maxItems 5
        self.assertEqual(parse_llm_output("[1,2]")[2], "MALFORMED_JSON")
        _, ignored, _ = parse_llm_output(json.dumps({"candidates": [], "ignored": [
            {"evidence": "x", "reason": "TRANSIENT_STATE"}, {"evidence": "y", "reason": "MADE_UP"}]}))
        self.assertEqual([i.reason for i in ignored], ["TRANSIENT_STATE"])


if __name__ == "__main__":
    unittest.main()
