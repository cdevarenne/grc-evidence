package ai_inventory_complete

import rego.v1

inventory(systems) := {"risk_tier": "limited", "components": [{"path": "app/assistant", "kind": "assistant"}, {"path": "app/widgets", "kind": "api"}], "systems": systems}

test_missing_assistant_entry_denied if count(deny) == 1 with input as inventory([])

test_listed_assistant_allowed if count(deny) == 0 with input as inventory([{"path": "app/assistant"}])

test_non_ai_component_ignored if {
	count(deny) == 0 with input as {"components": [{"path": "app/widgets", "kind": "api"}], "systems": []}
}

test_other_documents_ignored if count(deny) == 0 with input as {"kind": "Deployment"}
