"""Replay exact statements and rounding cells; reject edited certificates."""
from .canonical import construct, controls
from .specification import canonical_bytes


def check_certificate(emitted, preparation, certificate, *, refinement=(384,768,1536,3072,4096)):
    expected=construct(emitted,preparation,refinement=refinement)
    if canonical_bytes(expected)!=canonical_bytes(certificate):
        raise ValueError('canonical certificate fails exact replay')
    return certificate['status']=='certified'


def check_controls(certificate, legacy_basis, legacy_full, retained, legacy_projector=None):
    if controls(certificate,legacy_basis,legacy_full,legacy_projector)!=retained:
        raise ValueError('canonical control certificate differs')
    return retained['status']=='pass'
