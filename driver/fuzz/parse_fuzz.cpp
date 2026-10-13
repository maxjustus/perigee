#include <cstdlib>
#include <cstring>
#include <vector>

#include "Protocol.h"

using namespace Ensemble;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t * data, size_t size)
{
    std::vector<uint32_t> words(size / 4);
    std::memcpy(words.data(), data, words.size() * 4);
    parseMessage(words.data(), uint32_t(words.size()), [](const Report & r) {
        if (r.length > kMaxReportData) {
            std::abort();
        }
    });
    return 0;
}
