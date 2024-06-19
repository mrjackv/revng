#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/ADT/RecursiveCoroutine.h"
#include "revng/Model/Identifier.h"
#include "revng/Model/Type.h"
#include "revng/Model/VerifyHelper.h"

/* TUPLE-TREE-YAML
name: Argument
doc: |
  The argument of a function type. It features an argument index (the key), a
  type and an optional name
type: struct
fields:
  - name: Index
    type: uint64_t
  - name: Type
    type: Type
    upcastable: true
  - name: CustomName
    type: Identifier
    optional: true
  - name: OriginalName
    type: string
    optional: true
  - name: Comment
    type: string
    optional: true
key:
  - Index
TUPLE-TREE-YAML */

#include "revng/Model/Generated/Early/Argument.h"

class model::Argument : public model::generated::Argument {
public:
  using generated::Argument::Argument;
  Argument(uint64_t Index, UpcastableType &&Type) :
    model::generated::Argument(Index, std::move(Type), {}, {}, {}) {}

  Identifier name() const;

public:
  bool verify() const debug_function;
  bool verify(bool Assert) const debug_function;
  RecursiveCoroutine<bool> verify(VerifyHelper &VH) const;
};

#include "revng/Model/Generated/Late/Argument.h"
