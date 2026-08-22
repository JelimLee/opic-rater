"""opic-rater — local-first OPIc speaking practice grader."""

__version__ = "0.1.0"

# NOTE: `segment` is a submodule name, so the function is re-exported under a
# distinct name. Importing it as `segment` here would shadow the module and
# break `from . import segment`.
from .fluency import FluencyStats, analyse, analyse_file  # noqa: F401
from .segment import Answer  # noqa: F401
from .segment import segment as segment_answers  # noqa: F401

__all__ = [
    "__version__",
    "FluencyStats",
    "analyse",
    "analyse_file",
    "Answer",
    "segment_answers",
]
