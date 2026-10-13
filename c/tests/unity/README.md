# Unity (vendored)

Unity v2.6.0, the C unit-test framework by ThrowTheSwitch: https://github.com/ThrowTheSwitch/Unity,
release tag `v2.6.0` (https://github.com/ThrowTheSwitch/Unity/archive/refs/tags/v2.6.0.tar.gz).

Files copied unchanged from that release: `src/unity.c`, `src/unity.h`, `src/unity_internals.h`
and `LICENSE.txt` (MIT, see that file). `c/CMakeLists.txt` builds them into `ekf_tests` with
`UNITY_INCLUDE_DOUBLE`, without `-Werror -Wpedantic`.
