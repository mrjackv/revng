#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/ADT/ArrayRef.h"

#include "revng/PipeboxCommon/Helpers/Native/Container.h"

namespace revng::pypeline::helpers {

// Helper function to unpack containers from an ArrayRef.
// To be used in conjunction with PipeRunner or AnalysisRunner
template<typename C, size_t I>
inline C &
extractContainerFromList(llvm::ArrayRef<native::Container *> Containers) {
  return *static_cast<C *>(Containers[I]->get());
}

} // namespace revng::pypeline::helpers
