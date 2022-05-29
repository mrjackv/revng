/// \file HTML.cpp
/// \brief

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/Support/FormatVariadic.h"

#include "revng/Model/Binary.h"
#include "revng/Yield/ControlFlow/FallthroughDetection.h"
#include "revng/Yield/HTML.h"
#include "revng/Yield/Internal/Function.h"

namespace tags {

static constexpr auto Function = "function";
static constexpr auto BasicBlock = "basic-block";
static constexpr auto FunctionLabel = "function-label";
static constexpr auto BasicBlockLabel = "basic-block-label";

static constexpr auto Instruction = "instruction";
static constexpr auto InstructionAddress = "instruction-address";
static constexpr auto InstructionBytes = "instruction-bytes";

static constexpr auto InstructionMnemonic = "mnemonic";
static constexpr auto InstructionMnemonicPrefix = "mnemonic-prefix";
static constexpr auto InstructionMnemonicSuffix = "mnemonic-suffix";
static constexpr auto InstructionOpcode = "instruction-opcode";

static constexpr auto Comment = "comment";
static constexpr auto Error = "error";
static constexpr auto ImmediateValue = "immediate-value";
static constexpr auto MemoryOperand = "memory-operand";
static constexpr auto Register = "register";

static constexpr auto CommentIndicator = "comment-indicator";
static constexpr auto LabelIndicator = "label-indicator";

static constexpr auto FunctionLink = "function-link";
static constexpr auto BasicBlockLink = "basic-block-link";
static constexpr auto InstructionLink = "instruction-link";

static constexpr auto BasicBlockOwner = "basic-block-owner";

static constexpr auto InstructionTarget = "instruction-target";
static constexpr auto InstructionTargets = "instruction-targets";

static constexpr auto Whitespace = "whitespace";
static constexpr auto Untagged = "untagged";

} // namespace tags

namespace templates {

static constexpr auto BlockDiv = R"(<div class="{0}" id="{1}">{2}</div>)";
static constexpr auto SimpleDiv = R"(<div class="{0}">{1}</div>)";

static constexpr auto Link = R"(<a class="{0}" href="{1}">{2}</a>)";
static constexpr auto Span = R"(<span class="{0}">{1}</span>)";

} // namespace templates

static std::string linkAddress(const MetaAddress &Address) {
  std::string Result = Address.toString();

  constexpr std::array ForbiddenCharacters = { ' ', ':', '!', '#',  '?',
                                               '<', '>', '/', '\\', '{',
                                               '}', '[', ']' };

  for (char &Character : Result)
    if (llvm::find(ForbiddenCharacters, Character) != ForbiddenCharacters.end())
      Character = '_';

  return Result;
}

static std::string basicBlockID(const MetaAddress &Address) {
  return "basic_block_at_" + linkAddress(Address);
}

static std::string instructionID(const MetaAddress &Address) {
  return "instruction_at_" + linkAddress(Address);
}

static std::string link(const MetaAddress &Target,
                        const yield::Function &Function,
                        const model::Binary &Binary,
                        llvm::StringRef CustomName = "") {
  if (auto Iterator = Binary.Functions.find(Target);
      Iterator != Binary.Functions.end()) {
    // The target is a function
    std::string FinalName = CustomName.str();
    if (FinalName.empty())
      FinalName = Iterator->name().str().str();
    return llvm::formatv(templates::Link,
                         tags::FunctionLink,
                         linkAddress(Target) + ".html#" + basicBlockID(Target),
                         std::move(FinalName));
  } else if (auto Iterator = Function.BasicBlocks.find(Target);
             Iterator != Function.BasicBlocks.end()) {
    // The target is a basic block
    std::string FinalName = CustomName.str();
    if (FinalName.empty()) {
      auto FunctionIterator = Binary.Functions.find(Function.Address);
      revng_assert(FunctionIterator != Binary.Functions.end());

      std::string FunctionPrefix = FunctionIterator->name().str().str() + "_";
      std::string BlockOwnerName = llvm::formatv(templates::Span,
                                                 tags::BasicBlockOwner,
                                                 std::move(FunctionPrefix));

      std::string BlockName = "basic_block_at_" + linkAddress(Target);
      FinalName = std::move(BlockOwnerName) + std::move(BlockName);
    }
    return llvm::formatv(templates::Link,
                         tags::BasicBlockLink,
                         linkAddress(Function.Address) + ".html#"
                           + basicBlockID(Target),
                         std::move(FinalName));
  } else if (Target.isValid()) {
    // The target is an instruction
    std::string FinalName = CustomName.str();
    if (FinalName.empty())
      FinalName = Target.toString();
    return llvm::formatv(templates::Link,
                         tags::InstructionLink,
                         linkAddress(Function.Address) + ".html#"
                           + instructionID(Target),
                         std::move(FinalName));
  } else {
    // The target is impossible to deduce, it's an indirect call or the like.
    return "";
  }
}

static std::string commentIndicator(const yield::BasicBlock &BasicBlock) {
  return llvm::formatv(templates::Span,
                       tags::CommentIndicator,
                       BasicBlock.CommentIndicator);
}

static std::string labelIndicator(const yield::BasicBlock &BasicBlock) {
  return llvm::formatv(templates::Span,
                       tags::LabelIndicator,
                       BasicBlock.LabelIndicator);
}

static std::string label(const yield::BasicBlock &BasicBlock,
                         const yield::Function &Function,
                         const model::Binary &Binary) {
  std::string Link = link(BasicBlock.Address, Function, Binary);
  return llvm::formatv(templates::SimpleDiv,
                       Function.Address == BasicBlock.Address ?
                         tags::FunctionLabel :
                         tags::BasicBlockLabel,
                       std::move(Link += labelIndicator(BasicBlock)));
}

static std::string whitespace(size_t Count) {
  if (Count == 0)
    return "";

  std::string Result;
  for (size_t Counter = 0; Counter < Count; ++Counter)
    Result += "&nbsp;";
  return llvm::formatv(templates::Span, tags::Whitespace, std::move(Result));
}

static std::string newLine() {
  return llvm::formatv(templates::Span, tags::Whitespace, "<br />");
}

static std::string commentImpl(const char *Template,
                               llvm::StringRef Tag,
                               const yield::BasicBlock &BasicBlock,
                               std::string &&Body,
                               size_t Offset,
                               bool NeedsNewLine) {
  std::string Result = commentIndicator(BasicBlock) + whitespace(1)
                       + std::move(Body);
  Result = llvm::formatv(Template, Tag, std::move(Result));
  return (NeedsNewLine ? newLine() : "") + whitespace(Offset)
         + std::move(Result);
}

static std::string comment(const yield::BasicBlock &BasicBlock,
                           std::string &&Body,
                           size_t Offset = 0,
                           bool NeedsNewLine = false) {
  return commentImpl(templates::Span,
                     tags::Comment,
                     BasicBlock,
                     std::move(Body),
                     Offset,
                     NeedsNewLine);
}

static std::string error(const yield::BasicBlock &BasicBlock,
                         std::string &&Body,
                         size_t Offset = 0,
                         bool NeedsNewLine = false) {
  return commentImpl(templates::Span,
                     tags::Error,
                     BasicBlock,
                     std::move(Body),
                     Offset,
                     NeedsNewLine);
}

static std::string blockComment(llvm::StringRef Tag,
                                const yield::BasicBlock &BasicBlock,
                                std::string &&Body,
                                size_t Offset = 0,
                                bool NeedsNewLine = false) {
  return commentImpl(templates::SimpleDiv,
                     Tag,
                     BasicBlock,
                     std::move(Body),
                     Offset,
                     NeedsNewLine);
}

