# Cross toolchain for the footprint build (the spec, S3): Cortex-M4 with the single-precision FPU, hard float.
# Only the ekf library is built; nothing is linked, so no startup code, linker script or C library is needed.
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_C_FLAGS_INIT "-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -O2")
