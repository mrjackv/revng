/// \file GlobalsMap.cpp
/// \brief GlobalsMap methods implementations

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <filesystem>
#include <system_error>

#include "llvm/ADT/StringRef.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

#include "revng/Pipeline/GlobalsMap.h"

using namespace std;
using namespace pipeline;
using namespace llvm;

llvm::Error GlobalsMap::storeToDisk(llvm::StringRef Path) const {
  for (const auto &Global : Map) {
    std::filesystem::path Root(Path.str());
    std::filesystem::path ContextDir = Root / "context";
    if (auto EC = llvm::sys::fs::create_directories(std::string(ContextDir));
        EC)
      return llvm::createStringError(EC,
                                     "Could not create dir %s",
                                     ContextDir.c_str());
    auto FilePath = Root / "context" / Global.first().str();
    if (auto E = Global.second->storeToDisk(std::string(FilePath)); !!E)
      return E;
  }
  return llvm::Error::success();
}

llvm::Error GlobalsMap::loadFromDisk(llvm::StringRef Path) {
  for (const auto &Global : Map) {
    std::filesystem::path Root(Path.str());
    auto FilePath = Root / "context" / Global.first().str();
    if (auto E = Global.second->loadFromDisk(std::string(FilePath)); !!E)
      return E;
  }
  return llvm::Error::success();
}
