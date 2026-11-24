"""Validate generated contracts, examples, and malformed-message regressions.

Run: python -m pip install -r tools/requirements-validation.txt
     python tools/validate_specs.py
"""
import contextlib
import copy
from datetime import datetime
import io
from pathlib import Path
import runpy
import sys
import tempfile
import unittest

import jsonschema
from openapi_spec_validator import validate
import yaml


ROOT = Path(__file__).resolve().parents[1]
FILES = ["specs/openapi/provider-portal-partner-api.yaml",
         "specs/openapi/customer-portal-partner-api.yaml",
         "specs/asyncapi/roomscanner-kafka.yaml"]
DOCS = {name: yaml.safe_load((ROOT / name).read_text(encoding="utf-8")) for name in FILES}
ASYNC = DOCS[FILES[2]]
MESSAGES = ASYNC["components"]["messages"]


def validator(doc, schema):
    # OpenAPI 3.0 schema features used here are compatible with Draft 4.
    return jsonschema.Draft4Validator({"components": doc["components"], "allOf": [schema]},
                                     format_checker=jsonschema.FormatChecker())


def example(message, index=0):
    return copy.deepcopy(MESSAGES[message]["examples"][index]["payload"])


def rest_examples(node, path="$", doc=None):
    if isinstance(node, dict):
        if "schema" in node and isinstance(node.get("examples"), dict):
            for name, item in node["examples"].items():
                if isinstance(item, dict) and "value" in item:
                    yield path + "/" + name, node["schema"], item["value"]
        for key, value in node.items():
            yield from rest_examples(value, path + "/" + str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from rest_examples(value, path + "/" + str(index))


class ContractValidation(unittest.TestCase):
    def assert_valid(self, message, data):
        errors = list(validator(ASYNC, MESSAGES[message]["payload"]).iter_errors(data))
        self.assertFalse(errors, "\n".join(error.message for error in errors[:3]))

    def assert_invalid(self, message, data):
        self.assertFalse(validator(ASYNC, MESSAGES[message]["payload"]).is_valid(data),
                         f"Malformed {message} accepted: {data}")

    def test_openapi_structure_and_authentication(self):
        for path in FILES[:2]:
            doc = DOCS[path]
            with self.subTest(file=path):
                validate(doc)
                bearer = doc["components"]["securitySchemes"]["partnerBearer"]
                self.assertEqual((bearer["type"], bearer["scheme"]), ("http", "bearer"))
                for item in doc["paths"].values():
                    for method, op in item.items():
                        if method not in {"get", "post", "put", "patch", "delete"}:
                            continue
                        if op["operationId"] == "issuePartnerToken":
                            self.assertEqual(op["security"], [])
                            self.assertIn("application/json", op["requestBody"]["content"])
                        else:
                            self.assertEqual(op["security"][0]["partnerBearer"], [])
                            self.assertTrue(op["x-required-scopes"])

    def test_every_embedded_example(self):
        count = 0
        for path, doc in DOCS.items():
            if "openapi" in doc:
                examples = rest_examples(doc)
            else:
                examples = ((name + "/" + ex["name"], msg["payload"], ex["payload"])
                            for name, msg in doc["components"]["messages"].items()
                            for ex in msg.get("examples", []))
            for name, schema, data in examples:
                count += 1
                with self.subTest(file=path, example=name):
                    errors = list(validator(doc, schema).iter_errors(data))
                    self.assertFalse(errors, "\n".join(error.message for error in errors[:3]))
        print(f"Validated {count} embedded examples.")

    def test_generator_matches_checked_in_specs(self):
        with tempfile.TemporaryDirectory(prefix="roomscanner-contract-") as output:
            previous = sys.argv[:]
            try:
                sys.argv = ["generate_specs.py", output]
                with contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(ROOT / "tools/generate_specs.py"), run_name="__main__")
            finally:
                sys.argv = previous
            for path in FILES:
                with self.subTest(file=path):
                    generated = yaml.safe_load((Path(output) / path).read_text(encoding="utf-8"))
                    self.assertEqual(generated, DOCS[path], "Regenerate specs after changing the generator.")

    def test_request_type_cannot_use_another_operations_payload(self):
        data = example("BookingRequest")
        data["payload"] = {"bookingId": data["payload"]["quoteId"],
                           "customerId": data["payload"]["customer"]["customerId"]}
        self.assert_invalid("BookingRequest", data)

    def test_requests_require_transport_metadata_and_write_identity(self):
        for field in ["replyTo", "attempt", "deadline", "traceId", "idempotencyKey"]:
            with self.subTest(missing=field):
                data = example("BookingRequest")
                del data[field]
                self.assert_invalid("BookingRequest", data)
        for field, value in [("replyTo", "rs.search.response.v1"), ("attempt", 0),
                             ("source", "PP"), ("status", "OK")]:
            with self.subTest(field=field):
                data = example("BookingRequest")
                data[field] = value
                self.assert_invalid("BookingRequest", data)

    def test_response_status_and_metadata_match_payload(self):
        data = example("BookingResponse", 1)  # Known business error.
        data["status"] = "OK"
        self.assert_invalid("BookingResponse", data)
        data = example("BookingResponse")
        data["status"] = "ERROR"
        self.assert_invalid("BookingResponse", data)
        for field in ["status", "causationId", "traceId"]:
            data = example("BookingResponse")
            del data[field]
            self.assert_invalid("BookingResponse", data)
        for field, value in [("replyTo", "rs.booking.request.v1"), ("attempt", 1),
                             ("deadline", "2026-12-01T03:00:45Z"), ("source", "CP")]:
            data = example("BookingResponse")
            data[field] = value
            self.assert_invalid("BookingResponse", data)
        data = example("BookingResponse", 1)
        del data["payload"]["error"]["httpStatus"]
        self.assert_invalid("BookingResponse", data)

    def test_payment_mode_requires_matching_gateway_state_and_references(self):
        for field in ["paymentReference", "chargeReference", "paidAt"]:
            data = example("BookingRequest")
            del data["payload"]["payment"][field]
            self.assert_invalid("BookingRequest", data)
        for field, value in [("gateway", "NONE"), ("state", "SIMULATED_ISSUED"),
                             ("paymentReference", ""), ("chargeReference", "")]:
            data = example("BookingRequest")
            data["payload"]["payment"][field] = value
            self.assert_invalid("BookingRequest", data)
        for mode, gateway, state, references in [
            ("SIMULATED", "NONE", "SIMULATED_ISSUED", {}),
            ("DIRECT", "PAYPAL_SANDBOX", "CAPTURED",
             {"paymentReference": "PAYPAL-CAPTURE-TEST", "paidAt": "2026-12-01T03:00:00Z"}),
        ]:
            data = example("BookingRequest")
            previous = data["payload"]["payment"]
            data["payload"]["payment"] = {"mode": mode, "gateway": gateway, "state": state,
                                           "orderId": previous["orderId"], "amount": previous["amount"], **references}
            self.assert_valid("BookingRequest", data)

    def test_favorite_event_fields_and_discriminators(self):
        for field in ["customerId", "favoriteId", "favoritedAt"]:
            data = example("EventFavoriteChanged")
            del data["payload"][field]
            self.assert_invalid("EventFavoriteChanged", data)
        data = example("EventFavoriteChanged")
        data["type"] = "FAVORITE_REMOVED"
        self.assert_invalid("EventFavoriteChanged", data)
        data = example("EventFavoriteChanged")
        data["status"] = "OK"
        self.assert_invalid("EventFavoriteChanged", data)
        deleted = next(ex["payload"] for ex in MESSAGES["EventFavoriteChanged"]["examples"]
                       if ex["payload"]["type"] == "EVENT_DELETED")
        self.assert_valid("EventFavoriteChanged", copy.deepcopy(deleted))
        data = copy.deepcopy(deleted)
        data["payload"]["customerId"] = "7d1e2f30-0000-4000-8000-000000000902"
        self.assert_invalid("EventFavoriteChanged", data)
        data = copy.deepcopy(deleted)
        data["payload"]["changeType"] = "EVENT_DATES_CHANGED"
        self.assert_invalid("EventFavoriteChanged", data)

    def test_reversal_outcome_requires_reference_or_failure_cause(self):
        schema = ASYNC["components"]["schemas"]["BookingPaymentStatus"]
        sample = copy.deepcopy(example("BookingResponse")["payload"]["payment"])
        sample["transferReversalStatus"] = "SUCCEEDED"
        check = validator(ASYNC, schema)
        self.assertFalse(check.is_valid(sample))
        sample["transferReversalReference"] = "trr_contract_test"
        self.assertTrue(check.is_valid(sample))
        sample["transferReversalStatus"] = "FAILED"
        self.assertFalse(check.is_valid(sample))
        sample["transferReversalFailureCause"] = "insufficient_balance"
        self.assertTrue(check.is_valid(sample))

    def test_deadline_budgets_and_response_correlation_examples(self):
        requests = {}
        for message in MESSAGES.values():
            for ex in message.get("examples", []):
                data = ex["payload"]
                if "replyTo" not in data:
                    continue
                start = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(data["deadline"].replace("Z", "+00:00"))
                expected = (45 if data["type"] in {"CREATE_QUOTE", "CREATE_BOOKING", "CANCEL_BOOKING"}
                            else 20 if data["type"] == "GET_RATING_STATISTICS" else 12)
                self.assertEqual((end - start).total_seconds(), expected)
                requests[data["messageId"]] = data
        for message in MESSAGES.values():
            for ex in message.get("examples", []):
                response = ex["payload"]
                if "status" not in response:
                    continue
                request = requests[response["causationId"]]
                self.assertEqual(response["type"], request["type"] + "_RESULT")
                self.assertEqual(response["correlationId"], request["correlationId"])
                self.assertEqual(response["traceId"], request["traceId"])

    def test_order_reconciliation_binding_is_available(self):
        doc = DOCS[FILES[0]]
        operation = doc["paths"]["/customers/{customerId}/bookings"]["get"]
        self.assertTrue(any(p.get("name") == "orderId" for p in operation["parameters"]))
        payload = ASYNC["components"]["schemas"]["ListBookingsRequest"]
        self.assertIn("orderId", payload["properties"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
