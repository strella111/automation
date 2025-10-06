import time
import pyvisa
from loguru import logger
from core.common.exceptions import WrongInstrumentError, PlanarScannerError
from utils.logger import format_device_log

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
            logger.info('Соединение с PSN закрыто')
        elif self.mode == 0 and not self.connection:
            logger.error('Не обнаружено подключение к PSN')
            raise WrongInstrumentError('При попытке обращения к connection PSN произошла ошибка')
        logger.info('Подключение к PSN закрыто')

    def write(self, string: str) -> None:
        """Write string to the instrument."""
        if self.mode == 0:
            if not self.connection:
                logger.error('Не обнаружено подключение к PSN при попытке отправки данных')
                raise WrongInstrumentError('Не обнаружено подключение к PSN')
            self.connection.write(string)
            logger.debug(format_device_log('PSN', '>>', string))
        else:
            logger.debug(format_device_log('PSN', '>>', string))
            time.sleep(0.01)

    def read(self) -> str:
        """Read string from the instrument."""
        if self.mode == 0:
            if not self.connection:
                logger.error('Не обнаружено подключение к PSN при попытке чтения данных')
                raise WrongInstrumentError('Не обнаружено подключение к PSN')
            response = self.connection.read().strip()
            logger.debug(format_device_log('PSN', '<<', response))
            return response
        else:
            logger.debug(format_device_log('PSN', '<<', '0'))
            time.sleep(0.01)
            return "0"

    def query(self, string: str) -> str:
        """Makes a request to the device and returns a response"""
        if self.mode == 0:
            if not self.connection:
                logger.error('Не обнаружено подключение к PSN при попытке запроса данных')
                raise WrongInstrumentError('Не обнаружено подключение к PSN')
            #logger.debug(format_device_log('PSN', '>>', string))
            response = self.connection.query(string)
            #logger.debug(format_device_log('PSN', '<<', response))
            return response
        else:
            time.sleep(0.01)
            #logger.debug(format_device_log('PSN', '>>', string))
            #logger.debug(format_device_log('PSN', '<<', '0'))
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
            logger.info(f'Перемещение сканера в точку ({x}, {y})')
            res = self.query("AXIS0:STAT:OP?")
            if res != "0":
                logger.error("Ошибка в оси X планарного сканера.")
                raise PlanarScannerError(f'Ошибка оси X: Статус {res}')
            res = self.query("AXIS1:STAT:OP?")
            if res != "0":
                logger.error("Ошибка в оси Y планарного сканера.")
                raise PlanarScannerError(f'Ошибка оси Y: Статус {res}')

            axis_x_move_string = "AXIS0:UMOV:ABS " + str(x + self.x_offset)
            axis_y_move_string = "AXIS1:UMOV:ABS " + str(y + self.y_offset)
            self.write(axis_x_move_string)
            self.write(axis_y_move_string)

            stat = False
            while not stat:
                stat_x = self.query("AXIS0:STAT:OP?")
                stat_y = self.query("AXIS1:STAT:OP?")
                if stat_x == '0' and stat_y == '0':
                    stat = True
                    time.sleep(0.1)


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
            value: Скорость в RPM
        """
        self.write(f'AXIS{axis}:SPE {value}')
        logger.info(f'Для AXIS{axis} установлена скорость {value} RPM')

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
        logger.info('Сброс PSN')

    def preset_axis(self, axis: int) -> None:
        """
        Сброс оси
        Args:
            axis: Ось (0: x, 1: y)
        """
        self.write(f'AXIS{axis}:PRESET')
        logger.info(f'Сброс оси {axis}') 