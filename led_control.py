#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LED控制模块
用于控制LED的开关和亮度调节
支持PWM调光功能
"""

import RPi.GPIO as GPIO
import time
from loguru import logger
from hardware_config import PIN_LED, LED_PWM_FREQ

# 配置日志
logger.add("Log/led_control.log", rotation="10 MB", compression="zip", level="INFO")

class LEDController:
    """LED控制器类，支持PWM调光"""
    
    def __init__(self, pin=PIN_LED, pwm_freq=LED_PWM_FREQ):
        """
        初始化LED控制器
        
        参数:
            pin: GPIO引脚号，默认从hardware_config导入
            pwm_freq: PWM频率，默认从hardware_config导入
        """
        self.pin = pin
        self.pwm_freq = pwm_freq
        self.pwm = None
        self.is_on = False
        self.brightness = 100  # 亮度百分比，0-100
        
        # 初始化GPIO
        self._setup_gpio()
    
    def _setup_gpio(self):
        """初始化GPIO设置"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.pin, GPIO.OUT)
            
            # 初始化PWM
            self.pwm = GPIO.PWM(self.pin, self.pwm_freq)
            self.pwm.start(0)  # 初始占空比为0（关闭状态）
            logger.info(f"LED控制器初始化完成，连接到GPIO{self.pin}")
        except Exception as e:
            logger.error(f"LED控制器初始化失败: {e}")
            self.pwm = None
    
    def turn_on(self, brightness=None):
        """
        开启LED
        
        参数:
            brightness: 亮度百分比(0-100)，如果为None则使用默认亮度（100%）
        
        返回:
            操作是否成功
        """
        if self.pwm is None:
            logger.error("PWM未初始化，无法控制LED")
            return False
        
        try:
            # 先设置为开启状态，这样set_brightness会应用PWM设置
            self.is_on = True
            
            # 如果指定了亮度，则更新亮度设置
            if brightness is not None:
                self.set_brightness(brightness)
            else:
                # 默认使用100%亮度
                self.set_brightness(100)
            
            # 确保PWM信号被应用
            self.pwm.ChangeDutyCycle(self.brightness)
            
            logger.info(f"LED已开启，亮度: {self.brightness}%")
            return True
        except Exception as e:
            logger.error(f"开启LED失败: {e}")
            return False
    
    def turn_off(self):
        """
        关闭LED
        
        返回:
            操作是否成功
        """
        if self.pwm is None:
            logger.error("PWM未初始化，无法控制LED")
            return False
        
        try:
            self.pwm.ChangeDutyCycle(0)
            self.is_on = False
            logger.info("LED已关闭")
            return True
        except Exception as e:
            logger.error(f"关闭LED失败: {e}")
            return False
    
    def set_brightness(self, brightness):
        """
        设置LED亮度
        
        参数:
            brightness: 亮度百分比(0-100)
        
        返回:
            操作是否成功
        """
        if self.pwm is None:
            logger.error("PWM未初始化，无法控制LED亮度")
            return False
        
        try:
            # 确保亮度在有效范围内
            brightness = max(0, min(100, brightness))
            self.brightness = brightness
            
            # 如果LED当前是开启状态，则应用新的亮度设置
            if self.is_on:
                self.pwm.ChangeDutyCycle(brightness)
                logger.info(f"LED亮度已设置为: {brightness}%")
            
            return True
        except Exception as e:
            logger.error(f"设置LED亮度失败: {e}")
            return False
    
    def increase_brightness(self, step=10):
        """
        增加LED亮度
        
        参数:
            step: 增加的亮度步长(百分比)
        
        返回:
            操作是否成功
        """
        new_brightness = min(100, self.brightness + step)
        return self.set_brightness(new_brightness)
    
    def decrease_brightness(self, step=10):
        """
        降低LED亮度
        
        参数:
            step: 降低的亮度步长(百分比)
        
        返回:
            操作是否成功
        """
        new_brightness = max(0, self.brightness - step)
        return self.set_brightness(new_brightness)
    
    def blink(self, times=3, interval=0.5):
        """
        LED闪烁
        
        参数:
            times: 闪烁次数
            interval: 闪烁间隔(秒)
        
        返回:
            操作是否成功
        """
        if self.pwm is None:
            logger.error("PWM未初始化，无法控制LED闪烁")
            return False
        
        try:
            original_state = self.is_on
            original_brightness = self.brightness
            
            for i in range(times):
                self.turn_on(100)  # 全亮
                time.sleep(interval)
                self.turn_off()
                time.sleep(interval)
            
            # 恢复原始状态
            if original_state:
                self.turn_on(original_brightness)
            
            logger.info(f"LED闪烁完成: {times}次")
            return True
        except Exception as e:
            logger.error(f"LED闪烁失败: {e}")
            return False
    
    def cleanup(self):
        """清理资源"""
        if self.pwm is not None:
            try:
                self.turn_off()
                self.pwm.stop()
                logger.info("LED PWM已停止")
            except Exception as e:
                logger.error(f"停止PWM时出错: {e}")
        
        # 不清理GPIO，因为可能有其他设备在使用

# 单例模式
_led_controller = None

def get_led_controller(pin=PIN_LED):
    """
    获取LED控制器实例（单例模式）
    
    参数:
        pin: GPIO引脚号，默认从hardware_config导入
    
    返回:
        LEDController实例
    """
    global _led_controller
    
    if _led_controller is None:
        _led_controller = LEDController(pin=pin)
    
    return _led_controller

# 简单测试
if __name__ == "__main__":
    led = get_led_controller()
    
    try:
        print("测试LED控制...")
        print("1. 开启LED")
        led.turn_on(10)  # 50%亮度
        time.sleep(2)
        
        print("2. 增加亮度")
        led.increase_brightness(20)  # 增加20%
        time.sleep(2)
        
        print("3. 降低亮度")
        led.decrease_brightness(30)  # 降低30%
        time.sleep(2)
        
        print("4. LED闪烁")
        led.blink(3)
        
        print("5. 关闭LED")
        led.turn_off()
        
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    finally:
        led.cleanup()
        print("程序已退出") 