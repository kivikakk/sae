CFLAGS = -march=rv32i -mabi=ilp32

test: test.o
	riscv32-none-elf-objcopy -O binary $< $@

test.o: test.c


.PHONY: clean
clean:
	-rm test test.o
