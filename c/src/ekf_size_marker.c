/* An object whose size is sizeof(ekf_t), so the footprint script reads the size of the filter state
 * on the target with nm -S instead of running code there. */
#include "ekf.h"

const char ekf_t_size_marker[sizeof(ekf_t)] = {0};
