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
    addi x0, x0, 0              ; nop
    addi x0, x0, 0
    addi x0, x0, 0
    auipc x1, 0x12345
    .assert x1=0x1234500C       ; I think.

test_add:
    .init x1=3, x2=5
    add x3, x1, x2
    .assert x3=8

    .init x1=-1
    add x2, x0, x1
    .assert x2=-1