static std::string bytes(const yield::BasicBlock &BasicBlock,
                         const yield::ByteContainer &Bytes,
                         size_t Limit = std::numeric_limits<size_t>::max()) {
  std::string Result;
  llvm::raw_string_ostream FormattingStream(Result);

  bool NeedsSpace = false;
  for (const auto &Byte : llvm::ArrayRef<uint8_t>{ Bytes }.take_front(Limit)) {
    if (NeedsSpace)
      FormattingStream << "&nbsp;";
    else
      NeedsSpace = true;

    llvm::write_hex(FormattingStream, Byte, llvm::HexPrintStyle::Upper, 2);
  }

  if (Bytes.size() > Limit)
    FormattingStream << "&nbsp;[...]";

  FormattingStream.flush();
  return blockComment(tags::InstructionBytes, BasicBlock, std::move(Result));
}

static size_t countTargets(const SortedVector<MetaAddress> &Targets) {
  return Targets.size() - Targets.count(MetaAddress::invalid());
}

static bool areTargetsAdjacent(const MetaAddress &CurrentAddress,
                               const MetaAddress &TargetAddress,
                               const yield::Function &Function) {
  auto CurrentIterator = Function.BasicBlocks.find(CurrentAddress);
  if (CurrentIterator == Function.BasicBlocks.end())
    return false;

  return CurrentIterator->NextAddress == TargetAddress;
}

static std::string targetLink(const MetaAddress &Target,
                              const yield::BasicBlock &BasicBlock,
                              const yield::Function &Function,
                              const model::Binary &Binary) {
  if (areTargetsAdjacent(BasicBlock.Address, Target, Function))
    return llvm::formatv(templates::Span,
                         tags::InstructionTarget,
                         link(Target,
                              Function,
                              Binary,
                              "the next instruction"));
  else
    return llvm::formatv(templates::Span,
                         tags::InstructionTarget,
                         link(Target, Function, Binary));
}

static std::string targets(const yield::BasicBlock &BasicBlock,
                           const yield::Function &Function,
                           const model::Binary &Binary,
                           size_t TailOffset = 0) {
  size_t TargetCount = countTargets(BasicBlock.Targets);
  if (TargetCount == 0)
    return ""; // We know nothing about the targets.

  std::string Result;
  if (BasicBlock.Targets.size() == 1) {
    // There's only a single known target. This is probably a direct call.
    revng_assert(BasicBlock.Targets.begin()->isValid());
    Result += comment(BasicBlock,
                      "always goes to "
                        + targetLink(*BasicBlock.Targets.begin(),
                                     BasicBlock,
                                     Function,
                                     Binary));
  } else {
    Result += comment(BasicBlock, "known targets include: ");
    bool HasInvalidTargets = false;
    for (size_t Counter = 0; const auto &Destination : BasicBlock.Targets) {
      if (Destination.isValid()) {
        auto Link = targetLink(Destination, BasicBlock, Function, Binary);
        if (BasicBlock.Targets.size() == TargetCount
            && Counter != TargetCount - 1) {
          Link = std::move(Link) + ",";
        }
        ++Counter;

        Result += comment(BasicBlock, "- " + std::move(Link), TailOffset, true);
      } else {
        HasInvalidTargets = true;
      }
    }

    if (HasInvalidTargets)
      Result += comment(BasicBlock, "and more", TailOffset, true);
  }

  return llvm::formatv(templates::Span,
                       tags::InstructionTargets,
                       std::move(Result));
}

static std::string tagTypeAsString(yield::TagType::Values Type) {
  switch (Type) {
  case yield::TagType::Immediate:
    return tags::ImmediateValue;
  case yield::TagType::Memory:
    return tags::MemoryOperand;
  case yield::TagType::Mnemonic:
    return tags::InstructionMnemonic;
  case yield::TagType::MnemonicPrefix:
    return tags::InstructionMnemonicPrefix;
  case yield::TagType::MnemonicSuffix:
    return tags::InstructionMnemonicSuffix;
  case yield::TagType::Register:
    return tags::Register;
  case yield::TagType::Whitespace:
    return tags::Whitespace;
  case yield::TagType::Invalid:
  default:
    revng_abort("Unknown tag type");
  }
}

