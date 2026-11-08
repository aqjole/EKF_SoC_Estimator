/* The 2RC and 3RC-D0 filters from python/ekfsoc/ekf.py.
 *
 * Every function repeats its Python namesake with the same operation order, so the double build
 * matches Python to rounding. Equation numbers ("Eq. n") are those of docs/model.md. Matrix products are separate steps, with every sum in state order from zero.
 */
#include "ekf.h"

#include <math.h>
#include <stddef.h>

/* min(max(x, lowest), highest), as in model.py and ekf.py. */
static ekf_real_t clamp(ekf_real_t x, ekf_real_t lowest, ekf_real_t highest)
{
    if (x < lowest) {
        return lowest;
    }
    if (x > highest) {
        return highest;
    }
    return x;
}

/* Return the cell j of `axis` (n nodes, strictly ascending or descending) that holds x, and in
 * *weight how far x lies into it (Eq. 4, steps 1 to 3). Same steps as find_cell in model.py. */
static int find_cell(const ekf_real_t *axis, int n, ekf_real_t x, ekf_real_t *weight)
{
    ekf_real_t first = axis[0];
    ekf_real_t last = axis[n - 1];
    ekf_real_t direction, lowest, highest, x_clamped;
    int low = 0;
    int high = n - 1;

    if (last > first) {
        direction = EKF_R(1.0);
        lowest = first;
        highest = last;
    } else {
        direction = EKF_R(-1.0);
        lowest = last;
        highest = first;
    }

    x_clamped = clamp(x, lowest, highest);

    while (high - low > 1) {
        int mid = (low + high) / 2;
        if (direction * (x_clamped - axis[mid]) >= EKF_R(0.0)) {
            low = mid;
        } else {
            high = mid;
        }
    }

    *weight = (x_clamped - axis[low]) / (axis[low + 1] - axis[low]);
    return low;
}

ekf_real_t ekf_interp2(const ekf_real_t *table, const ekf_real_t *t_grid, int n_t,
                       const ekf_real_t *soc_grid, int n_soc, ekf_real_t t, ekf_real_t soc)
{
    ekf_real_t weight_t, weight_s;
    int j = find_cell(t_grid, n_t, t, &weight_t);
    int m = find_cell(soc_grid, n_soc, soc, &weight_s);
    const ekf_real_t *row_j = table + j * n_soc;
    const ekf_real_t *row_j1 = row_j + n_soc;

    ekf_real_t value_j = (EKF_R(1.0) - weight_s) * row_j[m] + weight_s * row_j[m + 1];
    ekf_real_t value_j1 = (EKF_R(1.0) - weight_s) * row_j1[m] + weight_s * row_j1[m + 1];
    return (EKF_R(1.0) - weight_t) * value_j + weight_t * value_j1;
}

/* Read one table of the filter's parameter set at (t_degc, soc) (Eq. 4). */
static ekf_real_t lookup(const ekf_t *e, const ekf_real_t *table, ekf_real_t t_degc, ekf_real_t soc)
{
    const ekf_params_t *params = e->cfg->params;
    return ekf_interp2(table, params->t_grid, EKF_N_T, params->soc_grid, EKF_N_SOC, t_degc, soc);
}

static ekf_real_t dot_state(const ekf_real_t a[EKF_N_STATE], const ekf_real_t b[EKF_N_STATE])
{
    ekf_real_t sum = EKF_R(0.0);
    int k;
    for (k = 0; k < EKF_N_STATE; k++) {
        sum += a[k] * b[k];
    }
    return sum;
}

/* out = a @ v */
static void mat_vec(ekf_real_t a[EKF_N_STATE][EKF_N_STATE], const ekf_real_t v[EKF_N_STATE], ekf_real_t out[EKF_N_STATE])
{
    int i;
    for (i = 0; i < EKF_N_STATE; i++) {
        out[i] = dot_state(a[i], v);
    }
}

/* out = a @ b */
static void mat_mul(ekf_real_t a[EKF_N_STATE][EKF_N_STATE], ekf_real_t b[EKF_N_STATE][EKF_N_STATE], ekf_real_t out[EKF_N_STATE][EKF_N_STATE])
{
    int i, j, k;
    for (i = 0; i < EKF_N_STATE; i++) {
        for (j = 0; j < EKF_N_STATE; j++) {
            ekf_real_t sum = EKF_R(0.0);
            for (k = 0; k < EKF_N_STATE; k++) {
                sum += a[i][k] * b[k][j];
            }
            out[i][j] = sum;
        }
    }
}

/* out = a @ b.T */
static void mat_mul_transposed(ekf_real_t a[EKF_N_STATE][EKF_N_STATE], ekf_real_t b[EKF_N_STATE][EKF_N_STATE], ekf_real_t out[EKF_N_STATE][EKF_N_STATE])
{
    int i, j;
    for (i = 0; i < EKF_N_STATE; i++) {
        for (j = 0; j < EKF_N_STATE; j++) {
            out[i][j] = dot_state(a[i], b[j]);
        }
    }
}

