test_addi:
    .init
    addi x1, x0, 3
    addi x2, x1, 5
    .assert x1=3, x2=8

    .init
    addi x1, x0, 1
    addi x2, x1, -2
    .assert x1=1, x2=-1

    .init
    addi x1, x0, 1
    addi x2, x1, -2
    addi x3, x2, -3
    .assert x1=1, x2=-1, x3=-4

    .init
    addi x1, x0, 3
    mv x2, x1
    .assert x1=3, x2=3

    .init
    li x1, 0x123
    li x2, 0x12345678
    .assert x1=0x123, x2=0x12345678

test_slti:
    .init
    slti x1, x0, 0
    .assert x1=0

    .init
    slti x1, x0, 1
    .assert x1=1

    .init
    slti x1, x0, -1
    .assert x1=0

test_sltiu:
    .init x1=1
    sltiu x2, x1, 1
    .assert x2=0

    .init x1=1
    sltiu x2, x1, 2
    .assert x2=1

    .init x1=1
    sltiu x2, x1, -1
    .assert x2=1

    .init
    seqz x1, x0
    .assert x1=1

    .init x1=1
    seqz x2, x1
    .assert x2=0

    .init x1=-1
    seqz x2, x1
    .assert x2=0

test_andi:
    .init x1=1
    andi x2, x1, 3
    .assert x2=1

    .init x1=-1
    andi x2, x1, 3
    .assert x2=3

    .init x1=3
    andi x2, x1, -1
    .assert x2=3

test_ori:
    .init x1=1
    ori x2, x1, 2
    .assert x2=3

    .init x1=1
    ori x2, x1, -2
    .assert x2=-1

    .init x1=-2
    ori x2, x1, 1
    .assert x2=-1

test_xori:
    .init x1=0xAAAAAAAA
    xori x2, x1, -1
    .assert x2=0x55555555

    .init
    xori x1, x0, -1
    .assert x1=-1

    .init x1=0x555
    xori x2, x1, 0x555
    .assert x2=0

    .init x1=0xAAA
    xori x2, x1, 0xAAA          ; sx to 0xFFFFFAAA
    .assert x2=0xFFFFF000

    .init
    not x1, x0
    .assert x1=0xFFFFFFFF

    .init x1=0xFFFFFFFF
    not x2, x1
    .assert x2=0

test_slli:
    .init x1=0x55555555
    slli x2, x1, 1
    .assert x2=0xAAAAAAAA

    .init x1=0x55555555
    slli x2, x1, 2
    .assert x2=0x55555554

    .init x1=0x55555555
    slli x2, x1, 3
    .assert x2=0xAAAAAAA8

    .init x1=0x55555555
    slli x2, x1, 4
    .assert x2=0x55555550

test_srli:
    .init x1=0x55555555
    srli x2, x1, 1
    .assert x2=0x2AAAAAAA

    .init x1=0x55555555
    srli x2, x1, 2
    .assert x2=0x15555555

test_srai:
    .init x1=0x55555555
    srai x2, x1, 1
    .assert x2=0x2AAAAAAA

    .init x1=0xAAAAAAAA
    srai x2, x1, 1
    .assert x2=0xD5555555

    .init x1=0xAAAAAAAA
    srai x2, x1, 2
    .assert x2=0xEAAAAAAA

    .init x1=0xAAAAAAAA
    srai x2, x1, 3
    .assert x2=0xF5555555

test_lui:
    .init
    lui x1, 0x12345
    .assert x1=0x12345000

    .init
    lui x1, 0xFFFFF
    .assert x1=0xFFFFF000

test_auipc:
    .init
    nop
    nop
    nop
    auipc x1, 0x12345
    .assert x1=0x1234500C       ; I think.

test_add:
    .init x1=3, x2=5
    add x3, x1, x2
    .assert x3=8

    .init x1=-1
    add x2, x0, x1
    .assert x2=-1

    .init x1=0xffffffff
    add x1, x1, x1
    .assert x1=0xfffffffe

test_slt:
    .init
    slt x1, x0, x0
    .assert x1=0

    .init x1=1
    slt x2, x0, x1
    .assert x2=1

    .init x1=-1
    slt x2, x0, x1
    .assert x2=0

test_sltu:
    .init x1=1
    sltu x2, x1, x1
    .assert x2=0

    .init x1=1, x2=2
    sltu x3, x1, x2
    .assert x3=1

    .init x1=1, x2=-1
    sltu x3, x1, x2
    .assert x3=1

    .init
    snez x1, x0
    .assert x1=0

    .init x1=1
    snez x2, x1
    .assert x2=1

    .init x1=-1
    snez x2, x1
    .assert x2=1

test_and:
    .init x1=1, x2=3
    and x3, x1, x2
    .assert x3=1

    .init x1=-1, x2=3
    and x3, x1, x2
    .assert x3=3

    .init x1=3, x2=-1
    and x3, x1, x2
    .assert x3=3

test_or:
    .init x1=1, x2=2
    or x3, x1, x2
    .assert x3=3

    .init x1=1, x2=-2
    or x3, x1, x2
    .assert x3=-1

    .init x1=-2, x2=1
    or x3, x1, x2
    .assert x3=-1

test_xor:
    .init x1=0xAAAAAAAA, x2=-1
    xor x3, x1, x2
    .assert x3=0x55555555

    .init x1=-1
    xor x2, x0, x1
    .assert x2=-1

    .init x1=0x555
    xor x2, x1, x1
    .assert x2=0

    .init x1=0xAAA, x2=0xFFFFFAAA
    xor x3, x1, x2
    .assert x3=0xFFFFF000

