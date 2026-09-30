package deny_latest_tag

import rego.v1

deployment(image) := {"kind": "Deployment", "spec": {"template": {"spec": {"containers": [{"name": "api", "image": image}]}}}}

test_latest_denied if count(deny) == 1 with input as deployment("ghcr.io/example/api:latest")

test_untagged_denied if count(deny) == 1 with input as deployment("ghcr.io/example/api")

test_registry_port_is_not_a_tag if count(deny) == 1 with input as deployment("registry:5000/api")

test_version_tag_allowed if count(deny) == 0 with input as deployment("ghcr.io/example/api:1.4.2")

test_digest_allowed if count(deny) == 0 with input as deployment("ghcr.io/example/api@sha256:0123abcd")

test_other_workload_kinds_checked if {
	count(deny) == 1 with input as {"kind": "CronJob", "spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [{"name": "job", "image": "busybox:latest"}]}}}}}}
}

test_init_container_checked if {
	count(deny) == 1 with input as {"kind": "Pod", "spec": {"containers": [{"name": "a", "image": "a:1.0"}], "initContainers": [{"name": "i", "image": "i:latest"}]}}
}
