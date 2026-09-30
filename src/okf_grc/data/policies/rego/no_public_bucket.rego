package no_public_bucket

import rego.v1

public_members := {"allUsers", "allAuthenticatedUsers"}

deny contains msg if {
	some name, blocks in input.resource.google_storage_bucket_iam_member
	some binding in blocks
	binding.member in public_members
	msg := sprintf("bucket IAM binding %q grants access to %s", [name, binding.member])
}

deny contains msg if {
	some name, blocks in input.resource.google_storage_bucket_iam_binding
	some binding in blocks
	some member in binding.members
	member in public_members
	msg := sprintf("bucket IAM binding %q grants access to %s", [name, member])
}
