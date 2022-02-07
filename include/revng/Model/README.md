## tuple_tree_generator HOWTO

tuple_tree_generator takes a description of a struct/enum and generates boilerplate required to make them YAML
serializable/deserializable, compatible with `KeyedObjectContainer`s, and so on.

This document explains how to add an enum or a class to rev.ng model.

Remember to add the new header file to the `MODEL_HEADERS` list in `include/revng/Model/CMakeLists.txt`.

**Note**: Never include the generated headers anywhere apart from the one file containing the YAML that generated it.
Other files should include the header containing the YAML.

### Defining an enum

Enums can be defined like this

`<Name>.h` (the filename must match the name of the generated enum)
```cpp
#pragma once

// <copyright notice>

// Note: the TUPLE-TREE-YAML delimiter is mandatory
/* TUPLE-TREE-YAML
name: <Name>
type: enum
doc: <Optional documentation about the enum itself>
members:
  - name: <Member_1_Name>
  - name: <Member_2_Name>
    doc: <Optional documentation about the specific enum member>
tag: <Optional tag>
TUPLE-TREE-YAML */

#include "revng/Model/Generated/Early/<Name>.h"

// <other definitions>

#include "revng/Model/Generated/Late/<Name>.h"
```

The `tag` property will be used as `!Tag` when serializing the enum to YAML to be able to disambiguate it. It defaults
to `!<EnumName>`.

The autogenerated header file will contain something similar to this:

```cpp
namespace <EnumName> {
  enum Values {
    Invalid = 0
    Member_1_Name = 1;
    Member_2_Name = 2;
    ...
  };
}
```

Note that an `Invalid` member will be added automatically.

You can refer to the enum with `EnumName::Values` and to its values with `EnumName::Values::MemberName` or
`EnumName::MemberName`.

### Defining a struct

Structs can be defined like this

`<Name>.h` (the filename must match the name of the generated struct)
```cpp
#pragma once

// <copyright notice>

// Various includes (e.g. headers declaring field types)
#include "revng/ADT/Something.h"

/* TUPLE-TREE-YAML
name: <ClassName>
type: struct
doc: <Optional documentation about the struct itself>
fields:
  - name: <Field1_name>
    type: <Field1_type>
    doc: <Optional documentation about this specific field>
  - name: <Field2_name>
    type: <Field2_type>
    # marks a field as optional when deserializing YAML
    optional: true
key:
  # List the fields that uniquely identify an object inside a container here.
  # They are also used for building the appropriate TupleTreeReference -- a "path" inside the YAML
  - Index
tag: <Optional tag>
TUPLE-TREE-YAML */

#include "revng/Model/Generated/Early/<Name>.h"

class model::<ClassName> : public model::generated::<ClassName> {
public:
  // Inherit constructors from autogenerated class
  using model::generated::<ClassName>::<ClassName>;
};

#include "revng/Model/Generated/Late/<Name>.h"
```

**Note**: You **must** define a class with a matching name that inherits from the generated class, between the `Early`
and the `Late` includes.

The `tag` property is used to disambiguate YAML parsing like enums.

#### Sequence members

You can define a member composed of a sequence of items as follows

```yaml
name: MyStruct
type: struct
fileds:
  - name: MyArray
    sequence:
      type: std::vector
      elementType: int
```

The sequence type must be instantiable with one type parameter (the element type). If the element type is polymorphic,
add `upcastable: true`

```yaml
name: MyStruct
type: struct
fileds:
  - name: MyArray
    sequence:
      type: std::vector
      upcastable: true
      elementType: model::FunctionEdgeBase
```

This will get translated in C++ as `std::vector<UpcastablePointer<model::FunctionEdgeBase>>`.

#### Reference members

Members can also specify references like this:

```yaml
name: MyStruct
type: struct
fileds:
  - name: MyRef
    reference:
      pointeeType: model::Type
      rootType: model::Binary
```

This gets translated in C++ as a `TupleTreeReference<model::Type, model::Binary>`.

#### Upcastable structs

It is possible to define polymorphic classes. To do so, first define a common base class (like `Type`).
This class can be marked with the attribute `abstract` if it should not be instantiated on its own.

Example (`Type.h`):

```YAML
name: Type
type: struct
fields:
  - name: Kind
    type: model::TypeKind::Values
  ...
key: [...]
abstract: true
```

Then, define the derived classes adding the `inherits: <ParentClass>` property (example from `StructType.h`):

```YAML
name: StructType
type: struct
inherits: Type
fields: [...]
```

Derived classes inherit the fields of their parent, so they must not be duplicated.

All classes that are part of a polymorphic hierarchy are expected to supply two `classof` methods:

```cpp
// Don't inherit from model::Type or model::generated::Type!
class model::StructType : public model::generated::StructType {
public:
  using model::generated::StructType::StructType;

  // ...

public:
  static bool classof(const Type *T) { return classof(T->key()); }
  static bool classof(const Key &K) { return std::get<0>(K) == AssociatedKind; }
};
```

The `classof` methods should return true if the object they receive (an instance of the polymorphic object or of the
object key) can be identified as an object of the current class.