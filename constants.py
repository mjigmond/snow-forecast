from scipy.interpolate import interp1d


INCHES = {  # Conversion factor from model units to inches
    "hrrr": 3.28084 * 12,
    "gfs": 1 / 25.4,
    "aifs": 1 / 25.4,
    "ifs": 3.28084 * 12,
}
VALID_MODELS = ["hrrr", "gfs", "aifs", "ifs"]
PRODUCT = {
    "hrrr": "sfc",
    "gfs": "pgrb2.0p25",
    "aifs": "oper",
    "ifs": "oper",
}
VARIABLE = {
    "hrrr": "ASNOW",
    "gfs": "WEASD",
    "aifs": "sf",
    "ifs": "tp",
}
RESOLUTION = {
    "hrrr": 300,
    "gfs": .01,
    "aifs": .01,
    "ifs": .01,
}
PROVIDER_DOMAINS = {
    'verizon': 'mypixmessages.com',
    'at&t': 'mms.att.net',
    't-mobile': 'tmomail.net'
}
FXX = {
    "hrrr": 48,
    "gfs": 16 * 24,
    "aifs": 15 * 24,
    "ifs": 15 * 24,
}

C2F = 9 / 5.
REF_T = [-33, 0, 5, 19.33, 32, 50]
REF_STL = [18, 18, 17, 13, 10, 10]
IPF = interp1d(REF_T, [REF_STL], axis=1)
