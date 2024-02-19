CFLAGS = -march=rv32i -mabi=ilp32

TARGETS = shrimple.bin

all: ../sae/rtl/test_shrimple.bin

../sae/rtl/test_shrimple.bin: shrimple.bin
	cp $< $@

%.bin: %.o
	riscv32-none-elf-objcopy -O binary $< $@

.PRECIOUS: %.o

.PHONY: clean
clean:
	-rm *.bin *.o
