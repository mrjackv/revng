/// \file Global.cpp
/// \brief a savable object is a objecet that an be serialized and deserialized
/// froms a string

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <system_error>

#include "llvm/ADT/StringRef.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

#include "revng/Pipeline/Global.h"

using namespace std;
using namespace pipeline;
using namespace llvm;

Error Global::storeToDisk(StringRef Path) const {
  std::error_code EC;
  raw_fd_ostream OS(Path, EC, llvm::sys::fs::F_None);
  if (EC)
    return createStringError(EC,
                             "could not write file at %s",
                             Path.str().c_str());

  return serialize(OS);
}

Error Global::loadFromDisk(StringRef Path) {
  if (not llvm::sys::fs::exists(Path)) {
    clear();
    return llvm::Error::success();
  }

  if (auto MaybeBuffer = MemoryBuffer::getFile(Path); !MaybeBuffer)
    return llvm::createStringError(MaybeBuffer.getError(),
                                   "could not read file at %s",
                                   Path.str().c_str());
  else
    return deserialize(**MaybeBuffer);
}

llvm::Error GlobalsMap::storeToDisk(llvm::StringRef Path) const {
  for (const auto &Global : Map)
    if (auto E = Global.second->storeToDisk(Path.str() + "/"
                                            + Global.first().str());
        !!E)
      return E;
  return llvm::Error::success();
}

llvm::Error GlobalsMap::loadFromDisk(llvm::StringRef Path) {
  for (const auto &Global : Map)
    if (auto E = Global.second->loadFromDisk(Path.str() + "/"
                                             + Global.first().str());
        !!E)
      return E;
  return llvm::Error::success();
}
