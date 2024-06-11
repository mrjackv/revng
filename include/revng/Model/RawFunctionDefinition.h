#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Model/Identifier.h"
#include "revng/Model/NamedTypedRegister.h"
#include "revng/Model/TypeDefinition.h"

/* TUPLE-TREE-YAML
name: RawFunctionDefinition
type: struct
inherits: TypeDefinition
fields:
  - name: Architecture
    type: Architecture
    doc: The processor architecture of this function
  - name: Arguments
    sequence:
      type: SortedVector
      elementType: NamedTypedRegister
    doc: The argument registers must be valid in the target architecture
  - name: ReturnValues
    sequence:
      type: SortedVector
      elementType: NamedTypedRegister
    doc: The return value registers must be valid in the target architecture
  - name: ReturnValueComment
    type: string
    optional: true
  - name: PreservedRegisters
    sequence:
      type: SortedVector
      elementType: Register
    doc: The preserved registers must be valid in the target architecture
  - name: FinalStackOffset
    type: uint64_t
  - name: StackArgumentsType
    doc: The type of the struct representing stack arguments
    reference:
      pointeeType: TypeDefinition
      rootType: Binary
    optional: true
TUPLE-TREE-YAML */

#include "revng/Model/Generated/Early/RawFunctionDefinition.h"

class model::RawFunctionDefinition
  : public model::generated::RawFunctionDefinition {
public:
  static constexpr const char *AutomaticNamePrefix = "rawfunction_";

public:
  using generated::RawFunctionDefinition::RawFunctionDefinition;

public:
  Identifier name() const;

public:
  const llvm::SmallVector<model::QualifiedType, 4> edges() const {
    llvm::SmallVector<model::QualifiedType, 4> Result;

    for (auto &Argument : Arguments())
      Result.push_back(Argument.Type());
    for (auto &RV : ReturnValues())
      Result.push_back(RV.Type());
    if (not StackArgumentsType().empty())
      Result.push_back(QualifiedType{ StackArgumentsType(), {} });

    return Result;
  }

public:
  static bool classof(const TypeDefinition *D) { return classof(D->key()); }
  static bool classof(const Key &K) { return std::get<1>(K) == AssociatedKind; }
};

#include "revng/Model/Generated/Late/RawFunctionDefinition.h"
