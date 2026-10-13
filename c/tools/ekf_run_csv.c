/* Host-only tool: run the filter over a CSV of filter inputs and write the SoC of every row.
 *
 * usage: ekf_run_csv <in.csv> <out.csv> <q_soc> <q_v> <r> <soc0>
 *
 * in.csv has a header line naming at least the columns dt_s, i_a, v_v and t_degc, in any order (other
 * columns, such as soc_expected in the test fixtures, are ignored). dt_s is the step to the previous row,
 * computed by Python in double; the tool never subtracts timestamps, because a float32 time near 1e4 s
 * resolves only about 1 ms (the spec, S3). The first row has dt_s = 0: an update and no predict, as
 * python run_ekf. out.csv gets a header "soc" and one SoC per input row with 10 significant digits.
 * The initial standard deviations are the defaults of EkfConfig, 0.2 (SoC) and 0.05 V (V1, V2).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ekf.h"

#define MAX_LINE 1024
#define MAX_COLUMNS 16

static const char *const INPUTS[4] = {"dt_s", "i_a", "v_v", "t_degc"};

/* Find the column index of each name of INPUTS in the header line; return 0 if one is missing. */
static int find_columns(char *header, int index[4])
{
    int column = 0;
    int found = 0;
    char *name;

    header[strcspn(header, "\r\n")] = '\0';
    for (name = strtok(header, ","); name != NULL; name = strtok(NULL, ","), column++) {
        int k;
        for (k = 0; k < 4; k++) {
            if (strcmp(name, INPUTS[k]) == 0) {
                index[k] = column;
                found++;
            }
        }
    }
    return found == 4;
}

/* Parse the comma-separated numbers of one data line into values; return how many were read. */
static int parse_line(const char *line, double values[MAX_COLUMNS])
{
    int n = 0;
    char *end;

    while (n < MAX_COLUMNS) {
        values[n++] = strtod(line, &end);
        if (end == line || *end != ',') {
            break;
        }
        line = end + 1;
    }
    return n;
}

int main(int argc, char **argv)
{
    FILE *in, *out;
    char line[MAX_LINE];
    double values[MAX_COLUMNS];
    int index[4];
    long row = 0;
    ekf_cfg_t cfg;
    ekf_t e;

    if (argc != 7) {
        fprintf(stderr, "usage: %s <in.csv> <out.csv> <q_soc> <q_v> <r> <soc0>\n", argv[0]);
        return 2;
    }
    in = fopen(argv[1], "r");
    if (in == NULL || fgets(line, sizeof line, in) == NULL || !find_columns(line, index)) {
        fprintf(stderr, "%s: cannot read the columns dt_s, i_a, v_v, t_degc\n", argv[1]);
        return 1;
    }
    out = fopen(argv[2], "w");
    if (out == NULL) {
        fprintf(stderr, "%s: cannot write\n", argv[2]);
        return 1;
    }

    cfg.q_soc = (ekf_real_t)atof(argv[3]);
    cfg.q_v = (ekf_real_t)atof(argv[4]);
    cfg.r = (ekf_real_t)atof(argv[5]);
    cfg.p0_soc_std = EKF_R(0.2);
    cfg.p0_v_std = EKF_R(0.05);
    cfg.params = &ekf_params_default;
    ekf_init(&e, &cfg, (ekf_real_t)atof(argv[6]));

    fprintf(out, "soc\n");
    while (fgets(line, sizeof line, in) != NULL) {
        ekf_status_t status;
        int n = parse_line(line, values);
        if (n <= index[0] || n <= index[1] || n <= index[2] || n <= index[3]) {
            fprintf(stderr, "%s: row %ld has %d columns\n", argv[1], row, n);
            return 1;
        }
        status = ekf_step(&e, (ekf_real_t)values[index[1]], (ekf_real_t)values[index[2]],
                          (ekf_real_t)values[index[3]], (ekf_real_t)values[index[0]]);
        if (status != EKF_OK && status != EKF_WARN_TEMP_CLAMPED) {
            fprintf(stderr, "%s: row %ld: ekf_step returned status %d\n", argv[1], row, (int)status);
            return 1;
        }
        fprintf(out, "%.10g\n", (double)ekf_get_soc(&e));
        row++;
    }
    fclose(in);
    return fclose(out) == 0 ? 0 : 1;
}
