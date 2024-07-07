from amaranth import C

from .isa_rv32 import RV32I

__all__ = [
    "disasm",
]


def decode(struct, value):
    view = struct.shape(C(value, 32))
    result = {}

    for field in struct.shape.members:
        slice = view[field]
        assert type(slice).__name__ == "Slice"
        v = (slice.value.value & (2**slice.stop - 1)) >> slice.start
        result[field] = v
    return result


def c2(count, value):
    sb = 1 << (count - 1)
    if value & sb:
        return -((sb << 1) - value)
    return value


def c2foff(count, value):
    v = c2(count, value)
    if v == 0:
        return "0"
    elif v < 0:
        return f"-0x{-v:x}"
    else:
        return f"0x{v:x}"


def arg_fence(v):
    assert not (v & ~0b1111)
    a = []
    if v & 0b1000:
        a.append("i")
    if v & 0b0100:
        a.append("o")
    if v & 0b0010:
        a.append("r")
    if v & 0b0001:
        a.append("w")
    return "".join(a)


def disasm(op):
    v_i = decode(RV32I.I, op)
    v_b = decode(RV32I.B, op)
    v_u = decode(RV32I.U, op)
    v_r = decode(RV32I.R, op)
    v_j = decode(RV32I.J, op)
    v_s = decode(RV32I.S, op)

    try:
        opcode = RV32I.Opcode(v_i["opcode"])
    except ValueError:
        opcode = v_i["opcode"]

    match opcode:
        case RV32I.Opcode.LOAD:
            return f"{RV32I.I.LFunct(v_i['funct3']).name.lower()} x{v_i['rd']}, {c2foff(12, v_i['imm'])}(x{v_i['rs1']})"
        case RV32I.Opcode.MISC_MEM:
            match v_i["funct3"]:
                case RV32I.I.MMFunct.FENCE:
                    succ = v_i["imm"] & 0xF
                    pred = (v_i["imm"] >> 4) & 0xF
                    fm = v_i["imm"] >> 8
                    if fm == 0b1000 and succ == pred == 0b0011:
                        return "fence.tso"
                    return f"fence {arg_fence(pred)}, {arg_fence(succ)}"
        case RV32I.Opcode.OP_IMM:
            funct = RV32I.I.IFunct(v_i["funct3"])
            if funct == RV32I.I.IFunct.ADDI and v_i["imm"] == 0:
                if v_i["rd"] == v_i["rs1"] == 0:
                    return "nop"
                return f"mv x{v_i['rd']}, x{v_i['rs1']}"
            if funct == RV32I.I.IFunct.ADDI and v_i["rs1"] == 0:
                return f"li x{v_i['rd']}, 0x{v_i['imm']:x}"
            if funct == RV32I.I.IFunct.SLTIU and v_i["imm"] == 1:
                return f"seqz x{v_i['rd']}, x{v_i['rs1']}"
            if funct == RV32I.I.IFunct.XORI and v_i["imm"] == 0xFFF:
                return f"not x{v_i['rd']}, x{v_i['rs1']}"
            match funct:
                case RV32I.I.IFunct.ADDI | RV32I.I.IFunct.SLTI:
                    return f"{funct.name.lower()} x{v_i['rd']}, x{v_i['rs1']}, {c2foff(12, v_i['imm'])}"
                case RV32I.I.IFunct.SLTIU | RV32I.I.IFunct.ANDI | RV32I.I.IFunct.ORI | RV32I.I.IFunct.XORI | RV32I.I.IFunct.SLLI:
                    return f"{funct.name.lower()} x{v_i['rd']}, x{v_i['rs1']}, 0x{v_i['imm']:x}"
                case RV32I.I.IFunct.SRI:
                    opc = "srai" if (v_i["imm"] >> 10) & 1 else "srli"
                    return f"{opc} x{v_i['rd']}, x{v_i['rs1']}, 0x{v_i['imm'] & 0b111111:x}"
        case RV32I.Opcode.OP:
            funct = RV32I.R.Funct(v_r["funct3"])
            if funct == RV32I.R.Funct.SLTU and v_r["rs1"] == 0:
                return f"snez x{v_r['rd']}, x{v_r['rs2']}"
            match funct:
                case RV32I.R.Funct.ADDSUB:
                    opc = "sub" if (v_r["funct7"] >> 5) & 1 else "add"
                    return f"{opc} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
                case RV32I.R.Funct.SLT | RV32I.R.Funct.SLTU | RV32I.R.Funct.AND | RV32I.R.Funct.OR | RV32I.R.Funct.XOR | RV32I.R.Funct.SLL:
                    return f"{funct.name.lower()} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
                case RV32I.R.Funct.SR:
                    opc = "sra" if (v_r["funct7"] >> 5) & 1 else "srl"
                    return f"{opc} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
        case RV32I.Opcode.LUI | RV32I.Opcode.AUIPC:
            return f"{opcode.name.lower()} x{v_u['rd']}, 0x{v_u['imm']:x}"
        case RV32I.Opcode.STORE:
            imm = v_s["imm4_0"] | v_s["imm11_5"] << 5
            return f"{RV32I.S.Funct(v_s['funct3']).name.lower()} x{v_s['rs2']}, {c2foff(12, imm)}(x{v_s['rs1']})"
        case RV32I.Opcode.BRANCH:
            imm = (
                v_b["imm4_1"] << 1
                | v_b["imm10_5"] << 5
                | v_b["imm11"] << 11
                | v_b["imm12"] << 12
            )
            return f"{RV32I.B.Funct(v_b['funct3']).name.lower()} x{v_b['rs1']}, x{v_b['rs2']}, {c2foff(13, imm)}"
        case RV32I.Opcode.JALR:
            return f"jalr x{v_i['rd']}, x{v_i['rs1']}, {c2foff(12, v_i['imm'])}"
        case RV32I.Opcode.JAL:
            imm = (
                v_j["imm10_1"] << 1
                | v_j["imm11"] << 11
                | v_j["imm19_12"] << 12
                | v_j["imm20"] << 20
            )
            if v_j["rd"] == 0:
                return f"j {c2foff(21, imm)}"
            return f"jal x{v_j['rd']}, {c2foff(21, imm)}"
        case RV32I.Opcode.SYSTEM:
            if v_i["funct3"] == 0:
                funct = RV32I.I.SFunct(v_i["imm"] << 3)
                return funct.name.lower()
        case 0x00:
            if op & 0xFFFF == 0:
                return "invalid"
        case 0x7F:
            if op == 0xFFFFFFFF:
                return "invalid"
    raise RuntimeError(f"unknown insn: {op:0>8x}")
