import socket
from loguru import logger
import serial
import time

from core.common.enums import Channel, Direction, PpmState
from core.common.exceptions import WrongInstrumentError
from utils.logger import format_device_log

class Afar:

    def __init__(self, connection_type, com_port=None, ip=None, port=None, mode=0, write_delay_ms=100):

        self.connection_type = connection_type
        self.com_port = com_port
        self.ip = ip
        self.port = port
        self.mode = mode
        self.write_delay_ms = write_delay_ms  # Задержка в миллисекундах перед отправкой команды
        self.connection = None
        self.CRC_POLY = 0x1021
        self.CRC_INIT = 0x1d0f
        self.ppm_data = [bytearray(25) for _ in range(40)]
        self.number_of_command = 1

    def connect(self):
        try:
            if self.connection_type == 'udp':
                if self.mode == 0:
                    if not self.ip or not self.port:
                        raise WrongInstrumentError("Для UDP подключения необходимо указать IP и порт")
                    self.connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.connection.connect((self.ip, self.port))
                    self.connection.settimeout(1)
                    self.connection.sendto(' '.encode()) # Отправить любые данные для инициализации
                    logger.debug(f"АФАР подключен. {self.ip}:{self.port}")
                    logger.info('Произведено подключение к АФАР')
                else:
                    logger.info("АФАР работает в тестовом режиме")
                    self.connection = True

            elif self.connection_type == 'com':
                if self.mode == 0:
                    if not self.com_port:
                        raise WrongInstrumentError("Для COM подключения необходимо указать COM-порт")
                    logger.info(f'Попытка подключения к COM-порту: {self.com_port}')
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
                        raise WrongInstrumentError(
                            f'Не удалось открыть COM-порт {self.com_port}. Проверьте: 1) Правильность номера порта, 2) Что порт не занят другим приложением, 3) Что устройство подключено') from serial_error

                    if not self.connection.is_open:
                        raise WrongInstrumentError(f'Не удалось подключиться к {self.com_port}. Порт закрыт.')

                    logger.info(f'COM-порт {self.com_port} успешно открыт.')

                else:
                    self.connection = True
                    logger.info('Произведено подключение к АФАР в тестовом режиме')

        except Exception as e:
            logger.error(f'Произошла ошибка при подключении к АФАР. {e}')
            raise WrongInstrumentError

    def disconnect(self):
        if self.connection:
            if self.mode == 0:
                self.connection.close()
            self.connection = None
            logger.info("Произведено отключение от АФАР")

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

    def write(self, string) -> None:
        """
        Отправка сообщения модулю

        Args:
            string: Данные
        """
        # Применяем настраиваемую задержку (если больше 0)
        if self.write_delay_ms > 0:
            time.sleep(self.write_delay_ms / 1000.0)  # Конвертируем миллисекунды в секунды
        
        if self.mode == 0:
            if self.connection_type == 'com':
                if not self.connection or not self.connection.is_open:
                    logger.error('Не обнаружено подключение к MA при попытке отправки данных')
                    raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
                self.connection.write(string if isinstance(string, bytes) else string.encode())
                logger.debug(format_device_log('АФАР', '>>', string))
            elif self.connection_type == 'udp':
                if not self.connection:
                    logger.error('При отправке команды на АФАР произошла ошибка: не обнаружено подлючение к PNA')
                    raise ConnectionError("АФАР не подключена")
                try:
                    self.connection.sendall((string + '\n').encode())
                    logger.debug(format_device_log('АФАР', '>>', string))
                except Exception as e:
                    logger.error(f"Ошибка отправки данных на PNA: {e}")
                    raise
        else:
            logger.debug(format_device_log('АФАР', '>>', string))

    def read(self):
        if self.mode == 0:
            if self.connection_type == 'com':
                if not self.connection or not self.connection.is_open:
                    logger.error('Не обнаружено подключение к MA при попытке чтения данных')
                    raise WrongInstrumentError('При попытке обращения к connection MA произошла ошибка')
                if self.connection.in_waiting > 0:
                    response = self.connection.read(self.connection.in_waiting)
                    logger.debug(format_device_log('MA', '<<', response))
                    return response
                logger.debug('Нет данных для чтения.')
                return b''
            elif self.connection_type == 'udp':
                if not self.connection:
                    logger.error('При чтении данных с АФАР произошла ошибка: не обнаружено подключение к PNA')
                    raise ConnectionError("АФАР не подключена")
                try:
                    response = self.connection.recv(65536).decode('ascii').strip()
                    return response
                except Exception as e:
                    logger.error(f"Ошибка чтения данных с АФАР: {e}")
                    raise
        return b''


    def _generate_command(self, bu_num: int, command_code: bytes, data: bytes=b'') -> bytes:
        preamble = b''
        if bu_num == 0:
            preamble = b'\x00\xhtff\x00'
        if 1 <= bu_num <= 8:
            preamble = b'\x00\x10\xef'
        elif 9 <= bu_num <= 16:
            preamble = b'\x00\x12\xed'
        elif 17 <= bu_num <= 24:
            preamble = b'\x00\x14\xeb'
        elif 25 <= bu_num <= 32:
            preamble = b'\x00\x16\xe9'
        elif 33 <= bu_num <= 40:
            preamble = b'\x00\x18\xe7'
        separator = b'\xaa'
        addr = bu_num.to_bytes(length=1, byteorder='big')
        command_id = self.number_of_command.to_bytes(2, byteorder='big')
        self.number_of_command += 1
        if self.number_of_command > 2 ** 16:
            self.number_of_command = 1
        data_bytes = bytes(data) if isinstance(data, bytearray) else data
        command = b''.join([separator, addr, command_code, command_id, data_bytes])
        crc = self._crc16(command).to_bytes(2, 'big')
        return b''.join([preamble, command, crc])


    def set_ppm_att(self, bu_num, chanel: Channel, direction: Direction, ppm_num:int, value: int):
        logger.info(f'БУ№{bu_num}. Установка аттенюатора {value} в ППМ№{ppm_num}. Канал - {chanel}, поляризация {direction}')
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
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)

    def set_mdo_att(self, bu_num: int, chanel: Channel, direction: Direction, value: int):
        logger.info(f'БУ№{bu_num}. Установка аттенюатора {value} в МДО. Канал - {chanel}, поляризация {direction}')
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
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)

    def switch_ppm(self, bu_num: int, ppm_num: int, chanel: Channel, direction: Direction, state: PpmState):
        if state == PpmState.ON:
            logger.info(f'БУ№{bu_num}. Включение ППМ №{ppm_num}. Канал - {chanel}, поляризация - {direction}')
        else:
            logger.info(f'БУ№{bu_num}. Выключение ППМ №{ppm_num}. Канал - {chanel}, поляризация - {direction}')
        ppm_num -= 1
        current_ppm_data = self.ppm_data[bu_num - 1]
        if chanel == Channel.Transmitter and direction == Direction.Horizontal:
            if state == PpmState.ON:
                current_ppm_data[16] = current_ppm_data[16] | 1
                if 0 <= ppm_num < 8:
                    current_ppm_data[0] = current_ppm_data[0] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[1] = current_ppm_data[1] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[2] = current_ppm_data[2] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[3] = current_ppm_data[3] | (1 << (ppm_num - 24))
            else:
                current_ppm_data[16] = current_ppm_data[16] & ~ 1
                if 0 <= ppm_num < 8:
                    current_ppm_data[0] = current_ppm_data[0] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[1] = current_ppm_data[1] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[2] = current_ppm_data[2] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[3] = current_ppm_data[3] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Transmitter and direction == Direction.Vertical:
            if state == PpmState.ON:
                current_ppm_data[16] = current_ppm_data[16] | (1 << 1)
                if 0 <= ppm_num < 8:
                    current_ppm_data[4] = current_ppm_data[4] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[5] = current_ppm_data[5] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[6] = current_ppm_data[6] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[7] = current_ppm_data[7] | (1 << (ppm_num - 24))
            else:
                current_ppm_data[16] = current_ppm_data[16] & ~ (1 << 1)
                if 0 <= ppm_num < 8:
                    current_ppm_data[4] = current_ppm_data[4] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[5] = current_ppm_data[5] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[6] = current_ppm_data[6] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[7] = current_ppm_data[7] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Receiver and direction == Direction.Horizontal:
            if state == PpmState.ON:
                current_ppm_data[16] = current_ppm_data[16] | (1 << 2)
                if 0 <= ppm_num < 8:
                    current_ppm_data[8] = current_ppm_data[8] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[9] = current_ppm_data[9] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[10] = current_ppm_data[10] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[11] = current_ppm_data[11] | (1 << (ppm_num - 24))
            else:
                current_ppm_data[16] = current_ppm_data[16] & ~ (1 << 2)
                if 0 <= ppm_num < 8:
                    current_ppm_data[8] = current_ppm_data[8] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[9] = current_ppm_data[9] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[10] = current_ppm_data[10] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[11] = current_ppm_data[11] & ~ (1 << (ppm_num - 24))

        if chanel == Channel.Receiver and direction == Direction.Vertical:
            if state == PpmState.ON:
                current_ppm_data[16] = current_ppm_data[16] | (1 << 3)
                if 0 <= ppm_num < 8:
                    current_ppm_data[12] = current_ppm_data[12] | (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[13] = current_ppm_data[13] | (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[14] = current_ppm_data[14] | (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[15] = current_ppm_data[15] | (1 << (ppm_num - 24))
            else:
                current_ppm_data[16] = current_ppm_data[16] & ~ (1 << 3)
                if 0 <= ppm_num < 8:
                    current_ppm_data[12] = current_ppm_data[12] & ~ (1 << ppm_num)
                if 8 <= ppm_num < 16:
                    current_ppm_data[13] = current_ppm_data[13] & ~ (1 << (ppm_num - 8))
                if 16 <= ppm_num < 24:
                    current_ppm_data[14] = current_ppm_data[14] & ~ (1 << (ppm_num - 16))
                if 24 <= ppm_num < 32:
                    current_ppm_data[15] = current_ppm_data[15] & ~ (1 << (ppm_num - 24))

        data = self.ppm_data[bu_num-1]
        command_code = b'\x33'
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)

    def set_phase_shifter(self, bu_num: int, ppm_num: int, chanel: Channel, direction: Direction, value: int):
        logger.info(f'БУ№{bu_num}. Включение рабочего значения ФВ№{value}({value*5.625}). Канал - {chanel}, поляризация - {direction}')
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
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)


    def turn_on_vips(self, bu_num: int, no_wait=False):
        logger.info(f'БУ№{bu_num}. Включение ВИПов')
        data = b'\xff\xff'
        data = bytes(data)
        command_code = b'\x0b'
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)
        if not no_wait:
            time.sleep(7)

    def turn_off_vips(self, bu_num: int):
        logger.info(f'БУ№{bu_num}. Выключение ВИПов')
        data = b'\x00\x00'
        data = bytes(data)
        command_code = b'\x0b'
        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)

    def set_delay(self, bu_num: int, chanel: Channel, direction: Direction, value: int):
        logger.info(f'БУ№{bu_num}. Включение ЛЗ№{value}. Канал - {chanel}')
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

        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)


    def set_calb_mode(self, bu_num: int,
                      chanel: Channel,
                      direction: Direction,
                      delay_number: int,
                      fv_number: int,
                      att_ppm_number,
                      att_mdo_number: int,
                      number_of_strobes: int):

        logger.info(f'БУ№{bu_num}. Включение режима калибровки')
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

        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)


    def preset_task(self, bu_num):
        logger.info(f'БУ№{bu_num}. Сброс задания на МА')
        command_code = b'\x66'
        command = self._generate_command(bu_num=bu_num, command_code=command_code)
        self.write(command)

    def set_task(self, bu_num: int, number_of_beam_prm: int, number_of_beam_prd: int, amount_strobs: int, is_cycle: bool):
        logger.info(f'Добавление луча в массив задания. '
                    f'НомерПрм - {number_of_beam_prm} '
                    f'НомерПрд - {number_of_beam_prd} '
                    f'Число стробов - {amount_strobs} '
                    f'Признак цикла - {"да" if is_cycle else "нет"}')
        command_code = b'\x65'
        data = bytearray()
        
        data.extend(number_of_beam_prm.to_bytes(2, byteorder='little'))
        data.extend(number_of_beam_prd.to_bytes(2, byteorder='little'))
        data.extend(amount_strobs.to_bytes(4, byteorder='little'))
        data.append(1 if is_cycle else 0)

        command = self._generate_command(bu_num=bu_num, command_code=command_code, data=data)
        self.write(command)


    def get_tm(self, bu_num: int):
        logger.info('БУ№{bu_num}. Запрошена телеметрия МА')
        command_code = b'\xfa'
        command = self._generate_command(bu_num=bu_num, command_code=command_code)
        self.write(command)
        time.sleep(0.005)
        response = self.read()
        if not response:
            logger.error(f"Не поступило ответа на команду КУ-ТМ от БУ№{bu_num}")
            return None

        if len(response) < 107:
            logger.error(f"Недостаточная длина ответа телеметрии: {len(response)} байт (ожидается минимум 107)")
            return None

        data = dict()
        try:
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
        except Exception as e:
            logger.error(f"Ошибка при парсинге телеметрии: {e}")
            return None










