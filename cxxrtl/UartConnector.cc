#include "UartConnector.h"

extern uint64_t vcd_time;
const uint32_t DIVISOR = CLOCK_HZ / 115200;

UartConnector::UartConnector(cxxrtl_design::p_sae& top):
    // We transmit on the design's RX line and receive from its TX.
    _tx(top.p_uart__rx),
    _rx(top.p_uart__tx),
    _rx_state(RX_IDLE),
    _tx_state(TX_IDLE)
{
    _tx.set(true);
}

void UartConnector::tx(const std::string& b) {
    _tx_buffer = b;
}

UartConnector::result UartConnector::tick() {
    switch (_tx_state) {
    case TX_IDLE:
        if (_tx_buffer.size()) {
            _tx.set(false);
            _tx_state = TX_BIT;
            _tx_timer = DIVISOR;
            _tx_sr = 0x100u | (uint16_t)_tx_buffer[0];
            _tx_counter = 0;

            _tx_buffer.erase(_tx_buffer.begin());
        }
        break;

    case TX_BIT:
        if (!--_tx_timer) {
            _tx_timer = DIVISOR;
            _tx.set(_tx_sr & 1);
            _tx_sr >>= 1;

            if (++_tx_counter == 10) {
                _tx.set(true);
                _tx_state = TX_IDLE;
            }
        }
        break;
    }

    switch (_rx_state) {
    case RX_IDLE:
        if (!_rx.get<bool>()) {
            _rx_state = RX_BIT;
            _rx_timer = DIVISOR / 2;
            _rx_sr = 0;
            _rx_counter = 0;
        }
        return NOP;

    case RX_BIT:
        if (!--_rx_timer) {
            _rx_timer = DIVISOR;
            _rx_sr = _rx_sr << 1 | _rx.get<uint16_t>();

            if (++_rx_counter == 10) {
                _rx_state = RX_IDLE;

                if ((_rx_sr & 0x200) || !(_rx_sr & 0x1)) {
                    std::cerr << "UartConnector ERR" << std::endl;
                } else {
                    _rx_sr = (_rx_sr >> 1) & 0xFF;
                    _rx_sr =
                        (_rx_sr & 0x80) >> 7 |
                        (_rx_sr & 0x40) >> 5 |
                        (_rx_sr & 0x20) >> 3 |
                        (_rx_sr & 0x10) >> 1 |
                        (_rx_sr & 0x08) << 1 |
                        (_rx_sr & 0x04) << 3 |
                        (_rx_sr & 0x02) << 5 |
                        (_rx_sr & 0x01) << 7;

                    _last_byte = (uint8_t)_rx_sr;
                    return RECEIVED;
                }
            }
        }

        return NOP;
    }
}

uint8_t UartConnector::last_byte() const {
    return _last_byte;
}
