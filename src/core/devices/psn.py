import time
import pyvisa
from typing import Optional
from loguru import logger
from ..common.enums import Channel, Direction
from ..common.exceptions import WrongInstrumentError, PlanarScannerError

class PSN:
    """Класс планарнего сканера"""
    def __init__(self, ip: str, port: int, mode: int = 0):
        """
        Конструктор класса
        Args:
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.ip = ip
        self.port = port
        self.connection = None
        self.x_offset = 0
        self.y_offset = 0
        self.mode = mode
        self.visa_name = f'TCPIP0::{self.ip}::{self.port}::SOCKET'

    def set_offset(self, x: float, y: float) -> None:
        """
        Установка офсета системы координат относительно аппаратной системы координат
        Args:
            x: Смещение по оси X
            y: Смещение по оси Y
        """
        self.x_offset = x
        self.y_offset = y

    def connect(self) -> None:
        """Подключение к сканеру"""
        try:
            if self.mode == 0:
                rm = pyvisa.ResourceManager()
                self.connection = rm.open_resource(self.visa_name)
                self.connection.read_termination = '\n'
                self.connection.write_termination = '\n'
                self.write('*IDN?')
                response = self.read()
                if 'RADIOLINE' not in response:
                    raise WrongInstrumentError(
                        'Wrote "ID" Expected "7230" got "{}"'.format(response))
                logger.info('Произведено подключение к PSN')
            else:
                time.sleep(0.2)
                self.connection = True
                logger.info('Произведено подключние к PSN')
        except Exception as e:
            logger.error(f'Ошибка при подключении к PSN: {e}')
            raise WrongInstrumentError(f'Ошибка подключения к PSN: {e}') from e

    def disconnect(self) -> None:
        """Отключение от сканера"""
        if self.mode == 0 and self.connection:
            self.connection.close()
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружено подключение к PSN')
            raise WrongInstrumentError('При попытке обращения к connection PSN произошла ошибка')
        logger.info('Подключение к PSN закрыто')

    def write(self, string: str) -> None:
        """Write string to the instrument."""
        if self.mode == 0:
            self.connection.write(string)
        else:
            logger.info(f'Вызов метода psn.write. command="{string}"')
            time.sleep(0.01)

    def read(self) -> str:
        """Read string from the instrument."""
        if self.mode == 0:
            response = self.connection.read().strip()
            return response
        else:
            logger.info('Вызов метода psn.read')
            time.sleep(0.01)
            return "0"

    def query(self, string: str) -> str:
        """Makes a request to the device and returns a response"""
        if self.mode == 0:
            response = self.connection.query(string)
            return response
        else:
            logger.info(f'Вызов метода psn.query. command="{string}"')
            time.sleep(0.01)
            if "STAT:OP?" in string:
                return "0"
            elif "STAT:UPOS?" in string:
                return "0.0"
            elif "SYST:ERR?" in string:
                return "No error"
            return "0"

    def move(self, x: float, y: float) -> None:
        """
        Перемещение каретки сканера в точку (x, y)
        в пользовательской системе координат, которая задается переменными
        Args:
            x: Координата X
            y: Координата Y
        """
        try:
            res = self.query("AXIS0:STAT:OP?")
            if res != "0":
                logger.error("Ошибка в оси X планарного сканера.")
                raise PlanarScannerError(f'Ошибка оси X: Статус {res}')
            res = self.query("AXIS0:STAT:UPOS?")
            current_x_pos = float(res) - self.x_offset

            res = self.query("AXIS1:STAT:OP?")
            if res != "0":
                logger.error("Ошибка в оси Y планарного сканера.")
                raise PlanarScannerError(f'Ошибка оси Y: Статус {res}')
            res = self.query("AXIS1:STAT:UPOS?")
            current_y_pos = float(res) - self.y_offset

            x_diff = x - current_x_pos
            y_diff = y - current_y_pos
            axis_x_move_string = "AXIS0:UMOV " + str(x_diff)
            axis_y_move_string = "AXIS1:UMOV " + str(y_diff)
            self.write(axis_x_move_string)
            self.write(axis_y_move_string)

            dist = (abs(x_diff) ** 2 + abs(y_diff) ** 2) ** 0.5
            probe_speed = 14
            min_time = 1.2
            delay = dist / probe_speed + min_time
            logger.info(f'PSN move to ({x}, {y})')
            time.sleep(delay)
        except Exception as e:
            logger.error(f'Ошибка при перемещении планарного сканера в точку ({x}, {y}): {e}')
            raise PlanarScannerError(f'Ошибка перемещения PSN: {e}') from e

    def check_errors(self) -> None:
        """Проверка ошибок сканера"""
        err_check = self.query('SYST:ERR?')
        if 'No error' not in err_check:
            logger.error(f'Обнаружена ошибка в планарном сканере. {err_check}')
            raise PlanarScannerError(err_check)

    def set_speed(self, axis: int, value: int) -> None:
        """
        Установить скорость осей сканера в см/сек
        Args:
            axis: Ось (0: x, 1: y)
            value: Скорость в см/сек
        """
        if 1 <= value <= 50:
            self.write(f'AXIS{axis}:USPE {value}')
            logger.info(f'Для AXIS{axis} установлена скорость {value} см/сек')
        else:
            logger.error(f'Недопустимое значение скорости: {value}. Диапазон: 1–50.')
            raise ValueError('Скорость должна быть в диапазоне от 1 до 50 см/сек')

    def set_acc(self, axis: int, value: int) -> None:
        """
        Установить ускорение осей сканера
        Args:
            axis: Ось (0: x, 1: y)
            value: Значение ускорения
        """
        self.write(f'AXIS{axis}:ACC {value}')
        logger.info(f'Для AXIS{axis} установлено ускорение {value}')

    def preset(self) -> None:
        """Сброс прибора"""
        self.write('*CLS')
        logger.info('Preset PSN')

    def preset_axis(self, axis: int) -> None:
        """
        Сброс оси
        Args:
            axis: Ось (0: x, 1: y)
        """
        self.write(f'AXIS{axis}:PRESET')
        logger.debug(f'Сброс AXIS{axis}') 