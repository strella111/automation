import serial
import time
from typing import Union
from loguru import logger

from core.common.enums import MdoState
from src.core.common.enums import Channel, Direction, PpmState
from src.core.common.exceptions import WrongInstrumentError, BuAddrNotFound, MaCommandNotDelivered

class MA:
    """Класс для работы с модулем антенным"""
    
    def __init__(self, com_port: str, mode: int = 0):
        """
        Инициализация модуля антенного
        
        Args:
            bu_addr: Адрес блока управления
            ma_num: Номер модуля антенного
            com_port: COM-порт для подключения
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.bu_addr = 0
        self.com_port = com_port
        self.mode = mode
        self.connection = None
        self.CRC_POLY = 0x1021
        self.CRC_INIT = 0x1d0f
        self.ppm_data = bytearray(25)
        self.retry_counter = 0

    def connect(self) -> None:
        """Подключение к модулю антенному"""
        try:
            if self.mode == 0:
                self.connection = serial.Serial(
                    port=self.com_port,
                    baudrate=921600,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_TWO,
                    timeout=1
                )
                if not self.connection.is_open:
                    raise WrongInstrumentError(f'Не удалось подключиться к {self.com_port}. Порт закрыт.')
                bu_num = self.search_bu_num()
                if bu_num == 0:
                    raise BuAddrNotFound('Не удалось найти нужный адрес БУ')
                else:
                    self.bu_addr = bu_num
                    logger.info(f'Произведено подключение к БУ№{self.bu_addr}')
            else:
                time.sleep(0.2)
                self.connection = True
                self.bu_addr = 1
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
            self.bu_addr = 0
        logger.info('Подключение к MA закрыто')

    def _generate_command(self, bu_num: int, command_code: bytes, data: bytes=b'') -> bytes:
        separator = b'\xaa'
        addr = bu_num.to_bytes(length=1, byteorder='big')
        command_id = b'\x00\x00'
        command = b''.join([separator, addr, command_code, command_id, data])
        crc = self._crc16(command).to_bytes(2, 'big')
        return b''.join([command, crc])

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
        logger.debug(f'На МА - "{string}"')

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
                logger.debug(f'От МА: "{response}"')
                return response
            logger.debug('Нет данных для чтения.')
            return b''
        return b''

    def _check_request(self):
        if self.mode == 0:
            command_code = b'\xFB'
            command = self._generate_command(bu_num=self.bu_addr, command_code=command_code)
            self.write(command)
            logger.debug(f'МА -> {command.hex(' ')}')
            response = self.read()
            if response:
                logger.debug(f'МА <- {command.hex(' ')}')
                if response[1] == b'\x00':
                    return True
                elif response[1] == b'\x01':
                    logger.error('Ошибка целостности принятой КУ ')
                    return False
                else:
                    logger.error(f'Код ошибки при выполнения последней КУ: {int(response[1])}')
                    return False
            return False
        else:
            return True

    def _crc16(self, data):
        """
        Параметры:
            data: bytes или bytearray - входные данные
        Возвращает:
            crc: int - значение CRC-16 (2 байта)
        """
        crc = self.CRC_INIT

        for byte in data:
            for bit in range(8):
                bit_val = (byte >> 7) & 1
                crc_msb = (crc >> 15) & 1

                if crc_msb ^ bit_val:
                    crc = (crc << 1) ^ self.CRC_POLY
                else:
                    crc = (crc << 1)

                crc &= 0xFFFF
                byte = (byte << 1) & 0xFF

        return crc

    def search_bu_num(self):
        if self.mode == 0:
            if not self.connection:
                logger.error('Не обнаружено подключение к MA')
                raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
            for i in range(1, 45):
                command = self._generate_command(i, command_code=b'\xfa')
                logger.debug(f'Команда на МА {command.hex(' ')}')
                self.write(command)
                response = self.read()
                if response:
                    logger.debug(f'Ответ от МА - {response.hex(' ')}')
                    return int(response[1])
        return 0

    def _send_command(self, command: bytes):
        self.write(command)
        logger.debug(f'МА -> {command}')
        if self._check_request():
            logger.debug(f'Команда f{command.hex(' ')} успешно принята БУ')
            return
        else:
            if self.retry_counter >= 3:
                logger.error(f'Команда f{command.hex(' ')} не принята бу.')
                raise MaCommandNotDelivered(f'После 3 попыток не удалось отправить команду {command.hex(' ')} на БУ')
            self.retry_counter += 1

    def turn_off_vips(self) -> None:
        logger.info('Отключение ВИПов')
        if self.mode == 1:
            time.sleep(0.1)
        else:
            command_code = b'\x0b'
            data = b'\x00'
            command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
            self._send_command(command)

    def turn_on_vips(self):
        logger.info('Отключение ВИПов')
        if self.mode == 1:
            time.sleep(0.1)
        else:
            command_code = b'\x0b'
            data = b'\x3f'
            command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
            self._send_command(command)

    def switch_ppm(self, ppm_num: int, chanel: Channel, direction: Direction, state: PpmState):
        if state == PpmState.ON:
            logger.info(f'Включение ППМ №{ppm_num}. Канал - {chanel}, поляризация - {direction}')
        else:
            logger.info(f'Выключение ППМ №{ppm_num}. Канал - {chanel}, поляризация - {direction}')
        ppm_num -= 1
        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            if state == PpmState.ON:
                self.ppm_data[16] = self.ppm_data[16] | 1
                if 0 <= ppm_num < 8:
                    self.ppm_data[0] = self.ppm_data[0] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[1] = self.ppm_data[1] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[2] = self.ppm_data[2] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[3] = self.ppm_data[3] | (1 << (ppm_num - 24))
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ 1
                if 0 <= ppm_num < 8:
                    self.ppm_data[0] = self.ppm_data[0] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[1] = self.ppm_data[1] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[2] = self.ppm_data[2] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[3] = self.ppm_data[3] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Transmitter and direction == Direction.Vertical:
            if state == PpmState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 1)
                if 0 <= ppm_num < 8:
                    self.ppm_data[4] = self.ppm_data[4] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[5] = self.ppm_data[5] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[6] = self.ppm_data[6] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[7] = self.ppm_data[7] | (1 << (ppm_num - 24))
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 1)
                if 0 <= ppm_num < 8:
                    self.ppm_data[4] = self.ppm_data[4] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[5] = self.ppm_data[5] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[6] = self.ppm_data[6] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[7] = self.ppm_data[7] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Receiver and direction == Direction.Horizontal:
            if state == PpmState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 2)
                if 0 <= ppm_num < 8:
                    self.ppm_data[8] = self.ppm_data[8] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[9] = self.ppm_data[9] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[10] = self.ppm_data[10] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[11] = self.ppm_data[11] | (1 << (ppm_num - 24))
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 2)
                if 0 <= ppm_num < 8:
                    self.ppm_data[8] = self.ppm_data[8] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[9] = self.ppm_data[9] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[10] = self.ppm_data[10] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[11] = self.ppm_data[11] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Receiver and direction == Direction.Vertical:
            if state == PpmState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 3)
                if 0 <= ppm_num < 8:
                    self.ppm_data[12] = self.ppm_data[12] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[13] = self.ppm_data[13] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[14] = self.ppm_data[14] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[15] = self.ppm_data[15] | (1 << (ppm_num - 24))
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 3)
                if 0 <= ppm_num < 8:
                    self.ppm_data[12] = self.ppm_data[12] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    self.ppm_data[13] = self.ppm_data[13] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    self.ppm_data[14] = self.ppm_data[14] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    self.ppm_data[15] = self.ppm_data[15] & ~ (1 << (ppm_num - 24))

        data = self.ppm_data
        command_code = b'\x33'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)

    def switch_mdo(self, chanel: Channel, direction: Direction, state: MdoState):
        if state == MdoState.ON:
            logger.info(f'Включение МДО. Канал - {chanel}, поляризация - {direction}')
        else:
            logger.info(f'Выключение МДО. Канал - {chanel}, поляризация - {direction}')

        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            if state == MdoState.ON:
                self.ppm_data[16] = self.ppm_data[16] | 1
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ 1
        if chanel == Channel.Transmitter and direction == Direction.Vertical:
            if state == MdoState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 1)
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 1)

        if chanel == Channel.Receiver and direction == Direction.Horizontal:
            if state == MdoState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 2)
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 2)

        if chanel == Channel.Receiver and direction == Direction.Vertical:
            if state == MdoState.ON:
                self.ppm_data[16] = self.ppm_data[16] | (1 << 3)
            else:
                self.ppm_data[16] = self.ppm_data[16] & ~ (1 << 3)

        data = self.ppm_data
        command_code = b'\x33'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)

    def set_phase_shifter(self, ppm_num: int, chanel: Channel, direction: Direction, value: int):
        logger.info(f'Включение ФВ№{value}({value*5.625}). Канал - {chanel}, поляризация - {direction}')
        data = bytearray(32 * 4)
        base_index = (ppm_num - 1) * 4
        offset = 0
        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            offset = 0
        elif chanel == Channel.Transmitter and direction == Direction.Vertical:
            offset = 1
        elif chanel == Channel.Receiver and direction == Direction.Vertical:
            offset = 2
        elif chanel == Channel.Receiver and direction == Direction.Horizontal:
            offset = 3
        index = base_index + offset
        data[index] = value
        data = bytes(data)
        command_code = b'\x01'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)



if __name__ == '__main__':
    ma = MA(com_port='Тестовый', mode=1)
    ma.search_bu_num()