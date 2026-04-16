"""Benchmark target definitions.

Each target is a BenchmarkTarget with a module path, function name,
initial args, category, and human-readable metadata. The TEST_SUITE
list is the default workload when no custom target is specified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkTarget:
    """One benchmark target function.

    When ``source_path`` is set, coverage is measured across the whole
    package — runners re-execute discovered inputs under a broad
    coverage.py session and score against a frozen baseline (if one is
    committed under ``benchmark/baselines/``). Used for realworld and
    library targets where the entry function is a thin wrapper that
    delegates to internal modules. Without ``source_path``, runners
    measure only the entry function's own lines.
    """

    name: str
    module: str
    function: str
    initial_args: dict[str, Any] = field(default_factory=dict)
    category: str = ""
    description: str = ""
    source_path: str | None = None


_BT = "examples"

TEST_SUITE: list[BenchmarkTarget] = [
    # --- String Constraints ---
    BenchmarkTarget(
        name="Email Validation",
        module=f"{_BT}.string_constraints.email_validation",
        function="email_validation",
        initial_args={"email": "user@example.com"},
        category="string_constraints",
        description="RFC format rules — solver can't generate valid email strings",
    ),
    BenchmarkTarget(
        name="URL Routing",
        module=f"{_BT}.string_constraints.url_routing",
        function="url_routing",
        initial_args={"url": "https://example.com/api/v2/users"},
        category="string_constraints",
        description="Path-based dispatch — hierarchical string structure",
    ),
    BenchmarkTarget(
        name="Semver Parsing",
        module=f"{_BT}.string_constraints.semver_parsing",
        function="semver_parsing",
        initial_args={"version": "1.2.3"},
        category="string_constraints",
        description="Structured format with embedded numerics — str.split + int chain",
    ),
    BenchmarkTarget(
        name="Log Level Routing",
        module=f"{_BT}.string_constraints.log_level_routing",
        function="log_level_routing",
        initial_args={"log_line": "[2024-01-15 10:30:45] ERROR: Connection failed"},
        category="string_constraints",
        description="Multiple format detection paths — syslog, JSON, CSV",
    ),
    # --- Library Black Boxes ---
    BenchmarkTarget(
        name="JSON Config Validation",
        module=f"{_BT}.library_black_box.json_config_validation",
        function="json_config_validation",
        initial_args={"config_str": '{"mode": "production", "version": "1.0.0"}'},
        category="library_black_box",
        description="json.loads() is opaque — validate structure after parsing",
    ),
    BenchmarkTarget(
        name="Regex Data Extraction",
        module=f"{_BT}.library_black_box.regex_data_extraction",
        function="regex_data_extraction",
        initial_args={"text": "Call 555-123-4567 for info"},
        category="library_black_box",
        description="re.match()/re.search() opaque — extract phone/date/ID",
    ),
    BenchmarkTarget(
        name="Datetime Classification",
        module=f"{_BT}.library_black_box.datetime_classification",
        function="datetime_classification",
        initial_args={"date_str": "2024-06-15 14:30:00"},
        category="library_black_box",
        description="datetime.strptime() opaque — classify into business periods",
    ),
    # --- Hash/Encoding ---
    BenchmarkTarget(
        name="Credit Card Validation",
        module=f"{_BT}.hash_encoding.credit_card_validation",
        function="credit_card_validation",
        initial_args={"number": "4111111111111111"},
        category="hash_encoding",
        description="Luhn checksum + prefix-based card type — irreversible for solver",
    ),
    BenchmarkTarget(
        name="Base64 Payload Classification",
        module=f"{_BT}.hash_encoding.base64_payload_classification",
        function="base64_payload_classification",
        initial_args={"payload": "eyJrZXkiOiAidmFsdWUifQ=="},
        category="hash_encoding",
        description="base64.b64decode() opaque — content type detection after decode",
    ),
    # --- Pure Numeric ---
    BenchmarkTarget(
        name="Triangle Classification",
        module=f"{_BT}.pure_numeric.triangle_classification",
        function="triangle_classification",
        initial_args={"a": 3, "b": 4, "c": 5},
        category="pure_numeric",
        description="Classic integer comparison — solver should reach 100%",
    ),
    BenchmarkTarget(
        name="Tax Bracket Calculator",
        module=f"{_BT}.pure_numeric.tax_bracket_calculator",
        function="tax_bracket_calculator",
        initial_args={"income": 75000, "filing_status": "single"},
        category="pure_numeric",
        description="Progressive numeric ranges — boundary value analysis",
    ),
    BenchmarkTarget(
        name="BMI Risk Classifier",
        module=f"{_BT}.pure_numeric.bmi_risk_classifier",
        function="bmi_risk_classifier",
        initial_args={"height_cm": 175, "weight_kg": 70},
        category="pure_numeric",
        description="Float arithmetic via integers — range checks",
    ),
    # --- Mixed Types ---
    BenchmarkTarget(
        name="HTTP Request Classification",
        module=f"{_BT}.mixed_type_synergy.http_request_classification",
        function="http_request_classification",
        initial_args={"method": "GET", "path": "/api/v2/users", "content_length": 0},
        category="mixed_type_synergy",
        description="String dispatch + numeric thresholds — cross-type dependencies",
    ),
    BenchmarkTarget(
        name="Discount Engine",
        module=f"{_BT}.mixed_type_synergy.discount_engine",
        function="discount_engine",
        initial_args={"price": 100, "quantity": 2, "coupon": "SAVE10"},
        category="mixed_type_synergy",
        description="String coupon matching + numeric price/quantity thresholds",
    ),
    BenchmarkTarget(
        name="Access Control Checker",
        module=f"{_BT}.mixed_type_synergy.access_control_checker",
        function="access_control_checker",
        initial_args={"role": "editor", "resource": "/api/data", "trust_level": 50},
        category="mixed_type_synergy",
        description="Role-resource matrix + numeric trust threshold",
    ),
    BenchmarkTarget(
        name="Shipping Rate Calculator",
        module=f"{_BT}.mixed_type_synergy.shipping_rate_calculator",
        function="shipping_rate_calculator",
        initial_args={"weight": 5, "zone": "domestic", "speed": "standard"},
        category="mixed_type_synergy",
        description="Numeric weight thresholds + string zone/speed dispatch",
    ),
    # --- Complex Structures ---
    BenchmarkTarget(
        name="Nested Config Validator",
        module=f"{_BT}.complex_structures.nested_config_validator",
        function="nested_config_validator",
        initial_args={
            "data": {
                "database": {"host": "localhost", "port": 5432, "name": "mydb"},
                "server": {"host": "0.0.0.0", "port": 8080, "workers": 4},
            }
        },
        category="complex_structures",
        description="Dict traversal, required keys, type checks, cross-field rules",
    ),
    BenchmarkTarget(
        name="Transaction Ledger Analysis",
        module=f"{_BT}.complex_structures.transaction_ledger_analysis",
        function="transaction_ledger_analysis",
        initial_args={
            "transactions": [
                {"amount": 100.0, "type": "credit"},
                {"amount": 50.0, "type": "debit"},
            ]
        },
        category="complex_structures",
        description="List of dicts, accumulation, anomaly detection",
    ),
    # --- Deep Path Dependencies ---
    BenchmarkTarget(
        name="State Machine Validator",
        module=f"{_BT}.deep_path_dependency.state_machine_validator",
        function="state_machine_validator",
        initial_args={"events": "create,pay,ship,deliver"},
        category="deep_path_dependency",
        description="Must traverse specific transition sequence to reach deep branches",
    ),
    BenchmarkTarget(
        name="Multi-Stage Form Validation",
        module=f"{_BT}.deep_path_dependency.multi_stage_form_validation",
        function="multi_stage_form_validation",
        initial_args={"form_data": "John Doe|john@example.com|30|123 Main Street"},
        category="deep_path_dependency",
        description="Sequential validation stages — each depends on all prior passing",
    ),
    # --- Solver-Hard Constraints ---
    BenchmarkTarget(
        name="String Similarity Classification",
        module=f"{_BT}.solver_hard.string_similarity_classification",
        function="string_similarity_classification",
        initial_args={"s1": "listen", "s2": "silent"},
        category="solver_hard",
        description="Anagram, substring, prefix, edit distance — character-level constraints",
    ),
    BenchmarkTarget(
        name="Pattern Matching Dispatcher",
        module=f"{_BT}.solver_hard.pattern_matching_dispatcher",
        function="pattern_matching_dispatcher",
        initial_args={"pattern": "*.py", "text": "main.py"},
        category="solver_hard",
        description="Glob/wildcard matching — quantifier constraints timeout solver",
    ),
]
