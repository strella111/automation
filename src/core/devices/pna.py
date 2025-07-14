import math
import random
import time
import pyvisa
import socket
from typing import Tuple, Optional, Union
from loguru import logger
from ..common.enums import Channel, Direction
from ..common.exceptions import WrongInstrumentError
from utils.logger import format_device_log

class PNA:
    """Класс Векторного анализатора цепей KeySight"""

    def __init__(self, ip: str, port: int, mode: int = 0):
        """
        Конструктор класса
        Args:
            visa_name: A Visa Resource ID, like 'TCPIP0::10.0.0.2::50000::SOCKET'
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.ip = ip
        self.port = port
        self.mode = mode
        self.connection = None
        self.count_freqs_point = 11
        # TODO Количество частотных точек должны задаваться из настройки ПНА из файла либо из UI


    def connect(self) -> None:
        """Подключение к PNA"""
        try:
            if self.mode == 0:  # Реальный режим
                self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.connection.connect((self.ip, self.port))
                #self.connection.settimeout(1)
                logger.debug(f"PNA подключен к {self.ip}:{self.port}")
                logger.info('Произведено подлючение к PNA')
            else:  # Тестовый режим
                logger.info("PNA работает в тестовом режиме")
                self.connection = True
        except Exception as e:
            logger.error(f"Ошибка подключения к PNA: {e}")
            raise

    def disconnect(self) -> None:
        """Отключение от PNA"""
        if self.connection:
            if self.mode == 0:
                self.connection.close()
            self.connection = None
            logger.info("PNA отключен")

    def _send_data(self, command: str):
        """Отправка команды в PNA"""
        if not self.connection:
            logger.error('При отправке команды на PNA произошла ошибка: не обнаружено подлючение к PNA')
            raise ConnectionError("PNA не подключен")
        if self.mode == 0:  # Реальный режим
            try:
                self.connection.sendall((command + '\n').encode())
                logger.debug(format_device_log('PNA', '>>', command))
            except Exception as e:
                logger.error(f"Ошибка отправки данных на PNA: {e}")
                raise 
        else:  # Тестовый режим
            logger.debug(format_device_log('PNA', '>>', command))

    def _read_data(self):
        if not self.connection:
            logger.error('При чтении данных с PNA произошла ошибка: не обнаружено подключение к PNA')
            raise ConnectionError("PNA не подключен")
        if self.mode == 0:
            try:
                response = self.connection.recv(8192).decode('ascii').strip()
                if response.startswith('"'):
                    response = response[1:]
                if response.endswith('"'):
                    response = response[:-1]
                logger.debug(format_device_log('PNA', '<<', response))
                return response
            except Exception as e:
                logger.error(f"Ошибка чтения данных с PNA: {e}")
                raise
        else:
            response = '0'
            logger.debug(format_device_log('PNA', '<<', response))
            return response


    def preset(self) -> None:
        """Сброс PNA в начальное состояние"""
        self._send_data("SYST:FPRESET")
        logger.info("PNA сброшен в начальное состояние")

    def create_measure(self, s_param: str):
        """Создание измерения"""
        name = f'My'
        self._send_data(f"CALC:PAR:DEF '{name}', {s_param}")
        logger.info(f"Создано измерение {name} на PNA")

    def turn_window(self, state: bool):
        """Отображение экрана"""
        self._send_data(f"DISPlay:WINDow1:STATE {'ON' if state else 'OFF'}")

    def put_and_visualize_trace(self):
        self._send_data("DISP:WIND1:TRACE1:FEED 'My'")

    def get_power(self):
        self._send_data("SOUR:POW?")
        response = self._read_data()
        return float(response)

    def get_start_freq(self):
        self._send_data("SENS:FREQ:STAR?")
        response = self._read_data()
        return float(response)

    def get_stop_freq(self):
        self._send_data("SENS:FREQ:STOP?")
        response = self._read_data()
        return float(response)

    def get_amount_of_points(self):
        self._send_data("SENS:SWE:POIN?")
        response = self._read_data()
        return float(response)

    def get_s_param(self):
        self._send_data("CALC:PAR:CAT?")
        response = self._read_data()
        result = response.split(',')[1]
        return result

    def get_selected_meas(self):
        self._send_data("CALC:PAR:SEL?")
        response = self._read_data()
        return response

    def get_all_meas(self):
        self._send_data("CALC:PAR:CAT?")
        response = self._read_data()
        result = response.split(',')[::2]
        return result

    def set_current_meas(self, meas: str):
        self._send_data(f"CALC:PAR:SEL '{meas}'")

    def set_power(self, power: float, port: int = 1):
        """Установка мощности"""
        self._send_data(f"SOUR:POW{port} {power}")
        logger.info(f"Установлена мощность {power} дБм на порту {port}")


    def set_freq_start(self, freq: float):
        """Установка начальной частоты"""
        self._send_data(f"SENS:FREQ:STAR {freq}")
        logger.info(f"Установлена начальная частота {freq} Гц")


    def set_freq_stop(self, freq: float):
        """Установка конечной частоты"""
        self._send_data(f"SENS:FREQ:STOP {freq}")
        logger.info(f"Установлена конечная частота {freq} Гц")


    def set_points(self, points: int):
        """Установка количества точек измерения"""
        self._send_data(f"SENS:SWE:POIN {points}")
        logger.info(f"Установлено количество точек измерения {points}")

    def get_data(self):
        if self.mode == 0:
            self._send_data(f'CALC:DATA? SDATA')
            response = self._read_data()
            response_list = response.split(',')
            amps = []
            phases = []

            for i in range(0, len(response_list), 2):
                real = float(response_list[i])
                imag = float(response_list[i + 1])
                amp_db = 20 * math.log10(abs(complex(real, imag)))
                phase_degrees = math.atan2(imag, real) * 180 / math.pi
                amps.append(amp_db)
                phases.append(phase_degrees)
            return amps, phases

        else:
            amps = [random.uniform(0, 15) for _ in range(self.count_freqs_point)]
            phases = [random.uniform(-180, 180) for _ in range(self.count_freqs_point)]
            return amps, phases

    def get_center_freq_data(self):
        amps, phases = self.get_data()
        amount_freq = len(amps)
        amp, phase = amps[amount_freq//2], phases[amount_freq//2]
        logger.debug(format_device_log('PNA', '<<', f'Получена фаза и амплитуда на центральной частоте: {amp}дБ, {phase}'))
        return amp, phase

    def set_output(self, state: bool):
        """Включение/выключение порта на генерацию"""
        self._send_data(f"OUTP {'ON' if state else 'OFF'}")
        logger.info(f"Выход PNA {'включен' if state else 'выключен'}")

    def load_state(self, filename: str):
        """Загрузка состояния из файла"""
        self._send_data(f'MMEM:LOAD "{filename}"')
        logger.info(f"Загружено состояние из файла {filename}")


    def select_par(self, number: int) -> None:
        """Выбор параметра измерения"""
        self._send_data(f'CALC:PAR:MNUM {number}')
        logger.debug(f'Выбрано измерение №{number} на pna')

    def imm(self) -> None:
        """Запуск измерения"""
        self._send_data('INIT:IMM')
        logger.debug('Запущен триггер на измерение одного экрана pna')

    def set_ascii_data(self) -> None:
        """Установка формата данных ASCII"""
        self._send_data('FORM:DATA ascii')
        logger.debug('Установление формат данных ASCII на pna')

    def normalize(self) -> None:
        """Нормализация измерений"""
        self._send_data('CALC:MATH:MEM')
        self._send_data('CALC:MATH:FUNC DIV')
        logger.debug('Отнормировано текущее измерение на pna')

    def load_settings_file(self, filepath: str = None) -> None:
        """Загрузка файла настроек"""
        self._send_data(f'MMEM:LOAD "{filepath}"')
        logger.debug(f'Подгружен файл настроек pna {filepath}')


    def get_mean_value(self) -> float:
        """Получение среднего значения"""
        self._send_data('CALC:FUNC:TYPE MEAN')
        self._send_data('CALC:FUNC:DATA?')
        response = self._read_data()
        logger.debug('Запрошено среднее значение текущего измерения pna')
        return float(response.strip())

    def set_unwrapped_phase_type(self) -> None:
        """Установка типа фазы unwrapped"""
        self._send_data('CALC:FORM UPH')
        logger.debug('Установлен формат unwrapped phase на pna')

    def set_delay_type(self) -> None:
        """Установка типа задержки"""
        self._send_data('CALC:FROM GDEL')
        logger.debug('Установлен формат group delay на pna')

    def set_mlog_type(self) -> None:
        """Установка типа логарифмической шкалы"""
        self._send_data('CALC:FROM MLOG')
        logger.debug('Установлен формат LogM на pna')

    def get_files_in_dir(self, folder: str = None) -> list:
        """Получение списка файлов в директории"""
        command = f'MMEM:CAT? \"{folder}\"'
        self._send_data(command)
        response = self._read_data()
        result_list = response[2:len(response)-1].split(',')
        logger.debug(f'Запрошены файлы pna в folder={folder}')
        return result_list
