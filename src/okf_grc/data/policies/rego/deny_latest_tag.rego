package deny_latest_tag

import data.lib.k8s
import rego.v1

deny contains msg if {
	some container in k8s.containers
	not pinned(container.image)
	msg := sprintf("%s container %q uses unpinned image %q", [input.kind, container.name, container.image])
}

pinned(image) if contains(image, "@sha256:")

pinned(image) if {
	parts := split(image, "/")
	name := parts[count(parts) - 1]
	contains(name, ":")
	not endswith(name, ":latest")
}
