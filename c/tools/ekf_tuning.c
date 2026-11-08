/* Offline double-precision 3RC evaluator for S11 tuning, not the embedded library.
 * Equations 4 and 6--11 in docs/model.md; checked against Python before use.
 * Tables are [table][temperature][SoC], in Params.table_names order.
 */
#include <math.h>
#include <stddef.h>

static int cell(const double *axis, int n, double x, double *w)
{
    double direction = axis[n - 1] > axis[0] ? 1.0 : -1.0;
    double lower = fmin(axis[0], axis[n - 1]);
    double upper = fmax(axis[0], axis[n - 1]);
    x = fmin(fmax(x, lower), upper);
    int low = 0, high = n - 1;
    while (high - low > 1) {
        int mid = (low + high) / 2;
        if (direction * (x - axis[mid]) >= 0.0) low = mid;
        else high = mid;
    }
    *w = (x - axis[low]) / (axis[low + 1] - axis[low]);
    return low;
}

static double lookup(const double *table, int ns, int j, int m, double wt, double ws)
{
    const double *a = table + j * ns + m;
    const double *b = a + ns;
    double low = (1.0 - ws) * a[0] + ws * a[1];
    double high = (1.0 - ws) * b[0] + ws * b[1];
    return (1.0 - wt) * low + wt * high;
}

/* cfg = q_soc, q_v, r, p0_soc_std, p0_v_std. Outputs are full-length arrays. */
int ekf_tuning_run(int n, int nt, int ns, const double *tables,
                   const double *tg, const double *sg, const double *cfg,
                   const double *current, const double *voltage,
                   const double *temp, const double *dt, double capacity,
                   double soc0, double offset, double *soc, double *predicted)
{
    double x[4] = {soc0, 0.0, 0.0, 0.0}, p[4][4] = {{0}};
    double held = 0.0;
    int stride = nt * ns;
    for (int i = 0; i < 4; ++i) p[i][i] = cfg[i == 0 ? 3 : 4] * cfg[i == 0 ? 3 : 4];
    for (int k = 0; k < n; ++k) {
        double wt, ws, a[4] = {1.0, 0.0, 0.0, 0.0};
        double step = k == 0 ? 0.0 : dt[k];
        double amps = current[k] + offset;
        int j = cell(tg, nt, temp[k], &wt);
        int m = cell(sg, ns, x[0], &ws);
        for (int i = 1; i < 4; ++i) {
            int ri = 2 * i + 1;
            double r = lookup(tables + ri * stride, ns, j, m, wt, ws);
            double tau = lookup(tables + (ri + 1) * stride, ns, j, m, wt, ws);
            a[i] = exp(-step / tau);
            x[i] = a[i] * x[i] + (r * (1.0 - a[i])) * held;
        }
        x[0] = x[0] + (-step / (3600.0 * capacity)) * held; /* Eq. 6 */
        for (int i = 0; i < 4; ++i) {
            for (int l = 0; l < 4; ++l) p[i][l] = (a[i] * p[i][l]) * a[l];
            p[i][i] += cfg[i == 0 ? 0 : 1] * step;
        }
        m = cell(sg, ns, x[0], &ws);
        double ocv = lookup(tables, ns, j, m, wt, ws);
        double h[4] = {lookup(tables + stride, ns, j, m, wt, ws), -1.0, -1.0, -1.0};
        double r0 = lookup(tables + 2 * stride, ns, j, m, wt, ws);
        double y = ocv;
        for (int i = 1; i < 4; ++i) y -= x[i];
        y -= r0 * amps;
        double ph[4] = {0}, gain[4], innovation = voltage[k] - y;
        for (int i = 0; i < 4; ++i)
            for (int l = 0; l < 4; ++l) ph[i] += p[i][l] * h[l];
        double s = 0.0;
        for (int i = 0; i < 4; ++i) s += h[i] * ph[i];
        s += cfg[2];
        if (!(s > 0.0) || !isfinite(s)) return k + 1;
        for (int i = 0; i < 4; ++i) {
            gain[i] = ph[i] / s;
            x[i] += gain[i] * innovation;
        }
        double ikh[4][4], ip[4][4] = {{0}}, post[4][4] = {{0}};
        for (int i = 0; i < 4; ++i)
            for (int l = 0; l < 4; ++l) ikh[i][l] = (i == l ? 1.0 : 0.0) - gain[i] * h[l];
        for (int i = 0; i < 4; ++i)
            for (int l = 0; l < 4; ++l)
                for (int q = 0; q < 4; ++q) ip[i][l] += ikh[i][q] * p[q][l];
        for (int i = 0; i < 4; ++i)
            for (int l = 0; l < 4; ++l) {
                for (int q = 0; q < 4; ++q) post[i][l] += ip[i][q] * ikh[l][q];
                p[i][l] = post[i][l] + cfg[2] * (gain[i] * gain[l]); /* Eq. 11 */
                if (!isfinite(p[i][l])) return k + 1;
            }
        double bound = fmin(fmax(x[0], 0.0), 1.0);
        if (x[0] != bound) {
            if (!(p[0][0] > 0.0)) return k + 1;
            double excess = x[0] - bound;
            for (int i = 0; i < 4; ++i) x[i] -= p[i][0] * excess / p[0][0];
            x[0] = bound;
        }
        for (int i = 0; i < 4; ++i) if (!isfinite(x[i])) return k + 1;
        soc[k] = x[0];
        predicted[k] = y;
        held = amps;
    }
    return 0;
}
