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
  VH.maybeFail(Type != TagType::Invalid);
  VH.maybeFail(FromPosition < ToPosition);
  VH.maybeFail(FromPosition != std::string::npos);
  VH.maybeFail(ToPosition != std::string::npos);

  return true;
}

bool yield::Instruction::verify(model::VerifyHelper &VH) const {
  VH.maybeFail(Address.isValid());
  VH.maybeFail(!Raw.empty());
  VH.maybeFail(!Bytes.empty());

  // TODO: Tags might need special verification as well.

  return true;
}

bool yield::BasicBlock::verify(model::VerifyHelper &VH) const {
  VH.maybeFail(Address.isValid());
  VH.maybeFail(Type != BasicBlockType::Invalid);

  VH.maybeFail(!Instructions.empty());
  for (const auto &Instruction : Instructions)
    Instruction.verify(VH);

  VH.maybeFail(!CommentIndicator.empty());
  VH.maybeFail(!LabelIndicator.empty());

  return true;
}

bool yield::Function::verify(model::VerifyHelper &VH) const {
  VH.maybeFail(Address.isValid());

  VH.maybeFail(!BasicBlocks.empty());
  for (const auto &BasicBlock : BasicBlocks)
    BasicBlock.verify(VH);

  return true;
}
