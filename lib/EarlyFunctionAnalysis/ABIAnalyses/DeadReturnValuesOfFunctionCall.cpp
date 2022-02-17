//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/GraphTraits.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/iterator_range.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/GlobalVariable.h"
#include "llvm/IR/Instruction.h"
#include "llvm/IR/Instructions.h"
#include "llvm/Support/Casting.h"

#include "revng/MFP/MFP.h"
#include "revng/Model/Binary.h"

#include "Analyses.h"

namespace ABIAnalyses::DeadReturnValuesOfFunctionCall {
using namespace llvm;
using namespace ABIAnalyses;

std::map<const GlobalVariable *, State>
analyze(const BasicBlock *CallSiteBlock, const GeneratedCodeBasicInfo &GCBI) {
  using MFI = MFIAnalysis<true, CoreLattice>;

  std::map<const GlobalVariable *, State> RegNoOrDead{};
  MFI Instance{ { getPreCallHook(CallSiteBlock), GCBI } };
  MFI::LatticeElement InitialValue;
  MFI::LatticeElement ExtremalValue(CoreLattice::ExtremalLatticeElement);
  auto *Start = CallSiteBlock->getUniqueSuccessor();

  if (!Start)
    return RegNoOrDead;

  auto
    Results = MFP::getMaximalFixedPoint<MFI, MFI::GT, MFI::LGT>(Instance,
                                                                Start,
                                                                InitialValue,
                                                                ExtremalValue,
                                                                { Start },
                                                                { Start });

  for (auto &[BB, Result] : Results) {
    for (auto &[GV, RegState] : Result.OutValue) {
      if (RegState == CoreLattice::NoOrDead) {
        RegNoOrDead[GV] = State::NoOrDead;
      }
    }
  }
  return RegNoOrDead;
}
} // namespace ABIAnalyses::DeadReturnValuesOfFunctionCall
