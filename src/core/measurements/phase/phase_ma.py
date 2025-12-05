from loguru import logger
from core.devices.ma import MA
from core.devices.pna  import PNA
from core.devices.psn  import PSN
from core.common.enums import Channel, Direction, PhaseDir, PpmState
from core.common.exceptions import WrongInstrumentError, PlanarScannerError
from utils.excel_module import CalibrationCSV
from PyQt5.QtCore import QThread

class PhaseMaMeas:
    """Класс для измерения и настройки фаз в антенном модуле"""
    
    def __init__(self, ma: MA, psn: PSN, pna: PNA, point_callback=None, stop_flag=None):
        """
        Инициализация класса
        
        Args:
            ma: Модуль антенный
            psn: Позиционер
            pna: Анализатор цепей
            point_callback: Функция обратного вызова для обновления результатов
            stop_flag: Флаг для остановки измерений
            
        Raises:
            ValueError: Если какой-либо из параметров None
        """
        self.norm_phase = None
        if not all([ma, psn, pna]):
            raise ValueError("Все устройства должны быть указаны")
            
        self.ma = ma
        self.psn = psn
        self.pna = pna
        self.ppm_norm_number = 12
        self.ppm_norm_cords = [-14, 1.1]
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        self.point_callback = point_callback
        self.stop_flag = stop_flag
        self.pause_flag = None
        self.norm_amp = None

        self.phase_results = []

        self.calibration_csv = None
        if hasattr(ma, 'bu_addr') and ma.bu_addr:
            self.calibration_csv = CalibrationCSV(ma.bu_addr)

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



    def _find_best_phase(self, ppm_num: int,chanel: Channel, direction: Direction, initial_phase: float, i: int, j: int, amp: float) -> int:
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
                                    chanel=chanel,
                                    direction=direction,
                                    value=value)
            _, phase_first = self.pna.get_center_freq_data(wait=True)
            phase_first -= self.norm_phase
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
                                        direction=direction,
                                        chanel=chanel,
                                        value=new_value)
                _, phase_iter = self.pna.get_center_freq_data(wait=True)
                phase_iter -= self.norm_phase
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

    def start(self, chanel: Channel, direction: Direction) -> None:
        """
        Запуск процесса измерения и настройки фаз
        
        Raises:
            ConnectionError: При отсутствии подключения устройств
            WrongInstrumentError: При ошибке работы с устройствами
            PlanarScannerError: При ошибке перемещения
        """
        try:
            self.phase_results = []
            
            if not self._check_connections():
                raise ConnectionError("Не все устройства подключены")
            try:
                self.psn.move(self.ppm_norm_cords[0], self.ppm_norm_cords[1])
            except Exception as e:
                raise PlanarScannerError(f"Ошибка перемещения к нормализующему ППМ: {e}")

            self.pna.set_output(True)
            self.ma.turn_on_vips()
            self.pna.set_ascii_data()
            logger.info("Нормировка PNA...")
            self.ma.switch_ppm(self.ppm_norm_number, chanel=chanel, direction=direction, state=PpmState.ON)
            self.ma.set_phase_shifter(self.ppm_norm_number, chanel=chanel, direction=direction, value=0)
            self.ma.set_delay(chanel, direction=direction, value=0)
            _ , self.norm_phase = self.pna.get_center_freq_data(wait=True)
            self.ma.switch_ppm(self.ppm_norm_number, chanel=chanel, direction=direction, state=PpmState.OFF)

            for i in range(4):
                for j in range(8):
                    if self.stop_flag and self.stop_flag.is_set():
                        logger.info("Измерение остановлено пользователем")
                        if self.calibration_csv and len(self.phase_results) > 0:
                            while len(self.phase_results) < 32:
                                self.phase_results.append(0)
                            try:
                                self.calibration_csv.save_phase_results(
                                    channel=chanel,
                                    direction=direction,
                                    phase_results=self.phase_results
                                )
                                logger.info(f"Частичные результаты фазировки сохранены в файл: {self.calibration_csv.get_file_path()}")
                            except Exception as e:
                                logger.error(f"Ошибка при сохранении частичных результатов в CSV: {e}")
                        return

                    while self.pause_flag and self.pause_flag.is_set():
                        if self.stop_flag and self.stop_flag.is_set():
                            break
                        QThread.msleep(100)

                    ppm_num = i * 8 + j + 1
                    logger.info(f"Фазировка ППМ№ {ppm_num}")
                    
                    try:
                        self.psn.move(self.x_cords[i], self.y_cords[j])
                    except Exception as e:
                        raise PlanarScannerError(f"Ошибка перемещения к ППМ {ppm_num}: {e}")

                    self.ma.switch_ppm(ppm_num=ppm_num, chanel=chanel, direction=direction, state=PpmState.ON)
                    amp_zero, phase_zero = self.pna.get_center_freq_data(wait=True)
                    phase_zero -= self.norm_phase
                    if phase_zero < 0:
                        phase_zero += 360
                    if self.point_callback:
                        self.point_callback(i, j, self.x_cords[i], self.y_cords[j], amp_zero, phase_zero)
                    
                    best_value = self._find_best_phase(ppm_num,chanel, direction, phase_zero, i, j, amp_zero)

                    self.phase_results.append(best_value)
                    
                    self.ma.set_phase_shifter(ppm_num=ppm_num,
                                            chanel=chanel,
                                            direction=direction,
                                            value=best_value)
                    
                    self.ma.switch_ppm(ppm_num=ppm_num,
                                       chanel=chanel,
                                       direction=direction,
                                       state=PpmState.OFF)

            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")

            if self.calibration_csv and len(self.phase_results) == 32:
                try:
                    self.calibration_csv.save_phase_results(
                        channel=chanel,
                        direction=direction,
                        phase_results=self.phase_results
                    )
                    logger.info(f"Результаты фазировки сохранены в файл: {self.calibration_csv.get_file_path()}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении результатов в CSV: {e}")
            elif len(self.phase_results) != 32:
                logger.warning(f"Ожидалось 32 результата, получено {len(self.phase_results)}. CSV не сохранен.")
                
            logger.info("Измерение и настройка фаз завершены успешно")

        except Exception as e:
            logger.error(f"Ошибка при выполнении измерений: {e}")
            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise 