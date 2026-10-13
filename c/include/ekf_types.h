/* The real type of the EKF library and the two macros that keep literals and exp in that type.
 *
 * ekf_real_t is float by default and double when EKF_USE_DOUBLE is defined. Every literal is
 * written EKF_R(0.5), which becomes 0.5f in the float build and 0.5 in the double build, and every
 * exponential is EKF_EXP, which is expf or exp, so neither build promotes to double by accident
 * (-Wdouble-promotion). The double build exists to compare with the Python reference almost exactly.
 */
#ifndef EKF_TYPES_H
#define EKF_TYPES_H

#include <math.h>

#ifdef EKF_USE_DOUBLE
typedef double ekf_real_t;
#define EKF_R(x) x
#define EKF_EXP(x) exp(x)
#else
typedef float ekf_real_t;
#define EKF_R(x) x##f
#define EKF_EXP(x) expf(x)
#endif

#endif /* EKF_TYPES_H */
