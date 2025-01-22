#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <chrono>

// Returns the number of milliseconds since epoch
inline uint64_t getUnixMilliseconds() {
  namespace sc = std::chrono;
  auto Now = sc::system_clock::now().time_since_epoch();
  return sc::duration_cast<std::chrono::milliseconds>(Now).count();
}
