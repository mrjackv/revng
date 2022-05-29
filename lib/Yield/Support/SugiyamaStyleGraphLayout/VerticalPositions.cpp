/// \file VerticalPositions.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "Layout.h"

void setVerticalCoordinates(const LayerContainer &Layers,
                            const LaneContainer &Lanes,
                            float MarginSize,
                            float EdgeDistance) {
  float LastY = 0;
  for (size_t Index = 0; Index < Layers.size(); ++Index) {
    float MaxHeight = 0;
    for (auto Node : Layers[Index]) {
      auto NodeHeight = Node->size().H;
      if (MaxHeight < NodeHeight)
        MaxHeight = NodeHeight;
      Node->center().Y = LastY - Node->size().H / 2;
    }

    auto LaneCount = Index < Lanes.Horizontal.size() ?
                       Lanes.Horizontal.at(Index).size() :
                       0;
    LastY -= MaxHeight + EdgeDistance * LaneCount + MarginSize * 2;
  }
}
