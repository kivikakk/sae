#include <stdint.h>

volatile uint8_t *const UART = (uint8_t *)0x10000;

void print(const char *m) {
  while (*m)
    *UART = (uint8_t)*m++;
}

char inkey(void) {
  uint8_t r = 0;
  while (!r)
    r = *UART;
  return (char)r;
}

int main() {
  print("i am ur princess\r\nagreed? [Yn] ");
  while (1) {
    char c = inkey();
    if (c == 'y' || c == 'Y' || c == '\n' || c == '\r') {
      print("y\r\nohhhhhh!\r\n");
      return 420;
    } else if (c == 'n' || c == 'N') {
      print("n\r\n:<\r\n");
      return 696969;
    }
  }
}
