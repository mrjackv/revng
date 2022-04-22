#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "revng/Pipeline/Pipe.h"

namespace pipeline {

class Analysis {
private:
  PipeWrapper Pipe;
  std::string Name;

public:
  const std::string &getName() const { return Name; }
  const PipeWrapper &getPipe() const { return Pipe; }

  PipeWrapper &getPipe() { return Pipe; }

  Analysis(PipeWrapper Pipe, std::string Name) :
    Pipe(std::move(Pipe)), Name(std::move(Name)) {}
};
} // namespace pipeline
