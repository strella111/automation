import serial
import time
from typing import Optional, Union
from loguru import logger
from ..common.enums import Channel, Direction
from ..common.exceptions import WrongInstrumentError

class MA:
    """Класс для работы с модулем антенным"""
    
    def __init__(self, bu_addr: int, ma_num: int, com_port: str, 
                 baudrate: int = 91600, timeout: int = 1, mode: int = 0):
        """
        Инициализация модуля антенного
        
        Args:
            bu_addr: Адрес блока управления
            ma_num: Номер модуля антенного
            com_port: COM-порт для подключения
            baudrate: Скорость передачи данных
            timeout: Таймаут операции
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.bu_addr = bu_addr
        self.ma_num = ma_num
        self.com_port = com_port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection: Optional[serial.Serial] = None
        self.mode = mode

    def connect(self) -> None:
        """Подключение к модулю антенному"""
        try:
            if self.mode == 0:
                self.connection = serial.Serial(
                    self.com_port,
                    baudrate=self.baudrate,
                    timeout=self.timeout
                )
                if not self.connection.is_open:
                    raise WrongInstrumentError(f'Не удалось подключиться к {self.com_port}. Порт закрыт.')
                logger.info(f'Произведено подключение к {self.com_port}')
            else:
                time.sleep(0.2)
                self.connection = True
            logger.info('Произведено подключение к MA')
        except serial.SerialException as e:
            logger.error(f'Ошибка подключения к MA - ошибка ввода/вывода: {e}')
            raise WrongInstrumentError('Ошибка ввода/вывода при подключении к MA') from e
        except Exception as e:
            logger.error(f'Неизвестная ошибка подключения к MA: {e}')
            raise WrongInstrumentError('Неизвестная ошибка подключения к MA') from e

    def disconnect(self) -> None:
        """Отключение от модуля антенного"""
        if self.mode == 0:
            if not self.connection:
                logger.error('Не обнаружено подключение к MA')
                raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
            self.connection.close()
        logger.info('Подключение к MA закрыто')

    def write(self, string: Union[str, bytes]) -> None:
        """
        Отправка сообщения модулю
        
        Args:
            string: Сообщение для отправки
        """
        if self.mode == 0:
            if not self.connection or not self.connection.is_open:
                logger.error('Не обнаружено подключение к MA при попытке отправки данных')
                raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
            self.connection.write(string if isinstance(string, bytes) else string.encode())
        logger.info(f'Отправлена команда "{string}" на MA')

    def read(self) -> bytes:
        """
        Чтение данных из модуля
        
        Returns:
            bytes: Прочитанные данные
        """
        if self.mode == 0:
            if not self.connection or not self.connection.is_open:
                logger.error('Не обнаружено подключение к MA при попытке чтения данных')
                raise WrongInstrumentError('Не обнаружено подключение к MA')
            if self.connection.in_waiting > 0:
                response = self.connection.read(self.connection.in_waiting)
                logger.info(f'Считаны данные с MA: "{response}"')
                return response
            logger.info('Нет данных для чтения.')
            return b''
        logger.info('Произведено чтение данных из MA')
        return b''

    def turn_on_vips(self) -> None:
        """Включение ВИПов"""
        logger.info('Включение ВИПов')
        if self.mode == 1:
            time.sleep(0.1)

    def turn_off_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> None:
        """
        Отключение ППМ
        
        Args:
            ppm_num: Номер ППМ
            channel: Канал
            direction: Направление
        """
        logger.info(f'Отключение ППМА№{ppm_num} канал {channel} поляризация {direction}')
        if self.mode == 1:
            time.sleep(0.05)

    def turn_on_ppm(self, ppm_num: int, channel: Channel, direction: Direction) -> None:
        """
        Включение ППМ
        
        Args:
            ppm_num: Номер ППМ
            channel: Канал
            direction: Направление
        """
        logger.info(f'Включение ППМА№{ppm_num} канал {channel} поляризация {direction}')
        if self.mode == 1:
            time.sleep(0.05)

    def set_phase_shifter(self, ppm_num: int, channel: Channel, direction: Direction, value: int) -> None:
        """
        Установка значения фазовращателя
        
        Args:
            ppm_num: Номер ППМ
            channel: Канал
            direction: Направление
            value: Значение фазовращателя
        """
        logger.info(f'Включение ФВ {value} ППМ№{ppm_num} канал {channel} поляризация {direction}')
        if self.mode == 1:
            time.sleep(1)

    def set_att(self, ppm_num: int, channel: Channel, direction: Direction, value: int) -> None:
        """
        Установка значения аттенюатора
        
        Args:
            ppm_num: Номер ППМ
            channel: Канал
            direction: Направление
            value: Значение аттенюатора
        """
        logger.info(f'Включение атт {value} ППМ№{ppm_num} канал {channel} поляризация {direction}')
        if self.mode == 1:
            time.sleep(0.03)

    def set_delay(self, channel: Channel, value: int) -> None:
        """
        Установка задержки
        
        Args:
            channel: Канал
            value: Значение задержки
        """
        logger.info(f'Установка задержки {value} для канала {channel}')
        if self.mode == 1:
            time.sleep(0.02)

    def read_ph_table(self) -> list:
        """
        Чтение таблицы фаз
        
        Returns:
            list: Таблица фаз
        """
        logger.info('Чтение таблицы фаз')
        if self.mode == 1:
            time.sleep(0.05)
        return []  # Возвращаем пустой список в dev режиме 