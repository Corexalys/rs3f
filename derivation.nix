{ lib, pkgs, python38Packages }:

with python38Packages;

buildPythonApplication rec {
    pname = "rs3fc";
    version = "1.1.0";

    nativeBuildInputs = [ pkgs.sshfs pkgs.gocryptfs ];

    src = ./.;
}
