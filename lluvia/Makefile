ASFLAGS = -march=rv32i -mabi=ilp32
CFLAGS  = -march=rv32i -mabi=ilp32 -O2
LDFLAGS = -T linker.ld

all: ../sae/rtl/test_shrimple.bin ../sae/rtl/test_shrimprw.bin

../sae/rtl/test_%.bin: %.bin
	cp $< $@

%.bin: %.exe
	$(OBJCOPY) -O binary $< $@

%.exe: %.o crt0.o
	$(LD) $(LDFLAGS) -o $@ $<

.PRECIOUS: %.o %.bin %.exe

.PHONY: clean
clean:
	-rm *.bin *.exe *.o
