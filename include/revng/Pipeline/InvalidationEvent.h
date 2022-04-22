#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Pipeline/Target.h"

namespace pipeline {

class Runner;

class InvalidationEventBase {
private:
  const char *ID;

public:
  explicit InvalidationEventBase(const char &ID) : ID(&ID) {}
  llvm::Error apply(Runner &Runner) const;
  void getInvalidations(const Runner &Runner, InvalidationMap &Out) const;
  virtual ~InvalidationEventBase() = default;

  const char *getID() const { return ID; }
};

template<typename Derived>
class InvalidationEvent : public InvalidationEventBase {
private:
  template<typename T>
  static const char &ID() {
    static char ID;
    return ID;
  }

public:
  explicit InvalidationEvent() : InvalidationEventBase(ID<Derived>()) {}

  static bool classof(const InvalidationEventBase *Base) {
    return Base->getID() == &ID<Derived>();
  }
};

} // namespace pipeline
