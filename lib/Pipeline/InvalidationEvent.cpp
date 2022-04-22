/// \file InvalidationEvent.cpp
/// \brief Implementation of invalidation events

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Pipeline/InvalidationEvent.h"
#include "revng/Pipeline/Kind.h"
#include "revng/Pipeline/Runner.h"

using namespace pipeline;

llvm::Error InvalidationEventBase::apply(Runner &Runner) const {
  InvalidationMap Map;
  getInvalidations(Runner, Map);
  if (auto Error = Runner.getInvalidations(Map); Error)
    return Error;
  return Runner.invalidate(Map);
}

void InvalidationEventBase::getInvalidations(const Runner &Runner,
                                             InvalidationMap &Map) const {
  for (const auto &Step : Runner) {
    auto &StepInvalidations = Map[Step.getName()];
    for (const auto &Cotainer : Step.containers()) {
      if (not Cotainer.second)
        continue;

      auto &ContainerInvalidations = StepInvalidations[Cotainer.first()];
      for (const Kind &Rule : Runner.getKindsRegistry())
        Rule.getInvalidations(ContainerInvalidations, *this);
    }
  }
}
