import math
import random
import time
import pyvisa
from typing import Tuple, Optional, Union
from loguru import logger
from ..common.enums import Channel, Direction
from ..common.exceptions import WrongInstrumentError

class PNA:
    """Класс Векторного анализатора цепей KeySight"""

    def __init__(self, ip: str, port: int, mode: int = 0):
        """
        Конструктор класса
        Args:
            visa_name: A Visa Resource ID, like 'TCPIP0::10.0.0.2::50000::SOCKET'
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.visa_name = f'TCPIP0::{ip}::{port}::SOCKET'
        self.connection = None
        self.mode = mode

    def connect(self) -> None:
        """Подключение к PNA"""
        try:
            if self.mode == 0:
                rm = pyvisa.ResourceManager()
                self.connection = rm.open_resource(self.visa_name)
                self.connection.read_termination = '\n'
                self.connection.write_termination = '\n'
                response = self.query('*IDN?')
                if not response or 'Agilent Technologies' not in response:
                    logger.error(f'Неверный ответ от устройства: {response}')
                    raise WrongInstrumentError(
                        f'Wrote "ID" Expected "Agilent Technologies" got "{response}"')
            else:
                time.sleep(0.2)
                self.connection = True
            logger.info('Произведено подключение к PNA')
        except pyvisa.VisaIOError as e:
            logger.error(f'Ошибка подключения к PNA - ошибка ввода/вывода: {e}')
            raise WrongInstrumentError('Ошибка ввода/вывода при подключении к PNA') from e
        except Exception as e:
            logger.error(f'Неизвестная ошибка подключения к PNA: {e}')
            raise WrongInstrumentError('Неизвестная ошибка подключения к PNA') from e

    def disconnect(self) -> None:
        """Отключение от PNA"""
        if self.mode == 0 and self.connection:
            self.connection.close()
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружен подключение к PNA')
            raise WrongInstrumentError('При попытке обращения к connection pna произошла ошибка')
        logger.info('Подключение к PNA закрыто')

    def write(self, data: str) -> None:
        """Write string to the instrument."""
        if self.connection and self.mode == 0:
            self.connection.write(data)
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружено подключение к pna при попытки отправки данных')
            raise WrongInstrumentError('При попытке обращения к connection pna произошла ошибка')
        logger.info(f'Отправлена команда "{data}" на PNA')

    def read(self) -> str:
        """Read string from the instrument."""
        if self.mode == 0 and self.connection:
            response = self.connection.read().strip()
            logger.info(f'Считаны данные с PNA: "{response}"')
            return response
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружено подключение к pna при попытке чтения данных')
            raise WrongInstrumentError('Не обнаружено подключение к PNA')
        logger.info('Произведено чтения дынных из PNA')
        return ""

    def query(self, string: str) -> str:
        """Makes a request to the device and returns a response"""
        if self.mode == 0 and self.connection:
            response = self.connection.query(string)
            logger.info(f'Отправлена команда "{string}" на PNA')
            return response
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружено подключение к pna при попытке чтения данных')
            raise WrongInstrumentError('Не обнаружено подключение к PNA')
        logger.info(f'Отправлена команда "{string}" на PNA')
        return ""

    def set_power(self, port: int, value: float) -> None:
        """Установка мощности {value} дБм на порт номер {port}"""
        self.write(f'SOUR:POW{port} {value}')
        logger.info(f'Задано {value} дБм на порт №{port}')

    def get_data(self) -> Tuple[list, list]:
        """Получение данных измерений"""
        if self.mode == 0:
            # Реальная логика
            pass
        else:
            time.sleep(0.1)
            amps = [random.uniform(-10, 0) for _ in range(100)]
            phases = [random.uniform(-180, 180) for _ in range(100)]
            logger.info('Эмуляция get_data для PNA')
            return amps, phases

    def select_par(self, number: int) -> None:
        """Выбор параметра измерения"""
        self.write(f'CALC:PAR:MNUM {number}')
        logger.debug(f'Выбрано измерение №{number} на pna')

    def imm(self) -> None:
        """Запуск немедленного измерения"""
        self.write('INIT:IMM')
        logger.debug('Запущен триггер на измерение одного экрана pna')

    def set_ascii_data(self) -> None:
        """Установка формата данных ASCII"""
        self.write('FORM:DATA ascii')
        logger.debug('Установление формат данных ASCII на pna')

    def set_freq_start(self, value: int) -> None:
        """Установка начальной частоты в Гц"""
        self.write(f'SENS:FREQ:STAR {value}')
        logger.debug(f'Установлена начальная частота {value}Гц')

    def set_freq_stop(self, value: int) -> None:
        """Установка конечной частоты в Гц"""
        self.write(f'SENS:FREQ:STOP {value}')
        logger.info(f'Установлена конечная частота {value}Гц')

    def set_freq_points(self, value: int) -> None:
        """Установка количества частотных точек"""
        self.write(f'SENS:SWE:POIN {value}')
        logger.info(f'Установлено {value} частотных точек')

    def preset(self) -> None:
        """Сброс прибора"""
        self.write('*RST')
        logger.info('Произведен preset pna')

    def normalize(self) -> None:
        """Нормализация измерений"""
        self.write('CALC:MATH:MEM')
        self.write('CALC:MATH:FUNC DIV')
        logger.debug('Отнормировано текущее измерение на pna')

    def load_settings_file(self, filepath: str = None) -> None:
        """Загрузка файла настроек"""
        if self.mode == 0:
            self.write(f'MMEM:LOAD "{filepath}"')
            logger.debug(f'Подгружен файл настроек pna {filepath}')
        else:
            logger.info('Эмуляция загрузки файла настроек PNA (dev-режим)')

    def power_off(self) -> None:
        """Выключение питания"""
        self.write('OUTP OFF')
        logger.debug('Выключено СВЧ PNA')

    def get_mean_value(self) -> float:
        """Получение среднего значения"""
        self.write('CALC:FUNC:TYPE MEAN')
        result = float(self.query('CALC:FUNC:DATA?'))
        logger.debug('Запрошено среднее значение текущего измерения pna')
        return result

    def set_unwrapped_phase_type(self) -> None:
        """Установка типа фазы unwrapped"""
        self.write('CALC:FORM UPH')
        logger.debug('Установлен формат unwrapped phase на pna')

    def set_delay_type(self) -> None:
        """Установка типа задержки"""
        self.write('CALC:FROM GDEL')
        logger.debug('Установлен формат group delay на pna')

    def set_mlog_type(self) -> None:
        """Установка типа логарифмической шкалы"""
        self.write('CALC:FROM MLOG')
        logger.debug('Установлен формат LogM на pna')

    def power_on(self) -> None:
        """Включение питания"""
        self.write('OUTP ON')
        logger.debug('Включено СВЧ PNA')

    def get_files_in_dir(self, folder: str = None) -> list:
        """Получение списка файлов в директории"""
        command = f'MMEM:CAT? \"{folder}\"'
        result = self.query(command)
        result_list = result[1:len(result)-1].split(',')
        print(result_list)
        logger.debug(f'Запрошены файлы pna в folder={folder}')
        return result_list

    def measampphase(self) -> Tuple[float, float]:
        """Измерение амплитуды и фазы"""
        if self.mode == 0:
            #TODO Сделать создание маркеров на нужной частоте при настройке измерений
            self.write('CALC:PAR:SEL "CH1_S11_1"')
            amp = self.query('CALC:MARK2:Y?')
            amp = float(amp.split(',')[0])
            self.write('CALC:PAR:SEL "CH1_S12_1"')
            phase = self.query('CALC:MARK2:X?')
            phase = float(phase.split(',')[0])
            logger.info(f'Измерены амплитуда и фаза: amp={amp:.2f}, phase={phase:.2f}')
            return [amp, phase]
        else:
            time.sleep(0.1)
            amp = random.uniform(-5, 5)
            phase = random.uniform(-180, 180)
            logger.info(f'Эмуляция measampphase: amp={amp:.2f}, phase={phase:.2f}')
            return [amp, phase] 