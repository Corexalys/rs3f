{ lib, pkgs, python3Packages, qt5 }:

with python3Packages;

buildPythonApplication rec {
  pname = "rs3fc";
  version = "1.0.7";

  src = ./.;

  buildInputs = [pkgs.sshfs pkgs.gettext];
  propagatedBuildInputs = [ pyqt5 secretstorage ];
  nativeBuildInputs = [ qt5.wrapQtAppsHook ];

  preFixup = ''
    makeWrapperArgs+=("''${qtWrapperArgs[@]}")
  '';
}
