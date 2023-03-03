//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <mutex>
#include <optional>
#include <thread>

#include "llvm/Support/Base64.h"
#include "llvm/Support/Process.h"
#include "llvm/Support/raw_ostream.h"

#include "revng/ADT/ConstexprString.h"
#include "revng/PipelineC/PipelineC.h"
#include "revng/Support/Assert.h"

inline constexpr auto TracingEnv = "REVNG_C_API_TRACE_PATH";
static bool TracingEnabled = llvm::sys::Process::GetEnv(TracingEnv).hasValue();

// The opposite of a std::recursive_mutex, if locked by the same thread it will
// assert (this is to avoid a deadlock/malformed output when tracing)
class NonRecursiveMutex {
private:
  std::optional<std::thread::id> ThreadId;
  std::mutex TheLock;

public:
  NonRecursiveMutex() {}

  void lock() {
    if (ThreadId.has_value())
      revng_assert(std::this_thread::get_id() != *ThreadId,
                   "NonRecursiveMutex entered twice by the same thread!");
    TheLock.lock();
    ThreadId = std::this_thread::get_id();
  }

  void unlock() {
    revng_assert(std::this_thread::get_id() == *ThreadId);
    TheLock.unlock();
    ThreadId.reset();
  }
};

static NonRecursiveMutex TraceLock;

// Helper class for tracing, this will be used by the the
// tracing_wrapper.cpp.j2 template to create a wrapper around PipelineC
// functions. This class provides facilities to print basic C types to
// the tracing file
class PipelineCTracer {
private:
  std::string Path;
  std::error_code OpenEC;
  llvm::raw_fd_ostream OS;
  bool OutputtingArguments;

public:
  PipelineCTracer(std::string Path) :
    Path(Path), OpenEC(), OS(Path, OpenEC), OutputtingArguments(false) {
    revng_assert(!OpenEC);
    printHeader();
  }

  ~PipelineCTracer() {
    OS.flush();
    OS.close();
  }

private:
  void printHeader() {
    OS << "version: 1\n";
    OS << "commands:\n";
    OS.flush();
  }

  std::string reprString(const char *String) {
    return '"' + llvm::StringRef(String).str() + '"';
  }

public:
  void functionPrelude(const llvm::StringRef Name) {
    OS << "- name: " << Name << "\n";
    OS << "  arguments:\n";
    OutputtingArguments = true;
    OS.flush();
  }

  void newArgument() {
    OS << "  - ";
    OS.flush();
  }

  void printInt(const uint64_t &Int) {
    OS << Int << "\n";
    OS.flush();
  }

  template<typename T>
  // clang-format off
  requires std::is_same_v<T, uint8_t> ||
           std::is_same_v<T, uint32_t> ||
           std::is_same_v<T, uint64_t>
  // clang-format on
  void printIntList(const T List[], const uint64_t &Length) {
    OS << "[";
    for (uint64_t I = 0; I < Length; I++) {
      OS << (uint64_t) List[I];
      if (I < Length - 1) {
        OS << ", ";
      }
    }
    OS << "]\n";
    OS.flush();
  }

  void printString(const char *String) {
    if (OutputtingArguments)
      OS << reprString(String);
    else
      OS << "P" << (void *) String;
    OS << "\n";
    OS.flush();
  }

  void printStringList(const char *List[], const uint64_t Length) {
    OS << "[";
    for (uint64_t I = 0; I < Length; I++) {
      OS << reprString(List[I]);
      if (I < Length - 1) {
        OS << ", ";
      }
    }
    OS << "]\n";
    OS.flush();
  }

  void printBool(const bool &Bool) {
    OS << (Bool ? "true" : "false") << "\n";
    OS.flush();
  }

  template<typename T>
  void printOpaquePtr(const T *Ptr) {
    OS << "P" << (void *) Ptr << "\n";
    OS.flush();
  }

  template<typename T>
  void printPtrList(const T *List[], const uint64_t Length) {
    OS << "[";
    for (uint64_t I = 0; I < Length; I++) {
      OS << "P" << (void *) List[I];
      if (I < Length - 1) {
        OS << ", ";
      }
    }
    OS << "]\n";
    OS.flush();
  }

  void printBuffer(const char *Buffer, const uint64_t Length) {
    OS << llvm::encodeBase64(llvm::StringRef(Buffer, Length)) << "\n";
    OS.flush();
  }

  void printVoid() {
    OS << "null\n";
    OS.flush();
  }

  void endArguments() {
    OutputtingArguments = false;
    OS << "  return: ";
    OS.flush();
  }
};

static std::optional<PipelineCTracer>
  Tracer = []() -> std::optional<PipelineCTracer> {
  if (auto Path = llvm::sys::Process::GetEnv(TracingEnv)) {
    return std::make_optional(*Path);
  } else {
    return std::nullopt;
  }
}();

template<ConstexprString Name, int I>
constexpr int LengthHint = -1;

template<typename T, typename V>
constexpr bool is = std::is_same_v<std::remove_cvref_t<T>, V>;

template<ConstexprString Name, int I, int N, typename... T>
static void handleArg(std::tuple<T...> Args) {
  Tracer->newArgument();
  using ArgT = decltype(std::get<I>(Args));
  using RArgT = std::remove_reference_t<ArgT>;
  ArgT Arg = std::get<I>(Args);
  constexpr int LH = LengthHint<Name, I>;
  if constexpr (LH >= 0) {
    // Handle arguments with length hints
    if constexpr (is<ArgT, char *>) {
      // Buffer
      Tracer->printBuffer(Arg, std::get<LH>(Args));
    } else {
      // Array-like
      if constexpr (is<RArgT, uint64_t *>) {
        Tracer->printIntList(Arg, std::get<LH>(Args));
      } else if constexpr (is<ArgT, const char *>) {
        Tracer->printStringList(&Arg, std::get<LH>(Args));
      }
    }
  }
  if constexpr (std::is_same_v<RArgT, uint64_t>) {
    Tracer->printInt(Arg);
  } else {
    Tracer->printVoid();
  }
  if constexpr (I + 1 < N)
    handleArg<Name, I + 1, N>(Args);
}

template<ConstexprString Name, typename... T>
static void handleArgs(T &&...Args) {
  if constexpr (sizeof...(T) > 0)
    handleArg<Name, 0, sizeof...(T)>(std::make_tuple(Args...));
}

template<typename T>
static void handleReturn(T &&Ret) {
  using RetT = std::remove_reference_t<T>;
  if constexpr (std::is_same_v<RetT, bool>) {
    Tracer->printBool(Ret);
  } else if constexpr (std::is_same_v<RetT, uint64_t>) {
    Tracer->printInt(Ret);
  } else {
    Tracer->printVoid();
  }
}

template<ConstexprString Name, typename CalleeT, typename... ArgsT>
inline decltype(auto) wrap(CalleeT Callee, ArgsT... Args) {
  using ReturnT = typename decltype(std::function{ Callee })::result_type;
  if (TracingEnabled) {
    Tracer->functionPrelude(Name.String.data());
    handleArgs<Name>(Args...);
    Tracer->endArguments();
    if constexpr (std::is_same_v<ReturnT, void>) {
      Callee(std::forward<ArgsT>(Args)...);
      Tracer->printVoid();
    } else {
      ReturnT Return = Callee(std::forward<ArgsT>(Args)...);
      handleReturn(Return);
      return Return;
    }
  } else {
    if constexpr (std::is_same_v<ReturnT, void>)
      Callee(std::forward<ArgsT>(Args)...);
    else
      return Callee(std::forward<ArgsT>(Args)...);
  }
}
