/* The extended Kalman filter of the 2RC model, state x = [SoC, V1, V2], input I, measurement V.
 *
 * The C port of python/ekfsoc/ekf.py and of find_cell / interp2 in python/ekfsoc/model.py, function
 * for function and with the same operation order. Equation numbers ("Eq. n") are those of
 * docs/model.md. One filter is one ekf_t, so one controller can run one filter per cell; the
 * library allocates nothing and keeps no state of its own.
 */
#ifndef EKF_H
#define EKF_H

#include "ekf_params.h"
#include "ekf_types.h"

typedef enum {
    EKF_OK = 0,
    EKF_ERR_NONFINITE_INPUT, /* an input is NaN or infinite; the state is left unchanged */
    EKF_ERR_DT_NEGATIVE,     /* dt_s < 0; the state is left unchanged (dt_s = 0 is allowed) */
    EKF_WARN_TEMP_CLAMPED,   /* the step ran, but t_degc is outside the table axis and was clamped (Eq. 4) */
    EKF_ERR_NULL             /* a required pointer is NULL */
} ekf_status_t;

/* The noise settings of the filter (as EkfConfig in Python) and the model tables it reads.
 *
 * q_soc       process noise of the SoC state in 1/s (Q[0][0] = q_soc * dt)
 * q_v         process noise of V1 and V2 in V^2/s (Q[1][1] = Q[2][2] = q_v * dt)
 * r           measurement noise variance in V^2
 * p0_soc_std  initial standard deviation of the SoC state (0.2 = 20 pp)
 * p0_v_std    initial standard deviation of V1 and V2 in V
 */
typedef struct {
    ekf_real_t q_soc, q_v, r, p0_soc_std, p0_v_std;
    const ekf_params_t *params;
} ekf_cfg_t;

/* One filter. x and P are the posterior after the last step; i_held is the last sample's current,
 * held over the next step (docs/model.md C11); y_hat is the voltage predicted before the last
 * measurement was used (Eq. 8), NaN before the first step. */
typedef struct {
    ekf_real_t x[3];
    ekf_real_t P[3][3];
    ekf_real_t i_held;
    ekf_real_t y_hat;
    const ekf_cfg_t *cfg;
} ekf_t;

/* Start a filter at x = [soc0, 0, 0] with P = diag(p0_soc_std^2, p0_v_std^2, p0_v_std^2). */
ekf_status_t ekf_init(ekf_t *e, const ekf_cfg_t *cfg, ekf_real_t soc0);

/* Process one sample: predict over dt_s with the held current (skipped when dt_s = 0), update with
 * i_a and v_v, then hold i_a. Currents in A (positive on discharge), voltage in V, temperature in
 * degC, dt_s in s. The first sample of a run has dt_s = 0. */
ekf_status_t ekf_step(ekf_t *e, ekf_real_t i_a, ekf_real_t v_v, ekf_real_t t_degc, ekf_real_t dt_s);

/* The posterior SoC as a fraction. */
ekf_real_t ekf_get_soc(const ekf_t *e);

/* The parts of ekf_step, exposed for the unit tests. */

/* Read a row-major table [n_t][n_soc] at (t, soc) with the clamped bilinear rule (Eq. 4). */
ekf_real_t ekf_interp2(const ekf_real_t *table, const ekf_real_t *t_grid, int n_t,
                       const ekf_real_t *soc_grid, int n_soc, ekf_real_t t, ekf_real_t soc);

/* Move x and P over dt_s with i_held held over the step (Eq. 6, Eq. 7). */
void ekf_predict(ekf_t *e, ekf_real_t i_held, ekf_real_t t_degc, ekf_real_t dt_s);

/* Correct x and P with v_v measured at i_a (Eq. 8 to Eq. 11, then the SoC limit of Eq. 10). */
void ekf_update(ekf_t *e, ekf_real_t i_a, ekf_real_t v_v, ekf_real_t t_degc);

/* Move x onto the nearer SoC bound along P[:, 0] when its SoC is outside [0, 1] (Eq. 10). */
void ekf_limit_soc(ekf_t *e);

#endif /* EKF_H */
