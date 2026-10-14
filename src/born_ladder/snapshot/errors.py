"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations

class Rebuild1Error(RuntimeError):
    """Base error carrying the frozen operational status and nonzero exit."""

    status = "REBUILD1_ERROR"

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"{self.status}: {self.message}"



class SpecMismatch(Rebuild1Error):
    status = "SPEC_MISMATCH"



class GridInventoryMismatch(Rebuild1Error):
    status = "GRID_INVENTORY_MISMATCH"



class IncompleteCampaign(Rebuild1Error):
    status = "INCOMPLETE"



class ControlFailureEvidence(Rebuild1Error):
    """Complete evidence whose independently recomputed control does not pass."""

    status = "CONTROL_FAILURE"



class BlockedInfrastructure(Rebuild1Error):
    status = "BLOCKED_INFRASTRUCTURE"
