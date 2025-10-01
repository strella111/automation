from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.psn import PSN
from core.devices.trigger_box import E5818, E5818Config


class DeviceConnectionWorker(QThread):
    """Класс для асинхронного подключения к устройствам"""
    connection_finished = pyqtSignal(str, bool, str, object)  # device_name, success, message, device_instance
    
    def __init__(self, device_type: str, connection_params: dict):
        super().__init__()
        self.device_type = device_type
        self.connection_params = connection_params
        
    def run(self):
        """Выполняет подключение к устройству в отдельном потоке"""
        try:
            if self.device_type == 'MA':
                device = MA(**self.connection_params)
                device.connect()
                if device.bu_addr:
                    message = f"МА №{device.bu_addr} подключен"
                else:
                    message = "МА подключен"
                self.connection_finished.emit('MA', True, message, device)
                
            elif self.device_type == 'PNA':
                device = PNA(**self.connection_params)
                device.connect()
                message = "PNA подключен"
                self.connection_finished.emit('PNA', True, message, device)
                
            elif self.device_type == 'PSN':
                device = PSN(**self.connection_params)
                device.connect()
                message = "Планарный сканер подключен"
                self.connection_finished.emit('PSN', True, message, device)
                
            elif self.device_type == 'Trigger':
                device = E5818(self.connection_params['config'])
                idn = device.connect()
                message = f"Устройство синхронизации подключено: {idn if idn else 'OK'}"
                self.connection_finished.emit('Trigger', True, message, device)
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка подключения к {self.device_type}: {error_msg}")
            self.connection_finished.emit(self.device_type, False, error_msg, None)
