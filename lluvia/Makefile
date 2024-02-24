ASFLAGS = -march=rv32i -mabi=ilp32
CFLAGS  = -march=rv32i -mabi=ilp32 -O2
LDFLAGS = -T linker.ld

TARGETS = shrimple.bin

all: ../sae/rtl/test_shrimple.bin

../sae/rtl/test_shrimple.bin: shrimple.bin
	cp $< $@

%.bin: %.exe
	$(OBJCOPY) -O binary $< $@

%.exe: %.o crt0.o
	$(LD) $(LDFLAGS) -o $@ $<

.PRECIOUS: %.o %.bin %.exe

.PHONY: clean
clean:
	-rm *.bin *.exe *.o
