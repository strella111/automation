from typing import Tuple
from loguru import logger
from ...devices.ma import MA
from ...devices.pna import PNA
from ...devices.psn import PSN
from ...common.enums import Channel, Direction, PhaseDir
from ...common.exceptions import WrongInstrumentError, PlanarScannerError
from PyQt5.QtCore import QThread

class PhaseMaMeas:
    """Класс для измерения и настройки фаз в антенном модуле"""
    
    def __init__(self, ma: MA, psn: PSN, pna: PNA, channel: Channel, direction: Direction, point_callback=None, stop_flag=None):
        """
        Инициализация класса
        
        Args:
            ma: Модуль антенный
            psn: Позиционер
            pna: Анализатор цепей
            channel: Канал (приемник/передатчик)
            direction: Направление (горизонтальное/вертикальное)
            point_callback: Функция обратного вызова для обновления результатов
            stop_flag: Флаг для остановки измерений
            
        Raises:
            ValueError: Если какой-либо из параметров None
        """
        if not all([ma, psn, pna]):
            raise ValueError("Все устройства должны быть указаны")
            
        self.ma = ma
        self.psn = psn
        self.pna = pna
        self.ppm_norm_number = 12
        self.ppm_norm_cords = [-14, 1.1]
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        self.channel = channel
        self.direction = direction
        self.point_callback = point_callback
        self.stop_flag = stop_flag
        self.pause_flag = None

    def set_pause_flag(self, flag):
        """Установить флаг паузы"""
        self.pause_flag = flag

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
            ValueError: При неверном канале
        """
        try:
            self.pna.preset()
            if self.channel == Channel.Receiver:
                self.pna.load_settings_file()
                self.pna.set_power(1, 0)
            elif self.channel == Channel.Transmitter:
                self.pna.load_settings_file()
                self.pna.set_power(2, 12)
            else:
                raise ValueError('Не выбран канал')
            self.pna.power_on()
        except Exception as e:
            logger.error(f"Ошибка при настройке PNA: {e}")
            raise WrongInstrumentError(f"Ошибка настройки PNA: {e}")

    def _measure_phase(self, ppm_num: int) -> Tuple[float, float]:
        """
        Измерение фазы для конкретного ППМ
        
        Args:
            ppm_num: Номер ППМ (1-32)
            
        Returns:
            Tuple[float, float]: Амплитуда и фаза
            
        Raises:
            ValueError: При неверном номере ППМ
            WrongInstrumentError: При ошибке измерения
        """
        try:
            self.ma.turn_on_ppm(ppm_num=ppm_num, channel=self.channel, direction=self.direction)
            amp_zero, phase_zero = self.pna.measampphase()
            if phase_zero < 0:
                phase_zero += 360
            return amp_zero, phase_zero
        except Exception as e:
            logger.error(f"Ошибка при измерении фазы для ППМ {ppm_num}: {e}")
            raise WrongInstrumentError(f"Ошибка измерения фазы для ППМ {ppm_num}: {e}")

    def _find_best_phase(self, ppm_num: int, initial_phase: float, i: int, j: int, amp: float) -> int:
        """
        Поиск оптимального значения фазы
        Args:
            ppm_num: Номер ППМ (1-32)
            initial_phase: Начальная фаза
            i: Индекс строки
            j: Индекс столбца
            amp: Амплитуда
        Returns:
            int: Оптимальное значение фазы
        Raises:
            ValueError: При неверном номере ППМ
            WrongInstrumentError: При ошибке поиска фазы
        """
        try:
            value = int(initial_phase // 5.625)
            self.ma.set_phase_shifter(ppm_num=ppm_num,
                                    channel=self.channel,
                                    direction=self.direction,
                                    value=value)
            _, phase_first = self.pna.measampphase()
            if self.point_callback:
                self.point_callback(i, j, self.x_cords[i], self.y_cords[j], amp, phase_first)
            dir = PhaseDir.DOWN if phase_first < 0 else PhaseDir.UP
            phase_vals = [0, value]
            phase_list = [initial_phase, phase_first]
            new_value = value
            while True:
                if dir == PhaseDir.DOWN:
                    new_value = 63 if new_value == 0 else new_value - 1
                else:
                    new_value = 0 if new_value == 63 else new_value + 1
                phase_vals.append(new_value)
                self.ma.set_phase_shifter(ppm_num=ppm_num,
                                        direction=self.direction,
                                        channel=self.channel,
                                        value=new_value)
                _, phase_iter = self.pna.measampphase()
                phase_list.append(phase_iter)
                if self.point_callback:
                    self.point_callback(i, j, self.x_cords[i], self.y_cords[j], amp, phase_iter)
                if phase_iter * phase_first <= 0:
                    break
            phase_best = initial_phase
            best_value = 0
            for k, phase in enumerate(phase_list):
                if abs(phase) < abs(phase_best):
                    phase_best = phase
                    best_value = phase_vals[k]
            if self.point_callback:
                self.point_callback(i, j, self.x_cords[i], self.y_cords[j], amp, phase_best)
            return best_value
        except Exception as e:
            logger.error(f"Ошибка при поиске оптимальной фазы для ППМ {ppm_num}: {e}")
            raise WrongInstrumentError(f"Ошибка поиска оптимальной фазы для ППМ {ppm_num}: {e}")

    def start(self) -> None:
        """
        Запуск процесса измерения и настройки фаз
        
        Raises:
            ConnectionError: При отсутствии подключения устройств
            WrongInstrumentError: При ошибке работы с устройствами
            PlanarScannerError: При ошибке перемещения
        """
        try:
            if not self._check_connections():
                raise ConnectionError("Не все устройства подключены")
            try:
                self.psn.move(self.ppm_norm_cords[0], self.ppm_norm_cords[1])
            except Exception as e:
                raise PlanarScannerError(f"Ошибка перемещения к нормализующему ППМ: {e}")
            
            self._setup_pna()
            
            self.ma.turn_on_vips()
            
            self.ma.set_delay(self.channel, 0)

            for i in range(4):
                for j in range(8):
                    # Проверяем флаг остановки
                    if self.stop_flag and self.stop_flag.is_set():
                        logger.info("Измерение остановлено пользователем")
                        return

                    # Проверяем флаг паузы
                    while self.pause_flag and self.pause_flag.is_set():
                        if self.stop_flag and self.stop_flag.is_set():
                            break
                        QThread.msleep(100)

                    ppm_num = i * 8 + j + 1
                    logger.info(f"Фазировка ППМ№ {ppm_num}")
                    
                    # Перемещаемся к ППМ
                    try:
                        self.psn.move(self.x_cords[i], self.y_cords[j])
                    except Exception as e:
                        raise PlanarScannerError(f"Ошибка перемещения к ППМ {ppm_num}: {e}")
                    
                    # Измеряем начальную фазу
                    amp, phase_zero = self._measure_phase(ppm_num)
                    if self.point_callback:
                        self.point_callback(i, j, self.x_cords[i], self.y_cords[j], amp, phase_zero)
                    
                    # Находим оптимальное значение фазы
                    best_value = self._find_best_phase(ppm_num, phase_zero, i, j, amp)
                    
                    # Устанавливаем оптимальное значение
                    self.ma.set_phase_shifter(ppm_num=ppm_num,
                                            channel=self.channel,
                                            direction=self.direction,
                                            value=best_value)
                    
                    # Выключаем ППМ
                    self.ma.turn_off_ppm(ppm_num=ppm_num, 
                                       channel=self.channel, 
                                       direction=self.direction)

            # Завершаем работу
            try:
                self.pna.power_off()
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")
                
            logger.info("Измерение и настройка фаз завершены успешно")

        except Exception as e:
            logger.error(f"Ошибка при выполнении измерений: {e}")
            # Пытаемся безопасно завершить работу
            try:
                self.pna.power_off()
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise 