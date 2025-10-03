import serial
import time
from typing import Union
from loguru import logger

from core.common.enums import Channel, Direction, PpmState
from core.common.exceptions import WrongInstrumentError, BuAddrNotFound, MaCommandNotDelivered
from utils.logger import format_device_log

class MA:
    """Класс для работы с модулем антенным"""
    
    def __init__(self, com_port: str, mode: int = 0, command_delay=0.1):
        """
        Инициализация модуля антенного
        
        Args:
            com_port: COM-порт для подключения
            mode: Режим работы (0 - реальный, 1 - тестовый)
            command_delay: Задержка между отправкой команд на МА
        """
        self.bu_addr = 0
        self.com_port = com_port
        self.mode = mode
        self.connection = None
        self.CRC_POLY = 0x1021
        self.CRC_INIT = 0x1d0f
        self.ppm_data = bytearray(25)
        self.retry_counter = 0
        self.command_delay = command_delay

    def connect(self) -> None:
        """Подключение к модулю антенному"""
        try:
            if self.mode == 0:
                logger.info(f'Попытка подключения к COM-порту: {self.com_port}')
                
                # Проверяем доступность порта
                try:
                    self.connection = serial.Serial(
                        port=self.com_port,
                        baudrate=921600,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_TWO,
                        timeout=1
                    )
                except serial.SerialException as serial_error:
                    logger.error(f'Не удалось открыть COM-порт {self.com_port}: {serial_error}')
                    raise WrongInstrumentError(f'Не удалось открыть COM-порт {self.com_port}. Проверьте: 1) Правильность номера порта, 2) Что порт не занят другим приложением, 3) Что устройство подключено') from serial_error
                
                if not self.connection.is_open:
                    raise WrongInstrumentError(f'Не удалось подключиться к {self.com_port}. Порт закрыт.')
                
                logger.info(f'COM-порт {self.com_port} успешно открыт, ищем БУ...')
                
                bu_num = self.search_bu_num()
                if bu_num == 0:
                    self.connection.close()
                    raise BuAddrNotFound('Не удалось найти нужный адрес БУ. Проверьте: 1) Что устройство включено, 2) Правильность подключения, 3) Настройки COM-порта')
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
            string: Данные
        """
        if self.mode == 0:
            if not self.connection or not self.connection.is_open:
                logger.error('Не обнаружено подключение к MA при попытке отправки данных')
                raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
            self.connection.write(string if isinstance(string, bytes) else string.encode())
            time.sleep(self.command_delay)
            logger.debug(format_device_log('MA', '>>', string))

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
                logger.debug(format_device_log('MA', '<<', response))
                return response
            logger.debug('Нет данных для чтения.')
            return b''
        return b''

    def _check_request(self):
        if self.mode == 0:
            command_code = b'\xFB'
            command = self._generate_command(bu_num=self.bu_addr, command_code=command_code)
            self.write(command)
            response = self.read()
            if response:
                if response[6] == 0x00:
                    return True
                elif response[6] == 0x01:
                    logger.error('Ошибка целостности принятой КУ ')
                    return False
                else:
                    logger.error(f'Код ошибки при выполнения последней КУ: {int(response[6])}')
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
            
            logger.info('Начинаем поиск БУ (адреса 1-44)...')
            for i in range(1, 45):
                try:
                    command = self._generate_command(i, command_code=b'\xfa')
                    self.write(command)
                    time.sleep(0.1)
                    response = self.read()
                    if response and len(response) >= 2:
                        logger.info(f'Найден БУ с адресом: {int(response[1] & 0x3f)}')
                        return int(response[1] & 0x3f)
                    else:
                        logger.debug(f'Нет ответа от БУ #{i}')
                except Exception as e:
                    logger.debug(f'Ошибка при опросе БУ #{i}: {e}')
                    continue
            
            logger.warning('Поиск БУ завершен, ни один БУ не ответил')
        return 0

    def _send_command(self, command: bytes, is_check: bool = True):
        self.write(command)
        response = self.read()
        if response:
            if response[6] == 0x00:
                logger.info('Команда успешно принята БУ')
                self.retry_counter = 0
            else:
                logger.error(f'Код ошибки при выполнения последней КУ: {int(response[6])}')
                if self.retry_counter > 3:
                    logger.error(f'После 3 попыток не удалось отправить команду {command.hex(" ")} на БУ')
                    return
                    #raise MaCommandNotDelivered(f'После 3 попыток не удалось отправить команду {command.hex(" ")} на БУ')
                time.sleep(0.5)
                self.retry_counter += 1
                self._send_command(command, is_check=True)


    def set_ppm_att(self, chanel: Channel, direction: Direction, ppm_num:int, value: int):
        logger.info(f'Установка аттенюатора {value} в ППМ№{ppm_num}. Канал - {chanel}, поляризация {direction}')
        command_code = b'\x09'
        data = bytearray(99)
        offset = 0
        if chanel == Channel.Transmitter:
            offset = 0
        elif chanel == chanel.Receiver and direction == Direction.Horizontal:
            offset = 1
        elif chanel == chanel.Receiver and direction == Direction.Vertical:
            offset = 2

        index = (ppm_num - 1) * 3 + offset
        data[index] = value
        data = bytes(data)
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)

    def set_mdo_att(self, chanel: Channel, direction: Direction, value: int):
        logger.info(f'Установка аттенюатора {value} в МДО. Канал - {chanel}, поляризация {direction}')
        command_code = b'\x09'
        data = bytearray(99)
        index = 0
        if chanel == Channel.Transmitter:
            index = 96
        elif chanel == chanel.Receiver and direction == Direction.Horizontal:
            index = 97
        elif chanel == chanel.Receiver and direction == Direction.Vertical:
            index = 98

        data[index] = value
        data = bytes(data)
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


    def set_phase_shifter(self, ppm_num: int, chanel: Channel, direction: Direction, value: int):
        logger.info(f'Включение рабочего значения ФВ№{value}({value*5.625}). Канал - {chanel}, поляризация - {direction}')
        data = bytearray(35)
        chanel_byte = b''
        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            chanel_byte = 0x81
        elif chanel == Channel.Transmitter and direction == Direction.Vertical:
            chanel_byte = 0x82
        elif chanel == Channel.Receiver and direction == Direction.Vertical:
            chanel_byte = 0x88
        elif chanel == Channel.Receiver and direction == Direction.Horizontal:
            chanel_byte = 0x84
        data[0] = chanel_byte
        data[ppm_num] = value
        data = bytes(data)
        command_code = b'\x02'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)

    def turn_on_vips(self):
        logger.info(f'Включение ВИПов')
        data = b'\xff\xff'
        data = bytes(data)
        command_code = b'\x0b'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command, is_check=False)
        time.sleep(7)

    def turn_off_vips(self):
        logger.info(f'Выключение ВИПов')
        data = b'\x00\x00'
        data = bytes(data)
        command_code = b'\x0b'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command, is_check=False)


    def set_delay(self, chanel: Channel, direction: Direction, value: int):
        logger.info(f'Включение ЛЗ№{value}. Канал - {chanel}')
        command_code = b'\x02'
        data = bytearray(35)
        chanel_byte = b''
        if chanel == Channel.Receiver and direction == Direction.Horizontal:
            chanel_byte = 0x84
        elif chanel == Channel.Receiver and direction == Direction.Vertical:
            chanel_byte = 0x88
        elif chanel == Channel.Transmitter and direction == Direction.Horizontal:
            chanel_byte = 0x81
        elif chanel == Channel.Transmitter and direction == Direction.Vertical:
            chanel_byte = 0x82
        data[0] = chanel_byte
        data[33] = value
        data = bytes(data)

        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)


    def set_calb_mode(self, chanel: Channel,
                      direction: Direction,
                      delay_number: int,
                      fv_number: int,
                      att_ppm_number,
                      att_mdo_number: int,
                      number_of_strobes: int):

        logger.info('Включение режима калибровки')
        command_code = b'\xc9'
        data = bytearray(6)
        chanel_byte = 0x00
        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            chanel_byte = 0x01
        elif chanel == Channel.Transmitter and direction == Direction.Vertical:
            chanel_byte = 0x02
        elif chanel == Channel.Receiver and direction == Direction.Horizontal:
            chanel_byte = 0x04
        elif chanel == Channel.Receiver and direction == Direction.Vertical:
            chanel_byte = 0x08
        data[0] = chanel_byte
        data[1] = delay_number
        data[2] = fv_number
        data[3] = att_ppm_number
        data[4] = att_mdo_number
        data[5] = number_of_strobes

        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code, data=data)
        self._send_command(command)

    def preset_task(self):
        logger.info('Сбро задания на МА')
        command_code = b'\x66'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code)
        self._send_command(command)

    def get_tm(self):
        logger.info('Запрошена телеметрия МА')
        command_code = b'\xfa'
        command = self._generate_command(bu_num=self.bu_addr, command_code=command_code)
        self.write(command)
        response = self.read()
        if not response:
            logger.error(f"Не поступило ответа на команду КУ-ТМ от БУ№{self.bu_addr}")

        data = dict()
        data['addr']= int(response[1] & 0x3f)
        data['command_code'] = response[2]
        data['command_id'] = response[3:5]
        data['crc'] = response[-2:]
        for j in range(32):
            data[f'ppm{j+1}'] = response[5+j:5+j+2]

        data['mdo'] = response[69:72]
        data['bu'] = response[72]
        data['vip1'] = response[73:75]
        data['vip2'] = response[75:77]
        data['table_beam_number'] = int.from_bytes(response[77:79], byteorder='big')
        data['crc_of_table_beam_number'] = response[79:83]
        data['crc_calb_table'] = response[83:87]
        data['strobs_prd'] = int.from_bytes(response[87:91], byteorder='big')
        data['strobs_prm'] = int.from_bytes(response[91:95], byteorder='big')
        data['amount_beams'] = int.from_bytes(response[95:97], byteorder='big')
        data['beam_number_prd'] = int.from_bytes(response[97:99], byteorder='big')
        data['beam_number_prm'] = int.from_bytes(response[99:101], byteorder='big')
        data['configuration_ports'] = response[101]
        data['crc_voltage_table'] = response[102:106]
        data['state_bu'] = response[106]

        return data








if __name__ == '__main__':
    ma = MA('COM8', mode=0)
    ma.connect()
    ma.turn_on_vips()
    ma.switch_ppm(12, chanel=Channel.Transmitter, direction=Direction.Horizontal, state=PpmState.ON)
    for i in range(16):
        ma.set_delay(chanel=Channel.Transmitter, direction=Direction.Horizontal, value=i)




