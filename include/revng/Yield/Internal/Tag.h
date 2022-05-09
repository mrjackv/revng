#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <limits>
#include <string>

#include "revng/Model/VerifyHelper.h"
#include "revng/Yield/Internal/TagType.h"

/* TUPLE-TREE-YAML

name: Tag
type: struct
fields:
  - name: Type
    type: yield::TagType::Values
  - name: FromPosition
    type: size_t
  - name: ToPosition
    type: size_t

TUPLE-TREE-YAML */

#include "revng/Yield/Internal/Generated/Early/Tag.h"

namespace yield {

class Tag : public generated::Tag {
public:
  using generated::Tag::Tag;
  Tag(TagType::Values Type,
      size_t FromPosition = std::numeric_limits<size_t>::min(),
      size_t ToPosition = std::numeric_limits<size_t>::max()) :
    generated::Tag(Type, FromPosition, ToPosition) {}

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

#include "revng/Yield/Internal/Generated/Late/Tag.h"
