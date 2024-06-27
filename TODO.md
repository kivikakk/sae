# TODO

## µ-architecture

* Separate ALU, try to make this thing smaller and build faster.
  * **Next**: This implies making the design pipelined! OK.

## ISA

* RV32E
  * WIP in `rv32e` branch.
* RV64I
* "C" extension
  * **NextNext**: WIP and refactoring in `rv32c` branch which I need to take a long hard look at.
* "M" extension
* "A" extension
* "Zicsr": CSR insns

## Extras

* BMC
* Interface with sh1107/ili9341spi
* **Now**: CXXRTL test: e.g. verify the UART behaviour.
