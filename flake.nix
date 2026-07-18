{
  description = "remote-slskd — Soulseek album downloader that queues high-quality matches via a local slskd API";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs:
        let
          pythonEnv = pkgs.python312.withPackages (ps: with ps; [
            requests
            python-dotenv
          ]);

          remote-slskd = pkgs.stdenv.mkDerivation {
            pname = "remote-slskd";
            version = "0.1.0";
            src = ./.;

            nativeBuildInputs = [ pkgs.makeWrapper ];

            installPhase = ''
              runHook preInstall

              mkdir -p $out/libexec $out/bin
              cp auto_download.py $out/libexec/auto_download.py

              makeWrapper ${pythonEnv}/bin/python3 $out/bin/remote-slskd \
                --add-flags "$out/libexec/auto_download.py"

              runHook postInstall
            '';
          };
        in
        {
          default = remote-slskd;
          remote-slskd = remote-slskd;
        });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/remote-slskd";
        };
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python312.withPackages (ps: with ps; [
              requests
              python-dotenv
            ]))
            pkgs.slskd
            pkgs.curl
          ];

          # Auto-start slskd on port 5030 with an API key matching auto_download.py.
          # It is stopped again when you leave the shell.
          shellHook = ''
            export SLSKD_APP_DIR="$PWD/.slskd"
            mkdir -p "$SLSKD_APP_DIR"

            # Load Soulseek network credentials from .env if present.
            if [ -f .env ]; then
              set -a; . ./.env; set +a
            fi

            SLSK_ARGS=""
            if [ -n "$SOULSEEK_USERNAME" ]; then
              SLSK_ARGS="--slsk-username $SOULSEEK_USERNAME --slsk-password $SOULSEEK_PASSWORD"
            fi

            # Directory to share; override with SHARE_PATH in .env (e.g. on a Pi).
            SHARE_PATH="''${SHARE_PATH:-/mnt/1TB-HDD/Synced/Music}"

            if curl -sf -o /dev/null http://localhost:5030 2>/dev/null; then
              echo "remote-slskd: slskd already reachable on http://localhost:5030"
            else
              # --no-auth removes the web UI login (local dev); the API key still
              # works for the script, and Soulseek creds come from .env.
              slskd --app-dir "$SLSKD_APP_DIR" \
                    --http-port 5030 \
                    --no-auth \
                    --api-key copilot-secret-key-123456789 \
                    --shared "$SHARE_PATH" \
                    $SLSK_ARGS \
                    > "$SLSKD_APP_DIR/slskd.log" 2>&1 &
              SLSKD_PID=$!
              trap 'kill $SLSKD_PID 2>/dev/null || true' EXIT
              echo "remote-slskd: started slskd (pid $SLSKD_PID) on http://localhost:5030 (web login disabled)"
              echo "remote-slskd: logs -> $SLSKD_APP_DIR/slskd.log"
              if [ -z "$SOULSEEK_USERNAME" ]; then
                echo "remote-slskd: set SOULSEEK_USERNAME / SOULSEEK_PASSWORD in .env to search the network"
              else
                echo "remote-slskd: logging into Soulseek as $SOULSEEK_USERNAME"
              fi
            fi

            echo "remote-slskd: run  python3 auto_download.py \"Artist - Album\""
          '';
        };
      });
    };
}
