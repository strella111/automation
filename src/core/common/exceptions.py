class WrongInstrumentError(Exception):
    """Ошибка подключения к неправильному устройству"""
    pass
 
class PlanarScannerError(Exception):
    """Ошибка работы с планарным сканером"""
    pass

class BuAddrNotFound(Exception):
    """Ошибка поиска адреса БУ"""
    pass

class MaCommandNotDelivered(Exception):
    """Ошибка отправки команды на БУ."""
    pass