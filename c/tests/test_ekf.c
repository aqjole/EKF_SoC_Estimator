/* Unit tests of the EKF library: Eq. 4 lookups, predict, update and the SoC limit against values the
 * Python filter computed (vectors/vectors.h), and the guards of ekf_step.
 *
 * Tolerances are relative to each expected value: 1e-12 in the double build, where C repeats the
 * Python operations; 1e-5 for states and 1e-4 for covariances in the float build, which adds only
 * float32 rounding.
 */
#include <math.h>
#include <string.h>

#include "ekf.h"
#include "unity.h"
#include "vectors/vectors.h"

#ifdef EKF_USE_DOUBLE
#define TOL_STATE 1e-12
#define TOL_COV 1e-12
#else
#define TOL_STATE 1e-5
#define TOL_COV 1e-4
#endif

/* A sample inside the tables: 2.5 A discharge, 3.78 V, 25 degC, 1 s step. */
#define I_A EKF_R(2.5)
#define V_V EKF_R(3.78)
#define T_DEGC EKF_R(25.0)
#define DT_S EKF_R(1.0)

static const ekf_cfg_t cfg = {VEC_Q_SOC, VEC_Q_V, VEC_R, EKF_R(0.2), EKF_R(0.05), &ekf_params_default};
static ekf_t ekf;

void setUp(void)
{
    ekf_init(&ekf, &cfg, EKF_R(0.62));
}

void tearDown(void)
{
}

static void assert_close(double expected, double actual, double rel_tol, int line)
{
    UNITY_TEST_ASSERT_DOUBLE_WITHIN(rel_tol * fabs(expected), expected, actual, line, NULL);
}

static void load_state(ekf_t *e, const vec_state_t *state)
{
    memcpy(e->x, state->x, sizeof e->x);
    memcpy(e->P, state->P, sizeof e->P);
}

static void assert_x(const ekf_real_t expected[3], const ekf_t *e, int line)
{
    int i;
    for (i = 0; i < 3; i++) {
        assert_close(expected[i], e->x[i], TOL_STATE, line);
    }
}

static void assert_P(const ekf_real_t expected[3][3], const ekf_t *e, int line)
{
    int i, j;
    for (i = 0; i < 3; i++) {
        for (j = 0; j < 3; j++) {
            assert_close(expected[i][j], e->P[i][j], TOL_COV, line);
        }
    }
}

static void assert_interp2(const vec_interp2_t *c, int line)
{
    ekf_real_t value = ekf_interp2(c->table, ekf_t_grid_degc, EKF_N_T, ekf_soc_grid, EKF_N_SOC,
                                   c->t_degc, c->soc);
    assert_close(c->expected, value, TOL_STATE, line);
}

static void test_interp2_on_a_node(void)
{
    assert_interp2(&vec_interp2[0], __LINE__);
}

static void test_interp2_between_nodes(void)
{
    assert_interp2(&vec_interp2[1], __LINE__);
}

static void test_interp2_clamped_above_both_axes(void)
{
    assert_interp2(&vec_interp2[2], __LINE__);
}

static void test_interp2_clamped_below_both_axes(void)
{
    assert_interp2(&vec_interp2[3], __LINE__);
}

static void run_predict_vector(void)
{
    load_state(&ekf, &vec_predict.before);
    ekf_predict(&ekf, vec_predict.i_held, vec_predict.t_degc, vec_predict.dt_s);
}

static void test_predict_state_matches_python(void)
{
    run_predict_vector();
    assert_x(vec_predict.after.x, &ekf, __LINE__);
}

static void test_predict_covariance_matches_python(void)
{
    run_predict_vector();
    assert_P(vec_predict.after.P, &ekf, __LINE__);
}

static void run_update_vector(void)
{
    load_state(&ekf, &vec_update.before);
    ekf_update(&ekf, vec_update.i_a, vec_update.v_v, vec_update.t_degc);
}

static void test_update_state_matches_python(void)
{
    run_update_vector();
    assert_x(vec_update.after.x, &ekf, __LINE__);
}

static void test_update_covariance_matches_python(void)
{
    run_update_vector();
    assert_P(vec_update.after.P, &ekf, __LINE__);
}

static void test_update_y_hat_matches_python(void)
{
    run_update_vector();
    assert_close(vec_update.y_hat, ekf.y_hat, TOL_STATE, __LINE__);
}

static void test_limit_soc_matches_python(void)
{
    load_state(&ekf, &vec_limit_soc.before);
    ekf_limit_soc(&ekf);
    assert_x(vec_limit_soc.x, &ekf, __LINE__);
}

static void test_step_with_zero_dt_is_update_only(void)
{
    ekf_t expected;
    memcpy(&expected, &ekf, sizeof ekf);
    ekf_update(&expected, I_A, V_V, T_DEGC);
    expected.i_held = I_A;

    ekf_step(&ekf, I_A, V_V, T_DEGC, EKF_R(0.0));
    TEST_ASSERT_EQUAL_MEMORY(&expected, &ekf, sizeof ekf);
}

