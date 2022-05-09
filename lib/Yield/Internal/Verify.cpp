/// \file Verify.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Yield/Internal/BasicBlock.h"
#include "revng/Yield/Internal/Function.h"
#include "revng/Yield/Internal/Instruction.h"
#include "revng/Yield/Internal/Tag.h"

bool yield::Tag::verify(model::VerifyHelper &VH) const {
  if (Type == TagType::Invalid)
    return VH.fail("The type of this tag is not valid.");
  if (FromPosition == std::string::npos)
    return VH.fail("This tag doesn't have a starting point.");
  if (ToPosition == std::string::npos)
    return VH.fail("This tag doesn't have an ending point.");
  if (FromPosition >= ToPosition)
    return VH.fail("This tag doesn't have a positive length.");

  return true;
}

bool yield::Instruction::verify(model::VerifyHelper &VH) const {
  if (Address.isInvalid())
    return VH.fail("An instruction has to have a valid address.");
  if (Raw.empty())
    return VH.fail("A raw view of an instruction cannot be empty.");
  if (Bytes.empty())
    return VH.fail("An instruction has to be at least one byte big.");

  // TODO: Tags might need special verification as well.
  // Their order, the fact that they don't overlap in undesirable ways, etc.

  return true;
}

bool yield::BasicBlock::verify(model::VerifyHelper &VH) const {
  if (Start.isInvalid())
    return VH.fail("A basic block has to have a valid start address.");
  if (End.isInvalid())
    return VH.fail("A basic block has to have a valid end address.");
  if (Instructions.empty())
    return VH.fail("A basic block has to store at least a single instruction.");

  for (const auto &Instruction : Instructions)
    if (!Instruction.verify(VH))
      return VH.fail("Instuction verification failed.");

  if (CommentIndicator.empty())
    return VH.fail("A basic block has to store a valid comment indicator.");
  if (LabelIndicator.empty())
    return VH.fail("A basic block has to store a valid label indicator.");

  return true;
}

bool yield::Function::verify(model::VerifyHelper &VH) const {
  if (Entry.isInvalid())
    return VH.fail("A function has to have a valid entry point.");

  if (BasicBlocks.empty())
    return VH.fail("A function has to store at least a single basic block.");

  for (const auto &BasicBlock : BasicBlocks)
    if (!BasicBlock.verify(VH))
      return VH.fail("Basic block verification failed.");

  return true;
}
