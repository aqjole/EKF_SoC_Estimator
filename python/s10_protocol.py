"""Frozen inputs and run selection for decision 1.44."""

from hashlib import sha256

from compare_r1i import RESULTS_RI_CSV
from ekfsoc.constants import RAW_DIR
from ekfsoc.experiments import evaluation_runs
from export_params import PARAMS_CSV, md_table
from fit_3rcd import PARAMS_3RCD_CSV, RESULTS, drive_split
from fit_r1_current import R1_CURRENT_CSV
from run_all import CONFIG_JSON, RESULTS_CSV


COLD = (0, -10, -20)
PLOTS = RESULTS / "plots" / "s10"
DIAGNOSTIC_MD = RESULTS / "accuracy_diagnostics.md"
DISCLOSURE = (
    "The 23 standard runs are a previously inspected regression suite. They informed earlier diagnostics "
    "and the low-SoC boundary choice. They share segments with the 40 Mix runs, and the Mix folds also "
    "share segments with each other. All runs come from one cell in one campaign."
)
FROZEN = {
    PARAMS_CSV: "d51d1576e02c82a7f719e8029a78ff5937baf6e06eec2cd036524aa7da9f09a3",
    R1_CURRENT_CSV: "bc1e44b45aa98ea5942beb1a38600cfddacacd91c44f099efa70daa4f8ae9ec5",
    PARAMS_3RCD_CSV: "8e6d4e73f7762be69cfe4c9d3c2cb1166daffa87af1f8f73064907eee43b3ea4",
    CONFIG_JSON: "64f0f9568f740b046910b9f09576275c40996bcd0e00103d1c39dae8d2a2d830",
    RESULTS_CSV: "e29cd6ffd0ee3442db5c0813f3b8c6e4f3cbbf63e1794345c17480d53e92fb2f",
    RESULTS_RI_CSV: "4f39c31b644595b0c2b2839269c841cdc7aa1aa2b02773e8344650af914eb5e1",
    RESULTS / "ekf_results_3rcd.csv": "877185308d6e7ecc8519b1682c56f18c4b23ebb09a81dfbe641a52b06fcd1ac0",
}


def verify_baseline():
    for path, expected in FROZEN.items():
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"{path.name} differs from the frozen S10 baseline")


def splits():
    return drive_split(evaluation_runs(RAW_DIR))


def provenance(mix, standard):
    lines = ["## Frozen inputs", "",
             *md_table(["File in results/", "SHA-256"], [[path.name, value] for path, value in FROZEN.items()]),
             "", "## Run membership", "",
             *md_table(["Split", "Folder", "Cycle", "File"],
                       [[split, spec.folder, spec.cycle_name, spec.path.name]
                        for split, specs in (("Mix", mix), ("Standard", standard)) for spec in specs])]
    return lines
