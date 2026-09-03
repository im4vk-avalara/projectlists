# Self-Correcting Codeforces Tutor
# Main source package

from .tutor import Tutor, TutorOutput, TutorSession, TutorPhase
from .config import config

__all__ = [
    "Tutor",
    "TutorOutput",
    "TutorSession", 
    "TutorPhase",
    "config"
]

__version__ = "0.1.0"
