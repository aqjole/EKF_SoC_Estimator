# Test fixture: `lghg2_excerpt.mat`

A small copy of one file of the LG 18650HG2 dataset, so the loader tests run in CI without the 206 raw files.

- **Source file:** `data/raw/25degC/10-28-18_13.10 551_Cap_1C_25degC_LGHG2.mat`, a 1C (3 A) constant-current discharge at 25 degC, logged every 10 s.
- **Dataset:** LG 18650HG2 Li-ion Battery Data, Kollmeyer et al., McMaster University, Mendeley Data v2, DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2).
- **Licence:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The fixture is data from that dataset, so it carries the dataset's licence and the attribution above. It is **not** covered by the MIT licence of this repository's code.
- **How it was made:** `python/tests/make_fixture.py` copies the whole source file (397 rows, under 1 MB, so nothing is trimmed) with `scipy.io.savemat` (compressed) as the struct `meas` with the same eight fields (`Time`, `TimeStamp`, `Voltage`, `Current`, `Ah`, `Wh`, `Power`, `Battery_Temp_degC`). Each field keeps its stored type and column shape (`Wh` as `uint8`, `TimeStamp` as a cell array of text). The script reads the fixture back and checks every field against the source. Run it from the repo root with `.venv/bin/python python/tests/make_fixture.py`; it needs `data/raw/`.
- **Contents in the cycler's convention:** Current is -3.0011 A during the discharge and 0 A before and after it, and the Ah counter falls to -2.72639 Ah. The file has two rows that repeat the Time of the row before (`n_duplicates_removed = 2` after loading).
