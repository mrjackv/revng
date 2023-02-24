#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

add_custom_command(
  OUTPUT "${CMAKE_BINARY_DIR}/lib/PipelineC/TracingWrapper.cpp"
         "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineC.cpp"
  COMMAND
    # cmake-format: off
    env PYTHONPATH="${CMAKE_SOURCE_DIR}/python"
    python -m revng.pipelinec_proto.add_tracing
    -p "${CMAKE_BINARY_DIR}/lib/PipelineC/pipelinec_proto.yml"
    -t "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineCTracing.cpp"
    -i "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineC.cpp"
    "${CMAKE_BINARY_DIR}/lib/PipelineC"
    # cmake-format: on
  DEPENDS
    "${CMAKE_BINARY_DIR}/lib/PipelineC/pipelinec_proto.yml"
    "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineCTracing.cpp"
    "${CMAKE_SOURCE_DIR}/lib/PipelineC/PipelineC.cpp"
    "${CMAKE_SOURCE_DIR}/python/revng/pipelinec_proto/add_tracing.py"
    "${CMAKE_SOURCE_DIR}/python/revng/pipelinec_proto/tracing_wrapper.cpp.j2")

add_custom_command(
  OUTPUT "${CMAKE_BINARY_DIR}/lib/PipelineC/pipelinec_proto.yml"
  COMMAND
    # cmake-format: off
    env PYTHONPATH="${CMAKE_SOURCE_DIR}/python"
    python -m revng.pipelinec_proto.parse
    -i "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/ForwardDeclarationsC.h"
    -i "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/Prototypes.h"
    "${CMAKE_BINARY_DIR}/lib/PipelineC/pipelinec_proto.yml"
    # cmake-format: on
  DEPENDS "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/ForwardDeclarationsC.h"
          "${CMAKE_SOURCE_DIR}/include/revng/PipelineC/Prototypes.h")

install(FILES "${CMAKE_BINARY_DIR}/lib/PipelineC/pipelinec_proto.yml"
        DESTINATION "${CMAKE_INSTALL_PREFIX}/share/revng")

revng_add_library_internal(
  revngPipelineC SHARED "${CMAKE_BINARY_DIR}/lib/PipelineC/TracingWrapper.cpp"
  "${CMAKE_BINARY_DIR}/lib/PipelineC/PipelineC.cpp")

target_link_libraries(revngPipelineC revngPipes ${LLVM_LIBRARIES})
