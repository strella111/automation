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

from core import Channel
from utils.excel_module import save_beam_pattern_results
from core.devices.trigger_box import E5818


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
        self.trigger: E5818 = trigger
        self.psn = psn
        self.base_save_dir = base_save_dir or ''

        self.last_save_time = time.time()
        self.save_interval = 180
        self.save_dir = None
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


    def burst_and_check_ext(self, expected_strobs):
        self.trigger.burst(period_s=self.period, count=self.number_of_freqs, lead_s=self.lead)
        QThread.msleep(int((self.lead + self.period * self.number_of_freqs) * 1000))
        count_retry = 0
        while True:
            evt = self.trigger.pop_ext_event()
            if evt:
                return
            count_retry += 1
            QThread.msleep(5)
            if count_retry > 5:
                logger.debug('Произошло больше 5 попыток идентифицировать обратный триггер от PNA.')
                break

        counter = 0
        while True:
            tm = self.afar.get_tm(1)
            counter += 1
            logger.debug(f'Запрос для синхронизациии стробов. Ожидается - {expected_strobs}, реально - {tm['strobs_prm']}')
            if tm['strobs_prm'] == expected_strobs:
                logger.debug('Синхронизация произведена успешно')
                return
            elif (expected_strobs - tm['strobs_prm']) % self.number_of_freqs == 0 and (expected_strobs >  tm['strobs_prm']):
                logger.debug('Генерация дополнительной пачки стробов')
                self.trigger.burst(period_s=self.period, count=self.number_of_freqs, lead_s=self.lead)
                QThread.msleep(int((self.lead + self.period * self.number_of_freqs) * 1000))
                #TODO Делать возврат на точку, где синхронизация не была нарушена
            elif tm['strobs_prm'] > expected_strobs:
                return
            if counter > 5:
                raise Exception('Не удалось синхронизировать стробы')




    def measure(self, 
                beams: List[int], 
                scan_params: Dict,
                freq_list: List[float],
                progress_callback: Optional[Callable] = None,
                data_callback: Optional[Callable] = None,
                pna_settings: Optional[Dict] = None,
                sync_settings: Optional[Dict] = None) -> Dict:
        """
        Главный метод измерения 2D амплитудно-фазового распределения через планарное сканирование
        
        Args:
            beams: Список номеров лучей
            scan_params: Параметры сканирования {'left_x', 'right_x', 'up_y', 'down_y', 'step_x', 'step_y'}
            freq_list: Список частот в МГц [9300, 9550, 9800]
            progress_callback: Функция для обновления прогресса (current, total, message)
            data_callback: Функция для обновления данных в реальном времени
            pna_settings: Настройки векторного анализатора цепей
            sync_settings: Настройки синхронзатора (TriggerBox)
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


        n_x = int(round((right_x - left_x) / step_x)) + 1
        n_y = int(round((down_y - up_y) / step_y)) + 1
        x_list = np.round(np.linspace(left_x, right_x, n_x), 4)
        y_list = np.round(np.linspace(up_y, down_y, n_y), 4)
        
        logger.info(f"Сетка: {len(x_list)}x{len(y_list)} = {len(x_list) * len(y_list)} точек")
        
        start_time = time.time()

        expected_strobs = 0
        
        try:
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

                        expected_strobs += self.number_of_freqs

                        self.burst_and_check_ext(expected_strobs)

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

                    real_strobs = self.afar.get_tm(1)['strobs_prm']
                    logger.info(f'Ожидаем - {expected_strobs} Пришло - {real_strobs}')
                    if real_strobs != expected_strobs:
                        expected_strobs = 0
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

                        for beam_num in beams:
                            if self._stop_flag.is_set():
                                break

                            expected_strobs += self.number_of_freqs

                            self.burst_and_check_ext(expected_strobs)

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
            logger.error(f"Ошибка во время измерения: {e.args}", exc_info=True)
            raise Exception(e)
        
        return self.data

    
    def stop(self):
        """Остановить измерение"""
        logger.info("Запрос остановки измерения")
        self._stop_flag.set()
        self._pause_flag.set()
    
    def pause(self):
        """Приостановить измерение"""
        logger.info("Измерение приостановлено")
        self._pause_flag.clear()
    
    def resume(self):
        """Возобновить измерение"""
        logger.info("Измерение возобновлено")
        self._pause_flag.set()
    
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
