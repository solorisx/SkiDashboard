import numpy as np
from scipy.signal import find_peaks

def get_turning_points(data, prominence=100):
    peaks = find_peaks(data, prominence=100)
    mirror = (np.array(data) * - 1) + 10000 # only works for positive data
    valleys = find_peaks(mirror, prominence=100)
    result = []
    for idx in peaks[0]:
        result.append((idx, 'peak'))
    for idx in valleys[0]:
        result.append((idx, 'valley'))
    result.sort(key=lambda x: x[0])
    return result