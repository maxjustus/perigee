#ifndef check_h
#define check_h

#include <cstdio>
#include <cstdlib>

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

static int finish()
{
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}

#endif
