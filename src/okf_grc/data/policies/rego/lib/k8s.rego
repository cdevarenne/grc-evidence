package lib.k8s

import rego.v1

# Workload kinds whose pods come from spec.template.
template_kinds := {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"}

pod_spec := input.spec if input.kind == "Pod"

pod_spec := input.spec.template.spec if input.kind in template_kinds

pod_spec := input.spec.jobTemplate.spec.template.spec if input.kind == "CronJob"

# Every container the workload runs, init containers included.
containers contains container if {
	some field in ["containers", "initContainers"]
	some container in object.get(pod_spec, field, [])
}
