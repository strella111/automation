from scipy.fft import ifftshift, ifft2, fftshift
import numpy as np
import scipy as sp
from scipy.interpolate import RectBivariateSpline

# mag = np.loadtxt('mag.csv', delimiter=',')
# phase = np.loadtxt('phase.csv', delimiter=',')

DEG = np.pi / 180
current_params = dict()

def solv_far_field(mag_data: list, phase_data: list, freq, dx, dy, left_az, right_az, d_az,
                   left_el, right_el, d_el):
    mag_data = np.array(mag_data)
    phase_data = np.array(phase_data)
    ampl = 10 ** (0.05 * mag_data)  # амплитудный компонент
    af = ampl * np.exp((phase_data - 180) * DEG * 1j)  # комплексная амплитуда
    lmbd = scipy.constants.c / freq  # длина волны
    k0 = 2 * np.pi / lmbd  # волновое число
    size_m, size_n = af.shape
    MI = int(2 ** (np.ceil(np.log2(size_m)) + 1) * 2)
    NI = int(2 ** (np.ceil(np.log2(size_n)) + 1) * 2)
    m = np.arange(-MI / 2, MI / 2, 1)
    n = np.arange(-NI / 2, NI / 2, 1)
    kx = (2 * np.pi * m) / (MI * dx)
    ky = (2 * np.pi * n) / (NI * dy)

    NF_zeros = np.zeros((MI, NI), dtype=complex)
    start_x = (MI - size_m) // 2
    start_y = (NI - size_n) // 2

    NF_center = NF_zeros.copy()
    NF_center[start_x:start_x + size_m, start_y:start_y + size_n] = af

    az_range = np.arange(left_az * DEG, right_az * DEG + d_az * DEG, d_az * DEG)
    current_params['az_range'] = az_range
    el_range = np.arange(left_el * DEG, right_el * DEG + d_el * DEG, d_el * DEG)
    current_params['el_range'] = el_range

    kx_grid_LUDWIG2 = k0 * np.sin(az_range) * np.cos(el_range)
    ky_grid_LUDWIG2 = k0 * np.sin(el_range)

    fx = ifftshift(ifft2(fftshift(NF_center)))

    kx_sorted_indices = np.argsort(kx)
    ky_sorted_indices = np.argsort(ky)

    kx_sorted = kx[kx_sorted_indices]
    ky_sorted = ky[ky_sorted_indices]

    interp_func = RectBivariateSpline(kx_sorted, ky_sorted, fx.real[np.ix_(kx_sorted_indices, ky_sorted_indices)])
    interp_func_phase = RectBivariateSpline(kx_sorted, ky_sorted, fx.imag[np.ix_(kx_sorted_indices, ky_sorted_indices)])

    fx_ff_LUDWIG2 = interp_func(kx_grid_LUDWIG2, ky_grid_LUDWIG2)
    fx_ff_LUDWIG2_phase = interp_func_phase(kx_grid_LUDWIG2, ky_grid_LUDWIG2)

    fx_interp = fx_ff_LUDWIG2 + 1j * fx_ff_LUDWIG2_phase

    f_ampl = 20 * np.log10(MI * NI * np.abs(fx_interp))
    f_phase = np.rad2deg(np.angle(-fx_interp*1j))

    return f_ampl, f_phase


def get_sections_far_field(f_ampl, f_phase, is_norm = False):
    f_ampl = np.asarray(f_ampl)
    f_phase = np.asarray(f_phase)
    f_norm = f_ampl - np.max(f_ampl) # Нормированная амплитуда в дБ
    max_ampl_ind = np.argmax(f_ampl)
    max_ampl_row_ind, max_ampl_col_ind = np.unravel_index(max_ampl_ind, f_ampl.shape) # Координаты максимальной амплитуды

    # Берем сечения
    if is_norm:
        az_section_ampl = f_norm[max_ampl_row_ind, :]
        el_section_ampl = f_norm[:, max_ampl_col_ind]
    else:
        az_section_ampl = f_ampl[max_ampl_row_ind, :]
        el_section_ampl = f_ampl[:, max_ampl_col_ind]
    az_section_phase = f_phase[max_ampl_row_ind, :]
    el_section_phase = f_phase[:, max_ampl_col_ind]

    return az_section_ampl, az_section_phase, el_section_ampl, el_section_phase

