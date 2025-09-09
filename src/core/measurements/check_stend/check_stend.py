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
                time.sleep(0.005)
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
        delay_results = []
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

            if self.delay_callback:
                self.delay_callback.emit(delay_results)

            # for delay in self.delay_lines:
            #     self.ma.set_calb_mode(chanel=channel, direction=direction, delay_number=delay, fv_number=0)

            data = self._check_fv(chanel=channel, direction=direction)
            # Сохраняем реальные данные (амплитуда и фаза, как измерены)
            self.data_real = data

            # Формируем относительные фазы: фаза(0) - фаза(ФВ), амплитуды оставляем как есть
            if 0 in data:
                rel_data: Dict[float, List[float]] = {}
                zero_list = data[0]
                # zero_list длиной 64: [A1, P1, A2, P2, ...]
                for fv, values in data.items():
                    rel_list: List[float] = []
                    for i in range(0, len(values), 2):
                        amp_val = values[i]
                        phase_val = values[i + 1]
                        # Соответствующая нулевая фаза
                        phase_zero = zero_list[i + 1] if i + 1 < len(zero_list) else 0.0
                        phase_rel = phase_zero - phase_val if fv != 0 else 0.0
                        rel_list.extend([amp_val, phase_rel])
                    rel_data[fv] = rel_list
                self.data_relative = rel_data
            else:
                logger.warning('Не найдены данные для ФВ=0. Относительные фазы не будут сформированы')
                self.data_relative = None

            # Отправляем результат через callback, если задан
            if self.data_callback and self.data_relative is not None:
                try:
                    self.data_callback.emit(self.data_relative)
                except Exception as e:
                    logger.error(f"Ошибка при отправке результирующих данных в UI: {e}")

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
