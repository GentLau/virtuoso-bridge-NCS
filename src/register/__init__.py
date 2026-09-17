"""Registration package: the six-step manual registration flow.

Setup phase only.  The runtime imports nothing from here; it consumes
``registry.json`` through ``common.registry``.
"""

from register.flow import (
    RegistrationFlow,
    RegistrationProbeError,
    deploy_user,
    probe_user,
    register_user,
    test_connectivity,
    validate_local,
)
from register.models import (
    ConnectivityReport,
    ProbeResult,
    RegistrationRequest,
    RegistrationState,
)

__all__ = [
    "ConnectivityReport",
    "ProbeResult",
    "RegistrationFlow",
    "RegistrationProbeError",
    "RegistrationRequest",
    "RegistrationState",
    "deploy_user",
    "probe_user",
    "register_user",
    "test_connectivity",
    "validate_local",
]
