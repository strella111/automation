import math
import random
import time
import pyvisa
import socket
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
        self.ip = ip
        self.port = port
        self.mode = mode
        self.connection = None

    def connect(self) -> None:
        """Подключение к PNA"""
        try:
            if self.mode == 0:  # Реальный режим
                self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.connection.connect((self.ip, self.port))
                self.connection.settimeout(3)
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

    def _send_command(self, command: str) -> str:
        """Отправка команды в PNA"""
        if not self.connection:
            logger.error('При отправке команды на PNA произошла ошибка: не обнаружено подлючение к PNA')
            raise ConnectionError("PNA не подключен")
        if self.mode == 0:  # Реальный режим
            try:
                self.connection.sendall((command + '\n').encode())
                logger.debug(f'На PNA - {command}')
                response = self.connection.recv(4096).decode().strip()
                logger.debug(f'От PNA - {response}')
                return response
            except Exception as e:
                logger.error(f"Ошибка отправки команды в PNA: {e}")
                raise 
        else:  # Тестовый режим
            logger.debug(f'На PNA - {command}')
            logger.debug(f'От PNA - 0')
            return "0"

    def preset(self) -> None:
        """Сброс PNA в начальное состояние"""
        try:
            self._send_command("*RST")
            logger.info("PNA сброшен в начальное состояние")
        except Exception as e:
            logger.error(f"Ошибка сброса PNA: {e}")
            raise

    def set_s_param(self, s_param: str):
        """Установка S-параметра"""
        try:
            self._send_command(f"CALC:PAR:SEL 'CH1_{s_param}_1'")
            logger.info(f"Установлен S-параметр {s_param}")
        except Exception as e:
            logger.error(f"Ошибка установки S-параметра: {e}")
            raise

    def set_power(self, power: float, port: int = 1):
        """Установка мощности"""
        try:
            self._send_command(f"SOUR:POW{port} {power}")
            logger.info(f"Установлена мощность {power} дБм на порту {port}")
        except Exception as e:
            logger.error(f"Ошибка установки мощности: {e}")
            raise

    def set_freq_start(self, freq: float):
        """Установка начальной частоты"""
        try:
            self._send_command(f"SENS:FREQ:STAR {freq}")
            logger.info(f"Установлена начальная частота {freq} Гц")
        except Exception as e:
            logger.error(f"Ошибка установки начальной частоты: {e}")
            raise

    def set_freq_stop(self, freq: float):
        """Установка конечной частоты"""
        try:
            self._send_command(f"SENS:FREQ:STOP {freq}")
            logger.info(f"Установлена конечная частота {freq} Гц")
        except Exception as e:
            logger.error(f"Ошибка установки конечной частоты: {e}")
            raise

    def set_points(self, points: int):
        """Установка количества точек измерения"""
        try:
            self._send_command(f"SENS:SWE:POIN {points}")
            logger.info(f"Установлено количество точек измерения {points}")
        except Exception as e:
            logger.error(f"Ошибка установки количества точек: {e}")
            raise

    def measure(self) -> tuple[float, float]:
        """Измерение амплитуды и фазы"""
        try:
            # Измеряем амплитуду
            self._send_command("CALC:PAR:SEL 'CH1_S11_1'")
            amp_result = self._send_command("CALC:MARK2:Y?")
            amp = float(amp_result.split(',')[0])
            
            # Измеряем фазу
            self._send_command("CALC:PAR:SEL 'CH1_S12_2'")
            phase_result = self._send_command("CALC:MARK2:Y?")
            phase = float(phase_result.split(',')[0])
            
            logger.debug(f"Измерение: amp={amp:.2f} дБ, phase={phase:.1f}°")
            return amp, phase
            
        except Exception as e:
            logger.error(f"Ошибка измерения: {e}")
            raise

    def set_output(self, state: bool):
        """Включение/выключение выхода"""
        try:
            self._send_command(f"OUTP {'ON' if state else 'OFF'}")
            logger.info(f"Выход PNA {'включен' if state else 'выключен'}")
        except Exception as e:
            logger.error(f"Ошибка управления выходом PNA: {e}")
            raise

    def load_state(self, filename: str):
        """Загрузка состояния из файла"""
        try:
            self._send_command(f'MMEM:LOAD "{filename}"')
            logger.info(f"Загружено состояние из файла {filename}")
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния: {e}")
            raise

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
        self._send_command(f'CALC:PAR:MNUM {number}')
        logger.debug(f'Выбрано измерение №{number} на pna')

    def imm(self) -> None:
        """Запуск немедленного измерения"""
        self._send_command('INIT:IMM')
        logger.debug('Запущен триггер на измерение одного экрана pna')

    def set_ascii_data(self) -> None:
        """Установка формата данных ASCII"""
        self._send_command('FORM:DATA ascii')
        logger.debug('Установление формат данных ASCII на pna')

    def normalize(self) -> None:
        """Нормализация измерений"""
        self._send_command('CALC:MATH:MEM')
        self._send_command('CALC:MATH:FUNC DIV')
        logger.debug('Отнормировано текущее измерение на pna')

    def load_settings_file(self, filepath: str = None) -> None:
        """Загрузка файла настроек"""
        if self.mode == 0:
            self._send_command(f'MMEM:LOAD "{filepath}"')
            logger.debug(f'Подгружен файл настроек pna {filepath}')
        else:
            logger.info('Эмуляция загрузки файла настроек PNA (dev-режим)')

    def power_off(self) -> None:
        """Выключение питания"""
        self._send_command('OUTP OFF')
        logger.debug('Выключено СВЧ PNA')

    def get_mean_value(self) -> float:
        """Получение среднего значения"""
        self._send_command('CALC:FUNC:TYPE MEAN')
        result = float(self._send_command('CALC:FUNC:DATA?'))
        logger.debug('Запрошено среднее значение текущего измерения pna')
        return result

    def set_unwrapped_phase_type(self) -> None:
        """Установка типа фазы unwrapped"""
        self._send_command('CALC:FORM UPH')
        logger.debug('Установлен формат unwrapped phase на pna')

    def set_delay_type(self) -> None:
        """Установка типа задержки"""
        self._send_command('CALC:FROM GDEL')
        logger.debug('Установлен формат group delay на pna')

    def set_mlog_type(self) -> None:
        """Установка типа логарифмической шкалы"""
        self._send_command('CALC:FROM MLOG')
        logger.debug('Установлен формат LogM на pna')

    def power_on(self) -> None:
        """Включение питания"""
        self._send_command('OUTP ON')
        logger.debug('Включено СВЧ PNA')

    def get_files_in_dir(self, folder: str = None) -> list:
        """Получение списка файлов в директории"""
        command = f'MMEM:CAT? \"{folder}\"'
        result = self._send_command(command)
        result_list = result[1:len(result)-1].split(',')
        print(result_list)
        logger.debug(f'Запрошены файлы pna в folder={folder}')
        return result_list

    def measampphase(self) -> Tuple[float, float]:
        """Измерение амплитуды и фазы"""
        if self.mode == 0:
            #TODO Сделать создание маркеров на нужной частоте при настройке измерений
            self._send_command('CALC:PAR:SEL "CH1_S11_1"')
            amp = self._send_command('CALC:MARK2:Y?')
            amp = float(amp.split(',')[0])
            self._send_command('CALC:PAR:SEL "CH1_S12_1"')
            phase = self._send_command('CALC:MARK2:X?')
            phase = float(phase.split(',')[0])
            logger.info(f'Измерены амплитуда и фаза: amp={amp:.2f}, phase={phase:.2f}')
            return [amp, phase]
        else:
            time.sleep(0.1)
            amp = random.uniform(-5, 5)
            phase = random.uniform(-180, 180)
            logger.info(f'Эмуляция measampphase: amp={amp:.2f}, phase={phase:.2f}')
            return [amp, phase] 