ekf_status_t ekf_init(ekf_t *e, const ekf_cfg_t *cfg, ekf_real_t soc0)
{
    ekf_real_t var_soc, var_v;
    int i, j;

    if (e == NULL || cfg == NULL || cfg->params == NULL) {
        return EKF_ERR_NULL;
    }
    if (!isfinite(soc0)) {
        return EKF_ERR_NONFINITE_INPUT;
    }

    var_soc = cfg->p0_soc_std * cfg->p0_soc_std;
    var_v = cfg->p0_v_std * cfg->p0_v_std;
    e->x[0] = soc0;
    e->x[1] = EKF_R(0.0);
    e->x[2] = EKF_R(0.0);
#ifdef EKF_USE_3RCD0
    e->x[3] = EKF_R(0.0);
#endif
    for (i = 0; i < EKF_N_STATE; i++) {
        for (j = 0; j < EKF_N_STATE; j++) {
            e->P[i][j] = EKF_R(0.0);
        }
    }
    e->P[0][0] = var_soc;
    e->P[1][1] = var_v;
    e->P[2][2] = var_v;
#ifdef EKF_USE_3RCD0
    e->P[3][3] = var_v;
#endif
    e->i_held = EKF_R(0.0);
    e->y_hat = (ekf_real_t)NAN;
    e->cfg = cfg;
    return EKF_OK;
}

void ekf_predict(ekf_t *e, ekf_real_t i_held, ekf_real_t t_degc, ekf_real_t dt_s)
{
    const ekf_cfg_t *cfg = e->cfg;
    const ekf_params_t *params = cfg->params;
    ekf_real_t soc = e->x[0];
    ekf_real_t r1 = lookup(e, params->r1, t_degc, soc);
    ekf_real_t tau1 = lookup(e, params->tau1, t_degc, soc);
    ekf_real_t r2 = lookup(e, params->r2, t_degc, soc);
    ekf_real_t tau2 = lookup(e, params->tau2, t_degc, soc);

    ekf_real_t a1 = EKF_EXP(-dt_s / tau1);
    ekf_real_t a2 = EKF_EXP(-dt_s / tau2);
#ifdef EKF_USE_3RCD0
    ekf_real_t r3 = lookup(e, params->r3, t_degc, soc);
    ekf_real_t a3 = EKF_EXP(-dt_s / EKF_TAU3_S);
#endif
    ekf_real_t F[EKF_N_STATE][EKF_N_STATE] = {
        {EKF_R(1.0), EKF_R(0.0), EKF_R(0.0)},
        {EKF_R(0.0), a1, EKF_R(0.0)},
        {EKF_R(0.0), EKF_R(0.0), a2},
#ifdef EKF_USE_3RCD0
        {EKF_R(0.0), EKF_R(0.0), EKF_R(0.0), a3},
#endif
    };
    ekf_real_t B[EKF_N_STATE] = {
        -dt_s / (EKF_R(3600.0) * EKF_Q_REF_AH),
        r1 * (EKF_R(1.0) - a1),
        r2 * (EKF_R(1.0) - a2),
#ifdef EKF_USE_3RCD0
        r3 * (EKF_R(1.0) - a3),
#endif
    };
    ekf_real_t Q[EKF_N_STATE][EKF_N_STATE] = {
        {cfg->q_soc * dt_s, EKF_R(0.0), EKF_R(0.0)},
        {EKF_R(0.0), cfg->q_v * dt_s, EKF_R(0.0)},
        {EKF_R(0.0), EKF_R(0.0), cfg->q_v * dt_s},
#ifdef EKF_USE_3RCD0
        {EKF_R(0.0), EKF_R(0.0), EKF_R(0.0), cfg->q_v * dt_s},
#endif
    };
    ekf_real_t F_x[EKF_N_STATE], F_P[EKF_N_STATE][EKF_N_STATE], F_P_Ft[EKF_N_STATE][EKF_N_STATE];
    int i, j;

    mat_vec(F, e->x, F_x);
    for (i = 0; i < EKF_N_STATE; i++) {
        e->x[i] = F_x[i] + B[i] * i_held;  /* Eq. 6 */
    }

    mat_mul(F, e->P, F_P);
    mat_mul_transposed(F_P, F, F_P_Ft);
    for (i = 0; i < EKF_N_STATE; i++) {
        for (j = 0; j < EKF_N_STATE; j++) {
            e->P[i][j] = F_P_Ft[i][j] + Q[i][j];  /* Eq. 7 */
        }
    }
}

void ekf_limit_soc(ekf_t *e)
{
    ekf_real_t soc = e->x[0];
    ekf_real_t soc_bound = clamp(soc, EKF_R(0.0), EKF_R(1.0));
    ekf_real_t excess;
    int i;

    if (soc == soc_bound) {
        return;
    }

    excess = soc - soc_bound;
    for (i = 0; i < EKF_N_STATE; i++) {
        ekf_real_t shift = e->P[i][0] * excess / e->P[0][0];
        e->x[i] = e->x[i] - shift;  /* Eq. 10, the projection along P[:, 0] */
    }
    e->x[0] = soc_bound;  /* exactly on the bound, whatever the rounding of the line above */
}

