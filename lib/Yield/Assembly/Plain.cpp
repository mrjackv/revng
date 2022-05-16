/// \file Plain.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/Support/FormatVariadic.h"

#include "revng/Model/Binary.h"
#include "revng/Yield/ControlFlow/FallthroughDetection.h"
#include "revng/Yield/Internal/Function.h"
#include "revng/Yield/Plain.h"

static std::string linkAddress(const MetaAddress &Address) {
  std::string Result = Address.toString();

  constexpr std::array ForbiddenCharacters = { ' ', ':', '!', '#',  '?',
                                               '<', '>', '/', '\\', '{',
                                               '}', '[', ']' };

  for (char &Character : Result)
    if (llvm::find(ForbiddenCharacters, Character) != ForbiddenCharacters.end())
      Character = '_';

  return Result;
}

static std::string deduceName(const MetaAddress &Target,
                              const yield::Function &Function,
                              const model::Binary &Binary) {
  if (auto Iterator = Binary.Functions.find(Target);
      Iterator != Binary.Functions.end()) {
    // The target is a function
    return Iterator->name().str().str();
  } else if (auto Iterator = Function.BasicBlocks.find(Target);
             Iterator != Function.BasicBlocks.end()) {
    // The target is a basic block

    // TODO: maybe there's something better than the address to put here.
    return "basic_block_at_" + linkAddress(Target);
  } else if (Target.isValid()) {
    // The target is an instruction
    return "instruction_at_" + linkAddress(Target);
  } else {
    // The target is impossible to deduce, it's an indirect call or the like.
    return "(error)";
  }
}

static std::string label(const yield::BasicBlock &BasicBlock,
                         const yield::Function &Function,
                         const model::Binary &Binary) {
  std::string Result = deduceName(BasicBlock.Start, Function, Binary);
  return Result += BasicBlock.LabelIndicator + "\n";
}

static std::string instruction(const yield::Instruction &Instruction,
                               const yield::BasicBlock &BasicBlock) {
  std::string Result = Instruction.Raw;

  if (!Instruction.Comment.empty())
    Result += ' ' + BasicBlock.CommentIndicator + ' ' + Instruction.Comment;
  else if (!Instruction.Error.empty())
    Result += ' ' + BasicBlock.CommentIndicator
              + " Error: " + Instruction.Error;

  return Result;
}

static std::string basicBlock(const yield::BasicBlock &BasicBlock,
                              const yield::Function &Function,
                              const model::Binary &Binary) {
  std::string Result;

  for (const auto &Instruction : BasicBlock.Instructions)
    Result += instruction(Instruction, BasicBlock);

  return Result;
}

template<bool ShouldMergeFallthroughTargets>
static std::string labeledBlock(const yield::BasicBlock &FirstBlock,
                                const yield::Function &Function,
                                const model::Binary &Binary) {
  std::string Result;
  Result += label(FirstBlock, Function, Binary);

  if constexpr (ShouldMergeFallthroughTargets == false) {
    Result += basicBlock(FirstBlock, Function, Binary);
  } else {
    auto BasicBlocks = yield::cfg::labeledBlock(FirstBlock, Function, Binary);
    if (BasicBlocks.empty())
      return "";

    for (auto BasicBlock : BasicBlocks)
      Result += basicBlock(*BasicBlock, Function, Binary);
  }

  return Result;
}

std::string yield::plain::functionAssembly(const yield::Function &Function,
                                           const model::Binary &Binary) {
  std::string Result;

  for (const auto &BasicBlock : Function.BasicBlocks)
    Result += labeledBlock<true>(BasicBlock, Function, Binary);

  return Result;
}

std::string yield::plain::controlFlowNode(const MetaAddress &Address,
                                          const yield::Function &Function,
                                          const model::Binary &Binary) {
  auto Iterator = Function.BasicBlocks.find(Address);
  revng_assert(Iterator != Function.BasicBlocks.end());

  auto Result = labeledBlock<false>(*Iterator, Function, Binary);
  revng_assert(!Result.empty());

  return Result;
}
