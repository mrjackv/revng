#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

add_custom_command(
  OUTPUT "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineCTracing.cpp"
         "${CMAKE_BINARY_DIR}/lib/PipelineC/TracingPrototypes.h"
         "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineC.cpp"
  COMMAND
    # cmake-format: off
    python "${CMAKE_SOURCE_DIR}/lib/PipelineC/wrap.py"
    -i "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/ForwardDeclarationsC.h"
    -i "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/Prototypes.h"
    -t "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineCTracing.cpp"
    -m "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineC.cpp"
    "${CMAKE_BINARY_DIR}/lib/PipelineC"
    # cmake-format: on
  DEPENDS "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineCTracing.cpp"
          "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineC.cpp"
          "${CMAKE_SOURCE_DIR}/lib/PipelineC/wrap.py"
          "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/ForwardDeclarationsC.h"
          "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/Prototypes.h")

revng_add_library_internal(
  revngPipelineC SHARED
  "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineCTracing.cpp"
  "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineC.cpp")

target_link_libraries(revngPipelineC revngPipes ${LLVM_LIBRARIES})
