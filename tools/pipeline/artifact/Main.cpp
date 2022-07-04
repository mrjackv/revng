// \file Main.cpp

//
// This file is distributed under the MIT License. See LICENSE.md for details.
//

#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/DynamicLibrary.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/PluginLoader.h"
#include "llvm/Support/raw_os_ostream.h"

#include "revng/Model/LoadModelPass.h"
#include "revng/Pipeline/AllRegistries.h"
#include "revng/Pipeline/ContainerSet.h"
#include "revng/Pipeline/CopyPipe.h"
#include "revng/Pipeline/GenericLLVMPipe.h"
#include "revng/Pipeline/LLVMContainerFactory.h"
#include "revng/Pipeline/LLVMGlobalKindBase.h"
#include "revng/Pipeline/Loader.h"
#include "revng/Pipeline/Target.h"
#include "revng/Pipes/ModelGlobal.h"
#include "revng/Pipes/PipelineManager.h"

using std::string;
using namespace llvm;
using namespace llvm::cl;
using namespace pipeline;
using namespace ::revng::pipes;

cl::OptionCategory PipelineCategory("revng-pipeline options", "");

static cl::list<string>
  InputPipeline("P", desc("<Pipeline>"), cat(PipelineCategory));

static cl::list<string> Arguments(Positional,
                                  ZeroOrMore,
                                  desc("<ArtifactToProduce> <InputBinary>"),
                                  cat(PipelineCategory));

static opt<string> ModelOverride("m",
                                 desc("Load the model from a provided file"),
                                 cat(PipelineCategory),
                                 init(""));

static opt<string> Output("o",
                          desc("Output filepath of produced artifact"),
                          cat(PipelineCategory),
                          init("-"));

static opt<string> SaveModel("save-model",
                             desc("Save the model at the end of the run"),
                             cat(PipelineCategory),
                             init(""));

static opt<bool> ListArtifacts("list",
                               desc("list all possible targets of artifact and "
                                    "exit"),
                               cat(PipelineCategory),
                               init(false));

static opt<bool> AnalyzeAll("analyze-all",
                            desc("Try analyzing all possible "
                                 "targets"),
                            cat(PipelineCategory),
                            init(false));

static cl::list<string> EnablingFlags("f",
                                      desc("list of pipeline enabling flags"),
                                      cat(PipelineCategory));

static opt<string> ExecutionDirectory("p",
                                      desc("Directory from which all "
                                           "containers will "
                                           "be loaded before everything else "
                                           "and "
                                           "to which it will be store after "
                                           "everything else"),
                                      cat(PipelineCategory));

static alias
  A1("l", desc("Alias for --load"), aliasopt(LoadOpt), cat(PipelineCategory));

static ExitOnError AbortOnError;

static auto makeManager() {
  return PipelineManager::create(InputPipeline,
                                 EnablingFlags,
                                 ExecutionDirectory);
}

int main(int argc, const char *argv[]) {
  HideUnrelatedOptions(PipelineCategory);
  ParseCommandLineOptions(argc, argv);

  Registry::runAllInitializationRoutines();

  auto Manager = AbortOnError(makeManager());

  if (not ModelOverride.empty())
    AbortOnError(Manager.overrideModel(ModelOverride));

  if (Arguments.size() == 0) {
    for (const auto &Step : Manager.getRunner())
      if (Step.getArtifactsKind() != nullptr)
        dbg << Step.getName().str() << "\n";
    return EXIT_SUCCESS;
  }

  if (Arguments.size() == 1) {
    AbortOnError(createStringError(inconvertibleErrorCode(),
                                   "expected any number of positional "
                                   "arguments different from 1"));
  }

  auto &InputContainer = Manager.getRunner().begin()->containers()["input"];
  AbortOnError(InputContainer.loadFromDisk(Arguments[1]));

  if (AnalyzeAll)
    AbortOnError(Manager.getRunner().runAllAnalyses());

  if (not Manager.getRunner().containsStep(Arguments[0])) {
    AbortOnError(createStringError(inconvertibleErrorCode(),
                                   "no known artifact named %s, invoke this "
                                   "command without arguments to see the list "
                                   "of aviable artifacts",
                                   Arguments[0].c_str()));
  }
  auto &Step = Manager.getRunner().getStep(Arguments[0]);
  auto &Container = *Step.getArtifactsContainer();
  auto ContainerName = Container.first();
  auto *Kind = Step.getArtifactsKind();

  if (ListArtifacts) {
    Manager.recalculateAllPossibleTargets();
    auto &StepState = *Manager.getLastState().find(Step.getName());
    auto State = StepState.second.find(ContainerName)->second.filter(*Kind);
    TargetsList ToDump;
    for (const auto &Entry : State) {
      Entry.expand(Manager.context(), ToDump);
    }

    for (const auto &Entry : ToDump) {
      Entry.dumpPathComponents(dbg);
      dbg << "\n";
    }
    return EXIT_SUCCESS;
  }

  ContainerToTargetsMap Map;
  if (Arguments.size() == 2) {
    Map.add(ContainerName, Target(*Kind));
  } else {
    for (llvm::StringRef Argument : llvm::drop_begin(Arguments, 2)) {
      auto SlashRemoved = Argument.drop_front();
      llvm::SmallVector<StringRef, 2> Components;
      SlashRemoved.split(Components, "/");
      Map.add(ContainerName, Target(Components, *Kind));
    }
  }
  AbortOnError(Manager.getRunner().run(Step.getName(), Map));

  AbortOnError(Manager.storeToDisk());

  auto Produced = Container.second->cloneFiltered(Map.at(ContainerName));
  AbortOnError(Produced->storeToDisk(Output));

  if (not SaveModel.empty()) {
    auto Context = Manager.context();
    const auto &ModelName = ModelGlobalName;
    auto FinalModel = AbortOnError(Context.getGlobal<ModelGlobal>(ModelName));
    AbortOnError(FinalModel->storeToDisk(SaveModel));
  }

  return EXIT_SUCCESS;
}
