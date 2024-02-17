{
  description = "sae RV32I softcore cpu";

  inputs = {
    hdx.url = git+https://hrzn.ee/kivikakk/hdx;
    nixpkgs.follows = "hdx/nixpkgs";
    flake-utils.follows = "hdx/flake-utils";
  };

  outputs = inputs @ {
    self,
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
      inherit (inputs.hdx.packages.${system}) rainhdx;
      inherit (rainhdx) python;
    in rec {
      formatter = pkgs.alejandra;

      packages.default = rainhdx.buildProject {
        name = "sae";
        src = ./.;

        nativeBuildInputs = [python.pkgs.funcparserlib];
      };

      devShells = packages.default.devShells;
    });
}
