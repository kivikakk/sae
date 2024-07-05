test_start:
    .init rvc
    add sp,sp,-4
    sw ra,0(sp)
    jal ra,0xc
    lw ra,0(sp)
    add sp,sp,4
    ret
    li a0,69
    ret
    .assert a0=69
