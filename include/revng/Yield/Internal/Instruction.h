#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <limits>
#include <string>

#include "revng/ADT/SortedVector.h"
#include "revng/Model/VerifyHelper.h"
#include "revng/Support/MetaAddress.h"
#include "revng/Support/MetaAddress/YAMLTraits.h"
#include "revng/Yield/Internal/TagType.h"

namespace yield {
using ByteContainer = llvm::SmallVector<uint8_t, 16>;
}

/* TUPLE-TREE-YAML

name: Instruction
type: struct
fields:
  - name: Address
    type: MetaAddress
  - name: Bytes
    type: yield::ByteContainer
  - name: Raw
    type: std::string

  - name: Tags
    sequence:
      type: std::vector
      elementType: yield::Tag
    optional: true

  - name: Opcode
    type: std::string
    optional: true
  - name: Comment
    type: std::string
    optional: true
  - name: Error
    type: std::string
    optional: true

  - name: HasDelayedSlot
    type: bool
    optional: true

key:
  - Address

TUPLE-TREE-YAML */

#include "revng/Yield/Internal/Generated/Early/Instruction.h"

namespace yield {

class Instruction : public generated::Instruction {
public:
  using generated::Instruction::Instruction;

public:
  bool verify(model::VerifyHelper &VH) const;
  void dump() const debug_function;

public:
  inline bool verify() const debug_function { return verify(false); }
  inline bool verify(bool Assert) const debug_function {
    model::VerifyHelper VH(Assert);
    return verify(VH);
  }
};

} // namespace yield

#include "revng/Yield/Internal/Generated/Late/Instruction.h"
