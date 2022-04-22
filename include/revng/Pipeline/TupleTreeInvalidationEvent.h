#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Pipeline/InvalidationEvent.h"
#include "revng/TupleTree/TupleTreeDiff.h"

namespace pipeline {

template<TupleTreeCompatible T>
class TupleTreeInvalidationEvent
  : public pipeline::InvalidationEvent<TupleTreeInvalidationEvent<T>> {
private:
  TupleTreeDiff<T> Diff;

public:
  static char ID;

public:
  explicit TupleTreeInvalidationEvent(TupleTreeDiff<T> &&Diff) :
    Diff(std::move(Diff)) {}

  explicit TupleTreeInvalidationEvent(const TupleTreeDiff<T> &Diff) :
    Diff(Diff) {}

public:
  ~TupleTreeInvalidationEvent() override = default;

  const TupleTreeDiff<T> getDiff() const { return Diff; }
};
} // namespace pipeline
