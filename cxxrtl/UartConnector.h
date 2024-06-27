#ifndef UART_CONNECTOR_H
#define UART_CONNECTOR_H

#include <sae.h>

class UartConnector {
public:
    UartConnector(cxxrtl_design::p_sae& top);

    enum result {
        NOP,
        RECEIVED,
    };

    void tx(const std::string& b);
    result tick();

    uint8_t last_byte() const;

private:
    value<1>& _tx;
    value<1>& _rx;

    uint8_t _last_byte;

    enum {
        RX_IDLE,
        RX_BIT,
    } _rx_state;
    uint32_t _rx_timer;
    uint16_t _rx_sr;
    uint8_t _rx_counter;

    enum {
        TX_IDLE,
        TX_BIT,
    } _tx_state;
    std::string _tx_buffer;
    uint32_t _tx_timer;
    uint16_t _tx_sr;
    uint8_t _tx_counter;
};

#endif
