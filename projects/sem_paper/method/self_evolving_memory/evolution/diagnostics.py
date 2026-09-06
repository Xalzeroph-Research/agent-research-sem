from __future__ import annotations

"""Temporary cross-owner import seam for ROLE 10 composition.

ROLE 09 implementation has moved to responsibility-owned modules.  The only
remaining direct caller outside ROLE 09 imports ``AutomaticSliceDiscovery``
from this historical path.  Delete this module when that caller is migrated.
"""

from .slicing import AutomaticSliceDiscovery

__all__ = ["AutomaticSliceDiscovery"]
