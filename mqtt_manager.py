#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MQTT管理模块
使用单例模式管理MQTT客户端，确保系统中只有一个MQTT客户端实例
提供全局访问点，避免多次初始化和资源冲突
统一硬件控制接口
"""

import time
import threading
import os
import json
import RPi.GPIO as GPIO
from loguru import logger

# 导入硬件配置
from hardware_config import PIN_LED, PIN_BUZZER

# 导入MQTT传感器客户端
from mqtt_sensor_client import MQTTSensorClient

# 导入传感器和控制器模块
from dht11_sensor import get_dht11_sensor
from led_control import get_led_controller

# 配置日志
logger.add("Log/mqtt_manager.log", rotation="10 MB", compression="zip", level="INFO")

# 全局变量
_mqtt_client = None  # MQTT客户端实例
_mqtt_lock = threading.Lock()  # 线程锁，保护MQTT客户端访问
_initialized = False  # 初始化标志

class MockMQTTClient:
    """
    模拟MQTT客户端，用于测试环境
    提供与真实MQTT客户端相同的接口，但不实际连接MQTT服务器
    """
    def __init__(self):
        from led_control import get_led_controller
        from dht11_sensor import get_dht11_sensor
        
        self.connected = True
        self.led_controller = get_led_controller()
        self.dht11_sensor = get_dht11_sensor()
        self.running = True
        logger.info("模拟MQTT客户端已初始化（测试模式）")
    
    def publish_device_state(self, device, state, brightness=None):
        """模拟发布设备状态"""
        logger.info(f"模拟发布设备状态: {device}={state}, 亮度={brightness if brightness is not None else 'N/A'}")
        return True
    
    def publish_sensor_data(self):
        """模拟发布传感器数据"""
        try:
            # 获取DHT11传感器数据
            dht11_data = self.dht11_sensor.get_formatted_data()
            
            # 检查传感器数据
            temp_str = f"{dht11_data['temperature']}°C" if dht11_data['temperature'] is not None else "N/A"
            humidity_str = f"{dht11_data['humidity']}%" if dht11_data['humidity'] is not None else "N/A"
            
            logger.info(f"模拟发布传感器数据: 温度={temp_str}, 湿度={humidity_str}")
            return True
        except Exception as e:
            logger.error(f"模拟发布传感器数据时出错: {e}")
            return False
    
    def control_buzzer(self, state):
        """模拟控制蜂鸣器"""
        logger.info(f"模拟控制蜂鸣器: {'开启' if state else '关闭'}")
        return True
    
    def blink_led(self, times=3, interval=0.5):
        """模拟LED闪烁"""
        try:
            if self.led_controller:
                result = self.led_controller.blink(times, interval)
                logger.info(f"模拟LED闪烁: {times}次, 间隔{interval}秒")
                return result
            else:
                logger.error("LED控制器未初始化，无法执行闪烁")
                return False
        except Exception as e:
            logger.error(f"模拟LED闪烁时出错: {e}")
            return False
    
    def connect(self):
        """模拟MQTT连接"""
        logger.info("模拟MQTT连接成功")
        return True
    
    def start(self):
        """模拟启动MQTT客户端"""
        logger.info("模拟MQTT客户端启动")
        return True
    
    def stop(self):
        """模拟停止MQTT客户端"""
        self.running = False
        self.connected = False
        logger.info("模拟MQTT客户端已停止")
        return True

def get_mqtt_client():
    """
    获取MQTT客户端实例（单例模式）
    
    返回:
        MQTTSensorClient实例或None（如果初始化失败）
    """
    global _mqtt_client
    
    # 检查是否在测试模式下运行
    is_test_mode = os.environ.get('TESTING', '0') == '1'
    
    if _mqtt_client is None:
        try:
            if is_test_mode:
                # 测试模式下使用模拟客户端
                _mqtt_client = MockMQTTClient()
                logger.info("MQTT模拟客户端已启动（测试模式）")
            else:
                # 正常模式下初始化真实MQTT客户端
                _mqtt_client = MQTTSensorClient()
                logger.info("MQTT传感器客户端已启动")
        except Exception as e:
            logger.error(f"初始化MQTT客户端时出错: {e}")
            return None
    
    return _mqtt_client

def stop_mqtt_client():
    """
    停止MQTT客户端
    在程序退出前调用，确保资源被正确释放
    """
    global _mqtt_client
    
    with _mqtt_lock:
        if _mqtt_client:
            try:
                # 检查是否是模拟客户端
                if isinstance(_mqtt_client, MockMQTTClient):
                    _mqtt_client.stop()
                    logger.info('模拟MQTT客户端已停止')
                else:
                    _mqtt_client.stop()
                    logger.info('MQTT传感器客户端已停止')
            except Exception as e:
                logger.error(f"停止MQTT客户端时出错: {e}")
            finally:
                _mqtt_client = None

def get_sensor_data():
    """
    获取所有传感器数据
    
    返回:
        包含温度和湿度的字典，如果数据不可用，字段值为None
    """
    current_time = time.time()
    
    try:
        # 尝试通过MQTT客户端获取传感器数据
        client = get_mqtt_client()
        if client and hasattr(client, 'dht11_sensor'):
            dht11_data = client.dht11_sensor.get_formatted_data()
            
            # 构建传感器数据响应
            sensor_data = {
                "temperature": dht11_data["temperature"],
                "humidity": dht11_data["humidity"],
                "timestamp": current_time
            }
            
            return sensor_data
        else:
            # 如果MQTT客户端不可用，尝试直接获取DHT11传感器数据
            sensor = get_dht11_sensor()
            if sensor:
                dht_data = sensor.get_formatted_data()
                return {
                    "temperature": dht_data["temperature"],
                    "humidity": dht_data["humidity"],
                    "timestamp": current_time
                }
    except Exception as e:
        logger.error(f"获取传感器数据时出错: {e}")
    
    # 返回数据不可用的响应
    return {
        "temperature": None,
        "humidity": None,
        "timestamp": current_time,
        "status": "获取传感器数据失败"
    }

def get_device_status():
    """
    获取设备状态
    
    返回:
        包含LED状态的字典
    """
    led = get_led_controller()
    
    try:
        # 获取设备状态
        device_status = {
            "led": led.is_on,
            "led_brightness": led.brightness if led.is_on else 0
        }
        
        return device_status
    except Exception as e:
        logger.error(f"获取设备状态时出错: {e}")
        return {
            "led": False,
            "led_brightness": 0,
            "status": f"错误: {str(e)}"
        }

def control_led(state, brightness=None):
    """
    控制LED灯
    
    参数:
        state: 布尔值，True表示开启，False表示关闭
        brightness: 亮度百分比(0-100)，可选
    
    返回:
        布尔值，表示操作是否成功
    """
    led = get_led_controller()
    client = get_mqtt_client()
    
    try:
        # 根据状态控制LED
        if state:
            if brightness is not None:
                result = led.turn_on(brightness)
            else:
                result = led.turn_on()
        else:
            result = led.turn_off()
        
        # 如果MQTT客户端可用，发布状态更新
        if client:
            client.publish_device_state("led", state, brightness if state else None)
        
        logger.info(f"LED状态已设置为: {'开启' if state else '关闭'}{f'，亮度: {brightness}%' if brightness is not None and state else ''}")
        return result
    except Exception as e:
        logger.error(f"控制LED时出错: {e}")
        return False

def adjust_led_brightness(brightness=None, change=None):
    """
    调整LED亮度 - 统一的亮度控制函数
    
    参数:
        brightness: 要设置的具体亮度值(0-100)，优先级高于change
        change: 亮度变化量，正值表示增加，负值表示减少
    
    返回:
        布尔值，表示操作是否成功
    """
    led = get_led_controller()
    client = get_mqtt_client()
    
    try:
        result = False
        
        # 如果提供了具体亮度值
        if brightness is not None:
            result = led.set_brightness(brightness)
            # 如果LED当前是关闭状态，则开启它
            if not led.is_on:
                led.turn_on()
            logger.info(f"LED亮度已设置为: {led.brightness}%")
        
        # 如果提供了亮度变化量
        elif change is not None:
            if change > 0:
                result = led.increase_brightness(abs(change))
                logger.info(f"LED亮度已增加{abs(change)}%，当前亮度: {led.brightness}%")
            elif change < 0:
                result = led.decrease_brightness(abs(change))
                logger.info(f"LED亮度已降低{abs(change)}%，当前亮度: {led.brightness}%")
            
            # 如果增加亮度且LED当前是关闭状态，则开启它
            if change > 0 and not led.is_on:
                led.turn_on()
        
        # 如果MQTT客户端可用，发布状态更新
        if client and led.is_on:
            client.publish_device_state("led", True, led.brightness)
        
        return result
    except Exception as e:
        logger.error(f"调整LED亮度时出错: {e}")
        return False

def blink_led(times=3, interval=0.5):
    """
    LED闪烁
    
    参数:
        times: 闪烁次数
        interval: 闪烁间隔(秒)
    
    返回:
        布尔值，表示操作是否成功
    """
    try:
        # 获取MQTT客户端
        client = get_mqtt_client()
        
        # 检查是否是模拟客户端
        if client and hasattr(client, 'blink_led'):
            # 使用模拟客户端的blink_led方法
            result = client.blink_led(times, interval)
            return result
        else:
            # 获取LED控制器并直接调用blink方法
            led = get_led_controller()
            if led:
                result = led.blink(times, interval)
                logger.info(f"LED闪烁完成: {times}次")
                return result
            else:
                logger.error("LED控制器未初始化，无法控制LED闪烁")
                return False
    except Exception as e:
        logger.error(f"LED闪烁时出错: {e}")
        return False

def control_buzzer(state):
    """
    控制蜂鸣器（预留功能）
    
    参数:
        state: 布尔值，True表示开启，False表示关闭
    
    返回:
        布尔值，表示操作是否成功
    """
    client = get_mqtt_client()
    
    if client:
        try:
            client.control_buzzer(state)
            logger.info(f"蜂鸣器状态已设置为: {'开启' if state else '关闭'}")
            return True
        except Exception as e:
            logger.error(f"控制蜂鸣器时出错: {e}")
            return False
    else:
        logger.warning("MQTT客户端未初始化，无法控制蜂鸣器")
        return False

# 测试代码
if __name__ == "__main__":
    try:
        # 初始化MQTT客户端
        mqtt_client = get_mqtt_client()
        if mqtt_client:
            print("MQTT客户端初始化成功")
            
            # 测试LED控制
            print("测试LED控制...")
            control_led(True, 50)  # 开启LED，亮度50%
            time.sleep(2)
            
            adjust_led_brightness(change=20)  # 增加亮度
            time.sleep(2)
            
            adjust_led_brightness(change=-30)  # 降低亮度
            time.sleep(2)
            
            adjust_led_brightness(brightness=75)  # 直接设置亮度
            time.sleep(2)
            
            blink_led(3)  # LED闪烁
            time.sleep(2)
            
            control_led(False)  # 关闭LED
            
            # 获取传感器数据
            print("\n获取传感器数据...")
            sensor_data = get_sensor_data()
            print(f"温度: {sensor_data['temperature']}°C, 湿度: {sensor_data['humidity']}%")
            
        else:
            print("MQTT客户端初始化失败")
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    finally:
        # 停止MQTT客户端
        stop_mqtt_client()
        print("程序已退出") 