import os
import time

import openpyxl
from loguru import logger
from pathlib import Path
from PyQt5.QtCore import QThread
from config.settings_manager import get_main_settings

from core.devices.afar import Afar
from core.devices.pna import PNA
from core.devices.psn import PSN
from core.common.enums import Channel, Direction, PhaseDir, PpmState
from core.common.exceptions import WrongInstrumentError, PlanarScannerError
from utils.excel_module import CalibrationCSV





class PhaseAfar:

    def __init__(self, afar: Afar, psn: PSN, pna: PNA, point_callback = None, norm_callback = None):
        self.afar = afar
        self.psn = psn
        self.pna = pna

        self.pna_period = 0.002
        self.pna_amount_points = 11

        self.stop_flag = None
        self.pause_flag = None
        self.point_callback = point_callback
        self.norm_callback = norm_callback  # Callback для передачи амплитуды нормировки

        self.norm_phase = None

        # self.offset_x_list = [0, 14.016, 0, 14.016, 0, 14.016, 0, 14.016,
        #             112.128, 126.144, 112.128, 126.144, 112.128, 126.144, 112.128, 126.144,
        #             224.256, 238.272, 224.256, 238.272, 224.256, 238.272, 224.256, 238.272,
        #             336.384, 350.4, 336.384, 350.4, 336.384, 350.4, 336.384, 350.4,
        #             448.512, 462.528, 448.512, 462.528, 448.512, 462.528, 448.512, 462.528]


        self.offset_x_list = [14.016, 0, 14.016, 0, 14.016, 0, 14.016, 0,
                              126.144, 112.128, 126.144, 112.128, 126.144, 112.128, 126.144, 112.128,
                              238.272, 224.256, 238.272, 224.256, 238.272, 224.256, 238.272, 224.256,
                              350.4, 336.384, 350.4, 336.384, 350.4, 336.384, 350.4, 336.384,
                              462.528, 448.512, 462.528, 448.512, 462.528, 448.512, 462.528, 448.512]


        self.offset_y_list = [0, -17.76, -35.52, -53.28, -71.04, -88.8, -106.56, -124.32,
                    0, -17.76, -35.52, -53.28, -71.04, -88.8, -106.56, -124.32,
                    0, -17.76, -35.52, -53.28, -71.04, -88.8, -106.56, -124.32,
                    0, -17.76, -35.52, -53.28, -71.04, -88.8, -106.56, -124.32,
                    0, -17.76, -35.52, -53.28, -71.04, -88.8, -106.56, -124.32]

        self.offset_y_list.reverse()

        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.77, 5.55, 3.33, 1.11, -1.11, -3.33, -5.55, -7.77]

        # self.x_cords = [-43.216, -15.184, 12.848, 40.88]
        # self.y_cords = [7.77, 5.55, 3.33, 1.11, -1.11, -3.33, -5.55, -7.77]

        self.ppm_norm_number = 12
        self.bu_norm_number = 1
        self.norm_amplitude = None  # Амплитуда нормировочного ППМ (для передачи в UI)
        
        self.turn_off_vips = True  # Выключать ВИПы в конце измерения
        self.enable_delay_line_calibration = False  # Фазировать линии задержки
        
        self.calibration_csv = None
        self.delay_line_discretes = {}  # {bu_num: [16 значений для ЛЗ 0-15]}


    def set_pause_flag(self, flag):
        """Установить флаг паузы"""
        self.pause_flag = flag
    
    def _measure_delay_lines(self, bu_num: int, ppm_num: int, chanel: Channel, direction: Direction) -> list:
        """
        Измеряет фазовые сдвиги для всех линий задержки (0-15) и конвертирует в дискреты
        
        Args:
            bu_num: Номер БУ (модуля)
            ppm_num: Номер ППМ (обычно 12 - нормировочный)
            chanel: Канал (передатчик/приемник)
            direction: Поляризация
            
        Returns:
            list: Массив из 16 значений дискретов для ЛЗ 0-15
            
        Raises:
            WrongInstrumentError: При ошибке измерения
        """
        logger.info(f"Начало измерения линий задержки для БУ №{bu_num}, ППМ №{ppm_num}")
        
        try:
            discretes = []
            phase_lz0 = None

            for lz in range(16):
                self.afar.set_delay(bu_num=bu_num, chanel=chanel, direction=direction, value=lz)
                _, phase_lz = self.pna.get_center_freq_data(wait=True)

                if phase_lz < 0:
                    phase_lz += 360
                
                logger.debug(f"БУ №{bu_num}, ППМ №{ppm_num}, ЛЗ={lz}: фаза={phase_lz:.2f}°")
                
                if lz == 0:
                    phase_lz0 = phase_lz
                    discretes.append(0)
                else:
                    delta_phase = phase_lz - phase_lz0

                    if delta_phase < 0:
                        delta_phase += 360

                    discrete_value = int(delta_phase // 5.625)
                    logger.info(f'ЛЗ{lz} - дельта {delta_phase}')
                    
                    logger.info(f"БУ №{bu_num}, ЛЗ={lz}: Δфаза={delta_phase:.2f}°, дискреты={discrete_value}")
                    discretes.append(discrete_value)
                logger.info(f'Список дискретов {discretes}')

            self.afar.set_delay(bu_num=bu_num, chanel=chanel, direction=direction, value=0)
            
            logger.info(f"Измерение ЛЗ для БУ №{bu_num} завершено: {discretes}")
            return discretes
            
        except Exception as e:
            logger.error(f"Ошибка при измерении линий задержки для БУ №{bu_num}: {e}")
            raise WrongInstrumentError(f"Ошибка измерения линий задержки: {e}")

    def _check_connections(self) -> bool:
        """
        Проверка подключения всех устройств

        Returns:
            bool: True если все устройства подключены, False в противном случае
        """
        if not all([self.pna.connection, self.afar.connection, self.psn.connection]):
            logger.error("Не все устройства подключены")
            return False
        return True

    def _find_best_phase(self,
                         bu_num: int,
                         ppm_num: int,
                         chanel: Channel,
                         direction: Direction,
                         initial_phase: float,
                         i: int,
                         j: int,
                         amp: float) -> int:
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
            # В тестовом режиме используем упрощенную логику
            if self.pna.mode != 0:  # Тестовый режим
                # В тестовом режиме просто возвращаем случайное значение от 0 до 63
                import random
                best_value = random.randint(0, 63)
                logger.debug(f"Тестовый режим: для ППМ {ppm_num} выбрано случайное значение фазы {best_value}")
                if self.point_callback:
                    real_x = self.x_cords[i] + self.offset_x_list[bu_num-1]
                    real_y = self.y_cords[j] + self.offset_y_list[bu_num-1]
                    self.point_callback(i, j, real_x, real_y, amp, 0, bu_num)
                return best_value

            value = int(initial_phase // 5.625)
            self.afar.set_phase_shifter(bu_num=bu_num,
                                        ppm_num=ppm_num,
                                        chanel=chanel,
                                        direction=direction,
                                        value=value)
            _, phase_first = self.pna.get_center_freq_data(wait=True)
            phase_first -= self.norm_phase
            if self.point_callback:
                real_x = self.x_cords[i] + self.offset_x_list[bu_num-1]
                real_y = self.y_cords[j] + self.offset_y_list[bu_num-1]
                self.point_callback(i, j, real_x, real_y, amp, phase_first, bu_num)

            dir = PhaseDir.DOWN if phase_first < 0 else PhaseDir.UP
            phase_vals = [0, value]
            phase_list = [initial_phase, phase_first]
            new_value = value
            max_iterations = 64
            iteration_count = 0
            
            while iteration_count < max_iterations:
                if dir == PhaseDir.DOWN:
                    new_value = 63 if new_value == 0 else new_value - 1
                else:
                    new_value = 0 if new_value == 63 else new_value + 1
                phase_vals.append(new_value)
                self.afar.set_phase_shifter(bu_num=bu_num,
                                            ppm_num=ppm_num,
                                            chanel=chanel,
                                            direction=direction,
                                            value=new_value)
                _, phase_iter = self.pna.get_center_freq_data(wait=True)
                phase_iter -= self.norm_phase
                phase_list.append(phase_iter)
                if self.point_callback:
                    real_x = self.x_cords[i] + self.offset_x_list[bu_num-1]
                    real_y = self.y_cords[j] + self.offset_y_list[bu_num-1]
                    self.point_callback(i, j, real_x, real_y, amp, phase_iter, bu_num)
                if phase_iter * phase_first <= 0:
                    break
                iteration_count += 1
            
            # Если не нашли пересечение нуля, логируем предупреждение
            if iteration_count >= max_iterations:
                logger.warning(f"Не удалось найти пересечение нуля для ППМ {ppm_num} за {max_iterations} итераций. Используем текущее лучшее значение.")
            phase_best = initial_phase
            best_value = 0
            for k, phase in enumerate(phase_list):
                if abs(phase) < abs(phase_best):
                    phase_best = phase
                    best_value = phase_vals[k]
            if self.point_callback:
                real_x = self.x_cords[i] + self.offset_x_list[bu_num-1]
                real_y = self.y_cords[j] + self.offset_y_list[bu_num-1]
                self.point_callback(i, j, real_x, real_y, amp, phase_best, bu_num)
            return best_value
        except Exception as e:
            logger.error(f"Ошибка при поиске оптимальной фазы для ППМ {ppm_num}: {e}")
            raise WrongInstrumentError(f"Ошибка поиска оптимальной фазы для ППМ {ppm_num}: {e}")


    def start(self, chanel: Channel, direction: Direction, selected_bu_numbers: list = None) -> None:
        """
        Запуск процесса измерения и настройки фаз

        Raises:
            ConnectionError: При отсутствии подключения устройств
            WrongInstrumentError: При ошибке работы с устройствами
            PlanarScannerError: При ошибке перемещения
        """
        try:

            amp_workbook = openpyxl.Workbook()
            amp_worksheet = amp_workbook.active
            if selected_bu_numbers is None:
                bu_numbers = list(range(1, 41))
            else:
                bu_numbers = selected_bu_numbers


            vip_bu_numbers = set(bu_numbers)
            if self.bu_norm_number not in vip_bu_numbers:
                vip_bu_numbers.add(self.bu_norm_number)

            
            # logger.info(f"Включение ВИПов для БУ: {sorted(vip_bu_numbers)}")
            # for bu_num in sorted(vip_bu_numbers):
            #     no_wait = (self.afar.mode != 0)
            #     self.afar.turn_on_vips(bu_num, no_wait=no_wait)

            self.phase_results = []
            if not self._check_connections():
                raise ConnectionError("Не все устройства подключены")

            self.pna.set_output(True)
            self.pna.set_ascii_data()
            logger.info("Нормировка PNA...")


            self.psn.move(self.x_cords[(self.ppm_norm_number - 1) // 8] + self.offset_x_list[self.bu_norm_number - 1],
                          self.y_cords[(self.ppm_norm_number - 1) % 8] + self.offset_y_list[self.bu_norm_number - 1])

            self.afar.switch_ppm(bu_num=self.bu_norm_number,
                                 ppm_num=self.ppm_norm_number,
                                 chanel=chanel,
                                 direction=direction,
                                 state=PpmState.ON)

            self.afar.set_phase_shifter(bu_num=self.bu_norm_number,
                                        ppm_num=self.ppm_norm_number,
                                        chanel=chanel,
                                        direction=direction,
                                        value=0)
            self.afar.set_delay(bu_num=self.bu_norm_number, chanel=chanel, direction=direction, value=0)
            self.norm_amplitude, self.norm_phase = self.pna.get_center_freq_data(wait=True)
            logger.info(f"Нормировочные значения: амплитуда={self.norm_amplitude:.2f} дБ, фаза={self.norm_phase:.2f}°")
            
            if self.norm_callback:
                self.norm_callback(self.norm_amplitude)
            
            self.afar.switch_ppm(bu_num=self.bu_norm_number,
                                 ppm_num=self.ppm_norm_number,
                                 chanel=chanel,
                                 direction=direction,
                                 state=PpmState.OFF)
            
            logger.info(f"Фазировка БУ: {bu_numbers}")
            
            for bu_number in bu_numbers:
                logger.info(f"Начинаем фазировку БУ №{bu_number}")
                self.phase_results = []

                self.calibration_csv = CalibrationCSV(bu_number)

                self.afar.set_delay(bu_num=bu_number,
                                    chanel=chanel,
                                    direction=direction,
                                    value=0)
                
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
                                    logger.info(
                                        f"Частичные результаты фазировки БУ №{bu_number} сохранены в файл: {self.calibration_csv.get_file_path()}")
                                except Exception as e:
                                    logger.error(f"Ошибка при сохранении частичных результатов в CSV: {e}")
                            return

                        while self.pause_flag and self.pause_flag.is_set():
                            if self.stop_flag and self.stop_flag.is_set():
                                break
                            QThread.msleep(100)

                        ppm_num = i * 8 + j + 1
                        logger.info(f"Фазировка БУ №{bu_number}, ППМ №{ppm_num}")

                        self.afar.switch_ppm(bu_num=bu_number,
                                             ppm_num=ppm_num,
                                             chanel=chanel,
                                             direction=direction,
                                             state=PpmState.ON)

                        try:
                            self.psn.move(self.x_cords[i] + self.offset_x_list[bu_number-1],
                                          self.y_cords[j] + self.offset_y_list[bu_number-1])
                        except Exception as e:
                            raise PlanarScannerError(f"Ошибка перемещения к ППМ {ppm_num}: {e}")


                        self.afar.set_phase_shifter(bu_num=bu_number,
                                                    ppm_num=ppm_num,
                                                    chanel=chanel,
                                                    direction=direction,
                                                    value=0)

                        amp_zero, phase_zero = self.pna.get_center_freq_data(wait=True)
                        excel_list_amp = [bu_number, ppm_num, chanel.value, direction.value, amp_zero]
                        amp_worksheet.append(excel_list_amp)
                        phase_zero -= self.norm_phase
                        if phase_zero < 0:
                            phase_zero += 360
                        if self.point_callback:
                            real_x = self.x_cords[i] + self.offset_x_list[bu_number-1]
                            real_y = self.y_cords[j] + self.offset_y_list[bu_number-1]
                            self.point_callback(i, j, real_x, real_y, amp_zero, phase_zero, bu_number)

                        best_value = self._find_best_phase(bu_number, ppm_num, chanel, direction, phase_zero, i, j, amp_zero)

                        self.phase_results.append(best_value)

                        self.afar.set_phase_shifter(bu_num=bu_number,
                                                    ppm_num=ppm_num,
                                                  chanel=chanel,
                                                  direction=direction,
                                                  value=best_value)

                        if self.enable_delay_line_calibration and ppm_num == self.ppm_norm_number:
                            logger.info(f"Фазировка линий задержки для БУ №{bu_number}, ППМ №{ppm_num}")
                            try:
                                lz_discretes = self._measure_delay_lines(
                                    bu_num=bu_number,
                                    ppm_num=self.ppm_norm_number,
                                    chanel=chanel,
                                    direction=direction
                                )

                                self.delay_line_discretes[bu_number] = lz_discretes
                                
                                logger.info(f"Фазировка ЛЗ для БУ №{bu_number} завершена успешно")
                                
                            except Exception as e:
                                logger.error(f"Ошибка при фазировке ЛЗ для БУ №{bu_number}: {e}")
                                raise WrongInstrumentError(f"Ошибка фазировки ЛЗ: {e}")

                        self.afar.switch_ppm(bu_num=bu_number,
                                             ppm_num=ppm_num,
                                             chanel=chanel,
                                             direction=direction,
                                             state=PpmState.OFF)

                base_dir = None
                try:
                    if get_main_settings is not None:
                        qsettings = get_main_settings()
                        v = qsettings.value('base_save_dir')
                        if v:
                            base_dir = str(v)
                except Exception:
                    base_dir = None

                path_name_amp = Path(os.path.join(base_dir, 'phase', f'{chanel.value}.{direction.value}_amp.xlsx'))
                amp_workbook.save(path_name_amp)

                if self.calibration_csv and len(self.phase_results) == 32:
                    try:
                        lz_discretes = self.delay_line_discretes.get(bu_number, None)
                        
                        self.calibration_csv.save_phase_results(
                            channel=chanel,
                            direction=direction,
                            phase_results=self.phase_results,
                            delay_line_discretes=lz_discretes
                        )
                        logger.info(f"Результаты фазировки БУ №{bu_number} сохранены в файл: {self.calibration_csv.get_file_path()}")
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении результатов БУ №{bu_number} в CSV: {e}")
                elif len(self.phase_results) != 32:
                    logger.warning(f"БУ №{bu_number}: ожидалось 32 результата, получено {len(self.phase_results)}. CSV не сохранен.")
                
                logger.info(f"Фазировка БУ №{bu_number} завершена")

            # Выключение PNA
            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")
            
            # Опциональное выключение ВИПов
            if self.turn_off_vips:
                logger.info(f"Выключение ВИПов для БУ: {sorted(vip_bu_numbers)}")
                for bu_num in sorted(vip_bu_numbers):
                    try:
                        self.afar.turn_off_vips(bu_num)
                    except Exception as e:
                        logger.error(f"Ошибка при выключении ВИПов БУ №{bu_num}: {e}")

            logger.info("Измерение и настройка фаз завершены успешно")

        except Exception as e:
            logger.error(f"Ошибка при выполнении измерений: {e}")
            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")

            if self.turn_off_vips:
                logger.info("Аварийное выключение ВИПов")
                try:
                    for bu_num in sorted(vip_bu_numbers):
                        try:
                            self.afar.turn_off_vips(bu_num)
                        except Exception as vip_e:
                            logger.error(f"Ошибка при аварийном выключении ВИПов БУ №{bu_num}: {vip_e}")
                except Exception:
                    pass
            raise




