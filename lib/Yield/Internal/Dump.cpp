/// \file Dump.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Yield/Internal/BasicBlock.h"
#include "revng/Yield/Internal/Function.h"
#include "revng/Yield/Internal/Instruction.h"
#include "revng/Yield/Internal/Tag.h"

void yield::Tag::dump() const {
  serialize(dbg, *this);
}

void yield::Instruction::dump() const {
  serialize(dbg, *this);
}

void yield::BasicBlock::dump() const {
  serialize(dbg, *this);
}

void yield::Function::dump() const {
  serialize(dbg, *this);
}