using LeafContainer = llvm::SmallVector<llvm::SmallVector<size_t, 4>, 16>;
static std::string tag(size_t Index,
                       const LeafContainer &Leaves,
                       const yield::Instruction &Instruction) {
  revng_assert(Index < Instruction.Tags.size());
  const yield::Tag &Tag = Instruction.Tags[Index];
  llvm::StringRef TextView = Instruction.Raw;

  revng_assert(Index < Leaves.size());
  const auto &AdjacentLeaves = Leaves[Index];

  std::string Result;
  size_t CurrentIndex = Tag.FromPosition;
  for (const auto &LeafIndex : llvm::reverse(AdjacentLeaves)) {
    revng_assert(LeafIndex < Instruction.Tags.size());
    const auto &LeafTag = Instruction.Tags[LeafIndex];

    revng_assert(CurrentIndex <= LeafTag.FromPosition);
    if (CurrentIndex < LeafTag.FromPosition)
      Result += TextView.slice(CurrentIndex, LeafTag.FromPosition);
    Result += tag(LeafIndex, Leaves, Instruction);
    CurrentIndex = LeafTag.ToPosition;
  }
  revng_assert(CurrentIndex <= Tag.ToPosition);
  if (CurrentIndex < Tag.ToPosition)
    Result += TextView.slice(CurrentIndex, Tag.ToPosition);

  std::string TagStr = tagTypeAsString(Tag.Type);

  if (Tag.Type != yield::TagType::Mnemonic)
    return llvm::formatv(templates::Span, std::move(TagStr), std::move(Result));
  else
    return llvm::formatv(templates::Link,
                         std::move(TagStr),
                         "#" + instructionID(Instruction.Address),
                         std::move(Result));
}

static std::string taggedText(const yield::Instruction &Instruction) {
  revng_assert(!Instruction.Tags.empty(),
               "Tagless instructions are not supported");

  // Convert the tag list into a tree to simplify working with nested tags.
  llvm::SmallVector<size_t> RootIndices;
  LeafContainer Leaves(Instruction.Tags.size());
  for (size_t Index = Instruction.Tags.size() - 1; Index > 0; --Index) {
    const auto &CurrentTag = Instruction.Tags[Index];

    bool DependencyDetected = false;
    for (size_t PrevIndex = Index - 1; PrevIndex != size_t(-1); --PrevIndex) {
      const auto &PreviousTag = Instruction.Tags[PrevIndex];
      if (CurrentTag.FromPosition >= PreviousTag.FromPosition
          && CurrentTag.ToPosition <= PreviousTag.ToPosition) {
        // Current tag is inside the previous one.
        // Add an edge corresponding to this relation.
        if (!DependencyDetected)
          Leaves[PrevIndex].emplace_back(Index);
        DependencyDetected = true;
      } else if (CurrentTag.FromPosition >= PreviousTag.ToPosition
                 && CurrentTag.ToPosition >= PreviousTag.ToPosition) {
        // Current tag is after (and outside) the previous one.
        // Do nothing.
      } else if (CurrentTag.FromPosition <= PreviousTag.FromPosition
                 && CurrentTag.ToPosition <= PreviousTag.FromPosition) {
        // Current tag is before (and outside) the previous one.
        revng_abort("Tag container must be sorted.");
      } else {
        revng_abort("Tags must not intersect");
      }
    }

    // The node is not depended on - add it as a root.
    if (!DependencyDetected)
      RootIndices.emplace_back(Index);
  }

  // Make sure there's at least one root.
  RootIndices.emplace_back(0);

  // Insert html-flavoured tags based on the tree.
  std::string Result;
  size_t CurrentIndex = 0;
  llvm::StringRef TextView = Instruction.Raw;
  for (size_t RootIndex : llvm::reverse(RootIndices)) {
    revng_assert(RootIndex < Instruction.Tags.size());
    const auto &RootTag = Instruction.Tags[RootIndex];

    if (CurrentIndex < RootTag.FromPosition)
      Result += llvm::formatv(templates::Span,
                              tags::Untagged,
                              TextView.slice(CurrentIndex,
                                             RootTag.FromPosition));
    Result += tag(RootIndex, Leaves, Instruction);
    CurrentIndex = RootTag.ToPosition;
  }
  revng_assert(CurrentIndex <= TextView.size());
  if (CurrentIndex < TextView.size())
    Result += llvm::formatv(templates::Span,
                            tags::Untagged,
                            TextView.substr(CurrentIndex));

  return Result;
}

