"""Explicit storage projections for census/attachment representations.

Identities, data hashes, labels, shapes, exponents, statuses and numerical
values stay scientific. Pointer checksums describe serialized containers;
their decoded inputs are compared separately (including the exact CONTEXT).
"""

STORAGE_GROUPS=frozenset(('complete_inventory','complete_certificate_top_fields',
    'kernel','performance_attachments'))
LOCATION_FIELDS=frozenset(('path','attempt_path','line','born_line','byte_offset',
    'byte_range','char_range','file_sha256','line_sha256','payload_sha256',
    'field_sha256','stdout_sha256','native_capture_sha256',
    'native_kernel_field_sha256','original_row_copy_sha256','key_sha256'))


def storage_field(group,key,path):
    if group not in STORAGE_GROUPS:return False
    if key in LOCATION_FIELDS:return True
    # These are descriptions/declarations of the capture envelope, not K.
    # Exponent, operation, matrix_shape and the decoded matrix remain compared.
    if key=='source_semantics' and (group=='kernel' or '/kernel/' in path):return True
    if key=='availability_reason' and path.endswith('/kernel'):return True
    if key=='expected_schema' and path.endswith('/source/invocation'):return True
    return False


EMISSION_NAMES={'KEY_BORN_PROBE_JSON':'Born',
    'KEY_DISCOVERY_GRADE_JSON':'Discovery','KEY_AUDIT_JSON':'Audit'}


def emission_names(value):
    """Only the three documented tag/name aliases; preserve order/membership."""
    return [EMISSION_NAMES.get(v,v) for v in value] if isinstance(value,list) else value