static void test_step_with_negative_dt_returns_error(void)
{
    TEST_ASSERT_EQUAL_INT(EKF_ERR_DT_NEGATIVE, ekf_step(&ekf, I_A, V_V, T_DEGC, EKF_R(-1.0)));
}

static void test_step_with_negative_dt_leaves_state(void)
{
    ekf_t before;
    memcpy(&before, &ekf, sizeof ekf);

    ekf_step(&ekf, I_A, V_V, T_DEGC, EKF_R(-1.0));
    TEST_ASSERT_EQUAL_MEMORY(&before, &ekf, sizeof ekf);
}

/* The values ekf_step and ekf_init must reject: NaN and either infinity. */
static const ekf_real_t non_finite[3] = {(ekf_real_t)NAN, (ekf_real_t)INFINITY, (ekf_real_t)-INFINITY};

/* Steps with `value` in input k (0: i_a, 1: v_v, 2: t_degc, 3: dt_s) and the others valid. */
static ekf_status_t step_with_input(int k, ekf_real_t value)
{
    ekf_real_t inputs[4] = {I_A, V_V, T_DEGC, DT_S};
    inputs[k] = value;
    return ekf_step(&ekf, inputs[0], inputs[1], inputs[2], inputs[3]);
}

static void test_init_with_non_finite_soc0_returns_error(void)
{
    ekf_t e;
    int n;
    for (n = 0; n < 3; n++) {
        TEST_ASSERT_EQUAL_INT(EKF_ERR_NONFINITE_INPUT, ekf_init(&e, &cfg, non_finite[n]));
    }
}

static void test_step_with_non_finite_input_returns_error(void)
{
    int k, n;
    for (k = 0; k < 4; k++) {
        for (n = 0; n < 3; n++) {
            TEST_ASSERT_EQUAL_INT(EKF_ERR_NONFINITE_INPUT, step_with_input(k, non_finite[n]));
        }
    }
}

static void test_step_with_non_finite_input_leaves_state(void)
{
    ekf_t before;
    int k, n;
    memcpy(&before, &ekf, sizeof ekf);

    for (k = 0; k < 4; k++) {
        for (n = 0; n < 3; n++) {
            step_with_input(k, non_finite[n]);
        }
        TEST_ASSERT_EQUAL_MEMORY(&before, &ekf, sizeof ekf);
    }
}

static void test_step_outside_temperature_axis_returns_warning(void)
{
    TEST_ASSERT_EQUAL_INT(EKF_WARN_TEMP_CLAMPED, ekf_step(&ekf, I_A, V_V, EKF_R(55.0), DT_S));
}

/* 55 degC lies above the 40 degC end of the axis, so the step runs as at 40 degC (Eq. 4). */
static void test_step_outside_temperature_axis_runs_at_the_clamped_temperature(void)
{
    ekf_t expected;
    memcpy(&expected, &ekf, sizeof ekf);
    ekf_step(&expected, I_A, V_V, EKF_R(40.0), DT_S);

    ekf_step(&ekf, I_A, V_V, EKF_R(55.0), DT_S);
    TEST_ASSERT_EQUAL_MEMORY(&expected, &ekf, sizeof ekf);
}

static void test_get_soc_returns_the_soc_state(void)
{
    ekf_step(&ekf, I_A, V_V, T_DEGC, DT_S);
    TEST_ASSERT_TRUE(ekf_get_soc(&ekf) == ekf.x[0]);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_interp2_on_a_node);
    RUN_TEST(test_interp2_between_nodes);
    RUN_TEST(test_interp2_clamped_above_both_axes);
    RUN_TEST(test_interp2_clamped_below_both_axes);
    RUN_TEST(test_predict_state_matches_python);
    RUN_TEST(test_predict_covariance_matches_python);
    RUN_TEST(test_update_state_matches_python);
    RUN_TEST(test_update_covariance_matches_python);
    RUN_TEST(test_update_y_hat_matches_python);
    RUN_TEST(test_limit_soc_matches_python);
    RUN_TEST(test_step_with_zero_dt_is_update_only);
    RUN_TEST(test_step_with_negative_dt_returns_error);
    RUN_TEST(test_step_with_negative_dt_leaves_state);
    RUN_TEST(test_init_with_non_finite_soc0_returns_error);
    RUN_TEST(test_step_with_non_finite_input_returns_error);
    RUN_TEST(test_step_with_non_finite_input_leaves_state);
    RUN_TEST(test_step_outside_temperature_axis_returns_warning);
    RUN_TEST(test_step_outside_temperature_axis_runs_at_the_clamped_temperature);
    RUN_TEST(test_get_soc_returns_the_soc_state);
    return UNITY_END();
}