static std::string instruction(const yield::Instruction &Instruction,
                               bool IsInDelayedSlot,
                               bool NeedsToPrintTargets,
                               bool ShouldUseVerticalLayout,
                               const yield::BasicBlock &BasicBlock,
                               const yield::Function &Function,
                               const model::Binary &Binary) {
  // MetaAddress of the instruction.
  std::string Result = blockComment(tags::InstructionAddress,
                                    BasicBlock,
                                    Instruction.Address.toString());

  // Raw bytes of the instruction.
  //
  // \note the instructions disassembler failed on are limited to 16 bytes.
  if (Instruction.Error == "MCDisassembler failed")
    Result += bytes(BasicBlock, Instruction.Bytes, 16);
  else
    Result += bytes(BasicBlock, Instruction.Bytes);

  // LLVM's Opcode of the instruction.
  if (!Instruction.Opcode.empty())
    Result += llvm::formatv(templates::Span,
                            tags::InstructionOpcode,
                            Instruction.Opcode);

  if (ShouldUseVerticalLayout == true && !Instruction.Error.empty())
    Result += error(BasicBlock, "Error: " + Instruction.Error);

  // Tagged instruction body.
  Result += taggedText(Instruction);
  size_t Tail = Instruction.Raw.size() + 1;

  // The original comment if present.
  bool HasTailComments = false;
  if (!Instruction.Comment.empty()) {
    Result += comment(BasicBlock, std::string(Instruction.Comment), 1);
    HasTailComments = true;
  }

  // Delayed slot notice if applicable.
  if (ShouldUseVerticalLayout == false && IsInDelayedSlot) {
    if (HasTailComments == true)
      Result += comment(BasicBlock, "delayed", Tail, true);
    else
      Result += comment(BasicBlock, "delayed", 1);
    HasTailComments = true;
  }

  // An error message if present.
  if (ShouldUseVerticalLayout == false && !Instruction.Error.empty()) {
    if (HasTailComments == true)
      Result += error(BasicBlock, "Error: " + Instruction.Error, Tail, true);
    else
      Result += error(BasicBlock, "Error: " + Instruction.Error, 1);
    HasTailComments = true;
  }

  // The list of targets if needed
  if (NeedsToPrintTargets) {
    if (HasTailComments == false) {
      Result += whitespace(1);
    } else if (countTargets(BasicBlock.Targets) != 0) {
      Result += newLine() + whitespace(Tail);
    }

    Result += targets(BasicBlock, Function, Binary, Tail);
  }

  return llvm::formatv(templates::BlockDiv,
                       tags::Instruction,
                       instructionID(Instruction.Address),
                       std::move(Result));
}

