"""
Класс для измерения диаграммы направленности АФАР (лучей)
"""

import time
import os
import json
import numpy as np
from PyQt5.QtCore import QThread
from loguru import logger
from typing import List, Dict, Callable, Optional
import threading
from utils.excel_module import save_beam_pattern_results


class BeamMeasurement:
    """
    Класс для измерения 2D амплитудно-фазового распределения лучей АФАР
    
    Планарное сканирование: задаются координаты (X, Y) и шаги.
    Результат: 2D карта амплитуд и фаз для каждого луча и частоты.
    """
    
    def __init__(self, afar, pna, trigger, psn, base_save_dir: str = None):
        """
        Args:
            afar: Объект АФАР
            pna: Объект PNA
            trigger: Устройство синхронизации E5818
            psn: Планарный сканер
            base_save_dir: Базовая директория для сохранения результатов
        """
        self.afar = afar
        self.pna = pna
        self.trigger = trigger
        self.psn = psn
        self.base_save_dir = base_save_dir or ''
        
        # Переменные для периодического сохранения
        self.last_save_time = time.time()
        self.save_interval = 300  # Сохранять каждые 300 секунд
        self.save_dir = None  # Директория для текущего измерения
        self.current_scan_params = None  # Параметры текущего сканирования для сохранения
        self.pna_settings = None  # Настройки PNA для сохранения
        self.sync_settings = None  # Настройки синхронизатора для сохранения
        self.measurement_start_time = None
        self.measured_points_count = 0  # Количество реально измеренных точек (без пропущенных)

        # {beam_num: {freq: {'x': [...], 'y': [...], 'amp': [[...]], 'phase': [[...]]}}}
        self.data = {}

        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()

        self.period = None
        self.lead = None
        self.number_of_freqs = None
        
        # Карта границ БУ по оси X (из luchi.py)
        self.bu_map = [112.16, 224.32, 336.48, 448.64]

        self.bu_list = [
            33, 34, 35, 36, 37, 38, 39, 40,
            25, 26, 27, 28, 29, 30, 31, 32,
            17, 18, 19, 20, 21, 22, 23, 24,
            9, 10, 11, 12, 13, 14, 15, 16,
            1, 2, 3, 4, 5, 6, 7, 8
        ]
    
    def _get_bu_by_coordinates(self, x: float, y_ind: int) -> int:
        """
        Определение БУ по координатам
        
        Args:
            x: Координата X в мм
            y_ind: Индекс по оси Y
            
        Returns:
            int: Номер БУ
        """
        if x < self.bu_map[0]:
            bu_index = y_ind // 8
        elif self.bu_map[0] < x < self.bu_map[1]:
            bu_index = y_ind // 8 + 8
        elif self.bu_map[1] < x < self.bu_map[2]:
            bu_index = y_ind // 8 + 16
        elif self.bu_map[2] < x < self.bu_map[3]:
            bu_index = y_ind // 8 + 24
        else:
            bu_index = y_ind // 8 + 32
        
        return self.bu_list[bu_index]

    
    def measure(self, 
                beams: List[int], 
                scan_params: Dict,
                freq_list: List[float],
                progress_callback: Optional[Callable] = None,
                data_callback: Optional[Callable] = None,
                pna_settings: Optional[Dict] = None,
                sync_settings: Optional[Dict] = None) -> Dict:
        """
        Главный метод измерения 2D амплитудно-фазового распределения
        через планарное сканирование
        
        Args:
            beams: Список номеров лучей
            scan_params: Параметры сканирования {'left_x', 'right_x', 'up_y', 'down_y', 'step_x', 'step_y'}
            freq_list: Список частот в МГц [9300, 9550, 9800]
            progress_callback: Функция для обновления прогресса (current, total, message)
            data_callback: Функция для обновления данных в реальном времени
        Returns:
            dict: Результаты измерений {beam: {freq: {'x': [...], 'y': [...], 'amp': [[...]], 'phase': [[...]]}}}
        """
        logger.info(f"Начало планарного сканирования. Лучи: {beams}, Частоты: {len(freq_list)}")
        logger.info(f"Диапазон X: {scan_params['left_x']}-{scan_params['right_x']} мм, шаг {scan_params['step_x']} мм")
        logger.info(f"Диапазон Y: {scan_params['up_y']}-{scan_params['down_y']} мм, шаг {scan_params['step_y']} мм")

        if not self.data:
            self.data = {}
        self._stop_flag.clear()
        self._pause_flag.set()

        self.current_scan_params = scan_params.copy()
        self.pna_settings = pna_settings.copy() if pna_settings else None
        self.sync_settings = sync_settings.copy() if sync_settings else None

        left_x = scan_params['left_x']
        right_x = scan_params['right_x']
        up_y = scan_params['up_y']
        down_y = scan_params['down_y']
        step_x = scan_params['step_x']
        step_y = scan_params['step_y']
        
        x_list = np.round(np.linspace(left_x, right_x, int(round((right_x - left_x + step_x) // step_x))), 2)
        y_list = np.round(np.linspace(up_y, down_y, int(round((down_y - up_y + step_y) / step_y))), 2)
        
        logger.info(f"Сетка: {len(x_list)}x{len(y_list)} = {len(x_list) * len(y_list)} точек")
        
        start_time = time.time()
        
        try:
            # Инициализируем структуру данных для всех лучей и частот
            for beam_num in beams:
                if beam_num not in self.data:
                    self.data[beam_num] = {}
                for freq in freq_list:
                    if freq not in self.data[beam_num]:
                        amp_2d = np.full((len(y_list), len(x_list)), np.nan)
                        phase_2d = np.full((len(y_list), len(x_list)), np.nan)
                        self.data[beam_num][freq] = {
                            'x': x_list.tolist(),
                            'y': y_list.tolist(),
                            'amp': amp_2d.tolist(),
                            'phase': phase_2d.tolist()
                        }
                    else:
                        # Данные уже есть (досканирование) - обновляем только координаты если нужно
                        existing_data = self.data[beam_num][freq]
                        existing_data['x'] = x_list.tolist()
                        existing_data['y'] = y_list.tolist()
                        amp_2d = np.array(existing_data['amp'])
                        phase_2d = np.array(existing_data['phase'])
                        if amp_2d.shape != (len(y_list), len(x_list)):
                            logger.warning(f"Размеры данных не совпадают для луча {beam_num}, частоты {freq}. Пересоздаем.")
                            amp_2d = np.full((len(y_list), len(x_list)), np.nan)
                            phase_2d = np.full((len(y_list), len(x_list)), np.nan)
                        existing_data['amp'] = amp_2d.tolist()
                        existing_data['phase'] = phase_2d.tolist()

            points_amount = len(freq_list)

            self.afar.preset_task(bu_num=0)

            for idx, beam_num in enumerate(beams):
                if idx == len(beams) - 1:
                    self.afar.set_task(bu_num=0,
                                       number_of_beam_prm=beam_num,
                                       number_of_beam_prd=beam_num,
                                       amount_strobs=points_amount,
                                       is_cycle=True
                                       )
                else:
                    self.afar.set_task(bu_num=0,
                                       number_of_beam_prm=beam_num,
                                       number_of_beam_prd=beam_num,
                                       amount_strobs=points_amount,
                                       is_cycle=False
                                       )


            if self.data and self.save_dir:
                params_file = os.path.join(self.save_dir, 'scan_params.json')
                if os.path.exists(params_file):
                    try:
                        with open(params_file, 'r', encoding='utf-8') as f:
                            params_data = json.load(f)
                            if 'measurement_start_time' in params_data:
                                self.measurement_start_time = params_data['measurement_start_time']
                                logger.info(f"Продолжение измерения с времени начала: {self.measurement_start_time}")
                            else:
                                self.measurement_start_time = time.time()
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить время начала измерения: {e}")
                        self.measurement_start_time = time.time()
                else:
                    self.measurement_start_time = time.time()
            else:
                self.measurement_start_time = time.time()
            
            # Подсчитываем количество уже измеренных точек (для правильного расчета времени)
            already_measured_points = 0
            if beams and freq_list:
                first_beam = beams[0]
                first_freq = freq_list[0]
                if first_beam in self.data and first_freq in self.data[first_beam]:
                    amp_2d = np.array(self.data[first_beam][first_freq]['amp'])
                    already_measured_points = np.sum(~np.isnan(amp_2d))
                    logger.info(f"Найдено {already_measured_points} уже измеренных точек для досканирования")
            
            point_count = 0
            total_points = len(x_list) * len(y_list)
            self.measured_points_count = already_measured_points  # Начинаем с уже измеренных точек

            for x_ind, x in enumerate(x_list):
                if self._stop_flag.is_set():
                    logger.warning("Измерение остановлено пользователем")
                    break

                self._pause_flag.wait()

                y_iter = y_list if x_ind % 2 == 0 else y_list[::-1]
                
                for y in y_iter:
                    if self._stop_flag.is_set():
                        break

                    self._pause_flag.wait()
                    
                    y_ind = np.where(y_list == y)[0][0]

                    skip_point = False
                    if beams and freq_list:
                        first_beam = beams[0]
                        first_freq = freq_list[0]
                        if first_beam in self.data and first_freq in self.data[first_beam]:
                            amp_2d = np.array(self.data[first_beam][first_freq]['amp'])
                            if not np.isnan(amp_2d[y_ind, x_ind]):
                                # Точка уже измерена - пропускаем
                                skip_point = True
                                logger.debug(f"Пропуск точки X={x:.1f}, Y={y:.1f} - уже измерена")
                    
                    # Увеличиваем счетчик для всех точек (включая пропущенные) для правильного расчета прогресса
                    point_count += 1
                    
                    if skip_point:
                        continue
                    
                    # Увеличиваем счетчик реально измеренных точек
                    self.measured_points_count += 1

                    self.psn.move(x, y)

                    # Измеряем все лучи в текущей точке
                    for beam_num in beams:
                        if self._stop_flag.is_set():
                            break

                        self.trigger.burst(period_s=self.period, count=self.number_of_freqs, lead_s=self.lead)
                        QThread.msleep(int((self.lead + self.period * self.number_of_freqs) * 1000))
                        while True:
                            evt = self.trigger.pop_ext_event()
                            if evt:
                                break

                        amps, phases = self.pna.get_data()

                        for freq_idx, freq in enumerate(freq_list):
                            amp_val = amps[freq_idx]
                            phase_val = phases[freq_idx]

                            amp_2d = np.array(self.data[beam_num][freq]['amp'])
                            phase_2d = np.array(self.data[beam_num][freq]['phase'])

                            amp_2d[y_ind, x_ind] = amp_val
                            phase_2d[y_ind, x_ind] = phase_val

                            self.data[beam_num][freq]['amp'] = amp_2d.tolist()
                            self.data[beam_num][freq]['phase'] = phase_2d.tolist()
                    

                    if progress_callback and point_count % 10 == 0:
                        current_time = time.time()
                        elapsed_time = current_time - self.measurement_start_time

                        if self.measured_points_count > 0:
                            avg_time_per_point = elapsed_time / self.measured_points_count
                            remaining_points = total_points - self.measured_points_count
                            estimated_remaining = avg_time_per_point * remaining_points
                        else:
                            estimated_remaining = 0
                        
                        progress_callback(
                            point_count, 
                            total_points, 
                            f"Точка {point_count}/{total_points}, X={x:.1f}, Y={y:.1f}",
                            int(elapsed_time),
                            int(estimated_remaining)
                        )

                    if data_callback:
                        try:
                            data_callback(self.data)
                        except Exception as e:
                            logger.error(f"Ошибка при вызове callback: {e}", exc_info=True)

                    self._save_results_periodically(beams, freq_list, x_list, y_list, 
                                                   scan_params['step_x'], scan_params['step_y'])

                    #TODO  проде убрать задержку
                    time.sleep(0.02)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Измерение завершено за {elapsed_time:.1f} сек")
            logger.info(f"Всего точек: {len(x_list) * len(y_list)}, лучей: {len(beams)}, частот: {len(freq_list)}")
            
            # Финальное сохранение результатов
            if self.base_save_dir:
                try:
                    scan_params_with_time = scan_params.copy()
                    scan_params_with_time['measurement_start_time'] = self.measurement_start_time

                    save_dir = save_beam_pattern_results(
                        base_dir=self.base_save_dir,
                        beams=beams,
                        freq_list=freq_list,
                        data=self.data,
                        x_list=x_list.tolist(),
                        y_list=y_list.tolist(),
                        step_x=scan_params['step_x'],
                        step_y=scan_params['step_y'],
                        save_dir=self.save_dir,
                        scan_params=scan_params_with_time,
                        pna_settings=self.pna_settings,
                        sync_settings=self.sync_settings
                    )
                    if save_dir:
                        if not self.save_dir:
                            self.save_dir = save_dir
                        logger.info(f"Финальные результаты сохранены в {save_dir}")
                except Exception as e:
                    logger.error(f"Ошибка при финальном сохранении: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Ошибка во время измерения: {e}", exc_info=True)
            raise
        
        return self.data

    
    def stop(self):
        """Остановить измерение"""
        logger.info("Запрос остановки измерения")
        self._stop_flag.set()
        self._pause_flag.set()  # Разблокируем wait()
    
    def pause(self):
        """Приостановить измерение"""
        logger.info("Измерение приостановлено")
        self._pause_flag.clear()  # Блокируем wait()
    
    def resume(self):
        """Возобновить измерение"""
        logger.info("Измерение возобновлено")
        self._pause_flag.set()  # Разблокируем wait()
    
    def get_results(self) -> Dict:
        """Получить текущие результаты"""
        return self.data.copy()
    
    def _save_results_periodically(self, beams: List[int], freq_list: List[float], 
                                    x_list: np.ndarray, y_list: np.ndarray, 
                                    step_x: float, step_y: float):
        """
        Периодическое сохранение результатов (для досканирования)
        
        ВАЖНО: Этот метод вызывается только после измерения ВСЕХ лучей в текущей точке.
        Это гарантирует, что данные сохраняются только когда все измерения в точке завершены.
        
        Args:
            beams: Список лучей
            freq_list: Список частот
            x_list: Список координат X
            y_list: Список координат Y
            step_x: Шаг по X
            step_y: Шаг по Y
        """
        if not self.base_save_dir:
            return
        
        current_time = time.time()

        if current_time - self.last_save_time >= self.save_interval:
            try:
                scan_params_with_time = self.current_scan_params.copy() if self.current_scan_params else {}
                scan_params_with_time['measurement_start_time'] = self.measurement_start_time

                save_dir = save_beam_pattern_results(
                    base_dir=self.base_save_dir,
                    beams=beams,
                    freq_list=freq_list,
                    data=self.data,
                    x_list=x_list.tolist(),
                    y_list=y_list.tolist(),
                    step_x=step_x,
                    step_y=step_y,
                    save_dir=self.save_dir,
                    scan_params=scan_params_with_time,
                    pna_settings=self.pna_settings,
                    sync_settings=self.sync_settings
                )
                if save_dir:
                    if not self.save_dir:
                        self.save_dir = save_dir
                    self.last_save_time = current_time
                    logger.info(f"Периодическое сохранение результатов в {save_dir}")
            except Exception as e:
                logger.error(f"Ошибка при периодическом сохранении: {e}", exc_info=True)
