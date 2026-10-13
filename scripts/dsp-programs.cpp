// Print the DSP core FX programs that the vendor HAL plugin carries.
//
// The tables are C++ globals that the plugin builds in its static
// initializers, so this tool loads the plugin and reads them from memory.
// The symbols are private: pass "<name> <address>" lines from nm on stdin.
//
//   hal=/Library/Audio/Plug-Ins/HAL/ApogeeElementEnsemble.driver/Contents/MacOS/ApogeeElementEnsemble
//   clang++ -std=c++17 -o /tmp/dsp-programs scripts/dsp-programs.cpp
//   nm -arch arm64 "$hal" | c++filt | awk '$3 ~ /^DSPCore::[A-Za-z0-9]+FXInfo$/ {print $3, $1}' |
//     sort -u -k1,1 | /tmp/dsp-programs "$hal"
//
// The struct layouts come from the Apogee::DSPCore* constructors in the
// arm64 slice of HAL plugin 0.8.7.
#include <dlfcn.h>
#include <mach-o/dyld.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

struct CriticalSection {
  int32_t words[6];
};

struct CodeFragment {
  std::vector<uint32_t> code;
  std::vector<uint8_t> coefMap;
  std::vector<CriticalSection> criticalSections;
};

struct FXOption {
  std::string uuid;
  int kind;
  bool stereo;
  std::vector<CodeFragment> fragments;
};

struct FXInfo {
  int id;
  std::string name;
  std::vector<float> monoCoefs;
  std::vector<float> stereoCoefs;
  std::vector<FXOption> options;
};

static_assert(sizeof(CodeFragment) == 0x48);
static_assert(sizeof(FXOption) == 0x38);
static_assert(sizeof(FXInfo) == 0x68);

static void printFloats(const char *label, const std::vector<float> &v) {
  printf("  %s[%zu]:", label, v.size());
  for (float f : v) printf(" %g", f);
  printf("\n");
}

static void printFragment(const CodeFragment &f) {
  printf("   fragment: %zu words\n    coefMap:", f.code.size());
  for (auto c : f.coefMap) printf(" %u", c);
  printf("\n    criticalSections:");
  for (auto &s : f.criticalSections) {
    printf(" [");
    for (int i = 0; i < 6; i++) printf(i ? " %d" : "%d", s.words[i]);
    printf("]");
  }
  printf("\n");
  for (size_t i = 0; i < f.code.size(); i++)
    printf("    %3zu %08x\n", i, f.code[i]);
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s <HAL plugin binary> < symbols\n", argv[0]);
    return 2;
  }
  if (!dlopen(argv[1], RTLD_NOW | RTLD_LOCAL)) {
    fprintf(stderr, "%s\n", dlerror());
    return 1;
  }
  intptr_t slide = 0;
  for (uint32_t i = 0; i < _dyld_image_count(); i++)
    if (strcmp(_dyld_get_image_name(i), argv[1]) == 0)
      slide = _dyld_get_image_vmaddr_slide(i);

  std::string symbol;
  uintptr_t address;
  while (std::cin >> symbol >> std::hex >> address) {
    auto &fx = *reinterpret_cast<const FXInfo *>(address + slide);
    printf("%s: id %d, %s\n", symbol.c_str(), fx.id, fx.name.c_str());
    printFloats("monoCoefs", fx.monoCoefs);
    printFloats("stereoCoefs", fx.stereoCoefs);
    for (auto &option : fx.options) {
      printf("  option %s: kind %d, stereo %d, %zu fragments\n",
             option.uuid.c_str(), option.kind, option.stereo,
             option.fragments.size());
      for (auto &f : option.fragments) printFragment(f);
    }
  }
}