void ekf_update(ekf_t *e, ekf_real_t i_a, ekf_real_t v_v, ekf_real_t t_degc)
{
    const ekf_cfg_t *cfg = e->cfg;
    const ekf_params_t *params = cfg->params;
    ekf_real_t soc_prior = e->x[0];
    ekf_real_t v1_prior = e->x[1];
    ekf_real_t v2_prior = e->x[2];
    ekf_real_t ocv = lookup(e, params->ocv, t_degc, soc_prior);
    ekf_real_t docv = lookup(e, params->docv, t_degc, soc_prior);
    ekf_real_t r0 = lookup(e, params->r0, t_degc, soc_prior);

    ekf_real_t v_terminal = ocv - v1_prior - v2_prior;
#ifdef EKF_USE_3RCD0
    v_terminal -= e->x[3];
#endif
    ekf_real_t y_hat = v_terminal - r0 * i_a;  /* Eq. 8 */
    ekf_real_t H[EKF_N_STATE] = {  /* Eq. 8, dR0/dSoC left out */
        docv, EKF_R(-1.0), EKF_R(-1.0),
#ifdef EKF_USE_3RCD0
        EKF_R(-1.0),
#endif
    };

    ekf_real_t P_Ht[EKF_N_STATE], K[EKF_N_STATE], x_post[EKF_N_STATE];
    ekf_real_t I_KH[EKF_N_STATE][EKF_N_STATE], I_KH_P[EKF_N_STATE][EKF_N_STATE], I_KH_P_I_KH_t[EKF_N_STATE][EKF_N_STATE], K_R_Kt[EKF_N_STATE][EKF_N_STATE];
    ekf_real_t S, innovation;
    int i, j;

    mat_vec(e->P, H, P_Ht);
    S = dot_state(H, P_Ht) + cfg->r;  /* Eq. 9 */
    for (i = 0; i < EKF_N_STATE; i++) {
        K[i] = P_Ht[i] / S;  /* Eq. 9 */
    }

    innovation = v_v - y_hat;
    for (i = 0; i < EKF_N_STATE; i++) {
        x_post[i] = e->x[i] + K[i] * innovation;  /* Eq. 10 */
    }

    for (i = 0; i < EKF_N_STATE; i++) {
        for (j = 0; j < EKF_N_STATE; j++) {
            ekf_real_t identity = (i == j) ? EKF_R(1.0) : EKF_R(0.0);
            I_KH[i][j] = identity - K[i] * H[j];
            K_R_Kt[i][j] = cfg->r * (K[i] * K[j]);
        }
    }
    mat_mul(I_KH, e->P, I_KH_P);
    mat_mul_transposed(I_KH_P, I_KH, I_KH_P_I_KH_t);

    for (i = 0; i < EKF_N_STATE; i++) {
        e->x[i] = x_post[i];
        for (j = 0; j < EKF_N_STATE; j++) {
            e->P[i][j] = I_KH_P_I_KH_t[i][j] + K_R_Kt[i][j];  /* Eq. 11 */
        }
    }
    e->y_hat = y_hat;

    ekf_limit_soc(e);  /* Eq. 10, the SoC limit, along the posterior P of Eq. 11 */
}

/* Whether t_degc lies within the end nodes of the temperature axis (either direction). */
static int temp_in_table(const ekf_params_t *params, ekf_real_t t_degc)
{
    ekf_real_t first = params->t_grid[0];
    ekf_real_t last = params->t_grid[EKF_N_T - 1];
    return (t_degc >= first && t_degc <= last) || (t_degc <= first && t_degc >= last);
}

ekf_status_t ekf_step(ekf_t *e, ekf_real_t i_a, ekf_real_t v_v, ekf_real_t t_degc, ekf_real_t dt_s)
{
    if (e == NULL || e->cfg == NULL) {
        return EKF_ERR_NULL;
    }
    if (!isfinite(i_a) || !isfinite(v_v) || !isfinite(t_degc) || !isfinite(dt_s)) {
        return EKF_ERR_NONFINITE_INPUT;
    }
    if (dt_s < EKF_R(0.0)) {
        return EKF_ERR_DT_NEGATIVE;
    }

    if (dt_s > EKF_R(0.0)) {  /* dt = 0 makes predict the identity (Eq. 6, 7), so it is skipped */
        ekf_predict(e, e->i_held, t_degc, dt_s);
    }
    ekf_update(e, i_a, v_v, t_degc);
    e->i_held = i_a;

    return temp_in_table(e->cfg->params, t_degc) ? EKF_OK : EKF_WARN_TEMP_CLAMPED;
}

ekf_real_t ekf_get_soc(const ekf_t *e)
{
    return e->x[0];
}
