#include <cstdio>
#include <cstdlib>

#include "Registers.h"

using namespace Ensemble;

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

static void depth_follows_the_vendor_rate_bands()
{
    CHECK(depthFor(44100.0) == 2 && depthFor(48000.0) == 2);
    CHECK(depthFor(88200.0) == 8 && depthFor(96000.0) == 8);
    CHECK(depthFor(176400.0) == 32 && depthFor(192000.0) == 32);
}

int main()
{
    depth_follows_the_vendor_rate_bands();
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
