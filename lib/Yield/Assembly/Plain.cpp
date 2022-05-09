/// \file Plain.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/Support/FormatVariadic.h"

#include "revng/Model/Binary.h"
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
  std::string Result = deduceName(BasicBlock.Address, Function, Binary);
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

template<bool ShouldMergeFallthroughTargets>
static std::string basicBlock(const yield::BasicBlock &BasicBlock,
                              const yield::Function &Function,
                              const model::Binary &Binary) {
  // Blocks are strung together if there's no reason to keep them separate.
  // This determines whether this is the last block in the current string
  // (if `NextBlock` is `nullptr`) or if there's continuation.
  const yield::BasicBlock *NextBlock = nullptr;
  for (const MetaAddress &Target : BasicBlock.Targets) {
    if (Target == BasicBlock.NextAddress) {
      auto Iterator = Function.BasicBlocks.find(Target);
      revng_assert(Iterator != Function.BasicBlocks.end());

      using namespace yield::BasicBlockType;
      if (shouldSkip<ShouldMergeFallthroughTargets>(Iterator->Type)) {
        NextBlock = &*Iterator;
      }
    }
  }

  // String the results together.
  std::string Result;
  for (const auto &Instruction : BasicBlock.Instructions)
    Result += instruction(Instruction, BasicBlock);

  if (NextBlock != nullptr)
    return Result += basicBlock<ShouldMergeFallthroughTargets>(*NextBlock,
                                                               Function,
                                                               Binary);
  else
    return Result;
}

template<bool ShouldMergeFallthroughTargets>
static std::string basicBlockString(const yield::BasicBlock &BasicBlock,
                                    const yield::Function &Function,
                                    const model::Binary &Binary) {
  // Blocks that are merged into other block strings cannot start a new one.
  using namespace yield::BasicBlockType;
  if (shouldSkip<ShouldMergeFallthroughTargets>(BasicBlock.Type))
    return "";

  return label(BasicBlock, Function, Binary)
         + basicBlock<ShouldMergeFallthroughTargets>(BasicBlock,
                                                     Function,
                                                     Binary);
}

std::string yield::plain::functionAssembly(const yield::Function &Function,
                                           const model::Binary &Binary) {
  std::string Result;

  for (const auto &BasicBlock : Function.BasicBlocks)
    Result += basicBlockString<false>(BasicBlock, Function, Binary);

  return Result;
}

std::string yield::plain::controlFlowNode(const MetaAddress &BasicBlockAddress,
                                          const yield::Function &Function,
                                          const model::Binary &Binary) {
  auto Iterator = Function.BasicBlocks.find(BasicBlockAddress);
  revng_assert(Iterator != Function.BasicBlocks.end());

  auto Result = basicBlockString<true>(*Iterator, Function, Binary);
  revng_assert(!Result.empty());

  return Result;
}
