{ lib, pkgs, python38Packages }:

with python38Packages;

buildPythonApplication rec {
    pname = "rs3fc";
    version = "1.0.5";

    nativeBuildInputs = [ pkgs.sshfs pkgs.gocryptfs ];

    src = ./.;
}
