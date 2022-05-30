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
#include "revng/Yield/Internal/BasicBlock.h"

/* TUPLE-TREE-YAML

name: Function
type: struct
fields:
  - name: Entry
    type: MetaAddress
  - name: Name
    type: std::string

  - name: BasicBlocks
    sequence:
      type: SortedVector
      elementType: yield::BasicBlock

key:
  - Entry

TUPLE-TREE-YAML */

#include "revng/Yield/Internal/Generated/Early/Function.h"

namespace yield {

class Function : public generated::Function {
public:
  using generated::Function::Function;

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

#include "revng/Yield/Internal/Generated/Late/Function.h"
