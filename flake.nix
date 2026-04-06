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
            url = "https://files.pythonhosted.org/packages/2e/c7/5cffb4cfe7715c9c2ce86eab23ea0ebddd3cd0c99eefa06ee3ee9f4a292a/lib_one_proto-0.1.4-py3-none-any.whl";
            hash = "sha256-58oMJ9SZrf/9W1REWy2OHn9+Ipby5PyeY8464mhV5K0=";
          };
          propagatedBuildInputs = [ pkgs.python3Packages.protobuf ];
          pythonImportsCheck = [ "lib_one_proto" ];
          pythonCatchConflictsPhase = "true";
          pythonRemoveBinBytecodePhase = "true";
          dontCheckRuntimeDeps = true;
        };

      in {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "insta360-server";
          version = "0.1.0";
          pyproject = true;
          build-system = [ pkgs.python3Packages.setuptools ];

          src = ./insta360-server;

          propagatedBuildInputs = with pkgs.python3Packages; [
            aiohttp
            lib-one-proto
            protobuf
            bless
            aiohttp-jinja2
            jinja2
          ];

          nativeCheckInputs = with pkgs.python3Packages; [
            pytestCheckHook
            pytest-asyncio
          ];

          postPatch = ''
            cat > setup.py << 'SETUP_EOF'
from setuptools import setup
setup(
    name='insta360-server',
    version='0.1.0',
    py_modules=['server', 'database'],
    entry_points={
        'console_scripts': [
            'insta360-server=server:main_entry',
        ],
    },
    extras_require={
        'ble': ['bless'],
    },
)
SETUP_EOF
          '';

          postInstall = ''
            cp -r templates $out/${pkgs.python3.sitePackages}/templates
          '';

          # Since the source is just the root of insta360-server,
          # pytest will discover the tests folder inside it
          pytestFlagsArray = [ "tests/" ];
        };
      }
    );
  };
}
