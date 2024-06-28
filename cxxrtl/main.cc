#include <cstring>
#include <iostream>
#include <fstream>
#include <optional>
#include <chrono>

#include <cxxrtl/cxxrtl_vcd.h>
#include <sae.h>

#include "UartConnector.h"

static cxxrtl_design::p_sae top;
static cxxrtl::vcd_writer vcd;
uint64_t vcd_time = 0;

int main(int argc, char **argv) {
    std::optional<std::string> vcd_out = std::nullopt;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--vcd") == 0 && argc >= (i + 2)) {
            vcd_out = std::string(argv[++i]);
        } else {
            std::cerr << "unknown argument \"" << argv[i] << "\"" << std::endl;
            return 2;
        }
    }

    if (vcd_out.has_value()) {
        debug_items di;
        top.debug_info(&di, nullptr, "top ");
        vcd.add(di);
    }

    UartConnector uart(top);

    int rc = 0;
    bool done = false;

    auto start = std::chrono::high_resolution_clock::now();

    enum {
        RECV_QUERY,
        RECV_ANSWER,
    } state = RECV_QUERY;
    std::string recvd;

    for (int i = 0; i < 60000 && !done; ++i) {
        top.p_clk.set(true);
        top.step();
        vcd.sample(vcd_time++);

        switch (uart.tick()) {
        case UartConnector::NOP:
            break;
        case UartConnector::RECEIVED:
            recvd += (char)uart.last_byte();

            switch (state) {
            case RECV_QUERY:
                if (recvd == "i am ur princess\r\nagreed? [Yn] ") {
                    state = RECV_ANSWER;
                    recvd.clear();

                    uart.tx("1234567890y");
                }
                break;

            case RECV_ANSWER:
                if (recvd == "y\r\nohhhhhh!\r\n")
                    done = true;
                break;
            }

            break;
        }

        top.p_clk.set(false);
        top.step();
        vcd.sample(vcd_time++);
    }

    if (!done) rc = 1;

    auto finish = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(finish - start).count();

    std::cout << "finished on cycle " << std::dec << (vcd_time >> 1) << ", rc=" << rc << std::endl;
    std::cout << "took " << duration << "ns = " << (duration / (vcd_time >> 1)) << "ns/cyc" << std::endl;

    if (vcd_out.has_value()) {
        std::ofstream of(*vcd_out);
        of << vcd.buffer;
    }

    return rc;
}
