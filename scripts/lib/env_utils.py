import os
import sys

def get_venv_paths(repo_root: str):
    """
    Returns the absolute paths for the virtual environment directory and the python executable
    for the given repository root.
    """
    venv_path = os.path.join(repo_root, ".venv")
    if sys.platform == "win32":
        python_bin = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        python_bin = os.path.join(venv_path, "bin", "python")

    return venv_path, python_bin
