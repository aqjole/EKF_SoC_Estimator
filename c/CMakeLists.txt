cmake_minimum_required(VERSION 3.19)
project(ekf_soc C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(EKF_USE_3RCD0 "Build the adopted four-state 3RC-D0 model" OFF)
option(EKF_STACK_USAGE "Write compiler static stack-usage files" OFF)
option(EKF_USE_DOUBLE "ekf_real_t = double instead of float" OFF)
option(EKF_SANITIZE "Build host targets with AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

if(EKF_USE_DOUBLE)
  add_compile_definitions(EKF_USE_DOUBLE)
endif()
if(EKF_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()

if(EKF_USE_3RCD0)
  set(EKF_PARAMETER_SOURCE src/ekf_params_3rcd0.c)
else()
  set(EKF_PARAMETER_SOURCE src/ekf_params.c)
endif()
add_library(ekf STATIC src/ekf.c ${EKF_PARAMETER_SOURCE} src/ekf_size_marker.c)
if(EKF_USE_3RCD0)
  target_compile_definitions(ekf PUBLIC EKF_USE_3RCD0)
endif()
if(EKF_STACK_USAGE)
  target_compile_options(ekf PRIVATE -fstack-usage)
endif()
target_include_directories(ekf PUBLIC include)
target_compile_options(ekf PRIVATE -Wall -Wextra -Wpedantic -Werror -Wdouble-promotion)
target_link_libraries(ekf PUBLIC m)

# Host-only targets: the CSV tool and the fixture equivalence tests (never in the ARM build).
if(NOT CMAKE_CROSSCOMPILING)
  enable_testing()

  # Built without -Werror -Wpedantic (the spec, S3): it does file I/O and is not part of the library.
  add_executable(ekf_run_csv tools/ekf_run_csv.c)
  target_compile_options(ekf_run_csv PRIVATE -Wall -Wextra)
  target_link_libraries(ekf_run_csv PRIVATE ekf)

  if(NOT EKF_USE_3RCD0)
    # Fixture equivalence: max |SoC - soc_expected| below 0.1 pp (float) or 1e-3 pp (double), as fractions.
    # The noise settings are the frozen ones of results/ekf_config.json; soc0 = 1 for all three fixtures
    # (the reference SoC at their first row, c/tests/fixtures/README.md).
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    file(READ ${CMAKE_CURRENT_SOURCE_DIR}/../results/ekf_config.json EKF_CONFIG_JSON)
    string(JSON EKF_Q_SOC GET "${EKF_CONFIG_JSON}" q_soc)
    string(JSON EKF_Q_V GET "${EKF_CONFIG_JSON}" q_v)
    string(JSON EKF_R_MEAS GET "${EKF_CONFIG_JSON}" r)
    if(EKF_USE_DOUBLE)
      set(EKF_FIXTURE_MAX_ABS_SOC 1e-5)
    else()
      set(EKF_FIXTURE_MAX_ABS_SOC 1e-3)
    endif()
    foreach(fixture 25degC_551_US06 n20degC_610_US06 40degC_556_US06)
      add_test(NAME fixture_${fixture}
               COMMAND Python3::Interpreter ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_fixture.py
                       $<TARGET_FILE:ekf_run_csv> ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/${fixture}.csv
                       ${CMAKE_CURRENT_BINARY_DIR}/${fixture}_soc.csv ${EKF_FIXTURE_MAX_ABS_SOC}
                       ${EKF_Q_SOC} ${EKF_Q_V} ${EKF_R_MEAS} 1)
    endforeach()
  endif()

  # Unit tests on vendored Unity, built with the warnings but without -Werror -Wpedantic (the spec, S3).
  add_executable(ekf_tests tests/test_ekf.c tests/unity/unity.c)
  target_include_directories(ekf_tests PRIVATE tests/unity)
  target_compile_definitions(ekf_tests PRIVATE UNITY_INCLUDE_DOUBLE)
  target_compile_options(ekf_tests PRIVATE -Wall -Wextra)
  target_link_libraries(ekf_tests PRIVATE ekf)
  add_test(NAME ekf_tests COMMAND ekf_tests)
endif()
