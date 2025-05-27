from typing import Tuple, List, Optional
from loguru import logger
from ...devices.ma import MA
from ...devices.pna import PNA
from ...devices.psn import PSN
from ...common.enums import Channel, Direction
from ...common.exceptions import WrongInstrumentError, PlanarScannerError
from PyQt5.QtCore import QThread
import threading

class CheckMA:
    """Класс для проверки антенного модуля"""
    
    def __init__(self, ma: MA, psn: PSN, pna: PNA, stop_event: threading.Event, pause_event: threading.Event):
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
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.ppm_norm_number = 12
        self.ppm_norm_cords = [-14, 1.1]
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        self._last_measurement = None  # (amp, phase) последнего измерения

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

    def _measure_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> Tuple[float, float]:
        """
        Измерение параметров ППМ
        
        Args:
            ppm_num: Номер ППМ (1-32)
            channel: Канал
            direction: Направление
            
        Returns:
            Tuple[float, float]: Амплитуда и фаза
            
        Raises:
            ValueError: При неверном номере ППМ
            WrongInstrumentError: При ошибке измерения
        """
        
        try:
            self.ma.turn_on_ppm(ppm_num=ppm_num, channel=channel, direction=direction)
            amp, phase = self.pna.measampphase()
            self._last_measurement = (amp, phase)  # сохраняем последнее измерение
            return amp, phase
        except Exception as e:
            logger.error(f"Ошибка при измерении ППМ {ppm_num}: {e}")
            raise WrongInstrumentError(f"Ошибка измерения ППМ {ppm_num}: {e}")
        finally:
            self.ma.turn_off_ppm(ppm_num=ppm_num, channel=channel, direction=direction)

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
            
            # Измеряем параметры
            amp, phase = self._measure_ppm(ppm_num, channel, direction)
            
            # Проверяем результаты
            result = True
            if amp < -20:  # Слишком низкий уровень
                logger.warning(f"ППМ {ppm_num}: Низкий уровень сигнала ({amp:.1f} дБ)")
                result = False
                
            if abs(phase) > 180:  # Некорректная фаза
                logger.warning(f"ППМ {ppm_num}: Некорректная фаза ({phase:.1f}°)")
                result = False
                
            if result:
                logger.info(f"ППМ {ppm_num}: OK (amp={amp:.1f} дБ, phase={phase:.1f}°)")
            
            return result, (amp, phase)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке ППМ {ppm_num}: {e}")
            return False, (float('nan'), float('nan'))

    def start(self) -> List[Tuple[int, Tuple[bool, Tuple[float, float]]]]:
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

            # Перемещаемся к нормализующему ППМ
            try:
                self.psn.move(self.ppm_norm_cords[0], self.ppm_norm_cords[1])
            except Exception as e:
                raise PlanarScannerError(f"Ошибка перемещения к нормализующему ППМ: {e}")
            
            # Настраиваем PNA
            self._setup_pna()
            
            # Включаем ВИПы
            self.ma.turn_on_vips()
            
            # Проверяем каждый ППМ
            for i in range(4):
                for j in range(8):
                    if self.stop_event.is_set():
                        logger.info("Измерение остановлено пользователем (в CheckMA.start)")
                        return results

                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        QThread.msleep(100)

                    ppm_num = i * 8 + j + 1
                    logger.info(f"Проверка ППМ {ppm_num}")
                    
                    # Проверяем для каждого канала и направления
                    for channel in Channel:
                        for direction in Direction:
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