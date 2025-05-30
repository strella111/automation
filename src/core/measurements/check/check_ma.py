from typing import Tuple, List, Optional
from loguru import logger
from ...devices.ma import MA
from ...devices.pna import PNA
from ...devices.psn import PSN
from ...common.enums import Channel, Direction
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
        
        self.ppm_norm_number = 12
        self.ppm_norm_cords = [-14, 1.1]
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        self._last_measurement = None 
        self.channel = None
        self.direction = None

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

    def _setup_pna(self) -> None:
        """
        Настройка анализатора цепей
        
        Raises:
            WrongInstrumentError: При ошибке настройки PNA
        """
        try:
            self.pna.preset()
            self.pna.load_settings_file()
            self.pna.set_power(1, 0)
            self.pna.power_on()
        except Exception as e:
            logger.error(f"Ошибка при настройке PNA: {e}")
            raise WrongInstrumentError(f"Ошибка настройки PNA: {e}")

    def _check_phase_diff(self, phase_diff: float, channel: Channel) -> bool:
        """Проверяет разность фаз в соответствии с требованиями для канала"""
        if channel == Channel.Receiver:
            return self.rx_phase_diff_min <= phase_diff <= self.rx_phase_diff_max
        else:  # Transmitter
            return self.tx_phase_diff_min < phase_diff < self.tx_phase_diff_max
            
    def _check_amplitude(self, amp_zero: float, amp_all: float, channel: Channel) -> bool:
        """Проверяет амплитуду в соответствии с требованиями для канала"""
        amp_min = min(amp_zero, amp_all)
        amp_max = max(amp_zero, amp_all)
        
        if channel == Channel.Receiver:
            return -self.rx_amp_max <= amp_min and amp_max <= self.rx_amp_max
        else:  # Transmitter
            return -self.tx_amp_max <= amp_min and amp_max <= self.tx_amp_max
            
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
        
    def _check_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> tuple[bool, tuple[float, float]]:
        """Проверяет один ППМ"""
        try:
            # Включаем ППМ
            self.ma.switch_ppm(ppm_num, direction, channel, True)
            
            # Устанавливаем ФВ в нулевое положение
            self.ma.set_phase_shifter(ppm_num, direction, channel, 0)
            
            # Измеряем амплитуду и фазу в нулевом положении
            amp_zero, phase_zero = self.pna.measure()
            
            # Устанавливаем максимальное значение ФВ
            self.ma.set_phase_shifter(ppm_num, direction, channel, 63)
            
            # Измеряем амплитуду и фазу с включенным ФВ
            amp_all, phase_all = self.pna.measure()
            
            # Вычисляем разность фаз
            phase_diff = self._calculate_phase_diff(phase_all, phase_zero)
            
            # Проверяем разность фаз
            phase_ok = self._check_phase_diff(phase_diff, channel)
            
            # Проверяем амплитуду
            amp_ok = self._check_amplitude(amp_zero, amp_all, channel)
            
            # Если фаза не прошла проверку, проверяем дискреты
            phase_vals = []
            if not phase_ok:
                for shift in self.phase_shifts:
                    value = int(shift / 5.625)  # Конвертируем градусы в код ФВ
                    self.ma.set_phase_shifter(ppm_num, direction, channel, value)
                    _, phase_err = self.pna.measure()
                    phase_vals.append(self._calculate_phase_diff(phase_err, phase_zero))
            
            # Общий результат проверки
            result = phase_ok and amp_ok
            
            # Возвращаем результат и измерения
            return result, (amp_all, phase_all)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке ППМ {ppm_num}: {e}")
            return False, (np.nan, np.nan)
        finally:
            # Выключаем ППМ
            self.ma.switch_ppm(ppm_num, direction, channel, False)

    def check_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> Tuple[bool, Tuple[float, float]]:
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
            # Перемещаемся к ППМ
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
            return False, (float('nan'), float('nan'))

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
            
            self._setup_pna()
            
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
                self.pna.power_off()
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")
                
            logger.info("Проверка ППМ завершена")

        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки: {e}")
            # Пытаемся безопасно завершить работу
            try:
                self.pna.power_off()
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise
            
        return results 