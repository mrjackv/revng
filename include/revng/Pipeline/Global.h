#pragma once
//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <any>
#include <memory>
#include <type_traits>

#include "llvm/ADT/StringRef.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/raw_ostream.h"

#include "revng/Pipeline/AnyDiff.h"
#include "revng/Support/YAMLTraits.h"
#include "revng/TupleTree/TupleTreeDiff.h"

namespace pipeline {

class Global {
private:
  const char *ID;

public:
  Global(const char *ID) : ID(ID) {}

  virtual ~Global() {}

public:
  const char *getID() const { return ID; }

public:
  virtual AnyDiff diff(const Global &Other) const = 0;

  virtual llvm::Error applyDiff(const llvm::MemoryBuffer &Diff) = 0;
  virtual llvm::Error serialize(llvm::raw_ostream &OS) const = 0;
  virtual llvm::Error deserialize(const llvm::MemoryBuffer &Buffer) = 0;
  virtual void clear() = 0;
  virtual std::unique_ptr<Global> clone() const = 0;
  virtual llvm::Error storeToDisk(llvm::StringRef Path) const;
  virtual llvm::Error loadFromDisk(llvm::StringRef Path);
};

template<TupleTreeCompatible Object>
class TupleTreeGlobal : public Global {
private:
  TupleTree<Object> Value;

  static const char &getID() {
    static char ID;
    return ID;
  }

public:
  explicit TupleTreeGlobal(TupleTree<Object> Value) :
    Global(&getID()), Value(std::move(Value)) {}

  TupleTreeGlobal() : Global(&getID()) {}
  virtual ~TupleTreeGlobal() override = default;

  static bool classof(const Global *T) { return T->getID() == &getID(); }

public:
  std::unique_ptr<Global> clone() const override {
    auto Ptr = new TupleTreeGlobal(Value.clone());
    return std::unique_ptr<Global>(Ptr);
  }

  void clear() override { *Value = Object(); }

  llvm::Error serialize(llvm::raw_ostream &OS) const override {
    Value.serialize(OS);
    return llvm::Error::success();
  }

  llvm::Error deserialize(const llvm::MemoryBuffer &Buffer) override {
    auto MaybeDiff = TupleTree<Object>::deserialize(Buffer.getBuffer());
    if (!MaybeDiff)
      return llvm::errorCodeToError(MaybeDiff.getError());

    Value = std::move(*MaybeDiff);
    return llvm::Error::success();
  }

  AnyDiff diff(const Global &Other) const override {
    const TupleTreeGlobal &Casted = llvm::cast<TupleTreeGlobal>(Other);
    auto Diff = ::diff(*Value, *Casted.Value);
    return AnyDiff(std::move(Diff));
  }

  llvm::Error applyDiff(const llvm::MemoryBuffer &Diff) override {
    auto MaybeDiff = ::deserialize<TupleTreeDiff<Object>>(Diff.getBuffer());
    if (not MaybeDiff)
      return MaybeDiff.takeError();
    MaybeDiff->apply(Value);
    return llvm::Error::success();
  }

  const TupleTree<Object> &get() const { return Value; }
  TupleTree<Object> &get() { return Value; }
};

class GlobalsMap {
private:
  using MapType = llvm::StringMap<std::unique_ptr<Global>>;
  MapType Map;

public:
  DiffMap diff(const GlobalsMap &Other) const {
    llvm::StringMap<AnyDiff> ToReturn;

    for (const auto &Pair : Map) {
      const auto &OtherPair = *Other.Map.find(Pair.first());

      auto Diff = Pair.second->diff(*OtherPair.second);
      ToReturn.try_emplace(Pair.first(), std::move(Diff));
    }

    return ToReturn;
  }

  template<typename ToAdd, typename... T>
  void emplace(llvm::StringRef Name, T &&...Args) {
    Map.try_emplace(Name, std::make_unique<ToAdd>(std::forward<T>(Args)...));
  }

  template<typename T>
  llvm::Expected<T *> get(llvm::StringRef Name) const {
    auto Iter = Map.find(Name);
    if (Iter == Map.end()) {
      auto *Message = "could not find %s";
      return llvm::createStringError(llvm::inconvertibleErrorCode(),
                                     Message,
                                     Name.str().c_str());
    }

    auto *Casted = llvm::dyn_cast<T>(Iter->second.get());
    if (Casted == nullptr) {
      auto *Message = "requested to cast %s to the wrong type";
      return llvm::createStringError(llvm::inconvertibleErrorCode(),
                                     Message,
                                     Name.str().c_str());
    }

    return Casted;
  }

  llvm::StringRef getName(size_t Index) const {
    return std::next(Map.begin(), Index)->first();
  }

  llvm::Error
  serialize(llvm::StringRef GlobalName, llvm::raw_ostream &OS) const {
    auto Iter = Map.find(GlobalName);
    if (Iter == Map.end()) {
      auto *Message = "pipeline loader context did not contained object %s";
      return llvm::createStringError(llvm::inconvertibleErrorCode(),
                                     Message,
                                     GlobalName.str().c_str());
    }

    return Iter->second->serialize(OS);
  }

  llvm::Error
  deserialize(llvm::StringRef GlobalName, const llvm::MemoryBuffer &Buffer) {
    auto Iter = Map.find(GlobalName);
    if (Iter == Map.end()) {
      auto *Message = "pipeline loader context did not contained object %s";
      return llvm::createStringError(llvm::inconvertibleErrorCode(),
                                     Message,
                                     GlobalName.str().c_str());
    }

    return Iter->second->deserialize(Buffer);
  }

  llvm::Error storeToDisk(llvm::StringRef Path) const;
  llvm::Error loadFromDisk(llvm::StringRef Path);

  size_t size() const { return Map.size(); }

public:
  GlobalsMap() = default;
  ~GlobalsMap() = default;
  GlobalsMap(GlobalsMap &&Other) = default;
  GlobalsMap(const GlobalsMap &Other) {
    for (const auto &Entry : Other.Map)
      Map.try_emplace(Entry.first(), Entry.second->clone());
  }

  GlobalsMap &operator=(GlobalsMap &&Other) = default;
  GlobalsMap &operator=(const GlobalsMap &Other) {
    if (this == &Other)
      return *this;

    Map = MapType();

    for (const auto &Entry : Other.Map)
      Map.try_emplace(Entry.first(), Entry.second->clone());

    return *this;
  }
};

} // namespace pipeline