template<bool ShouldMergeFallthroughTargets, bool UseVerticalTargetLayout>
static std::string basicBlock(const yield::BasicBlock &BasicBlock,
                              const yield::Function &Function,
                              const model::Binary &Binary) {
  // Blocks are strung together if there's no reason to keep them separate.
  // This determines whether this is the last block in the current string
  // (if `NextBlock` is `nullptr`) or if there's continuation.
  constexpr bool MergeFallthrough = ShouldMergeFallthroughTargets;
  auto NextBlock = yield::cfg::detectFallthrough<MergeFallthrough>(BasicBlock,
                                                                   Function,
                                                                   Binary);

  // Compile the list of delayed instructions so the corresponding comment
  // can be emited.
  llvm::SmallVector<MetaAddress, 2> DelayedList;
  bool IsNextInstructionDelayed = false;
  for (const auto &Instruction : BasicBlock.Instructions) {
    if (IsNextInstructionDelayed)
      DelayedList.emplace_back(Instruction.Address);
    IsNextInstructionDelayed = Instruction.HasDelayedSlot;
  }

  // Determine the last "proper" instruction. This is the instruction "targets"
  // get printed for if this is the last basic block in a string.
  MetaAddress LastNotDelayedInstruction = MetaAddress::invalid();
  for (const auto &Instruction : llvm::reverse(BasicBlock.Instructions)) {
    if (!llvm::is_contained(DelayedList, Instruction.Address)) {
      LastNotDelayedInstruction = Instruction.Address;
      break;
    }
  }
  revng_assert(LastNotDelayedInstruction.isValid());

  // String the results together.
  std::string Result;
  for (const auto &Instruction : BasicBlock.Instructions) {
    bool PrintTargets = LastNotDelayedInstruction == Instruction.Address;
    PrintTargets = PrintTargets && !UseVerticalTargetLayout;
    if (NextBlock != nullptr)
      PrintTargets = PrintTargets && countTargets(BasicBlock.Targets) > 1;

    Result += instruction(Instruction,
                          llvm::is_contained(DelayedList, Instruction.Address),
                          PrintTargets,
                          UseVerticalTargetLayout,
                          BasicBlock,
                          Function,
                          Binary);
  }

  if (IsNextInstructionDelayed == true) {
    std::string DelayedError = "Error: Last instruction has a delayed slot.";
    Result += error(BasicBlock, std::move(DelayedError), 2, true);
  }

  if (NextBlock != nullptr) {
    return Result += basicBlock<ShouldMergeFallthroughTargets,
                                UseVerticalTargetLayout>(*NextBlock,
                                                         Function,
                                                         Binary);
  } else {
    if constexpr (UseVerticalTargetLayout == true) {
      auto Targets = targets(BasicBlock, Function, Binary);
      if (!Targets.empty())
        Result += newLine() + std::move(Targets);
    }

    return Result;
  }
}

template<bool ShouldMergeFallthroughTargets, bool UseVerticalTargetLayout>
static std::string basicBlockString(const yield::BasicBlock &BasicBlock,
                                    const yield::Function &Function,
                                    const model::Binary &Binary) {
  // Blocks that are merged into other block strings cannot start a new one.
  using namespace yield::BasicBlockType;
  if (shouldSkip<ShouldMergeFallthroughTargets>(BasicBlock.Type))
    return "";

  std::string Result;
  Result += label(BasicBlock, Function, Binary);
  Result += basicBlock<ShouldMergeFallthroughTargets,
                       UseVerticalTargetLayout>(BasicBlock, Function, Binary);

  return llvm::formatv(templates::BlockDiv,
                       tags::BasicBlock,
                       basicBlockID(BasicBlock.Address),
                       std::move(Result));
}

std::string yield::html::functionAssembly(const yield::Function &Function,
                                          const model::Binary &Binary) {
  std::string Result;

  for (const auto &BasicBlock : Function.BasicBlocks)
    Result += basicBlockString<true, false>(BasicBlock, Function, Binary);

  return Result;
}

std::string yield::html::controlFlowNode(const MetaAddress &Address,
                                         const yield::Function &Function,
                                         const model::Binary &Binary) {
  if (auto Iterator = Function.BasicBlocks.find(Address);
      Iterator != Function.BasicBlocks.end()) {
    auto Result = basicBlockString<false, true>(*Iterator, Function, Binary);
    revng_assert(!Result.empty());

    return Result;
  } else {
    revng_assert(Binary.Functions.find(Address) != Binary.Functions.end());
    return link(Address, Function, Binary);
  }
}
