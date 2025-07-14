from typing import Tuple, List, Optional
from loguru import logger
from ...devices.ma import MA
from ...devices.pna import PNA
from ...devices.psn import PSN
from core.common.enums import Channel, Direction, PpmState
from ...common.exceptions import WrongInstrumentError, PlanarScannerError
from PyQt5.QtCore import QThread
import threading
import numpy as np

class CheckMA:
    """Класс для проверки антенного модуля"""
    def __init__(self, ma: MA,
                 psn: PSN,
                 pna: PNA,
                 stop_event: threading.Event = None,
                 pause_event: threading.Event = None):
        """
        Инициализация класса
        
        Args:
            ma: Модуль антенный
            psn: Позиционер
            pna: Анализатор цепей
            stop_event: Событие для остановки измерений
            pause_event: Событие для приостановки измерений
            
        Raises:
            ValueError: Если какой-либо из параметров None
        """
        if not all([ma, psn, pna, stop_event, pause_event]):
            raise ValueError("Все устройства и события должны быть указаны")
            
        self.ma = ma
        self.psn = psn
        self.pna = pna
        self._stop_event = stop_event or threading.Event()
        self._pause_event = pause_event or threading.Event()
        
        # Параметры проверки
        self.rx_phase_diff_max = 12  # Максимальная разность фаз для RX
        self.rx_phase_diff_min = 2   # Минимальная разность фаз для RX
        self.tx_phase_diff_max = 20  # Максимальная разность фаз для TX
        self.tx_phase_diff_min = 2   # Минимальная разность фаз для TX
        self.rx_amp_max = 4.5        # Максимальная амплитуда для RX
        self.tx_amp_max = 2.5        # Максимальная амплитуда для TX
        
        # Дискреты ФВ для проверки
        self.phase_shifts = [5.625, 11.25, 22.5, 45, 90, 180]
        
        # Допуски для отдельных фазовращателей (будут переданы из интерфейса)
        self.phase_shifter_tolerances = None
        
        self.ppm_norm_number = 12
        self.ppm_norm_cords = [-14, 1.1]
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        self._last_measurement = None 
        self.channel = None
        self.direction = None
        
        # Нормировочные значения (будут установлены при нормировке)
        self.norm_amp = None
        self.norm_phase = None

    def _check_connections(self) -> bool:
        """
        Проверка подключения всех устройств
        
        Returns:
            bool: True если все устройства подключены, False в противном случае
        """
        if not all([self.pna.connection, self.ma.connection, self.psn.connection]):
            logger.error("Не все устройства подключены")
            return False
        return True


    def _check_phase_diff(self, phase_diff: float, channel: Channel) -> bool:
        """Проверяет разность фаз в соответствии с требованиями для канала"""
        if channel == Channel.Receiver:
            return self.rx_phase_diff_min <= phase_diff <= self.rx_phase_diff_max
        else:  # Transmitter
            return self.tx_phase_diff_min < phase_diff < self.tx_phase_diff_max
            
    def _check_individual_phase_shifter(self, phase_diff: float, expected_angle: float, tolerances=None) -> bool:
        """Проверяет отдельный фазовращатель с учетом его ожидаемого угла и допусков"""
        if tolerances and expected_angle in tolerances:
            min_tolerance = tolerances[expected_angle]['min']
            max_tolerance = tolerances[expected_angle]['max']
            return min_tolerance <= phase_diff <= max_tolerance
        else:
            # Допуски по умолчанию ±2°
            return -2.0 <= phase_diff <= 2.0
            
    def _check_amplitude(self, amp_current: float, channel: Channel) -> bool:
        """Проверяет амплитуду относительно нормировочного значения"""
        if self.norm_amp is None:
            logger.warning("Нормировочное значение амплитуды не установлено")
            return False
            
        amp_diff = amp_current - self.norm_amp  # Разность с нормировочным значением
        
        if channel == Channel.Receiver:
            return -self.rx_amp_max <= amp_diff <= self.rx_amp_max
        else:  # Transmitter
            return -self.tx_amp_max <= amp_diff <= self.tx_amp_max
            
    def _normalize_phase(self, phase: float) -> float:
        """Нормализует фазу в диапазон [-180, 180]"""
        while phase > 180:
            phase -= 360
        while phase < -180:
            phase += 360
        return phase
            
    def _calculate_phase_diff(self, phase_all: float, phase_zero: float) -> float:
        """Вычисляет разность фаз с учетом нормализации"""
        phase_diff = self._normalize_phase(phase_all - phase_zero)
        return phase_diff
        
    def _check_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> tuple[bool, tuple[float, float, list]]:
        """Проверяет один ППМ согласно новой логике"""
        try:
            self.ma.switch_ppm(ppm_num, channel, direction, PpmState.ON)
            self.ma.set_phase_shifter(ppm_num, channel, direction, 0)

            # Измеряем нормировочные значения (ФВ = 0)
            amp_zero, phase_zero = self.pna.get_center_freq_data()

            # Устанавливаем максимальное значение ФВ (все включены)
            self.ma.set_phase_shifter(ppm_num, channel, direction, 63)
            
            # Измеряем амплитуду и фазу с включенными всеми ФВ
            amp_all, phase_all = self.pna.get_center_freq_data()
            
            # Вычисляем разности
            amp_diff = amp_all - self.norm_amp if self.norm_amp is not None else amp_all
            phase_diff = self._calculate_phase_diff(phase_all, phase_zero)
            
            # Проверяем амплитуду относительно нормировочного значения
            amp_ok = self._check_amplitude(amp_all, channel)
            
            # Проверяем фазу при включении всех ФВ
            phase_all_ok = self._check_phase_diff(phase_diff, channel)
            
            # Инициализируем список значений ФВ
            phase_vals = [phase_diff]
            
            # Определяем финальный статус фазы
            if phase_all_ok:
                # Если все ФВ вместе прошли проверку - статус OK
                phase_final_ok = True
                # Заполняем остальные значения как NaN (не измерялись)
                phase_vals.extend([np.nan] * 6)
            else:
                                 # Если все ФВ вместе не прошли, проверяем каждый ФВ отдельно
                 fv_angles = [5.625, 11.25, 22.5, 45, 90, 180]
                 individual_fv_results = []
                 
                 for fv_angle in fv_angles:
                     value = int(fv_angle / 5.625)
                     self.ma.set_phase_shifter(ppm_num, channel, direction, value)
                     _, phase_fv = self.pna.get_center_freq_data()
                     phase_fv_diff = self._calculate_phase_diff(phase_fv, phase_zero)
                     phase_vals.append(phase_fv_diff)
                     
                     # Проверяем каждый ФВ отдельно с его собственными допусками
                     fv_ok = self._check_individual_phase_shifter(phase_fv_diff, fv_angle, self.phase_shifter_tolerances)
                     individual_fv_results.append(fv_ok)
                 
                 # Все отдельные ФВ должны пройти проверку для статуса OK
                 phase_final_ok = all(individual_fv_results)

            # Общий результат: и амплитуда, и фаза должны быть OK
            result = amp_ok and phase_final_ok

            return result, (amp_diff, phase_diff, phase_vals)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке ППМ {ppm_num}: {e}")
            return False, (np.nan, np.nan, [np.nan])
        finally:
            self.ma.switch_ppm(ppm_num, channel, direction, PpmState.OFF)

    def check_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> Tuple[bool, Tuple[float, float, List[float]]]:
        """
        Проверка работоспособности ППМ
        
        Args:
            ppm_num: Номер ППМ (1-32)
            channel: Канал
            direction: Направление
            
        Returns:
            Tuple[bool, Tuple[float, float]]: (результат проверки, (амплитуда, фаза))
            
        Raises:
            ValueError: При неверном номере ППМ
            PlanarScannerError: При ошибке перемещения
        """
        try:
            i = (ppm_num - 1) // 8
            j = (ppm_num - 1) % 8
            try:
                self.psn.move(self.x_cords[i], self.y_cords[j])
            except Exception as e:
                raise PlanarScannerError(f"Ошибка перемещения к ППМ {ppm_num}: {e}")
            
            result, measurements = self._check_ppm(ppm_num, channel, direction)

            if result:
                logger.info(f"ППМ {ppm_num}: OK (amp={measurements[0]:.1f} дБ, phase={measurements[1]:.1f}°)")
            
            return result, measurements
            
        except Exception as e:
            logger.error(f"Ошибка при проверке ППМ {ppm_num}: {e}")
            return False, (np.nan, np.nan, [np.nan for _ in range(6)])

    def start(self, channel: Channel, direction: Direction) -> List[Tuple[int, Tuple[bool, Tuple[float, float]]]]:
        """
        Запуск проверки всех ППМ
        
        Returns:
            List[Tuple[int, Tuple[bool, Tuple[float, float]]]]: 
            Список кортежей (номер ППМ, (результат проверки, (амплитуда, фаза)))
            
        Raises:
            ConnectionError: При отсутствии подключения устройств
            WrongInstrumentError: При ошибке работы с устройствами
        """
        results = []
        try:
            if not self._check_connections():
                raise ConnectionError("Не все устройства подключены")

            try:
                self.psn.move(self.ppm_norm_cords[0], self.ppm_norm_cords[1])
            except Exception as e:
                raise PlanarScannerError(f"Ошибка перемещения к нормализующему ППМ: {e}")
            
            try:
                logger.info("Нормировка PNA...")
                self.norm_amp, self.norm_phase = self.pna.get_center_freq_data()
                logger.info(f"Нормировочные значения: амплитуда={self.norm_amp:.2f} дБ, фаза={self.norm_phase:.1f}°")
            except Exception as e:
                logger.warning(f"Ошибка при нормировке PNA: {e}")
                self.norm_amp = None
                self.norm_phase = None
            
            self.ma.turn_on_vips()
            
            for i in range(4):
                for j in range(8):
                    if self._stop_event.is_set():
                        logger.info("Измерение остановлено пользователем (в CheckMA.start)")
                        return results

                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        QThread.msleep(100)

                    ppm_num = i * 8 + j + 1
                    logger.info(f"Проверка ППМ {ppm_num}")
                    
                    result, measurements = self.check_ppm(ppm_num, channel, direction)
                    results.append((ppm_num, (result, measurements)))

            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")
                
            logger.info("Проверка ППМ завершена")

        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки: {e}")
            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise
            
        return results 