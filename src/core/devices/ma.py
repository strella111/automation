import serial
import time
from typing import Optional, Union
from loguru import logger
from ..common.enums import Channel, Direction
from ..common.exceptions import WrongInstrumentError

class MA:
    """Класс для работы с модулем антенным"""
    
    def __init__(self, bu_addr: int, ma_num: int, com_port: str, mode: int = 0):
        """
        Инициализация модуля антенного
        
        Args:
            bu_addr: Адрес блока управления
            ma_num: Номер модуля антенного
            com_port: COM-порт для подключения
            mode: Режим работы (0 - реальный, 1 - тестовый)
        """
        self.bu_addr = bu_addr
        self.ma_num = ma_num
        self.com_port = com_port
        self.mode = mode
        self.connection = None
        self._poly = 0x1021
        self._preset = 0x1d0f

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
                logger.debug(f'Произведено подключение к {self.com_port}')
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

    def _crcb(self, data: bytes) -> int:
        """Вычисление CRC16"""
        crc = self._preset
        data = bytearray(data)
        for c in data:
            cc = 0xff & c
            tmp = (crc >> 8) ^ cc
            crc = (crc << 8) ^ self._tab[tmp & 0xff]
            crc = crc & 0xffff
        return crc
        
    def _send_command(self, command_id: bytes, data: bytes = b'') -> None:
        """Отправка команды в МА"""
        if not self.connection:
            logger.error('При отправке команды на МА произошла ошибка: не обнаружено подлючение к МА')
            raise ConnectionError("МА не подключен")
            
        if self.mode == 0:  # Реальный режим
            start_byte = b'\xaa'
            module_num_byte = self.bu_addr.to_bytes(1, 'big')
            arb_num = b'\x00\x00'
            
            command = b''.join([start_byte, module_num_byte, command_id, arb_num, data])
            command_crc = self._crcb(command).to_bytes(2, 'big')
            bytes_result = b''.join([command, command_crc])
            
            self.connection.write(bytes_result)
            time.sleep(0.1)
            
    def turn_vips_on(self):
        """Включение ВИП"""
        try:
            power_command_id = b'\x0b'
            power_command_vips_on = b'\x3f'
            self._send_command(power_command_id, power_command_vips_on)
            logger.info("ВИП включены")
        except Exception as e:
            logger.error(f"Ошибка включения ВИП: {e}")
            raise
            
    def turn_vips_off(self):
        """Выключение ВИП"""
        try:
            power_command_id = b'\x0b'
            power_command_vips_off = b'\x00'
            self._send_command(power_command_id, power_command_vips_off)
            logger.info("ВИП выключены")
        except Exception as e:
            logger.error(f"Ошибка выключения ВИП: {e}")
            raise
            
    def switch_ppm(self, ppm_num: int, direction: Direction, channel: Channel, state: bool):
        """Включение/выключение ППМ"""
        try:
            turn_on_cmd_id = b'\x33'
            data = bytearray(25)  # 25 байт нулей
            
            if state:  # Включение
                ppm_num = ppm_num - 1  # Нумерация с 0
                
                # Определяем смещение в массиве данных в зависимости от канала и поляризации
                if channel == Channel.Transmitter and direction == Direction.Horizontal:
                    data[16] = 1
                    if 0 <= ppm_num < 8:
                        data[0] = 1 << ppm_num
                    elif 8 <= ppm_num < 16:
                        data[1] = 1 << (ppm_num - 8)
                    elif 16 <= ppm_num < 24:
                        data[2] = 1 << (ppm_num - 16)
                    elif 24 <= ppm_num < 32:
                        data[3] = 1 << (ppm_num - 24)
                        
                elif channel == Channel.Transmitter and direction == Direction.Vertical:
                    data[16] = 2
                    if 0 <= ppm_num < 8:
                        data[4] = 1 << ppm_num
                    elif 8 <= ppm_num < 16:
                        data[5] = 1 << (ppm_num - 8)
                    elif 16 <= ppm_num < 24:
                        data[6] = 1 << (ppm_num - 16)
                    elif 24 <= ppm_num < 32:
                        data[7] = 1 << (ppm_num - 24)
                        
                elif channel == Channel.Receiver and direction == Direction.Horizontal:
                    data[16] = 4
                    if 0 <= ppm_num < 8:
                        data[8] = 1 << ppm_num
                    elif 8 <= ppm_num < 16:
                        data[9] = 1 << (ppm_num - 8)
                    elif 16 <= ppm_num < 24:
                        data[10] = 1 << (ppm_num - 16)
                    elif 24 <= ppm_num < 32:
                        data[11] = 1 << (ppm_num - 24)
                        
                elif channel == Channel.Receiver and direction == Direction.Vertical:
                    data[16] = 8
                    if 0 <= ppm_num < 8:
                        data[12] = 1 << ppm_num
                    elif 8 <= ppm_num < 16:
                        data[13] = 1 << (ppm_num - 8)
                    elif 16 <= ppm_num < 24:
                        data[14] = 1 << (ppm_num - 16)
                    elif 24 <= ppm_num < 32:
                        data[15] = 1 << (ppm_num - 24)
            
            self._send_command(turn_on_cmd_id, bytes(data))
            logger.info(f"ППМ {ppm_num + 1} {'включен' if state else 'выключен'}")
            
        except Exception as e:
            logger.error(f"Ошибка переключения ППМ {ppm_num}: {e}")
            raise
            
    def set_phase_shifter(self, ppm_num: int, direction: Direction, channel: Channel, value: int):
        """Установка значения фазовращателя"""
        try:
            set_ph_cmd_id = b'\x01'
            data_array = bytearray(128)  # 32 ППМ * 4 значения
            
            # Определяем индекс в массиве данных
            base_index = (ppm_num - 1) * 4
            offset = 0
            
            if channel == Channel.Transmitter and direction == Direction.Horizontal:
                offset = 0
            elif channel == Channel.Transmitter and direction == Direction.Vertical:
                offset = 1
            elif channel == Channel.Receiver and direction == Direction.Vertical:
                offset = 2
            elif channel == Channel.Receiver and direction == Direction.Horizontal:
                offset = 3
                
            index = base_index + offset
            data_array[index] = value % 64  # Значение должно быть в диапазоне 0-63
            
            self._send_command(set_ph_cmd_id, bytes(data_array))
            logger.info(f"Установлено значение ФВ {value} для ППМ {ppm_num}")
            
        except Exception as e:
            logger.error(f"Ошибка установки ФВ для ППМ {ppm_num}: {e}")
            raise
            
    def set_delay(self, channel: Channel, value: int):
        """Установка задержки"""
        try:
            delay_cmd_id = b'\x02'
            data_fv = bytearray(64)
            
            if channel == Channel.Receiver:
                data_lz_prm = value.to_bytes(1, 'big')
                data_lz_prd = b'\x00'
            else:
                data_lz_prd = value.to_bytes(1, 'big')
                data_lz_prm = b'\x00'
                
            data = b''.join([data_fv, data_lz_prd, data_lz_prm])
            self._send_command(delay_cmd_id, data)
            logger.info(f"Установлена задержка {value} для канала {channel.name}")
            
        except Exception as e:
            logger.error(f"Ошибка установки задержки: {e}")
            raise 