test_sll:
    .init x1=0x55555555, x2=1
    sll x3, x1, x2
    .assert x3=0xAAAAAAAA

    .init x1=0x55555555, x2=2
    sll x3, x1, x2
    .assert x3=0x55555554

    .init x1=0x55555555, x2=3
    sll x3, x1, x2
    .assert x3=0xAAAAAAA8

    .init x1=0x55555555, x2=4
    sll x3, x1, x2
    .assert x3=0x55555550

    ;; ensure we only use the lower 5 bits of rs2
    .init x1=0x55555555, x2=0xE1
    sll x3, x1, x2
    .assert x3=0xAAAAAAAA

test_srl:
    .init x1=0x55555555, x2=1
    srl x3, x1, x2
    .assert x3=0x2AAAAAAA

    .init x1=0x55555555, x2=2
    srl x3, x1, x2
    .assert x3=0x15555555

    .init x1=0x55555555, x2=0xE2
    srl x3, x1, x2
    .assert x3=0x15555555

test_sra:
    .init x1=0x55555555, x2=1
    sra x3, x1, x2
    .assert x3=0x2AAAAAAA

    .init x1=0xAAAAAAAA, x2=1
    sra x3, x1, x2
    .assert x3=0xD5555555

    .init x1=0xAAAAAAAA, x2=2
    sra x3, x1, x2
    .assert x3=0xEAAAAAAA

    .init x1=0xAAAAAAAA, x2=3
    sra x3, x1, x2
    .assert x3=0xF5555555

    .init x1=0xAAAAAAAA, x2=0xE3
    sra x3, x1, x2
    .assert x3=0xF5555555

test_sub:
    .init x1=3, x2=5
    sub x3, x1, x2
    sub x4, x2, x1
    sub x5, x1, x0
    sub x6, x0, x1
    .assert x3=-2, x4=2

test_jal:
    .init
    nop
    nop
    jal x1, 8                   ; &0x08
    xor x1, x1, x1              ; &0x0c -- skipped, address stored
    not x1, x1                  ; &0x10 -- jump target
    .assert x1=0xfffffff3

    .init
    jal x1, 12                  ;  .
    jal x3, 12                  ;  |  <-. --.
    .word 0                     ;  |    |   |
    jal x2, -8                  ; <  ---'   |
    li x4, 4                    ;       <---'
    .assert x1=4, x2=16, x3=8, x4=4

    .init
    j 4
    .assert

test_jalr:
    .init
    j 12                        ;  .
    nop                         ;  |
    jalr x3, x2, 4              ;  |  <-. --.
    auipc x1, 0                 ; <     |   |
    jalr x2, x1, -3             ; ------'   |
    .word 0                     ;           |
    li x4, 0xAAAA               ;       <---'
    .assert x1=0xC, x2=0x14, x3=0x0C, x4=0xAAAA

test_beq:
    .init x1=1
    beq x0, x1, 8
    j 8
    .word 0
    li x2, 0x5555
    .assert x2=0x5555

    .init
    beq x0, x0, 8
    .word 0
    li x1, 0xA5A5
    .assert x1=0xA5A5

test_bne:
    .init x1=1
    bne x0, x1, 8
    .word 0
    li x2, 0xABAB
    .assert x2=0xABAB

    .init
    bne x0, x0, 8
    j 8
    .word 0
    li x1, 0xABCD
    .assert x1=0xABCD

test_blt:
    .init x1=-1
    blt x1, x0, 8
    .word 0
    li x2, 0x099999
    .assert x2=0x099999

    .init
    blt x0, x0, 8
    j 8
    .word 0
    li x1, 0x777
    .assert x1=0x777

test_bge:
    .init
    bge x0, x0, 8
    .word 0
    li x1, 0x6969
    .assert x1=0x6969

    .init x1=1
    bge x1, x0, 8
    .word 0
    li x2, 0xBEEF
    .assert x2=0xBEEF

    .init x1=-1
    bge x1, x0, 8
    j 8
    .word 0
    li x2, 0xafafafaf
    .assert x2=0xafafafaf

test_bltu:
    .init x1=-1
    bltu x1, x0, 8
    j 8
    .word 0
    li x2, 0x099999
    .assert x2=0x099999

    .init
    bltu x0, x0, 8
    j 8
    .word 0
    li x1, 0x777
    .assert x1=0x777

    .init x1=1
    bltu x0, x1, 8
    .word 0
    li x2, 0x099999
    .assert x2=0x099999

test_bgeu:
    .init
    bgeu x0, x0, 8
    .word 0
    li x1, 0x6969
    .assert x1=0x6969

    .init x1=1
    bgeu x1, x0, 8
    .word 0
    li x2, 0xBEEF
    .assert x2=0xBEEF

    .init x1=1
    bgeu x0, x1, 8
    j 8
    .word 0
    li x2, 0xCAFE
    .assert x2=0xCAFE

    .init x1=-1
    bgeu x1, x0, 8
    .word 0
    li x2, 0xafafafaf
    .assert x2=0xafafafaf

test_load_store:
    .init x1=0x0, x2=0x12345678
    sw x1, x2, 0
    lw x3, x1, 0
    .assert x3=0x12345678

    .init
    lw x1, x0, 4                ; load *next* instruction
    nop                         ; addi x0, x0, 0 = 0x00000013
    sw x0, x1, 0
    lw x2, x0, 0
    .assert x1=0x13, x2=0x13
