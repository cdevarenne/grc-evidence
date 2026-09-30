package lib.k8s

import rego.v1

c := {"name": "api", "image": "x"}

test_pod if count(containers) == 1 with input as {"kind": "Pod", "spec": {"containers": [c]}}

test_statefulset if count(containers) == 1 with input as {"kind": "StatefulSet", "spec": {"template": {"spec": {"containers": [c]}}}}

test_cronjob if count(containers) == 1 with input as {"kind": "CronJob", "spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [c]}}}}}}

test_init_containers_included if count(containers) == 2 with input as {"kind": "Pod", "spec": {"containers": [c], "initContainers": [{"name": "init", "image": "y"}]}}

test_service_has_no_containers if count(containers) == 0 with input as {"kind": "Service", "spec": {}}
