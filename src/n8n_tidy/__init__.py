"""n8n-tidy: normalize, semantically diff and check n8n workflow exports.

The Python API below is internal in 0.x and may change; the command line is the stable surface.
"""

from .diff import Change, semantic_diff
from .io import NotAWorkflowError
from .normalize import dumps, normalize

__version__ = "0.1.0"
__all__ = ["normalize", "dumps", "semantic_diff", "Change", "NotAWorkflowError", "__version__"]
