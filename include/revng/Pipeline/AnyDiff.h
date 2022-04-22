#pragma once
//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <any>

#include "revng/Pipeline/InvalidationEvent.h"
#include "revng/Pipeline/TupleTreeInvalidationEvent.h"
#include "revng/Support/YAMLTraits.h"
#include "revng/TupleTree/TupleTreeDiff.h"

namespace pipeline {
class AnyDiffBase {
public:
  virtual void serialize(llvm::raw_ostream &OS) const = 0;
  virtual std::unique_ptr<InvalidationEventBase>
  getInvalidationEvent() const = 0;
  virtual ~AnyDiffBase() = default;
  virtual std::unique_ptr<AnyDiffBase> clone() const = 0;
};

template<TupleTreeCompatible T>
class AnyDiffImpl : public AnyDiffBase {
private:
  TupleTreeDiff<T> Diff;

public:
  AnyDiffImpl(TupleTreeDiff<T> Diff) : Diff(std::move(Diff)) {}
  ~AnyDiffImpl() override = default;

  void serialize(llvm::raw_ostream &OS) const override {
    ::serialize(OS, Diff);
  }

  std::unique_ptr<InvalidationEventBase> getInvalidationEvent() const override {
    InvalidationEventBase *ToReturn = new TupleTreeInvalidationEvent(Diff);
    return std::unique_ptr<InvalidationEventBase>(ToReturn);
  }

  std::unique_ptr<AnyDiffBase> clone() const override {
    return std::unique_ptr<AnyDiffBase>(new AnyDiffImpl(*this));
  }
};

class AnyDiff {
private:
  std::unique_ptr<AnyDiffBase> Diff;

public:
  template<typename T>
  AnyDiff(TupleTreeDiff<T> Diff) : Diff(new AnyDiffImpl<T>(std::move(Diff))) {}

  AnyDiff(AnyDiff &&) = default;
  AnyDiff &operator=(AnyDiff &&) = default;

  AnyDiff(const AnyDiff &Other) : Diff(Other.Diff->clone()) {}
  AnyDiff &operator=(const AnyDiff &Other) {
    if (this == &Other)
      return *this;

    Diff = Other.Diff->clone();
    return *this;
  }

  ~AnyDiff() = default;

  void serialize(llvm::raw_ostream &OS) const { Diff->serialize(OS); }

  std::unique_ptr<InvalidationEventBase> getInvalidationEvent() const {
    return Diff->getInvalidationEvent();
  }
};

using DiffMap = llvm::StringMap<AnyDiff>;
} // namespace pipeline
