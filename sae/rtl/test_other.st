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
    nop                         ;       <---'
    .assert x1=4, x2=16, x3=8

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
    nop                         ;       <---'
    .assert x1=0xC, x2=0x14, x3=0x0C

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
    .assert

test_bne:
    .init x1=1
    bne x0, x1, 8
    .word 0
    .assert

    .init
    bne x0, x0, 8
    j 8
    .word 0
    .assert

test_blt:
    .init x1=-1
    blt x1, x0, 8
    .word 0
    .assert

    .init
    blt x0, x0, 8
    j 8
    .word 0
    .assert

test_bge:
    .init
    bge x0, x0, 8
    .word 0
    .assert

    .init x1=1
    bge x1, x0, 8
    .word 0
    .assert

    .init x1=-1
    bge x1, x0, 8
    j 8
    .word 0
    .assert

test_bltu:
    .init x1=-1
    bltu x1, x0, 8
    j 8
    .word 0
    .assert

    .init
    bltu x0, x0, 8
    j 8
    .word 0
    .assert

    .init x1=1
    bltu x0, x1, 8
    .word 0
    .assert

test_bgeu:
    .init
    bgeu x0, x0, 8
    .word 0
    .assert

    .init x1=1
    bgeu x1, x0, 8
    .word 0
    .assert

    .init x1=1
    bgeu x0, x1, 8
    j 8
    .word 0
    .assert

    .init x1=-1
    bgeu x1, x0, 8
    .word 0
    .assert

test_load_store:
    .init x1=0x0, x2=0x12345678
    sw x2, 0(x1)
    lw x3, 0(x1)
    .assert x3=0x12345678

    .init
    lw x1, 4(x0)                ; load *next* instruction
    nop                         ; addi x0, x0, 0 = 0x00000013
    sw x1, 0(x0)
    lw x2, 0(x0)
    .assert x1=0x13, x2=0x13

test_load_store_h:
    .init
    li a0, 0x1234FEDC
    sw x0, 0(x0)                ; &0x00: 00 00  00 00
    sh a0, 0(x0)                ; &0x00: DC FE  00 00
    lw a1, 0(x0)
    lh a2, 0(x0)
    lhu a3, 0(x0)
    lh a4, 1(x0)
    lhu a5, 1(x0)
    .assert a0=0x1234FEDC, a1=0x0000FEDC, a2=0xFFFFFEDC, a3=0x0000FEDC, a4=0x000000FE, a5=0x000000FE

test_load_store_b:
    .init
    li x1, 0x1234FEDC
    sw x0, 0(x0)
    sb x1, 1(x0)
    lhu x2, 0(x0)
    lb x3, 1(x0)
    lbu x4, 1(x0)
    .assert x1=0x1234FEDC, x2=0x0000DC00, x3=0xFFFFFFDC, x4=0x000000DC

test_fence:
    .init
    fence iorw, r
    fence.tso                   ; rw, rw
    lw x1, 0(x0)
    lw x2, 4(x0)
    .assert x1=0x0F20000F, x2=0x8330000F

test_ecall:
    .init
    ecall
    .assert x1=0x1234CAFE

test_ebreak:
    .init
    ebreak
    .assert

    .init
    li x1, 1
    ebreak
    .assert x1=0x77774444
