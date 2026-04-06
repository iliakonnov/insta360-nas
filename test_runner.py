import subprocess
import sys

# We can run pytest through the nix environment to ensure it runs correctly with nix check Phase
subprocess.run(["nix", "build"])
