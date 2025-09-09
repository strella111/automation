from typing import Tuple, List, Dict
from loguru import logger

from ...devices.ma import MA
from ...devices.pna import PNA
from core.devices.trigger_box import E5818
from core.common.enums import Channel, Direction
from ...common.exceptions import WrongInstrumentError
import threading
import time


class CheckMAStend:
    """Класс для проверки антенного модуля на стенде с обратным триггером"""

    def __init__(self, ma: MA,
                 pna: PNA,
                 gen: E5818,
                 stop_event: threading.Event = None,
                 pause_event: threading.Event = None):
        """
        Инициализация класса

        Args:
            ma: Модуль антенный
            pna: Анализатор цепей
            gen: Устройство синхронизации (TriggerBox)
            stop_event: Событие для остановки измерений
            pause_event: Событие для приостановки измерений

        Raises:
            ValueError: Если какой-либо из параметров None
        """
        if not all([ma, pna, gen, stop_event, pause_event]):
            raise ValueError("Все устройства и события должны быть указаны")

        self.ma = ma
        self.pna = pna
        self.gen = gen
        self._stop_event = stop_event or threading.Event()
        self._pause_event = pause_event or threading.Event()

        self.period = None
        self.number_of_freqs = None
        self.lead = None

        self.phase_shifts = [0, 5.625, 11.25, 22.5, 45, 90, 180]
        self.delay_lines = [0, 1, 2, 4, 8]

        self.channel = None
        self.direction = None

        self.norm_amp = None
        self.norm_phase = None
        self.norm_delay = None

        self.delay_amp_tolerance = 1.0
        self.delay_tolerances = {
            1: {'min': 90.0, 'max': 110.0},
            2: {'min': 180.0, 'max': 220.0},
            4: {'min': 360.0, 'max': 440.0},
            8: {'min': 650, 'max': 800}
        }

        self.delay_callback = None
        self.data_callback = None
        self.realtime_callback = None
        self.data_real = None
        self.data_relative = None

    def _check_connections(self) -> bool:
        """
        Проверка подключения всех устройств

        Returns:
            bool: True если все устройства подключены, False в противном случае
        """
        if not all([self.pna.connection, self.ma.connection, self.gen.connection]):
            logger.error("Не все устройства подключены")
            return False
        return True

    def _check_fv(self, chanel: Channel, direction: Direction) -> Dict[float, List[float]]:

        results: Dict[float, List[float]] = {}
        zero_phases: List[float] = []
        for fv in self.phase_shifts:
            code = int(fv / 5.625)
            self.ma.set_calb_mode(chanel=chanel,
                                  direction=direction,
                                  delay_number=0,
                                  fv_number=code,
                                  att_ppm_number=0,
                                  att_mdo_number=0,
                                  number_of_strobes=self.number_of_freqs)

            if fv not in results:
                results[fv] = []
            ppm_index = 0
            # Собираем 32 значения (64 числа) последовательно
            for ppm_num in range(1, 33):
                self.gen.burst(period_s=self.period, count=self.number_of_freqs, lead_s=self.lead)
                while True:
                    evt = self.gen.pop_ext_event()
                    if evt:
                        break
                time.sleep(0.001)
                amp_db, phase_deg = self.pna.get_center_freq_data()
                results[fv].extend([amp_db, phase_deg])

                # Сохраняем опорные фазы для ФВ=0 и считаем относительную фазу для realtime
                if fv == 0:
                    if len(zero_phases) < 32:
                        zero_phases.append(phase_deg)
                    phase_rel = 0.0
                else:
                    phase_zero = zero_phases[ppm_index] if ppm_index < len(zero_phases) else 0.0
                    phase_rel = phase_zero - phase_deg

                # Рилтайм-эмит для UI: (угол, номер ППМ 1..32, амплитуда, относительная фаза)
                if self.realtime_callback:
                    try:
                        self.realtime_callback.emit(float(fv), int(ppm_index + 1), float(amp_db), float(phase_rel))
                    except Exception as e:
                        logger.error(f"Ошибка realtime обновления UI: {e}")

                ppm_index += 1
        return results

    def _check_lz(self, chanel: Channel, direction: Direction) -> Dict[int, tuple]:

        self.pna.set_delay_type()

        lz_to_amps: Dict[int, List[float]] = {}
        lz_to_delays: Dict[int, List[float]] = {}
        zero_amp_mean: float = None
        zero_delay_mean: float = None

        for lz in self.delay_lines:
            lz_to_amps[lz] = []
            lz_to_delays[lz] = []

            self.ma.set_calb_mode(chanel=chanel,
                                  direction=direction,
                                  delay_number=lz,
                                  fv_number=0,
                                  att_ppm_number=0,
                                  att_mdo_number=0,
                                  number_of_strobes=self.number_of_freqs)


            collected = 0
            for ppm_num in range(1, 33):
                self.gen.burst(period_s=self.period, count=self.number_of_freqs, lead_s=self.lead)
                while True:
                    evt = self.gen.pop_ext_event()
                    if evt:
                        break
                time.sleep(0.001)
                try:
                    amp_mean = float(self.pna.get_mean_value_from_sdata())
                except Exception:
                    amp_mean = float('nan')

                try:
                    delay_mean = float(self.pna.get_mean_value()) * 1e12
                except Exception:
                    delay_mean = float('nan')

                lz_to_amps[lz].append(amp_mean)
                lz_to_delays[lz].append(delay_mean)
                collected += 1

            mean_amp = (sum(lz_to_amps[lz]) / len(lz_to_amps[lz])) if lz_to_amps[lz] else float('nan')
            mean_delay = (sum(lz_to_delays[lz]) / len(lz_to_delays[lz])) if lz_to_delays[lz] else float('nan')

            if lz == 0:
                zero_amp_mean = mean_amp
                zero_delay_mean = mean_delay
                amp_delta_rt = 0.0
                delay_delta_rt = 0.0
            else:
                # Если по какой-то причине базовая ЛЗ ещё не определена – считаем без нормировки
                if zero_amp_mean is None or zero_delay_mean is None:
                    amp_delta_rt = mean_amp
                    delay_delta_rt = mean_delay
                else:
                    amp_delta_rt = (mean_amp - zero_amp_mean)
                    delay_delta_rt = (mean_delay - zero_delay_mean)

            if self.delay_callback:
                try:
                    self.delay_callback.emit({lz: (amp_delta_rt, delay_delta_rt)})
                except Exception as e:
                    logger.error(f"Ошибка realtime обновления таблицы ЛЗ: {e}")

        results: Dict[int, tuple] = {}
        zero_amp = None
        zero_delay = None
        if 0 in lz_to_amps and len(lz_to_amps[0]) > 0:
            zero_amp = sum(lz_to_amps[0]) / len(lz_to_amps[0])
        if 0 in lz_to_delays and len(lz_to_delays[0]) > 0:
            zero_delay = sum(lz_to_delays[0]) / len(lz_to_delays[0])

        for lz in self.delay_lines:
            amps = lz_to_amps.get(lz, [])
            delays = lz_to_delays.get(lz, [])
            mean_amp = (sum(amps) / len(amps)) if amps else float('nan')
            mean_delay = (sum(delays) / len(delays)) if delays else float('nan')

            if zero_amp is not None and zero_delay is not None:
                amp_delta = mean_amp - zero_amp
                delay_delta = mean_delay - zero_delay
            else:
                amp_delta = mean_amp
                delay_delta = mean_delay

            if lz == 0:
                amp_delta = 0.0
                delay_delta = 0.0

            results[lz] = (amp_delta, delay_delta)

        return results




    def start(self, channel: Channel, direction: Direction):
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

            self.pna.set_output(True)
            self.ma.turn_on_vips()
            self.pna.set_ascii_data()

            try:
                self.number_of_freqs = int(self.pna.get_amount_of_points())
            except Exception as e:
                logger.error(f"Не удалось получить количество точек с PNA: {e}")
                raise

            data = self._check_fv(chanel=channel, direction=direction)
            self.data_real = data

            # Формируем относительные фазы: фаза(0) - фаза(ФВ), амплитуды оставляем как есть
            if 0 in data:
                rel_data: Dict[float, List[float]] = {}
                zero_list = data[0]
                for fv, values in data.items():
                    rel_list: List[float] = []
                    for i in range(0, len(values), 2):
                        amp_val = values[i]
                        phase_val = values[i + 1]
                        phase_zero = zero_list[i + 1] if i + 1 < len(zero_list) else 0.0
                        phase_rel = phase_zero - phase_val if fv != 0 else 0.0
                        rel_list.extend([amp_val, phase_rel])
                    rel_data[fv] = rel_list
                self.data_relative = rel_data
            else:
                logger.warning('Не найдены данные для ФВ=0. Относительные фазы не будут сформированы')
                self.data_relative = None

            if self.data_callback and self.data_relative is not None:
                try:
                    self.data_callback.emit(self.data_relative)
                except Exception as e:
                    logger.error(f"Ошибка при отправке результирующих данных в UI: {e}")

            # После ФВ запускаем проверку линий задержки и отправляем усреднённые дельты
            try:
                lz_results = self._check_lz(chanel=channel, direction=direction)
                # ожидаемый формат: {lz: (mean_amp_delta, mean_delay_delta)}
                if self.delay_callback and lz_results:
                    self.delay_callback.emit(lz_results)
            except Exception as e:
                logger.error(f"Ошибка проверки линий задержки: {e}")

            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при выключении PNA: {e}")
                raise WrongInstrumentError(f"Ошибка выключения PNA: {e}")

            logger.info("Измерение ППМ завершена")
        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки: {e}")
            try:
                self.pna.set_output(False)
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise

        self.ma.turn_off_vips()
        return results
