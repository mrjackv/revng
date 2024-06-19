#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <compare>
#include <limits>
#include <string>

#include "revng/Model/VerifyHelper.h"
#include "revng/Yield/TagType.h"

/* TUPLE-TREE-YAML

name: TaggedString
type: struct
fields:
  - name: Index
    type: uint64_t

  - name: Type
    type: TagType

  - name: Content
    type: string

  - name: Attributes
    sequence:
      type: SortedVector
      elementType: TagAttribute
    optional: true
key:
  - Index

TUPLE-TREE-YAML */

#include "revng/Yield/Generated/Early/TaggedString.h"

namespace yield {

class TaggedString : public generated::TaggedString {
public:
  using generated::TaggedString::TaggedString;
  TaggedString(uint64_t Index, TagType::Values Type, llvm::StringRef Content) :
    generated::TaggedString(Index, Type, Content.str(), {}) {}

public:
  bool verify(model::VerifyHelper &VH) const;

public:
  inline bool verify() const debug_function { return verify(false); }
  inline bool verify(bool Assert) const debug_function {
    model::VerifyHelper VH(Assert);
    return verify(VH);
  }
};

} // namespace yield

#include "revng/Yield/Generated/Late/TaggedString.h"
