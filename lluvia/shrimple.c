#include <stdint.h>

int main() {
  volatile uint8_t *UART_TX = (uint8_t *)0x10000;

  *UART_TX = 'H';
  *UART_TX = 'i';
  *UART_TX = '!';
  *UART_TX = '\n';
  return 123;
}
