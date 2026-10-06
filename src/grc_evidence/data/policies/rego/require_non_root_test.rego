package require_non_root

import rego.v1

deployment(ctx) := {"kind": "Deployment", "spec": {"template": {"spec": {"containers": [object.union({"name": "api"}, ctx)]}}}}

pod(pod_ctx, ctx) := {"kind": "Pod", "spec": {"securityContext": pod_ctx, "containers": [object.union({"name": "api"}, ctx)]}}

test_missing_context_denied if count(deny) == 1 with input as deployment({})

test_explicit_root_denied if count(deny) == 1 with input as deployment({"securityContext": {"runAsNonRoot": false}})

test_non_root_allowed if count(deny) == 0 with input as deployment({"securityContext": {"runAsNonRoot": true}})

test_pod_level_setting_inherited if count(deny) == 0 with input as pod({"runAsNonRoot": true}, {})

test_container_override_wins if count(deny) == 1 with input as pod({"runAsNonRoot": true}, {"securityContext": {"runAsNonRoot": false}})

test_statefulset_checked if {
	count(deny) == 1 with input as {"kind": "StatefulSet", "spec": {"template": {"spec": {"containers": [{"name": "db"}]}}}}
}

test_other_kinds_ignored if count(deny) == 0 with input as {"kind": "Service"}
