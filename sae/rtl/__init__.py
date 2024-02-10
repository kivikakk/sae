from amaranth import Elaboratable, Module, Signal, Array
from amaranth.hdl.mem import Memory, ReadPort, WritePort

__all__ = ["Top"]

# R:
#   31-25: funct7
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
# I:
#   31-20: imm[11:0]
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
# S:
#   31-25: imm[11:5]
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-7: imm[4:0]
#     6-0: opcode
# B:
#      31: imm[12]
#   30-25: imm[10:5]
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-8: imm[4:1]
#       7: imm[11]
#     6-0: opcode
# U:
#   31-12: imm[31:12]
#    11-7: rd
#     6-0: opcode
# J:
#      31: imm[20]
#   30-21: imm[10:1]
#      20: imm[11]
#   19-12: imm[19:12]
#    11-7: rd
#     6-0: opcode


class Top(Elaboratable):
    XLEN = 32

    sysmem_rd: ReadPort
    sysmem_wr: WritePort

    xreg: Array[Signal]
    pc: Signal

    def elaborate(self, platform):
        m = Module()

        sysmem = Memory(width=8, depth=1024)
        self.sysmem_rd = m.submodules.sysmem_rd = sysmem.read_port()
        self.sysmem_wr = m.submodules.sysmem_wr = sysmem.write_port()

        self.xreg = Array(Signal(self.XLEN) for _ in range(32))
        self.pc = Signal(self.XLEN)

        m.d.sync += self.pc.eq(self.pc + 1)

        return m
