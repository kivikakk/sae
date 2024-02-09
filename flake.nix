{
  description = "sae RV32I softcore cpu";

  inputs = {
    rainhdx.url = git+https://hrzn.ee/kivikakk/rainhdx;
    nixpkgs.follows = "rainhdx/nixpkgs";
    flake-utils.follows = "rainhdx/flake-utils";
  };

  outputs = inputs @ {
    self,
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
      rainhdx = inputs.rainhdx.packages.${system}.default;
      inherit (pkgs) lib;
      inherit (rainhdx) python;
    in {
      formatter = pkgs.alejandra;

      packages.default = rainhdx.buildRainProject {
        name = "sae";
        src = ./.;

        nativeBuildInputs = [
          python.pkgs.pypng
        ];
      };
    });
}
