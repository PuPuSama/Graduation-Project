#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DHT11温湿度传感器数据采集模块
提供简单的接口读取DHT11传感器的温度和湿度数据
基于Adafruit DHT库实现，支持DHT11、DHT22和DHT21/AM2301传感器
"""

import time
import board
import adafruit_dht
from loguru import logger
import sys
from typing import Tuple, Dict, Any
from hardware_config import PIN_DHT11

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("sensor_log.log", rotation="10 MB")

class DHTSensor:
    """DHT系列温湿度传感器通用类"""
    
    # 支持的传感器类型
    SENSOR_TYPES = {
        "DHT11": adafruit_dht.DHT11,
        "DHT22": adafruit_dht.DHT22,
        "DHT21": adafruit_dht.DHT21
    }
    
    # 树莓派GPIO引脚映射到board库的引脚
    PIN_MAPPING = {
        4: board.D4,
        5: board.D5,
        6: board.D6,
        7: board.D7,
        8: board.D8,
        12: board.D12,
        13: board.D13,
        16: board.D16,
        17: board.D17,
        18: board.D18,
        19: board.D19,
        20: board.D20,
        21: board.D21,
        22: board.D22,
        23: board.D23,
        24: board.D24,
        25: board.D25,
        26: board.D26,
        27: board.D27
    }
    
    def __init__(self, pin: int = PIN_DHT11, sensor_type: str = "DHT11", use_pulseio: bool = False):
        """
        初始化DHT系列传感器
        
        参数:
            pin: GPIO引脚号，默认从hardware_config导入
            sensor_type: 传感器类型，可选值为"DHT11"、"DHT22"或"DHT21"，默认为"DHT11"
            use_pulseio: 是否使用PulseIO，默认为False（使用bitbang模式，在树莓派上更可靠）
        """
        self.pin = pin
        self.sensor_type = sensor_type
        self.use_pulseio = use_pulseio
        
        # 初始化状态变量
        self.device = None
        self.last_temp = None  # 移除默认值
        self.last_humidity = None  # 移除默认值
        self.last_read_time = 0
        self.read_success_count = 0  # 成功读取计数器
        self.consecutive_failures = 0  # 连续失败计数
        
        # 根据传感器类型设置读取间隔（秒）
        self.read_interval = 2.5 if sensor_type == "DHT11" else 2.0
        
        # 初始化传感器设备
        self._initialize_sensor()
    
    def _initialize_sensor(self):
        """初始化传感器设备"""
        try:
            # 获取对应的board引脚
            board_pin = self.PIN_MAPPING.get(self.pin)
            
            if board_pin is None:
                logger.error(f"不支持的GPIO引脚: {self.pin}")
                return
            
            # 获取传感器类
            sensor_class = self.SENSOR_TYPES.get(self.sensor_type)
            if sensor_class is None:
                logger.error(f"不支持的传感器类型: {self.sensor_type}")
                return
            
            # 初始化传感器
            self.device = sensor_class(board_pin, use_pulseio=self.use_pulseio)
            logger.info(f"{self.sensor_type}传感器初始化完成，连接到GPIO{self.pin}")
            
        except Exception as e:
            logger.error(f"{self.sensor_type}传感器初始化失败: {e}")
    
    def read_data(self) -> Tuple[float, float]:
        """
        读取传感器数据
        
        返回:
            (humidity, temperature): 湿度和温度的元组，如果读取失败则返回上次的有效值
            如果没有有效值，返回(None, None)
        """
        current_time = time.time()
        
        # 限制读取频率
        if current_time - self.last_read_time < self.read_interval:
            return self.last_humidity, self.last_temp
        
        # 如果设备初始化失败，尝试重新初始化
        if self.device is None:
            if self.consecutive_failures % 10 == 0:  # 每10次失败尝试重新初始化
                logger.info(f"尝试重新初始化{self.sensor_type}传感器...")
                self._initialize_sensor()
            
            if self.device is None:
                self.consecutive_failures += 1
                return self.last_humidity, self.last_temp
        
        # 尝试读取传感器数据
        temperature = None
        humidity = None
        success = False
        
        # 重试2次
        for attempt in range(2):
            try:
                temperature = self.device.temperature
                humidity = self.device.humidity
                
                # 检查读取是否成功
                if humidity is not None and temperature is not None:
                    # 数据合理性检查
                    if not (0 <= humidity <= 100) or not (-40 <= temperature <= 80):
                        logger.debug(f"读取到不合理的数据: 温度={temperature}°C, 湿度={humidity}%")
                        continue
                    
                    # 更新最后一次有效读数
                    self.last_humidity = humidity
                    self.last_temp = temperature
                    self.last_read_time = current_time
                    self.read_success_count += 1
                    self.consecutive_failures = 0
                    
                    # 只在首次成功或每10次成功时记录日志
                    if self.read_success_count == 1 or self.read_success_count % 10 == 0:
                        logger.info(f"成功读取{self.sensor_type}传感器: 温度={temperature:.1f}°C, 湿度={humidity:.1f}%")
                    else:
                        logger.debug(f"读取成功: 温度={temperature:.1f}°C, 湿度={humidity:.1f}%")
                    
                    success = True
                    break
            except RuntimeError as e:
                # DHT传感器有时会返回错误，等待一下再试
                logger.debug(f"读取失败 (尝试 {attempt+1}/2): {e}")
                time.sleep(0.5)
                continue
            except Exception as e:
                logger.debug(f"读取{self.sensor_type}传感器时发生错误: {e}")
                break
        
        # 如果所有尝试都失败
        if not success:
            self.consecutive_failures += 1
            
            # 只在连续多次失败时才记录警告日志
            if self.consecutive_failures >= 5 and self.consecutive_failures % 5 == 0:
                logger.warning(f"连续{self.consecutive_failures}次读取{self.sensor_type}传感器失败")
            else:
                logger.debug(f"读取{self.sensor_type}传感器失败，使用上次的有效值")
        
        return self.last_humidity, self.last_temp
    
    def get_temperature(self) -> float:
        """获取温度值（摄氏度）"""
        _, temp = self.read_data()
        return temp
    
    def get_humidity(self) -> float:
        """获取湿度值（百分比）"""
        humidity, _ = self.read_data()
        return humidity
    
    def get_formatted_data(self) -> Dict[str, Any]:
        """
        获取格式化的传感器数据
        
        返回:
            包含温度、湿度、时间戳和传感器类型的字典
            如果数据不可用，温度和湿度字段为None
        """
        humidity, temperature = self.read_data()
        return {
            "temperature": round(temperature, 1) if temperature is not None else None,
            "humidity": round(humidity, 1) if humidity is not None else None,
            "timestamp": time.time(),
            "sensor": self.sensor_type
        }
    
    def cleanup(self) -> None:
        """清理资源，在程序结束时调用"""
        if self.device:
            try:
                self.device.exit()
                logger.info(f"{self.sensor_type}传感器资源已释放")
            except Exception as e:
                logger.debug(f"释放{self.sensor_type}传感器资源时发生错误: {e}")

class DHT11Sensor(DHTSensor):
    """DHT11温湿度传感器类，继承自DHTSensor"""
    
    def __init__(self, pin: int = PIN_DHT11, use_pulseio: bool = False):
        """
        初始化DHT11传感器
        
        参数:
            pin: GPIO引脚号，默认从hardware_config导入
            use_pulseio: 是否使用PulseIO，默认为False（使用bitbang模式，在树莓派上更可靠）
        """
        super().__init__(pin=pin, sensor_type="DHT11", use_pulseio=use_pulseio)

# 单例模式
_dht11_sensor = None

def get_dht11_sensor(pin: int = PIN_DHT11, use_pulseio: bool = False) -> DHT11Sensor:
    """
    获取DHT11传感器实例（单例模式）
    
    参数:
        pin: GPIO引脚号，默认从hardware_config导入
        use_pulseio: 是否使用PulseIO，默认为False
    
    返回:
        DHT11Sensor实例
    """
    global _dht11_sensor
    
    if _dht11_sensor is None:
        _dht11_sensor = DHT11Sensor(pin=pin, use_pulseio=use_pulseio)
    
    return _dht11_sensor

# 简单测试
if __name__ == "__main__":
    print("DHT11传感器测试程序")
    
    # 使用单例模式获取传感器实例
    sensor = get_dht11_sensor()
    
    try:
        print(f"开始读取{sensor.sensor_type}传感器数据...")
        while True:
            try:
                data = sensor.get_formatted_data()
                print(f"温度: {data['temperature']}°C, 湿度: {data['humidity']}%")
            except Exception as e:
                print(f"读取失败: {e}")
            time.sleep(2)
    except KeyboardInterrupt:
        sensor.cleanup()
        print("程序已退出") 