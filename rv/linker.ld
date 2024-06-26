SECTIONS
{
    .text.startup 0 : {
        crt0.o(.text.startup)
        *(.text.startup)
    }
    .text : {
        *(.text*)
    }
    .rodata : {
        *(.rodata*)
    }
    .sdata : {
        *(.sdata*)
    }
    /DISCARD/ : {
        *(*)
    }
}
