"""Raw-file access for the LG 18650HG2 dataset (Mendeley Data b5mj79w5w9, version 2).

This module only reads what the cycler wrote. It does four things:

- parse_filename(): split a file name into date, time, test number and descriptor.
- classify_test(): map a descriptor such as "Mixed3_25degC_LGHG2" to a test type.
- parse_timestamp(): turn one TimeStamp string into a datetime.
- load_mat(): read one .mat file into a dict of 1-D float64 arrays.

Signs stay as the cycler wrote them: discharge current and discharged Ah are
NEGATIVE here. The S1 loader converts to the project convention (positive =
discharge). Nothing is cleaned here either: NaN rows, duplicate Time values and
backward Time steps are returned as they are, so the inventory can count them.
"""

import datetime
import re

import h5py
import numpy as np
import scipy.io


# The eight fields every file is expected to hold, in the order the files store them.
EXPECTED_FIELDS = ("Time", "TimeStamp", "Voltage", "Current", "Ah", "Wh", "Power", "Battery_Temp_degC")

# "<MM>-<DD>-<YY>_<hh>.<mm> <test number>_<descriptor>.mat", as the dataset readme describes.
# The underscore between date and time is optional because one file
# ("12-24-1822.25 610_Charge5.mat") was saved without it.
FILENAME_PATTERN = re.compile(
    r"^(?P<month>\d{2})-(?P<day>\d{2})-(?P<year>\d{2})(?P<sep>_?)(?P<hour>\d{2})\.(?P<minute>\d{2})"
    r" (?P<test_number>\d+)_(?P<descriptor>.+)\.mat$"
)

# Temperature written in a descriptor, e.g. "25degC" or "n10degC" (n = negative).
DESCRIPTOR_TEMP_PATTERN = re.compile(r"(?P<negative>n?)(?P<value>\d+)degC")

# Descriptor prefix -> test type. Checked in this order; the first match wins.
TEST_TYPE_PREFIXES = (
    ("HPPC", "hppc"),
    ("C20DisCh", "c20"),
    ("Dis_0p5C", "dis_0p5c"),
    ("Dis_2C", "dis_2c"),
    ("Cap_1C", "cap_1c"),
    ("Charge", "charge"),
    ("UDDS", "udds"),
    ("HWFET", "hwfet"),
    ("LA92", "la92"),
    ("US06", "us06"),
    ("PausCycl", "pauscycl"),
)
MIXED_PATTERN = re.compile(r"^Mixed(?P<k>[1-8])(?!\d)")


def parse_filename(name):
    """Split a dataset file name into its parts.

    The readme says the name starts with the test start date as MM-DD-YY and
    the start time as hh.mm. That reading is applied as written; it is not
    corrected here, because some files break it (fifteen 0degC files use
    DD-MM-YY). The inventory checks the name against the first TimeStamp.

    Returns a dict with keys:
        date: datetime.date from the name read as MM-DD-YY, or None if that is not a valid date
        time: datetime.time from the name
        test_number: cycler test number (int), e.g. 557
        descriptor: text after the test number, e.g. "Cap_1C_40degC_LGHG2"
        test_type: result of classify_test(descriptor)
        descriptor_temp_degc: temperature written in the descriptor (float), or None
        separator_ok: False when the "_" between date and time is missing
    Returns None if the name does not follow the pattern at all.
    """
    match = FILENAME_PATTERN.match(name)
    if match is None:
        return None

    year = 2000 + int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        date = datetime.date(year, month, day)
    except ValueError:
        date = None

    descriptor = match.group("descriptor")
    return {
        "date": date,
        "time": datetime.time(int(match.group("hour")), int(match.group("minute"))),
        "test_number": int(match.group("test_number")),
        "descriptor": descriptor,
        "test_type": classify_test(descriptor),
        "descriptor_temp_degc": descriptor_temperature(descriptor),
        "separator_ok": match.group("sep") == "_",
    }


def descriptor_temperature(descriptor):
    """Return the temperature written in a descriptor in degC, or None if it has none.

    "Mixed3_n10degC_LGHG2" gives -10.0; "Charge7" and "Cap_1C" give None.
    """
    match = DESCRIPTOR_TEMP_PATTERN.search(descriptor)
    if match is None:
        return None
    value = float(match.group("value"))
    if match.group("negative") == "n":
        value = -value
    return value


def classify_test(descriptor):
    """Return the test type for a descriptor.

    Types: hppc, c20, dis_0p5c, dis_2c, cap_1c, charge, udds, hwfet, la92,
    us06, mixed1..mixed8, pauscycl, other. The type is read from the start of
    the descriptor only, so a wrong temperature in the descriptor does not
    change the type.
    """
    mixed = MIXED_PATTERN.match(descriptor)
    if mixed is not None:
        return "mixed" + mixed.group("k")
    for prefix, test_type in TEST_TYPE_PREFIXES:
        if descriptor.startswith(prefix):
            return test_type
    return "other"


