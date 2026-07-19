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

      in {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "insta360-server";
          version = "0.1.0";
          pyproject = true;
          build-system = [ pkgs.python3Packages.setuptools ];

          src = ./insta360-server;

          propagatedBuildInputs = with pkgs.python3Packages; [
            aiohttp
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
    py_modules=['server', 'database', 'insta360_messages_pb2'],
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
          pytestFlags = [ "tests/" ];
        };
      }
    );

    nixosModules.default = { config, lib, pkgs, ... }:
      let
        cfg = config.services.insta360-nas;
      in {
        options.services.insta360-nas = {
          enable = lib.mkEnableOption "Insta360 NAS server";

          package = lib.mkOption {
            type = lib.types.package;
            default = self.packages.${pkgs.system}.default;
            description = "The insta360-server package to use.";
          };

          bind = lib.mkOption {
            type = lib.types.str;
            default = "192.168.42.1";
            description = "IP address to bind the server to.";
          };

          dir = lib.mkOption {
            type = lib.types.str;
            default = "/data/@storage/Photos";
            description = "Directory to serve files from.";
          };

          dbDir = lib.mkOption {
            type = lib.types.str;
            default = "$STATE_DIRECTORY";
            description = "Directory to store the insta360.db file.";
          };

          configFile = lib.mkOption {
            type = lib.types.str;
            default = "/var/lib/insta360-nas/config.json";
            description = "Path to the JSON configuration file containing secrets.";
          };

          http = lib.mkOption {
            type = lib.types.bool;
            default = true;
            description = "Start HTTP server.";
          };

          rtsp = lib.mkOption {
            type = lib.types.bool;
            default = true;
            description = "Start RTSP server.";
          };

          ble = lib.mkOption {
            type = lib.types.bool;
            default = false;
            description = "Start BLE server.";
          };
        };

        config = lib.mkIf cfg.enable {
          systemd.services.insta360-nas = {
            description = "Insta360 RTMP and HTTP Server";
            after = [ "network.target" ];
            wantedBy = [ "multi-user.target" ];
            serviceConfig = {
              ExecStart = ''
                ${cfg.package}/bin/insta360-server \
                  --bind "${cfg.bind}" \
                  --dir "${cfg.dir}" \
                  --db-dir "${cfg.dbDir}" \
                  --config-file "${cfg.configFile}" \
                  ${if cfg.http then "--http" else "--no-http"} \
                  ${if cfg.rtsp then "--rtsp" else "--no-rtsp"} \
                  ${if cfg.ble then "--ble" else ""}
              '';
              StateDirectory = "insta360-nas";
              Restart = "always";
              AmbientCapabilities = [ "CAP_NET_BIND_SERVICE" ];
              DynamicUser = true;
            };
          };
        };
      };
  };
}
