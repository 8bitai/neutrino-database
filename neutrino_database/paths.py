from pyproject import PROJECT_ROOT
from pathlib import Path

class ProjectPath:
    ROOT = Path(PROJECT_ROOT).resolve()
    CONFIG = ROOT / 'config'

    @classmethod
    def get_path(cls, *parts):
        return (cls.ROOT / Path(*parts)).resolve()