def parse_timestamp(text):
    """Parse one TimeStamp string into a datetime.

    The files use two formats. The rule below was checked against every file
    in the dataset (see results/s0/data_inventory.md):
      - 25degC files: "10/28/2018 5:44:00 PM", month first, whole seconds.
        At midnight the time part is missing ("10/26/2018").
      - all other folders: "02/11/2018  6:30:13.000 PM", DAY first, with
        milliseconds.
    So a fractional-seconds part means day first; no fractional part means
    month first. Within the day-first files the whole second sometimes lags
    the fraction (e.g. "17.999" followed by "17.097"), so this clock is only
    good to about 1 s. The Time field is the sample clock to use; TimeStamp
    is for the start date and for finding pauses that Time does not show.
    """
    parts = text.split()
    if len(parts) == 1:
        return datetime.datetime.strptime(parts[0], "%m/%d/%Y")
    joined = " ".join(parts)
    if "." in parts[1]:
        return datetime.datetime.strptime(joined, "%d/%m/%Y %I:%M:%S.%f %p")
    return datetime.datetime.strptime(joined, "%m/%d/%Y %I:%M:%S %p")


def load_mat(path):
    """Load one dataset .mat file as a dict of 1-D arrays keyed by field name.

    Numeric fields become float64 arrays (a few files store some fields as
    uint8; they are converted, and load_mat_details() reports it). TimeStamp
    becomes a 1-D array of str. Signs, NaNs, duplicates and order are kept
    exactly as in the file.
    """
    data, _ = load_mat_details(path)
    return data


def load_mat_details(path):
    """Load one .mat file and also say how it was stored.

    Returns (data, details):
        data: as load_mat()
        details: dict with
            reader: "scipy" for MATLAB v5/v7 files, "h5py" for v7.3 (HDF5) files
            variable: name of the struct variable that was read (normally "meas")
            dtypes: {field name: dtype string as stored in the file}

    scipy.io.loadmat is tried first. It refuses v7.3 files with
    NotImplementedError, and only then is h5py used. Every file in this
    dataset is MATLAB 5.0, so the h5py branch is not exercised by the data.
    """
    try:
        fields, variable = _read_with_scipy(path)
        reader = "scipy"
    except NotImplementedError:
        fields, variable = _read_with_h5py(path)
        reader = "h5py"

    data = {}
    dtypes = {}
    for name, values in fields.items():
        dtypes[name] = str(values.dtype)
        if name == "TimeStamp":
            data[name] = np.array([str(item) for item in values])
        else:
            data[name] = np.asarray(values, dtype=np.float64).ravel()
    details = {"reader": reader, "variable": variable, "dtypes": dtypes}
    return data, details


def _pick_struct_variable(names):
    """Return the variable to read: "meas" if present, else the only variable in the file."""
    if "meas" in names:
        return "meas"
    if len(names) == 1:
        return names[0]
    raise ValueError(f"expected one struct variable (normally 'meas'), found {names}")


def _read_with_scipy(path):
    """Read the struct fields of a v5/v7 file with scipy. Returns ({name: array as stored}, variable)."""
    contents = scipy.io.loadmat(path, squeeze_me=True, struct_as_record=False)
    names = [key for key in contents if not key.startswith("__")]
    variable = _pick_struct_variable(names)
    struct = contents[variable]

    fields = {}
    for name in struct._fieldnames:
        # squeeze_me turns a one-sample field into a scalar; keep everything 1-D.
        fields[name] = np.atleast_1d(getattr(struct, name))
    return fields, variable


def _read_with_h5py(path):
    """Read the struct fields of a v7.3 (HDF5) file. Returns ({name: array as stored}, variable).

    MATLAB writes each struct field as a dataset inside a group, transposed
    (shape (1, n) or (n, 1)). Field order is kept in the group's MATLAB_fields
    attribute when present. A TimeStamp cell array is stored as references to
    uint16 character arrays; a char matrix is stored as uint16 directly.
    """
    with h5py.File(path, "r") as handle:
        names = [key for key in handle.keys() if not key.startswith("#")]
        variable = _pick_struct_variable(names)
        group = handle[variable]

        field_names = list(group.keys())
        if "MATLAB_fields" in group.attrs:
            field_names = []
            for item in group.attrs["MATLAB_fields"]:
                field_names.append(b"".join(item).decode("ascii"))

        fields = {}
        for name in field_names:
            dataset = group[name]
            if name == "TimeStamp":
                fields[name] = np.array(_h5_strings(handle, dataset), dtype=object)
            else:
                fields[name] = np.asarray(dataset[()]).ravel()
    return fields, variable


def _h5_strings(handle, dataset):
    """Decode a MATLAB cell array of char (or a char matrix) stored in HDF5 into a list of str."""
    values = dataset[()]
    strings = []
    if values.dtype == object:
        for reference in values.ravel():
            codes = handle[reference][()].ravel()
            strings.append("".join(chr(int(code)) for code in codes))
    elif values.dtype == np.uint16:
        # A char matrix is stored transposed: one column of the HDF5 array per string.
        matrix = np.atleast_2d(values)
        for column in range(matrix.shape[1]):
            strings.append("".join(chr(int(code)) for code in matrix[:, column]).rstrip())
    else:
        raise ValueError(f"cannot decode TimeStamp stored as {values.dtype}")
    return strings
