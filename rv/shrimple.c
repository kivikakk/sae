#include <stdint.h>

void print(const char* m) {
  volatile uint8_t *UART_TX = (uint8_t *)0x80000001;
  while (*m)
    *UART_TX = (uint8_t)*m++;
}

int main() {
  print("i am ur princess\r\n");
  return 69;
}
