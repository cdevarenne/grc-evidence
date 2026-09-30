package require_non_root

import data.lib.k8s
import rego.v1

deny contains msg if {
	some container in k8s.containers
	not runs_as_non_root(container)
	msg := sprintf("%s container %q does not run as non-root (set runAsNonRoot: true)", [input.kind, container.name])
}

# A container-level setting overrides the pod-level one.
runs_as_non_root(container) if container.securityContext.runAsNonRoot == true

runs_as_non_root(container) if {
	object.get(container, ["securityContext", "runAsNonRoot"], null) == null
	k8s.pod_spec.securityContext.runAsNonRoot == true
}
