{
  description = "Insta360 Server";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
  let
    supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
    forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
  in {
    packages = forAllSystems (system:
      let
        pkgs = import nixpkgs { inherit system; };

        lib-one-proto = pkgs.python3Packages.buildPythonPackage rec {
          pname = "lib_one_proto";
          version = "0.1.4";
          format = "wheel";
          src = pkgs.fetchurl {
            url = "https://files.pythonhosted.org/packages/b9/62/db55476d05d5db9115ec6a2569b92207b5a88c7b80a37e19a9d70104e76a/lib_one_proto-0.1.4-py3-none-any.whl";
            hash = "sha256-c3cnveXBY9IL66SD7Ln9U1eSm7o1ddUeRjeZ5ljaefg=";
          };
        };

      in {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "insta360-server";
          version = "0.1.0";

          src = ./insta360-server;

          propagatedBuildInputs = with pkgs.python3Packages; [
            aiohttp
            lib-one-proto
            protobuf
          ];

          postPatch = ''
            cat > setup.py << 'SETUP_EOF'
from setuptools import setup
setup(
    name='insta360-server',
    version='0.1.0',
    py_modules=['server'],
    entry_points={
        'console_scripts': [
            'insta360-server=server:main',
        ],
    },
)
SETUP_EOF
          '';
        };
      }
    );
  };
}
