import pathlib

# Define the root directory of the project.
# Ensures the script can correctly locate the target folder regardless of the execution location.
base_path = pathlib.Path(__file__).resolve().parent.parent
