    .text
    .section .text.startup
    .global _start
_start:
    add sp,sp,-4
    sw ra,0(sp)
    call main
    lw ra,0(sp)
    add sp,sp,4
    ret
