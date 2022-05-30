#pragma once

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include <concepts>
#include <map>

#include "revng/ADT/Concepts.h"
#include "revng/ADT/GenericGraph.h"
#include "revng/EarlyFunctionAnalysis/FunctionMetadata.h"
#include "revng/Model/FunctionAttribute.h"

namespace efa {

namespace detail {
using SuccessorContainer = SortedVector<UpcastablePointer<FunctionEdgeBase>>;
}

template<typename T>
concept IsBasicBlock = requires {
  { T::Start } -> convertible_to<MetaAddress>;
  { T::End } -> convertible_to<MetaAddress>;
  { T::Successors } -> convertible_to<detail::SuccessorContainer>;
};

struct ParsedSuccessor {
  MetaAddress NextInstructionAddress;
  MetaAddress OptionalCallAddress;
};

inline ParsedSuccessor parseSuccessor(const efa::FunctionEdgeBase &Edge,
                                      const MetaAddress &FallthroughAddress,
                                      const model::Binary &Binary) {
  switch (Edge.Type) {
  case FunctionEdgeType::DirectBranch:
  case FunctionEdgeType::FakeFunctionCall:
  case FunctionEdgeType::FakeFunctionReturn:
  case FunctionEdgeType::Return:
  case FunctionEdgeType::BrokenReturn:
  case FunctionEdgeType::IndirectTailCall:
  case FunctionEdgeType::LongJmp:
  case FunctionEdgeType::Unreachable:
    return ParsedSuccessor{ .NextInstructionAddress = Edge.Destination,
                            .OptionalCallAddress = MetaAddress::invalid() };

  case FunctionEdgeType::FunctionCall:
  case FunctionEdgeType::IndirectCall:
    if (auto *CE = llvm::cast<efa::CallEdge>(&Edge);
        !hasAttribute(Binary, *CE, model::FunctionAttribute::NoReturn)) {
      return ParsedSuccessor{ .NextInstructionAddress = FallthroughAddress,
                              .OptionalCallAddress = Edge.Destination };
    } else {
      return ParsedSuccessor{ .NextInstructionAddress = MetaAddress::invalid(),
                              .OptionalCallAddress = Edge.Destination };
    }

  case FunctionEdgeType::Killer:
    return ParsedSuccessor{ .NextInstructionAddress = MetaAddress::invalid(),
                            .OptionalCallAddress = MetaAddress::invalid() };

  default:
  case FunctionEdgeType::Invalid:
  case FunctionEdgeType::Count:
    revng_abort();
    break;
  }
}

// clang-format off
template<IsGenericGraph GraphType,
         IsBasicBlock BasicBlockType,
         typename ...OtherTs,
         template<typename...> typename Container>
  requires std::is_constructible_v<typename GraphType::Node,
                                   const MetaAddress &>
std::pair<GraphType, std::map<MetaAddress, typename GraphType::Node *>>
buildControlFlowGraph(const Container<BasicBlockType, OtherTs...> &BasicBlocks,
                      const MetaAddress &EntryAddress,
                      const model::Binary &Binary) {
  // clang-format on
  std::pair<GraphType, std::map<MetaAddress, typename GraphType::Node *>> Res;

  auto &[Graph, AddressToNodeMap] = Res;
  for (const BasicBlockType &Block : BasicBlocks) {
    revng_assert(Block.Start.isValid());
    auto *Node = Graph.addNode(typename GraphType::Node{ Block.Start });
    auto [_, Success] = AddressToNodeMap.try_emplace(Block.Start, Node);
    revng_assert(Success != false,
                 "Different basic blocks with the same `Start` address");
  }

  constexpr auto Invalid = MetaAddress::invalid();
  auto *ExitNode = Graph.addNode(typename GraphType::Node{ Invalid });
  auto [_, Success] = AddressToNodeMap.try_emplace(MetaAddress::invalid(),
                                                   ExitNode);
  revng_assert(Success != false);

  for (const BasicBlockType &Block : BasicBlocks) {
    auto FromNodeIterator = AddressToNodeMap.find(Block.Start);
    revng_assert(FromNodeIterator != AddressToNodeMap.end());

    for (const auto &Edge : Block.Successors) {
      auto [NextInstruction, _] = parseSuccessor(*Edge, Block.End, Binary);
      if (NextInstruction.isValid()) {
        auto ToNodeIterator = AddressToNodeMap.find(NextInstruction);
        revng_assert(ToNodeIterator != AddressToNodeMap.end());
        FromNodeIterator->second->addSuccessor(ToNodeIterator->second);
      } else {
        FromNodeIterator->second->addSuccessor(ExitNode);
      }
    }
  }

  revng_assert(EntryAddress.isValid());
  auto EntryNodeIterator = AddressToNodeMap.find(EntryAddress);
  revng_assert(EntryNodeIterator != AddressToNodeMap.end());
  Graph.setEntryNode(EntryNodeIterator->second);

  return Res;
}

} // namespace efa
