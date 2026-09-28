package ai_inventory_complete

import rego.v1

deny contains msg if {
	some component in input.components
	component.kind == "assistant"
	not inventoried(component.path)
	msg := sprintf("AI component %q has no entry in the AI system inventory", [component.path])
}

inventoried(path) if {
	some system in input.systems
	system.path == path
}
